hou = hou # pylint: disable=undefined-variable
xrange = xrange # pylint: disable=undefined-variable
basestring = basestring # pylint: disable=undefined-variable
reload = reload # pylint: disable=undefined-variable

import stateutils # pylint: disable=import-error

from hutil.Qt import QtGui # pylint: disable=import-error
from hutil.Qt.QtCore import Qt # pylint: disable=import-error
from lightpanel.widgets import PointingLabel # pylint: disable=import-error

import baku_modules # pylint: disable=import-error
reload(baku_modules)

from baku_modules import Cursor # pylint: disable=import-error
from baku_modules import getViewportTransform # pylint: disable=import-error
from baku_modules import enterInteractiveEdit # pylint: disable=import-error
from baku_modules import computeDirectionRotates # pylint: disable=import-error
from baku_modules import computeDeltaXform # pylint: disable=import-error
from baku_modules import buildXformByTRS # pylint: disable=import-error
from baku_modules import EPSILON  # pylint: disable=import-error

EMPTY = -1

ZERO_VECTOR = hou.Vector3()

viewerState = None

class PointType:
	ANCHOR_MIDDLE, ANCHOR_FIRST, ANCHOR_LAST, INHANDLE, OUTHANDLE = (
		0, 1, 2, -1, -2)

	@staticmethod
	def isAnchor(type):
		return type >= 0

	@staticmethod
	def isEnd(type):
		return type >= 1

class ToolType:
	PEN, SELECT = (0, 1)


class HandleType:
	IN, OUT = (-1, +1)


