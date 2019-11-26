import hou  # pylint: disable=import-error
import viewerstate.utils as su  # pylint: disable=import-error
import stateutils  # pylint: disable=import-error

from get_viewport_transform import getViewportTransform # pylint: disable=import-error


class Cursor:
	def __init__(self, kwargs):

		self.objNode = stateutils.ancestorObject(kwargs['node'])
		self.sceneViewer = kwargs['scene_viewer']

		# snapping: points
		tolerance = 0.03  # 1.5
		testDist = 1

		# point snapping
		if 'points_geo' in kwargs:
			geo = kwargs['points_geo']
			options = {
				'snap_mode': hou.snappingMode.Point,
				'snap_gravity': 50,
				'snap_priorities': (hou.snappingPriority.GeoPoint, )}
			self.giPoints = su.GeometryIntersector(
				geo, snap_options=options, tolerance=tolerance, test_dist=testDist)
		else:
			self.giPoints = None

		# edge snapping
		if 'edge_geo' in kwargs:
			geo = kwargs['edge_geo']
			options = {
				'snap_mode': hou.snappingMode.Multi,
				'snap_gravity': 50,
				'snap_priorities': (hou.snappingPriority.GeoEdge, )}
			self.giEdge = su.GeometryIntersector(
				geo, snap_options=options, tolerance=tolerance, test_dist=testDist)
		else:
			self.giEdge = None

		# reference object
		self.refGeo = kwargs.get('reference_geo')

	def update(self, kwargs):

		# Parse Options
		uiEvent = kwargs.get('ui_event')
		curPosition = kwargs.get('current_position')
		enablePointsSnapping = not kwargs.get('disable_points_snapping', False)
		enableEdgeSnapping = not kwargs.get('disable_edge_snapping', False)

		origin, direction, snapped = uiEvent.snappingRay()

		if snapped:
			# Compensate geometry-level transform
			parentXformInv = self.objNode.worldTransform().inverted()
			origin *= parentXformInv

			parentXformInv.setAt(3, 0, 0)
			parentXformInv.setAt(3, 1, 0)
			parentXformInv.setAt(3, 2, 0)

			direction *= parentXformInv

		viewportXform = getViewportTransform(self.sceneViewer)

		# Reset settings
		self.position = None
		self.normal = None
		self.uvw = hou.Vector3(0, 0, 0)
		self.snapped = False
		self.snappedPtnum = None
		self.snappedEdge = None
		self.projectedPosition = None

		# Check if cursor is snapping to point
		if enablePointsSnapping and self.giPoints:
			self.giPoints.intersect(origin, direction)

			if self.giPoints.snapped:
				self.position = self.giPoints.snapped_position
				self.snapped = 'point'
				self.snappedPtnum = self.giPoints.snapped_point_num

		# Check if cursor is snappoing to edge
		if self.position == None and enableEdgeSnapping and self.giEdge:
			self.giEdge.intersect(origin, direction)

			if self.giEdge.snapped:
				self.position = self.giEdge.snapped_position
				self.snappedEdge = self.giEdge.snapped_edge
				self.snapped = 'edge'

		# Check if cursor is intersecting with reference object
		if self.position == None and self.refGeo:
			position = hou.Vector3()
			normal = hou.Vector3()
			uvw = hou.Vector3()
			if self.refGeo.intersect(origin, direction, position, normal, uvw) != -1:
				self.position = position
				self.normal = normal

		# Project to plane facing to viewport camera,
		# whose origin is pinned to the current anchor points
		if self.position == None and curPosition:
			self.position = hou.hmath.intersectPlane(
				curPosition,                     # plane_point
				direction,                       # plane_normal
				origin,                          # line_origin
				direction)                       # line_dir
				
			if uiEvent.device().isShiftKey():
				# Snap to axis
				delta = self.position - curPosition
				x, y, z = [abs(v) for v in delta]

				if x > y and x > z:
					delta = hou.Vector3(delta[0], 0, 0)
				elif y > z:
					delta = hou.Vector3(0, delta[1], 0)
				else:
					delta = hou.Vector3(0, 0, delta[2])
				
				self.position = curPosition + delta
				self.projectedPosition = curPosition

		# Project to reference plane
		if self.position == None:

			planePoint = hou.Vector3() * viewportXform
			planeNormal = hou.Vector3(
				0, 0, 1) * viewportXform.inverted().transposed()

			self.position = hou.hmath.intersectPlane(
				planePoint,
				planeNormal,
				origin,                 # line_origin
				direction)  # line_dir

		if self.projectedPosition == None:
			self.projectedPosition = self.position * viewportXform.inverted()
			self.projectedPosition[2] = 0
			self.projectedPosition = self.projectedPosition * viewportXform
