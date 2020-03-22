import hou
import viewerstate.utils as su
import stateutils
import toolutils
from os import path

EPSILON = 0.000001

AXIS_X = hou.Vector3(1, 0, 0)
AXIS_Y = hou.Vector3(0, 1, 0)
AXIS_Z = hou.Vector3(0, 0, 1)


def updateParmCache(node, parms):
    if not isinstance(parms, tuple):
        parms = (parms,)

    for name in parms:
        node.setCachedUserData('cache_%s' % name, node.parm(name).eval())


def detectChangedParms(node, watch_parms):
    changed = {}

    for name in watch_parms:
        key = 'cache_%s' % name
        value = node.parm(name).eval()
        prev_value = node.cachedUserData(key)

        if prev_value != value:
            changed[name] = {
                'prev_value': prev_value,
                'value': value
            }
            node.setCachedUserData(key, value)

    return changed


def getNodeTransform(node):
    return hou.hmath.buildTransform({
        'translate': node.evalParmTuple('t'),
        'rotate': node.evalParmTuple('r'),
        'scale': node.evalParmTuple('s')})


def setNodeTransform(node, xform=None, translate=None, rotate=None, scale=None, update_cache=True):

    if xform:
        components = xform.explode()
        translate = components['translate']
        rotate = components['rotate']
        scale = components['scale']

    if translate:
        node.setCachedUserData('cache_tx', translate[0])
        node.setCachedUserData('cache_ty', translate[1])
        node.setCachedUserData('cache_tz', translate[2])
        node.parmTuple('t').set(translate)

    if rotate:
        node.setCachedUserData('cache_rx', rotate[0])
        node.setCachedUserData('cache_ry', rotate[1])
        node.setCachedUserData('cache_rz', rotate[2])
        node.parmTuple('r').set(rotate)

    if scale:
        node.setCachedUserData('cache_sx', scale[0])
        node.setCachedUserData('cache_sy', scale[1])
        node.setCachedUserData('cache_sz', scale[2])
        node.parmTuple('s').set(scale)


def getHandleTRS(parms):

    rotate = hou.Vector3(parms['rx'], parms['ry'], parms['rz'])

    if parms.has_key('tx'):
        translate = hou.Vector3(parms['tx'], parms['ty'], parms['tz'])
        scale = hou.Vector3(parms['sx'], parms['sy'], parms['sz'])
    else:
        translate = hou.Vector3(
            parms['centerx'], parms['centery'], parms['centerz'])
        scale = hou.Vector3(parms['sizex'], parms['sizey'], parms['sizez'])

    return {
        'translate': translate,
        'rotate': rotate,
        'scale': scale}


def setHandleTransform(parms, xform=None, translate=None, rotate=None, scale=None):

    if xform:
        components = xform.explode()

        translate = components['translate']
        rotate = components['rotate']
        scale = components['scale']

    t_prefix = 't'
    s_prefix = 's'

    if parms.has_key('centerx'):
        t_prefix = 'center'
        s_prefix = 'size'

    parms[t_prefix + 'x'] = translate[0]
    parms[t_prefix + 'y'] = translate[1]
    parms[t_prefix + 'z'] = translate[2]

    parms['rx'] = rotate[0]
    parms['ry'] = rotate[1]
    parms['rz'] = rotate[2]

    parms[s_prefix + 'x'] = scale[0]
    parms[s_prefix + 'y'] = scale[1]
    parms[s_prefix + 'z'] = scale[2]


def getReferencePlaneXform(scene_viewer):
    viewport = scene_viewer.curViewport()
    cplane = scene_viewer.constructionPlane()

    if cplane.isVisible():
        xform = cplane.transform()
    elif viewport.type() == hou.geometryViewportType.Perspective:
        xform = scene_viewer.referencePlane().transform()
    else:
        rot = viewport.viewTransform().extractRotationMatrix3()
        xform = hou.Matrix4(rot)

    return xform


def callMouseEvents(viewer_state, kwargs):
    reason = kwargs['ui_event'].reason()

    if reason == hou.uiEventReason.Located:
        viewer_state.onMousemove(kwargs)

    elif reason == hou.uiEventReason.Picked:
        viewer_state.onMousedown(kwargs)
        viewer_state.onMouseup(kwargs)

    elif reason == hou.uiEventReason.Start:
        viewer_state.onMousedown(kwargs)

    elif reason == hou.uiEventReason.Active:
        viewer_state.onMousedrag(kwargs)

    elif reason == hou.uiEventReason.Changed:
        viewer_state.onMouseup(kwargs)


def enterNodeState():
    sceneViewer = stateutils.findSceneViewer()
    sceneViewer.setCurrentNode(hou.pwd())
    sceneViewer.enterCurrentNodeState()


def getHexColor(color):

    if isinstance(color, hou.Color):
        color = color.rgb()

    rgb = [('00' + hex(int(v * 0xff))[2:])[-2:] for v in color[:3]]

    return '#' + ''.join(rgb)