class Curves():

	def __init__(self, node):
		self.node = node
		self.geo = self.node.node('./RESULT').geometry()

	def position(self, ptnum):
		return self.geo.point(ptnum).position()

	def setPosition(self, ptnum, position):
		point = self.geo.point(ptnum)
		anchorRef = point.attribValue('__anchor_ref')
		parm = self.node.parmTuple(point.attribValue('__parm'))

		if anchorRef != EMPTY:
			# Handle
			anchorPos = self.geo.point(anchorRef).position()
			position = position - anchorPos
			   
		parm.set(position)

	
	def setAnchorValues(self, ptnum, anchor, inHandle, outHandle):
		point = self.geo.point(ptnum)
		
		anchorParm = self.node.parmTuple(point.attribValue('__parm'))
		inHandleParm = self.node.parmTuple(point.attribValue('__inhandle_parm'))
		outHandleParm = self.node.parmTuple(point.attribValue('__outhandle_parm'))

		anchorParm.set(anchor)
		inHandleParm.set(inHandle)
		outHandleParm.set(outHandle)

	def dragPosition(self, ptnum, position, breakHandle=False):
		point = self.geo.point(ptnum)
		name = point.attribValue('__parm')
		anchorRef = point.attribValue('__anchor_ref')
		parm = self.node.parmTuple(name)

		if anchorRef == EMPTY:
			# Anchor
			parm.set(position)
		
		else:
			# Handle
			pointType = self.pointType(ptnum)

			if pointType == PointType.INHANDLE:
				oppositeName = name.replace('in', 'out')
			else:
				oppositeName = name.replace('out', 'in')
			
			oppositeParm = self.node.parmTuple(oppositeName)
			oppositeHandle = hou.Vector3(oppositeParm.eval())
			
			oldHandle = hou.Vector3(parm.eval())
			newHandle = position - self.position(anchorRef)

			# check if the anchor is smooth
			if not breakHandle and abs(oldHandle.angleTo(oppositeHandle) - 180) < 0.01:

				# When smooth, sync with opposite handle
				oldLength = oldHandle.length()
				
				if oldLength < EPSILON:
					lengthScale = 1
				else:
					lengthScale = newHandle.length() / oldLength

				oppositeLength = oppositeHandle.length() * lengthScale                
				oppositeHandle = -newHandle.normalized() * oppositeLength

				oppositeParm.set(oppositeHandle)

			# Set handle
			parm.set(newHandle)
	
	def allPoints(self, primnum):
		return [point.number() for point in self.geo.prim(primnum).points()]

	def primnum(self, ptnum):
		return self.geo.point(ptnum).prims()[0].number()

	def pointType(self, ptnum):
		return self.geo.point(ptnum).attribValue('__point_type')

	def numSegments(self, primnum):
		return self.node.parm('curve%d_segs' % (primnum + 1)).eval()

	def addCurve(self, anchor):
		curvenum = self.__addMultiParm('curves')
		primnum = curvenum - 1
		segnum = self.__addMultiParm('curve%d_segs' % curvenum)
		self.node.parmTuple('curve%d_anchor%d' %
							(curvenum, segnum)).set(anchor)

		ptnum = self.geo.prim(primnum).points()[0].number()

		return ptnum

	def deleteCurve(self, primnum):
		self.node.parm('curves').removeMultiParmInstance(primnum)

	def addAnchor(self, ptnum, position, backward):

		point = self.geo.point(ptnum)
		primnum = point.prims()[0].number()

		curveName = 'curve%d' % (primnum + 1)
		vertexIndex = 0

		seg = self.__addMultiParm(curveName + '_segs', backward)
		vertexIndex = (seg - 1) * 3

		self.node.parmTuple('%s_anchor%d' % (curveName, seg)).set(position)

		ptnum = self.geo.prim(primnum).points()[vertexIndex].number()

		return ptnum

	def handle(self, ptnum, handleType=None):
		attribName = None
		if handleType != None:
			attribName = '__inhandle_parm' if handleType == HandleType.IN else '__outhandle_parm'
		else:
			attribName = '__parm'
		
		parmName = self.geo.point(ptnum).attribValue(attribName)
		
		return hou.Vector3(self.node.parmTuple(parmName).eval())

	def setHandle(self, ptnum, position, handleType=None):
		attribName = None
		if handleType != None:
			attribName = '__inhandle_parm' if handleType == HandleType.IN else '__outhandle_parm'
		else:
			attribName = '__parm'

		parmName = self.geo.point(ptnum).attribValue(attribName)

		self.node.parmTuple(parmName).set(position)

	def getHandlePtnum(self, ptnum, handleType):
		attribName = '__inhandle_ref' if handleType == HandleType.IN else '__outhandle_ref'
		return self.geo.point(ptnum).attribValue(attribName)
	
	def getAnchorPtnum(self, ptnum):
		return self.geo.point(ptnum).attribValue('__anchor_ref')
	
	def closed(self, primnum):
		return self.geo.prim(primnum).isClosed()

	def setClosed(self, primnum, closed):
		self.node.parm('curve%s_closed' % (primnum + 1)).set(closed)
	
	def deletePoints(self, points):

		handles = []
		anchors = []

		for ptnum in sorted(points, reverse=True):
			if PointType.isAnchor(self.pointType(ptnum)):
				anchors.append(ptnum)
			else:
				handles.append(ptnum)
		
		# First, set the selected handles' tangent to zero
		for ptnum in handles:
			parmName = self.geo.point(ptnum).attribValue('__parm')
			self.node.parmTuple(parmName).set((0, 0, 0))

		# Then remove the entire segments of anchors
		for ptnum in anchors:
			parmName = self.geo.point(ptnum).attribValue('__parm')
			segnum = int(parmName.split('_')[1].replace('anchor', '')) - 1

			segParm = self.node.parmTuple(parmName).parentMultiParm()
			segParm.removeMultiParmInstance(segnum)
		
		# Cleanup empty curves
		curveParm  = self.node.parm('curves')
		numcurve = curveParm.eval()

		for i in xrange(numcurve):
			curvenum = i + 1
			numseg = self.node.parm('curve%d_segs' % curvenum).eval()
			if numseg == 0:
				curveParm.removeMultiParmInstance(i)

	def joinCurves(self, sourcePrim, targetPrim, sourceEnd, targetEnd):
		sourcePositions, _ = self.__getCurveData(sourcePrim)
		targetPositions, _ = self.__getCurveData(targetPrim)

		vertexIndex = None

		if targetEnd == PointType.ANCHOR_LAST:
			targetPositions = reversed(targetPositions)

		if sourceEnd == PointType.ANCHOR_LAST:
			vertexIndex = len(sourcePositions)
			sourcePositions += targetPositions
		else:
			vertexIndex = len(targetPositions) - 3
			sourcePositions = targetPositions + sourcePositions

		self.__setCurveData(sourcePrim, (sourcePositions, False))

		self.deleteCurve(targetPrim)

		if targetPrim < sourcePrim:
			sourcePrim -= 1

		ptnum = self.geo.prim(sourcePrim).points()[vertexIndex].number()

		return ptnum

	def insertAnchor(self, bezierPtnums, t):

		anchor0 = bezierPtnums[0]

		# calc new beziers
		origBezier = [self.position(ptnum) for ptnum in bezierPtnums]
		bezierA, bezierB = self.splitBezier(origBezier, t)

		# insert new line of segment
		parmName = self.geo.point(anchor0).attribValue('__parm')

		curvePrefix, anchorSuffix = parmName.split('_')

		segParm = self.node.parm(curvePrefix + '_segs')

		segnum0 = int(anchorSuffix.replace('anchor', ''))

		segParm.insertMultiParmInstance(segnum0)

		numseg = segParm.eval()

		segnum1 = segnum0 + 1
		segnum2 = 1 if segnum0 + 2 > numseg else segnum0 + 2

		# Set new points
		self.node.parmTuple('%s_outhandle%d' %
							(curvePrefix, segnum0)).set(bezierA[1] - bezierA[0])
		self.node.parmTuple('%s_inhandle%d' %
							(curvePrefix, segnum1)).set(bezierA[2] - bezierA[3])
		self.node.parmTuple('%s_anchor%d' %
							(curvePrefix, segnum1)).set(bezierA[3])
		self.node.parmTuple('%s_outhandle%d' %
							(curvePrefix, segnum1)).set(bezierB[1] - bezierB[0])
		self.node.parmTuple('%s_inhandle%d' %
							(curvePrefix, segnum2)).set(bezierB[2] - bezierB[3])

		# calc new anchor's ptnum
		vertexIndex = segnum0 * 3
		primnum = int(curvePrefix.replace('curve', '')) - 1

		ptnum = self.geo.prim(primnum).points()[vertexIndex].number()

		return ptnum
	
	def cutCurveAtPoint(self, ptnum):
		parmName = self.geo.point(ptnum).attribValue('__parm')
		segnum = int(parmName.split('_')[1].replace('anchor', '')) - 1

		primnum = self.primnum(ptnum)
		closed = self.geo.prim(primnum).isClosed()
		positions, _ = self.__getCurveData(primnum)

		if closed:
			newPositions = positions[segnum*3:] + positions[:(segnum+1)*3]
			self.__setCurveData(primnum, (newPositions, False))
		
		else:
			if not PointType.isEnd(self.pointType(ptnum)):
				firstPositions = positions[:(segnum+1)*3]
				secondPositions = positions[segnum*3:]

				firstPrimnum = primnum
				secondPrimnum = self.__addMultiParm('curves') - 1
				
				self.__setCurveData(firstPrimnum, (firstPositions, False))
				self.__setCurveData(secondPrimnum, (secondPositions, False))
	
	def reverseCurve(self, primnum):
		positions, closed = self.__getCurveData(primnum)
		positions.reverse()

		self.__setCurveData(primnum, (positions, closed))

	def __addMultiParm(self, name, backward=False):
		parm = self.node.parm(name)
		insertPos = 0 if backward else parm.eval()
		parm.insertMultiParmInstance(insertPos)
		index = insertPos + 1
		return index

	def __getCurveData(self, primnum):
		prefix = 'curve%d' % (primnum + 1)
		numseg = self.node.parm(prefix + '_segs').eval()

		closed = self.node.parm(prefix + '_closed').eval()

		positions = []

		for segnum in xrange(1, numseg + 1):
			positions.append(self.node.parmTuple(
				'%s_inhandle%d' % (prefix, segnum)).eval())
			positions.append(self.node.parmTuple(
				'%s_anchor%d' % (prefix, segnum)).eval())
			positions.append(self.node.parmTuple(
				'%s_outhandle%d' % (prefix, segnum)).eval())

		return (positions, closed)

	def __setCurveData(self, primnum, data):
		prefix = 'curve%d' % (primnum + 1)

		segParm = self.node.parm(prefix + '_segs')

		# Delete all segments at first
		for i in xrange(segParm.eval()):
			segParm.removeMultiParmInstance(0)

		positions, closed = data

		numseg = len(positions) / 3

		for i in xrange(numseg):
			segnum = i + 1
			segParm.insertMultiParmInstance(i)
			self.node.parmTuple('%s_inhandle%d' %
								(prefix, segnum)).set(positions[i*3])
			self.node.parmTuple('%s_anchor%d' %
								(prefix, segnum)).set(positions[i*3 + 1])
			self.node.parmTuple('%s_outhandle%d' %
								(prefix, segnum)).set(positions[i*3 + 2])

		self.node.parm('%s_closed' % prefix).set(closed)

	def splitBezier(self, bezier, t):

		p0, p1, p2, p3 = bezier

		p4 = p0 + (p1 - p0) * t
		p5 = p1 + (p2 - p1) * t
		p6 = p2 + (p3 - p2) * t
		p7 = p4 + (p5 - p4) * t
		p8 = p5 + (p6 - p5) * t
		p9 = p7 + (p8 - p7) * t

		return ((p0, p4, p7, p9), (p9, p8, p6, p3))


