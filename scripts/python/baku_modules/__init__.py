import hou  # pylint: disable=import-error
from os import path

import cursor
# Force reload for the development
reload(cursor)

from cursor import Cursor
from get_viewport_transform import getViewportTransform
from enter_interactive_edit import enterInteractiveEdit


EPSILON = 0.000001

AXIS_X = hou.Vector3(1, 0, 0)
AXIS_Y = hou.Vector3(0, 1, 0)
AXIS_Z = hou.Vector3(0, 0, 1)


def buildXformByTRS(translate, rotate, scale):
	xform = hou.hmath.buildTransform({
		'translate': translate,
		'rotate': rotate,
		'scale': scale
	})

	return xform


def computeDirectionRotates(zDirection):

	zDirection = zDirection.normalized()

	if 1 - abs(AXIS_Y.dot(zDirection)) < EPSILON:
		quat = hou.Quaternion()
		quat.setToVectors(AXIS_Z, zDirection)

		return quat.extractEulerRotates()
	
	else:

		if zDirection.length() < EPSILON:
			zDirection = AXIS_Z

		z = zDirection

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


def computeDeltaXform(origXform, xform):

	if origXform.determinant() < EPSILON:
		# if either scale equals to zero, just calc translation
		t = origXform.extractTranslates()

		origXform = hou.Matrix4(xform.asTuple())
		origXform.setAt(3, 0, t[0])
		origXform.setAt(3, 1, t[1])
		origXform.setAt(3, 2, t[2])

	return origXform.inverted() * xform


def loadPythonModuleSource(kwargs):
	nodetype = kwargs['type']
	hda = nodetype.definition()
	hdaDir = path.dirname(hda.libraryFilePath())

	name = nodetype.name().split('::')[1]
	hmFile = path.join(hdaDir, "%s_PythonModule.py" % name)

	return open(hmFile).read()