def computeDirectionRotates(z_direction):

    z_direction = z_direction.normalized()

    if 1 - abs(AXIS_Y.dot(z_direction)) < EPSILON:
        quat = hou.Quaternion()
        quat.setToVectors(AXIS_Z, z_direction)

        return quat.extractEulerRotates()

    else:

        if z_direction.length() < EPSILON:
            z_direction = AXIS_Z

        z = z_direction

        y = hou.Vector3(0, 1, 0)
        x = y.cross(z)
        y = z.cross(x)

        mat = hou.Matrix4((
            x[0], x[1], x[2], 0,
            y[0], y[1], y[2], 0,
            z[0], z[1], z[2], 0,
            0, 0, 0, 1
        ))

        return mat.extractRotates()


def computeDeltaXform(orig_xform, xform):

    if orig_xform.determinant() < EPSILON:

        scale = xform.extractScales()
        scale = [s if abs(s) >= EPSILON else 1 for s in scale]

        elems = xform.asTupleOfTuples()
        orig_elems = orig_xform.asTupleOfTuples()

        axes = [hou.Vector3(row[:3]) for row in orig_elems[:3]]

        is_axis_zero = [axis.length() < EPSILON for axis in axes]
        num_zero_axis = sum(is_axis_zero)

        if num_zero_axis == 1:

            zero_dim = is_axis_zero.index(True)

            alt_axis0 = axes[(zero_dim + 1) % 3]
            alt_axis1 = axes[(zero_dim + 2) % 3]

            axes[zero_dim] = alt_axis0.cross(
                alt_axis1).normalized() * scale[zero_dim]

            orig_xform = hou.Matrix4((
                axes[0][0], axes[0][1], axes[0][2], 0,
                axes[1][0], axes[1][1], axes[1][2], 0,
                axes[2][0], axes[2][1], axes[2][2], 0,
                orig_elems[3][0], orig_elems[3][1], orig_elems[3][2], 1
            ))

        elif num_zero_axis == 2:

            valid_dim = is_axis_zero.index(False)

            orig_axis = axes[valid_dim]
            target_axis = hou.Vector3(elems[valid_dim][:3])

            rotscale_mat = orig_axis.matrixToRotateTo(target_axis)
            rotscale_mat *= target_axis.length() / orig_axis.length()
            rotscale_mat.setAt(3, 3, 1)

            orig_translate = hou.Vector3(orig_elems[3][:3])
            target_translate = hou.Vector3(elems[3][:3])
            translate = target_translate - orig_translate

            orig_translate_mat = hou.hmath.buildTranslate(orig_translate)
            translate_mat = hou.hmath.buildTranslate(translate)

            return orig_translate_mat.inverted() * rotscale_mat * orig_translate_mat * translate_mat

        else:
            # Take account of only translate
            orig_translate = hou.Vector3(orig_elems[3][:3])
            target_translate = hou.Vector3(elems[3][:3])
            delta_translate = target_translate - orig_translate

            return hou.hmath.buildTranslate(delta_translate)

    return orig_xform.inverted() * xform


def loadPythonModuleSource(kwargs, section):
    nodetype = kwargs['type']
    hda = nodetype.definition()
    hdaDir = path.dirname(hda.libraryFilePath())

    name = nodetype.name().split('::')[1]
    hmFile = path.join(hdaDir, "%s_%s.py" % (name, section))

    return open(hmFile).read()