class State():

	WATCH_PARMS = ('selection', 'tool', 'tx', 'ty', 'tz',
				   'rx', 'ry', 'rz', 'sx', 'sy', 'sz', 'move_geometry')

	def __init__(self, **kwargs):
		self.stateName = kwargs['state_name']
		self.sceneViewer = kwargs['scene_viewer']

		self.initialized = False
		self.shadedGuide = None

	def initialize(self, node):
		if self.initialized:
			return
		
		self.initialized = True

		self.node = node
		self.curves = Curves(node)

		# Pointer
		self.pointer = PointingLabel()
		self.pointer.setAttribute(Qt.WA_ShowWithoutActivating)
		self.pointer.setOffset(0, 20)
		self.pointer.setFixedWidth(100)
		self.pointer.setOrientation(self.pointer.PointUp)

		# Init State
		self.node.parm('selection').set('')
		self.setState('selected_points', [])
		self.setState('selected_mode', None)
		resetPenAction(self.node)

		self.onChangeTool()

		# Init pivot cahce
		self.updatePivotCache()

		self.cursor = Cursor({
			'node': self.node,
			'scene_viewer': self.sceneViewer,
			"points_geo":  self.node.node('./INTERSECTOR_POINTS').geometry(),
			"edge_geo":  self.node.node('./INTERSECTOR_EDGE').geometry(),
			'reference_geo': self.node.inputs()[1].geometry() if len(self.node.inputs()) >= 2 else None
		})
		
		
	def state(self, key):
		return self.node.cachedUserData(key)

	def setState(self, key, value):
		self.node.setCachedUserData(key, value)

	def onChangeTool(self):
		isSelect = self.node.parm('tool').eval() == ToolType.SELECT

		selectorAction = hou.triggerSelectorAction.Start if isSelect else hou.triggerSelectorAction.Stop
		self.sceneViewer.triggerStateSelector(selectorAction, 'select_points')

		if isSelect:
			resetPenAction(self.node)
		else:
			self.sceneViewer.setPromptMessage('Pen Mode')

	def detectParmChange(self):
		changed = {}

		for name in State.WATCH_PARMS:
			key = 'cache_%s' % name
			value = self.node.parm(name).eval()
			prevValue = self.state(key)

			if prevValue != value:
				changed[name] = {
					'prev_value': prevValue,
					'value': value
				}
				self.setState(key, value)

		# Side effects
		if 'selection' in changed:
			selection = changed['selection']['value']
			self.updateSelection(selection, updateParm=False)

		if 'tool' in changed:
			self.updateSelection('')
			self.onChangeTool()

		for key in ('tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz'):
			if key in changed:
				# On either transform component has changed
				with hou.undos.group('Transform curve'):
					xform = self.getPivotXform()
					self.transformWithPivot(xform)
				break

		if 'move_geometry' in changed:
			if changed['move_geometry']['value']:
				self.updatePivotCache()

	def updatePivotCache(self, pivotXform=None):
		if pivotXform == None:
			pivotXform = self.getPivotXform()

		selectedPoints = self.state('selected_points')
		selectedMode = self.state('selected_mode')

		cache = None

		if selectedMode == 'point':
			cache = [self.curves.position(ptnum) for ptnum in selectedPoints]
		elif selectedMode == 'anchor':
			cache = [
				(self.curves.handle(ptnum, HandleType.IN),
				self.curves.position(ptnum),
				self.curves.handle(ptnum, HandleType.OUT))
				for ptnum in selectedPoints]
		elif selectedMode == 'handle':
			cache = [self.curves.position(ptnum) for ptnum in selectedPoints]

		self.setState('selected_cache', cache)
		self.setState('pivot_original_xform', pivotXform)

	def transformWithPivot(self, pivotXform, breakHandle=False):
		if self.node.parm('./move_geometry').eval():

			pivotOrigXform = self.state('pivot_original_xform')

			breakHandle = self.node.parm('break_handle').eval()

			# TODO: If initial xform cannot be inverted as scale it set to zero,
			# ignore scale
			pivotDeltaXform = computeDeltaXform(pivotOrigXform, pivotXform)

			pivotDeltaRotate = hou.Matrix4(pivotDeltaXform.asTuple())
			pivotDeltaRotate.setAt(3, 0, 0)
			pivotDeltaRotate.setAt(3, 1, 0)
			pivotDeltaRotate.setAt(3, 2, 0)

			points = self.state('selected_points')
			cache = self.state('selected_cache')
			selectedMode = self.state('selected_mode')

			for (i, ptnum) in enumerate(points):

				if selectedMode == 'point':
					position = cache[i] * pivotDeltaXform
					self.curves.setPosition(ptnum, position)

				elif selectedMode == 'anchor':
					(inHandle, position, outHandle) = cache[i]

					position = position * pivotDeltaXform
					inHandle = inHandle * pivotDeltaRotate
					outHandle = outHandle * pivotDeltaRotate

					self.curves.setAnchorValues(ptnum, position, inHandle, outHandle)
				
				else: # selectedMode == 'handle'
					position = cache[i] * pivotDeltaXform
					if breakHandle:
						self.curves.setPosition(ptnum, position)
					else:
						self.curves.dragPosition(ptnum, position)

	def updateSelection(self, selection='', updateParm=True):
		geo = self.node.geometry()

		if isinstance(selection, basestring):
			selection = hou.Selection(geo, hou.geometryType.Points, selection)

		# adjust selection
		points = None
		origViewerPoints = [point.number() for point in selection.points(geo)]
		anchors = [ptnum for ptnum in origViewerPoints if PointType.isAnchor(self.curves.pointType(ptnum))]
		
		selectUnit = self.node.parm('select_unit').evalAsString()

		viewerPoints = None

		selectedMode = 'handle'
		
		if selectUnit == 'curve':
			selectedMode = 'anchor'
			viewerPoints = []

			prims = set([self.curves.primnum(ptnum) for ptnum in origViewerPoints])

			for primnum in prims:
				viewerPoints += self.curves.allPoints(primnum)
			
			points = [ptnum for ptnum in viewerPoints if PointType.isAnchor(self.curves.pointType(ptnum))]
		
		elif len(anchors) > 0:
			selectedMode = 'anchor'
			viewerPoints = []
			points = anchors

			for anchor in anchors:
				inhandle = self.curves.getHandlePtnum(anchor, HandleType.IN)
				outhandle = self.curves.getHandlePtnum(anchor, HandleType.OUT)
				if inhandle != EMPTY:
					viewerPoints.append(inhandle)
				viewerPoints.append(anchor)
				if outhandle != EMPTY:
					viewerPoints.append(outhandle)
		
		else:
			points = origViewerPoints

		# Recreate selection if neccesary
		if viewerPoints:
			selection = ' '.join([str(ptnum) for ptnum in viewerPoints])
			selection = hou.Selection(geo, hou.geometryType.Points, selection)

		# Then upate
		isSelected = len(points) > 0
		selectionString = selection.selectionString(
			geo, asterisk_to_select_all=True)
		
		# Should break handles on move?
		if len(points) > 0 and len(anchors) == 0:
			for ptnum in sorted(points):
				if self.curves.pointType(ptnum) != PointType.INHANDLE:
					continue
				anchor = self.curves.getAnchorPtnum(ptnum)
				outHandle = self.curves.getHandlePtnum(anchor, HandleType.OUT)
				if outHandle in points:
					selectedMode = 'point'
					break

		with hou.undos.group('Select points' if isSelected else 'Clear selection'):

			self.setState('selected_points', points)
			self.setState('selected_mode', selectedMode)
			self.setState('cache_selection', selectionString)

			if updateParm:
				self.node.parm('selection').set(selectionString)

			self.alignPivot()

			# Force update viewer
			if self.sceneViewer.currentGeometrySelection() != None:
				self.sceneViewer.setCurrentGeometrySelection(
					hou.geometryType.Points, (self.node,), (selection,))

			self.sceneViewer.showHandle('edit_xform', isSelected)

	def alignPivot(self):
		points = self.state('selected_points')
		selectedMode = self.state('selected_mode')

		numSelected = len(points)

		pivotPos = self.node.parm('pivot_pos').evalAsString()
		pivotAlign = self.node.parm('pivot_orient').evalAsString()

		positions = [self.curves.position(ptnum) for ptnum in points]

		# Calculate the new pivot center
		(translate, rotate, _) = self.getPivotTRS()
		scale = hou.Vector3(1, 1, 1)

		if numSelected != 0:

			# Calculate translate
			if pivotPos == 'centroid':
				translate = hou.Vector3()
				for position in positions:
					translate += position
				translate /= len(positions)

			elif pivotPos == 'first':
				translate = positions[0]

			elif pivotPos == 'last':
				translate = positions[len(positions) - 1]

			# Calculate align
			if pivotAlign == 'auto':

				tangent = None

				if selectedMode == 'handle' and numSelected == 1:
					# When selecting one handle
					tangent = self.curves.handle(points[0])

				elif selectedMode == 'anchor' and numSelected == 1:
					# When selecting one anchor
					anchor = points[0]
					pointType = self.curves.pointType(anchor)
					tangent = hou.Vector3()

					if pointType != PointType.ANCHOR_FIRST:
						tangent -= self.curves.handle(anchor, HandleType.IN)
					
					if pointType != PointType.ANCHOR_LAST:
						tangent += self.curves.handle(anchor, HandleType.OUT)
					
					if tangent.isAlmostEqual(ZERO_VECTOR):
						tangent = hou.Vector3(0, 0, 1)

				else:
					tangent = hou.Vector3(0, 0, 1) * getViewportTransform(self.sceneViewer).extractRotationMatrix3()
				
				rotate = computeDirectionRotates(tangent.normalized())
					
			elif pivotAlign == 'refplane':
				tangent = hou.Vector3(0, 0, 1) * getViewportTransform(self.sceneViewer).extractRotationMatrix3()
				rotate = computeDirectionRotates(tangent)
				


		xform = buildXformByTRS(translate, rotate, scale)

		self.movePivotWithoutTransform(translate, rotate, scale)
		self.updatePivotCache(xform)

	def updateCursor(self, uiEvent):

		curAnchor = self.node.parm('current_anchor').eval()

		forceProjectCursor = not not self.node.parm('force_project_cursor').eval()

		options = {
			'ui_event': uiEvent,
			'disable_points_snapping': not not self.node.parm('current_action').eval(),
			'disable_edge_snapping': curAnchor != EMPTY,
			'current_position': None if forceProjectCursor or curAnchor == EMPTY else self.curves.position(curAnchor)
		}
		self.cursor.update(options)

		# Update Cursor Projection
		with hou.undos.disabler():
			self.node.parmTuple('cursor_position').set(self.cursor.position)
			self.node.parmTuple('cursor_plane_projection').set(self.cursor.projectedPosition)

	def detectPenAction(self):
		type = None
		parms = {}

		currentAnchor = self.node.parm('current_anchor').eval()

		if currentAnchor == EMPTY:
			if self.cursor.snapped == 'point':
				pointType = self.curves.pointType(self.cursor.snappedPtnum)

				if PointType.isEnd(pointType):
					type = 'extend_curve'
					parms['anchor'] = self.cursor.snappedPtnum
					parms['backward'] = pointType == PointType.ANCHOR_FIRST
				else:
					type = 'drag_point'
					parms['point'] = self.cursor.snappedPtnum

			elif self.cursor.snapped == 'edge':
				# split at edge
				bezierPtnums, t = getBezierInfoByEdge(
					self.cursor.snappedEdge, self.cursor.position, self.node.geometry())

				type = 'insert_anchor'
				parms['bezier_ptnums'] = bezierPtnums
				parms['t'] = t

			else:
				type = 'create_curve'

		else:
			if self.cursor.snapped == 'point':

				targetPt = self.cursor.snappedPtnum
				targetPointType = self.curves.pointType(targetPt)
				sourcePointType = self.curves.pointType(currentAnchor)

				sourcePrim = self.curves.primnum(currentAnchor)
				targetPrim = self.curves.primnum(targetPt)

				samePrim = sourcePrim == targetPrim
				isSourceDot = self.curves.numSegments(sourcePrim) == 1

				canClose = samePrim and (
					(not isSourceDot and sourcePointType != targetPointType and PointType.isEnd(targetPointType)) or isSourceDot)
				canJoin = not samePrim and PointType.isAnchor(targetPointType) and targetPointType != PointType.ANCHOR_MIDDLE

				if canClose:
					# close
					type = 'close_curve'
					parms['primnum'] = sourcePrim
					parms['anchor'] = targetPt

				elif canJoin:
					# join
					type = 'join_curves'
					parms['source_prim'] = sourcePrim
					parms['target_prim'] = targetPrim
					parms['source_end'] = sourcePointType
					parms['target_end'] = targetPointType
				
				else:
					type = 'add_anchor'

			else:  # self.cursor.snapped != 'point':
				type = 'add_anchor'

		if type:
			parms['message'] = ' '.join(w.capitalize()
										for w in type.split('_'))

		return (type, parms)

	def onMousemove(self, uiEvent):

		tool = self.node.parm('tool').eval()

		if tool == ToolType.PEN:
			type, parms = self.detectPenAction()

			if type:  # and not type in ('create_curve', 'add_anchor'):
				pos = QtGui.QCursor.pos()
				self.pointer.pointAt(pos.x(), pos.y())
				self.pointer.setText(parms['message'])
				self.pointer.show()
				self.pointer.repaint()
			else:
				self.pointer.hide()

		else:
			self.pointer.hide()

	def onMousedown(self, uiEvent):

		tool = self.node.parm('tool').eval()

		if tool == ToolType.PEN:
			actionType, parms = self.detectPenAction()

			if actionType:
				self.sceneViewer.beginStateUndo(parms['message'])

				ptnum = self.node.parm('current_anchor').eval()

				if actionType == 'create_curve':
					ptnum = self.curves.addCurve(self.cursor.position)

					self.node.parm('current_action').set('edit_anchor')
					self.node.parm('current_anchor').set(ptnum)
					self.node.parm('draw_backward').set(False)

				elif actionType == 'add_anchor':
					position = self.cursor.position
					backward = self.node.parm('draw_backward').eval()
					ptnum = self.curves.addAnchor(ptnum, position, backward)

					self.node.parm('current_action').set('edit_anchor')
					self.node.parm('current_anchor').set(ptnum)

				elif actionType == 'extend_curve':
					self.node.parm('current_action').set('edit_anchor')
					self.node.parm('current_anchor').set(parms['anchor'])
					self.node.parm('draw_backward').set(parms['backward'])

				elif actionType == 'close_curve':
					self.curves.setClosed(parms['primnum'], True)

					anchor = parms['anchor']
					backward = self.node.parm('draw_backward').eval()
					self.node.parm('current_action').set('edit_anchor')
					self.node.parm('current_anchor').set(anchor)

				elif actionType == 'join_curves':
					anchor = self.curves.joinCurves(
						sourcePrim=parms['source_prim'],
						targetPrim=parms['target_prim'],
						sourceEnd=parms['source_end'],
						targetEnd=parms['target_end'])

					backward = self.node.parm('draw_backward').eval()
					self.node.parm('current_action').set('edit_anchor')
					self.node.parm('current_anchor').set(anchor)

				elif actionType == 'insert_anchor':
					anchor = self.curves.insertAnchor(
						parms['bezier_ptnums'], parms['t'])
					self.node.parm('current_action').set('edit_anchor')
					self.node.parm('current_anchor').set(anchor)

				elif actionType == 'drag_point':
					self.node.parm('current_action').set('drag_point')
					self.node.parm('current_anchor').set(parms['point'])

	def onMousedrag(self, uiEvent):
		tool = self.node.parm('tool').eval()

		if tool == ToolType.PEN:

			actionType = self.node.parm('current_action').eval()
			ptnum = self.node.parm('current_anchor').eval()
			backward = self.node.parm('draw_backward').eval()

			if actionType == 'edit_anchor':
				anchorPos = self.curves.position(ptnum)
				outHandle = (self.cursor.position - anchorPos)

				self.curves.setHandle(
					ptnum, outHandle, HandleType.IN if backward else HandleType.OUT)

				if not uiEvent.device().isAltKey():
					self.curves.setHandle(
						ptnum, -outHandle, HandleType.OUT if backward else HandleType.IN)

			elif actionType == 'drag_point':
				self.curves.dragPosition(ptnum, self.cursor.position, breakHandle=uiEvent.device().isAltKey())

	def onMouseup(self, uiEvent):
		tool = self.node.parm('tool').eval()

		if tool == ToolType.PEN:

			actionType = self.node.parm('current_action').eval()
			ptnum = self.node.parm('current_anchor').eval()

			if actionType:

				if actionType == 'edit_anchor':
					if self.curves.pointType(ptnum) == PointType.ANCHOR_MIDDLE:
						resetPenAction(self.node)
						self.updateSelection(str(ptnum))

				elif actionType == 'drag_point':
					self.node.parm('current_anchor').set(EMPTY)
					self.updateSelection(str(ptnum))

				self.node.parm('current_action').set('')
				self.sceneViewer.endStateUndo()

	def onMouseEvent(self, kwargs):
		uiEvent = kwargs['ui_event']
		reason = uiEvent.reason()

		self.updateCursor(uiEvent)

		if reason == hou.uiEventReason.Located:

			self.onMousemove(uiEvent)

			# Deselect when selection has cleared
			sel = self.sceneViewer.currentGeometrySelection()
			if sel and len(sel.selections()) == 0 and len(self.state('selected_points')) > 0:
				self.updateSelection('')

		elif reason == hou.uiEventReason.Picked:
			self.onMousedown(uiEvent)
			self.onMouseup(uiEvent)

		elif reason == hou.uiEventReason.Start:
			self.onMousedown(uiEvent)

		elif reason == hou.uiEventReason.Active:
			self.onMousedrag(uiEvent)

		elif reason == hou.uiEventReason.Changed:
			self.onMouseup(uiEvent)

	def onSelection(self, kwargs):
		sel = kwargs['selection']
		name = kwargs['name']

		if name == 'select_points' and len(sel.selections()) > 0:
			selection = sel.selections()[0]
			self.updateSelection(selection)

		return False

	def onHandleToState(self, kwargs):
		uiEvent = kwargs['ui_event']
		handle = kwargs['handle']
		reason = uiEvent.reason()

		if handle == 'edit_xform':

			parms = kwargs['parms']
			trans = hou.Vector3(parms['tx'], parms['ty'], parms['tz'])
			rotate = hou.Vector3(parms['rx'], parms['ry'], parms['rz'])
			scale = hou.Vector3(parms['sx'], parms['sy'], parms['sz'])
			handleXform = buildXformByTRS(trans, rotate, scale)

			if reason == hou.uiEventReason.Start:
				self.sceneViewer.beginStateUndo('Transform elements')
				self.updatePivotCache(handleXform)
				self.node.parm('show_cursor').set(False)

			self.movePivotWithoutTransform(trans, rotate, scale)

			if reason == hou.uiEventReason.Active:
				self.transformWithPivot(handleXform)

			if reason == hou.uiEventReason.Changed:
				self.updatePivotCache(handleXform)
				self.node.parm('show_cursor').set(True)
				self.sceneViewer.endStateUndo()

	def onStateToHandle(self, kwargs):
		# print('state -> handle')
		self.initialize(kwargs['node'])
		self.detectParmChange()

		handle = kwargs['handle']

		if handle == 'edit_xform':

			parms = kwargs['parms']

			(t, r, s) = self.getPivotTRS()

			parms['tx'] = t[0]
			parms['ty'] = t[1]
			parms['tz'] = t[2]

			parms['rx'] = r[0]
			parms['ry'] = r[1]
			parms['rz'] = r[2]

			parms['sx'] = s[0]
			parms['sy'] = s[1]
			parms['sz'] = s[2]

	def onMenuPreOpen(self, kwargs):
		menu_id = kwargs['menu']
		menu_item_states = kwargs['menu_item_states']

		if menu_id == '%s_menu' % self.node.type().name():  # Root
			
			points = self.state('selected_points')
			hasAnchors = self.state('selected_mode') == 'anchor'

			tool = self.node.parm('tool').eval()
			pointsSelected = len(points) > 0

			allMiddleAnchors = hasAnchors and all([self.curves.pointType(anchor) == PointType.ANCHOR_MIDDLE for anchor in points])
			
			canEndCurve = self.node.parm('current_anchor').eval() != EMPTY

			oneHandleSelected = self.state('selected_mode') == 'handle' and len(points) == 1

			menu_item_states['select_mode']['value'] = tool == ToolType.SELECT
			menu_item_states['end_curve']['enable'] = canEndCurve
			menu_item_states['cut_curve']['enable'] = not not self.cursor.snapped
			menu_item_states['reverse_curve']['enable'] = pointsSelected
			menu_item_states['straighten_segment']['enable'] = oneHandleSelected
			
			menu_item_states['delete']['enable'] = pointsSelected

			menu_item_states['smooth_tangent']['enable'] = allMiddleAnchors
			menu_item_states['hard_tangent']['enable'] = hasAnchors
			menu_item_states['equal_tangent']['enable'] = allMiddleAnchors

	def onMenuAction(self, kwargs):
		item = kwargs['menu_item']
		uiEvent = kwargs['ui_event']

		if item == 'select_mode':
			isSelect = self.node.parm('tool').eval() == ToolType.SELECT

			if (kwargs['select_mode'] == ToolType.SELECT) != isSelect:
				self.node.parm('tool').set(
					ToolType.PEN if isSelect else ToolType.SELECT)

		elif item == 'end_curve':
			with hou.undos.group('End curve'):
				resetPenAction(self.node)
				self.updateCursor(uiEvent)

		elif item == 'delete':
			with hou.undos.group('Delete selected anchros'):
				points = self.state('selected_points')
				self.curves.deletePoints(points)
				self.updateSelection('')
		
		elif item == 'smooth_tangent':
			with hou.undos.group('Smooth tangent'):
				for anchor in self.state('selected_points'):
					
					inHandle = self.curves.handle(anchor, HandleType.IN)
					outHandle = self.curves.handle(anchor, HandleType.OUT)

					inZero = inHandle.isAlmostEqual(ZERO_VECTOR)
					outZero = outHandle.isAlmostEqual(ZERO_VECTOR)

					if inZero and outZero:
						# NOTE: this solution can be dangerous.
						# Using adjecent handles to compute the new tangent
						p0 = self.curves.position(anchor)
						pi = self.curves.position(anchor - 2)
						po = self.curves.position(anchor + 2)

						tangentDir = ((p0 - pi).normalized() + (po - p0).normalized()).normalized()
						tangentLenght = min((pi - p0).length(), (po - p0).length()) / 2
						tangent = tangentDir * tangentLenght

						inHandle = -tangent
						outHandle = tangent
					
					elif inZero:
						inHandle = -outHandle

					elif outZero:
						outHandle = -inHandle
					
					else:
						tangentDir = (outHandle.normalized() - inHandle.normalized()).normalized()
						inHandle = -tangentDir * inHandle.length()
						outHandle = tangentDir * outHandle.length()
					
					self.curves.setHandle(anchor, inHandle, HandleType.IN)
					self.curves.setHandle(anchor, outHandle, HandleType.OUT)
		
		elif item == 'hard_tangent':
			with hou.undos.group('Hard tangent'):
				for anchor in self.state('selected_points'):
					self.curves.setHandle(anchor, ZERO_VECTOR, HandleType.IN)
					self.curves.setHandle(anchor, ZERO_VECTOR, HandleType.OUT)

		elif item == 'equal_tangent':
			with hou.undos.group('Equal tangent'):
				for anchor in self.state('selected_points'):
					inHandle = self.curves.handle(anchor, HandleType.IN)
					outHandle = self.curves.handle(anchor, HandleType.OUT)

					inLength = inHandle.length()
					outLength = outHandle.length()
					
					if inLength < EPSILON:
						inLength = outLength
						inHandle = -outHandle
					if outLength < EPSILON:
						outLength = inLength
						outHandle = -inHandle
					
					newLength = (inLength + outLength) / 2
					
					inHandle = inHandle.normalized() * newLength
					outHandle = outHandle.normalized() * newLength
					
					self.curves.setHandle(anchor, inHandle, HandleType.IN)
					self.curves.setHandle(anchor, outHandle, HandleType.OUT)
		
		elif item == 'cut_curve':
			with hou.undos.group('Cut curve'):
				if self.cursor.snapped == 'point':
					self.curves.cutCurveAtPoint(self.cursor.snappedPtnum)
					self.updateSelection('')
		
		elif item == 'reverse_curve':
			with hou.undos.group('Reverse curve'):
				
				points = self.state('selected_points')

				prims = [self.curves.primnum(ptnum) for ptnum in points]
				prims = list(set(prims))

				for primnum in prims:
					self.curves.reverseCurve(primnum)
				
				self.updateSelection('')
		
		elif item == 'move_pivot':
			with hou.undos.group('Move pivot'):
				translate = hou.Vector3(self.cursor.position)
				scale = hou.Vector3(1, 1, 1)

				self.movePivotWithoutTransform(translate=translate, scale=scale)
				self.updatePivotCache()
		
		elif item == 'orient_pivot':
			with hou.undos.group('Orient pivot'):
				origin = self.getPivotTRS()[0]
				target = self.cursor.position

				direction = (target - origin).normalized()

				rotate = computeDirectionRotates(direction)
				scale = hou.Vector3(1, 1, 1)

				self.movePivotWithoutTransform(rotate=rotate, scale=scale)
				self.updatePivotCache()

	def onInterrupt(self, kwargs): 
		with hou.undos.disabler():
			self.pointer.hide()
			self.node.parm('show_cursor').set(False)

	def onResume(self, kwargs):        
		with hou.undos.disabler():
			self.node.parm('show_cursor').set(True)

	def onEnter(self, kwargs):
		global viewerState
		viewerState = self
		self.initialize(kwargs['node'])
		self.node.parm('viewerstate_enabled').set(True)
		self.node.parm('show_cursor').set(True)

	def onExit(self, kwargs):
		global viewerState
		with hou.undos.disabler():
			self.node.parm('viewerstate_enabled').set(False)
			self.node.parm('show_cursor').set(False)
			resetPenAction(self.node)

		viewerState = None

	def getPivotTRS(self, useTuple=False):
		t = self.node.parmTuple('t').eval()
		r = self.node.parmTuple('r').eval()
		s = self.node.parmTuple('s').eval()

		if not useTuple:
			t = hou.Vector3(t)
			r = hou.Vector3(r)
			s = hou.Vector3(s)

		return (t, r, s)

	def getPivotXform(self):
		(t, r, s) = self.getPivotTRS()
		return buildXformByTRS(t, r, s)

	def movePivotWithoutTransform(self, translate=None, rotate=None, scale=None):

		if translate:
			self.setState('cache_tx', translate[0])
			self.setState('cache_ty', translate[1])
			self.setState('cache_tz', translate[2])
			self.node.parmTuple('t').set(translate)

		if rotate:
			self.setState('cache_rx', rotate[0])
			self.setState('cache_ry', rotate[1])
			self.setState('cache_rz', rotate[2])
			self.node.parmTuple('r').set(rotate)

		if scale:
			self.setState('cache_sx', scale[0])
			self.setState('cache_sy', scale[1])
			self.setState('cache_sz', scale[2])
			self.node.parmTuple('s').set(scale)

