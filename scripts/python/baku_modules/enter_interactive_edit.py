import hou  # pylint: disable=import-error
import stateutils  # pylint: disable=import-error


def enterInteractiveEdit():
    sceneViewer = stateutils.findSceneViewer()
    sceneViewer.setCurrentNode(hou.pwd())
    sceneViewer.enterCurrentNodeState()