class Cursor:
    def __init__(self, kwargs):

        self.objnode = stateutils.ancestorObject(kwargs['node'])
        self.scene_viewer = kwargs['scene_viewer']

        self.__resetSettings()

        # snapping: points
        tolerance = 0.03  # 1.5
        test_dist = 1

        # point snapping
        if 'points_geo' in kwargs:
            geo = kwargs['points_geo']
            options = {
                'snap_mode': hou.snappingMode.Point,
                'snap_gravity': 50,
                'snap_priorities': (hou.snappingPriority.GeoPoint, )}
            self.gi_points = su.GeometryIntersector(
                geo, snap_options=options, tolerance=tolerance, test_dist=test_dist)
        else:
            self.gi_points = None

        # edge snapping
        if 'edge_geo' in kwargs:
            geo = kwargs['edge_geo']
            options = {
                'snap_mode': hou.snappingMode.Multi,
                'snap_gravity': 50,
                'snap_priorities': (hou.snappingPriority.GeoEdge, )}
            self.gi_edge = su.GeometryIntersector(
                geo, snap_options=options, tolerance=tolerance, test_dist=test_dist)
        else:
            self.gi_edge = None

        # reference object
        self.reference_geo = kwargs.get('reference_geo')

    def __resetSettings(self):
        self.mouse_screen = hou.Vector3()
        self.position = hou.Vector3()
        self.projected_position = hou.Vector3()
        self.normal = hou.Vector3(0, 0, 1)
        self.primuv = hou.Vector3()
        self.snapped = False
        self.snapped_ptnum = None
        self.snapped_edge = None
        self.snapped_prim = None

    def computeDrawableXform(self, local_xform):

        parent_xform = self.objnode.worldTransform()

        if self.scene_viewer.isWorldSpaceLocal():
            return local_xform
        else:
            return parent_xform.inverted() * local_xform * parent_xform

    def setReferenceGeometry(self, geo):
        self.reference_geo = geo

    def update(self, kwargs):

        # Memo: how snappingRay is represented in various situation
        #             | Show All | Solo 
        # ------------+----------+------
        # Not snapped |  Local   | Local
        # Snapped     |  World   | Local

        # All of below process should be represented in local coordinate.

        # Reset settings
        self.__resetSettings()
        self.projected_position = None

        # Parse Options
        ui_event = kwargs.get('ui_event')
        plane_origin = kwargs.get('plane_origin')
        plane_normal = kwargs.get('plane_normal')
        do_point_snap = not kwargs.get('disable_points_snapping', False)
        do_edge_snap = not kwargs.get('disable_edge_snapping', False)

        # Ray (in local coordinate)
        snapping_ray = ui_event.snappingRay()
        ray_snapped = snapping_ray['snapped']
        ray_origin = snapping_ray['origin_point']
        ray_direction = snapping_ray['direction']

        parent_xform = self.objnode.worldTransform()
        parent_xform_inv = parent_xform.inverted()

        refplane_xform = getReferencePlaneXform(
            self.scene_viewer) * parent_xform_inv

        if ray_snapped and not self.scene_viewer.isWorldSpaceLocal():
            # Convert to local coordinate
            ray_origin *= parent_xform_inv
            ray_direction = ray_direction.multiplyAsDir(parent_xform_inv)

        # Update Mouse Screen
        ray_origin_world = ray_origin # * parent_xform
        mouse_screen = self.scene_viewer.curViewport().mapToScreen(ray_origin_world)
        self.mouse_screen = hou.Vector3(mouse_screen[0], mouse_screen[1], 0)

        # Check if cursor is snapping to point
        if do_point_snap and self.gi_points:
            self.gi_points.intersect(ray_origin, ray_direction)

            if self.gi_points.snapped:
                self.position = self.gi_points.snapped_position
                self.snapped = 'point'
                self.snapped_ptnum = self.gi_points.snapped_point_num

        # Check if cursor is snappoing to edge
        if not self.snapped and do_edge_snap and self.gi_edge:
            self.gi_edge.intersect(ray_origin, ray_direction)

            if self.gi_edge.snapped:
                self.position = self.gi_edge.snapped_position
                self.snapped_edge = self.gi_edge.snapped_edge
                self.snapped = 'edge'

        # Check if cursor is intersecting with reference object
        if not self.snapped and self.reference_geo:
            position = hou.Vector3()
            normal = hou.Vector3()
            primuv = hou.Vector3()
            if self.reference_geo.intersect(ray_origin, ray_direction, position, normal, primuv) != -1:
                self.position = position
                self.normal = normal
                self.primuv = primuv
                self.snapped = 'reference'
                self.snapped_prim, _, _, _ = self.reference_geo.nearestPrim(
                    position)

        # Project to plane facing to viewport camera,
        # whose ray_origin is pinned to the current anchor points
        if not self.snapped and plane_origin:
            intersection = hou.hmath.intersectPlane(
                plane_origin,                                       # plane_point
                plane_normal if plane_normal else ray_direction,    # plane_normal
                ray_origin,                                         # line_origin
                ray_direction)                                      # line_dir

            if ray_direction.dot(intersection - ray_origin) > 0:
                
                self.position = intersection
                self.snapped = 'viewport'

                if ui_event.device().isShiftKey():
                    # Snap to axis
                    delta = self.position - plane_origin

                    x, y, z = [abs(v) for v in delta]

                    if x > y and x > z:
                        delta = hou.Vector3(delta[0], 0, 0)
                    elif y > z:
                        delta = hou.Vector3(0, delta[1], 0)
                    else:
                        delta = hou.Vector3(0, 0, delta[2])

                    self.position = plane_origin + delta
                    self.projected_position = plane_origin
                    self.snapped = 'axis'

        # Project to reference plane
        if not self.snapped:
            plane_origin = hou.Vector3() * refplane_xform
            plane_normal = AXIS_Z * refplane_xform.inverted().transposed()

            intersection = hou.hmath.intersectPlane(
                plane_origin,
                plane_normal,
                ray_origin,     # line_origin
                ray_direction)  # line_dir

            if ray_direction.dot(intersection - ray_origin) > 0:

                self.position = intersection
                self.projected_position = intersection

                self.snapped = 'plane'

        if self.projected_position == None:
            self.projected_position = self.position * refplane_xform.inverted()
            self.projected_position[2] = 0
            self.projected_position = self.projected_position * refplane_xform