# -------------------------------------------------------
# Callbacks by UI

def alignPivot():
	global viewerState

	if not viewerState:
		return

	with hou.undos.group('Align pivot'):
		viewerState.alignPivot()


def resetTransform(mode):
	global viewerState

	if not viewerState:
		return

	if mode == 'translate':
		translate = hou.Vector3()
		viewerState.movePivotWithoutTransform(translate=translate)

	elif mode == 'rotate':
		rotate = hou.Vector3()
		viewerState.movePivotWithoutTransform(rotate=rotate)

	elif mode == 'scale':
		scale = hou.Vector3(1, 1, 1)
		viewerState.movePivotWithoutTransform(scale=scale)

	viewerState.updatePivotCache()


def updatePivotCache():
	global viewerState

	if not viewerState:
		return

	with hou.undos.disabler():
		viewerState.updatePivotCache()


def resetAll():
	node = hou.pwd()
	node.parm('curves').revertToDefaults()
	node.parm('selection').revertToDefaults()
	resetPenAction(node)


def resetPenAction(node):
	node.parm('current_action').set('')
	node.parm('current_anchor').set(EMPTY)
	node.parm('draw_backward').set(False)
	
	node.setCachedUserData('selected_points', [])
	node.setCachedUserData('selected_mode', None)

