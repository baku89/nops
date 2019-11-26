import hou  # pylint: disable=import-error


def getViewportTransform(scene_viewer):
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