def fetchSource():
	node = hou.pwd()

	geo = node.inputs()[0].geometry() if len(node.inputs()) > 0 else hou.Geometry()

	with hou.undos.group('Fetch source'):

		if node.parm('fetch_add_to_existing').eval() == 0:
			resetAll()

		curves = Curves(node)
		
		for prim in geo.iterPrims():
			if prim.type() != hou.primType.BezierCurve:
				continue
			
			points = prim.points()

			numpt = len(points)
			closed = prim.isClosed()

			ptnum = None

			for i in xrange(0, numpt, 3):

				anchorPos = points[i].position()
				
				inHandlePos = points[i-1].position() if i > 0 else None
				outHandlePos = points[i+1].position() if i < numpt - 1 else None
				
				if i == 0:
					ptnum = curves.addCurve(anchorPos)
				else:
					ptnum = curves.addAnchor(ptnum, anchorPos, backward=False)

				if i > 0:
					inHandlePos = points[i-1].position()
					curves.setHandle(ptnum, inHandlePos - anchorPos, HandleType.IN)
				elif i == 0 and closed:
					inHandlePos = points[numpt-1].position()
					curves.setHandle(ptnum, inHandlePos - anchorPos, HandleType.IN)
				
				if i < numpt - 1:
					outHandlePos = points[i+1].position()
					curves.setHandle(ptnum, outHandlePos - anchorPos, HandleType.OUT)
			
			if closed:
				primnum = curves.primnum(ptnum)
				curves.setClosed(primnum, True)


# -------------------------------------------------------
# Global functions

INTSERSECTOR_EDGE_SUBDIV = 20

def getBezierInfoByEdge(edge, position, bezierGeo):
	p0, p1 = edge.points()

	pos0 = p0.position()
	pos1 = p1.position()

	edgePos = 0
	if pos0.distanceTo(pos1) > EPSILON:
		edgePos = pos0.distanceTo(position) / pos0.distanceTo(pos1)

	primnum = p0.prims()[0].number()
	points = p0.prims()[0].points()

	index0 = points.index(p0)
	index1 = points.index(p1)

	# get ptnums of 4 points of bezier including the edge
	bezierPoints = bezierGeo.prim(primnum).points()
	numvtx = len(bezierPoints)
	segindex = index0 / INTSERSECTOR_EDGE_SUBDIV

	ptnum0 = bezierPoints[segindex * 3].number()
	ptnum1 = bezierPoints[segindex * 3 + 1].number()
	ptnum2 = bezierPoints[segindex * 3 + 2].number()
	ptnum3 = bezierPoints[(segindex * 3 + 3) % numvtx].number()

	# calc parameter T
	t0 = float(index0) / INTSERSECTOR_EDGE_SUBDIV % 1
	t1 = float(index1) / INTSERSECTOR_EDGE_SUBDIV % 1

	if t1 == 0:
		t1 = 1

	t = (t1 - t0) * edgePos + t0

	return ((ptnum0, ptnum1, ptnum2, ptnum3), t)



# -------------------------------------------------------
# Menu


def createMenu():
	nodetype = kwargs['type']

	typeDescription = nodetype.description()

	keyContext = "h.pane.gview.state.sop.%s" % nodetype.name()
	hou.hotkeys.addContext(
		keyContext, typeDescription,
		typeDescription
	)

	# Build the menu
	menu = hou.ViewerStateMenu('%s_menu' % nodetype.name(), typeDescription)

	hotkey = keyContext + '.switch_tool'
	description = "Switch Tool"
	hou.hotkeys.addCommand(hotkey, description, description, "V")
	menu.addToggleItem('select_mode', 'Select Mode', False, hotkey)

	hotkey = keyContext + '.end_curve'
	description = "End Curve"
	hou.hotkeys.addCommand(hotkey, description, description, ("Esc", 'Enter'))
	menu.addActionItem('end_curve', description, hotkey)

	menu.addSeparator()

	hotkey = keyContext + '.delete'
	description = "Delete Selected"
	hou.hotkeys.addCommand(hotkey, description, description, ("Backspace",))
	menu.addActionItem('delete', description, hotkey)

	
	menu.addSeparator()

	menu.addActionItem('smooth_tangent', 'Smooth Tangent')
	menu.addActionItem('hard_tangent', 'Hard Tangent')
	menu.addActionItem('equal_tangent', 'Equal Tangent') 

	menu.addSeparator()

	menu.addActionItem('cut_curve', 'Cut Curve at Here')
	menu.addActionItem('reverse_curve', 'Reverse Curve')
	menu.addActionItem('straighten_segment', 'Straighten Segment')
	menu.addActionItem('move_pivot', 'Move Pivot to Here')
	menu.addActionItem('orient_pivot', 'Orient Pivot to Here')

	return menu
# -------------------------------------------------------
# Initialize

def registerViewerState():
	template = createViewerStateTemplate()
	hou.ui.registerViewerState(template)


def unregisterViewerState():
	nodetype = kwargs['type']
	name = nodetype.definition().sections()['DefaultState'].contents()
	hou.ui.unregisterViewerState(name)


def createViewerStateTemplate():
	# Grab a reference to the asset's node type
	nodetype = kwargs['type']

	# Use the node's name and label as the state name and label
	state_name = nodetype.definition().sections()['DefaultState'].contents()
	label = nodetype.description()
	category = nodetype.category()
	# Instantiate ViewerStateTemplate with the state name, label,
	# and node type category
	template = hou.ViewerStateTemplate(state_name, label, category)

	# Mandatory binding
	template.bindFactory(State)

	template.bindGeometrySelector(
		name='select_points',
		ordered=True,
		prompt='Select Mode',
		geometry_types=(hou.geometryType.Points,),
				allow_other_sops=False,
		auto_start=False)

	template.bindHandle('sphere', 'edit_xform')
	template.bindHandle('domain', 'do_not_hide')

	template.bindMenu(createMenu())

	return template
