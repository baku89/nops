from __future__ import print_function
import stateutils
import viewerstate.utils as su
import math
from datetime import datetime
import json

from hutil.Qt import QtGui
from hutil.Qt.QtCore import Qt
from lightpanel.widgets import PointingLabel

hou = hou

class UndoClass():
	def __init__(self):
		print('init undo')
	
	def undo(self):
		print('undo')
	
	def redo(self):
		print('redo')


class Curves():

	def pointCount(self, node):
		return len(node.geometry().points())

	def primCount(self, node):
		return len(node.geometry().prims())

	def pointObject(self, node, ptnum):
		return node.geometry().point(ptnum)

	def primObject(self, node, primnum):
		return node.geometry().prim(primnum)

	def sourcePtnum(self, node, ptnum):
		modPoints = node.parm('mod_points').eval()
		delPoints = [int(key) for key in modPoints if modPoints[key] == 'null']

		for delpt in sorted(delPoints):
			if ptnum >= delpt:
				ptnum += 1

		return ptnum

	def sourcePrimnum(self, node, primnum):
		modPrims = node.parm('mod_prims').eval()
		delPrims = [int(key) for key in modPrims if modPrims[key] == 'null']

		for delprim in sorted(delPrims):
			if primnum >= delprim:
				primnum += 1

		return primnum

	def point(self, node, ptnum):
		return self.pointObject(node, ptnum).position()

	def addPoint(self, node, position):
		ptnum = self.pointCount(node)
		offset = self.__pointOffset(node)
		index = ptnum - offset

		pointsParm = node.parm('points')
		pointsParm.insertMultiParmInstance(index)

		self.setPoint(node, ptnum, position)

		return ptnum

	def setPoint(self, node, ptnum, position):
		offset = self.__pointOffset(node)
		index = ptnum - offset

		if index >= 0:
			node.parmTuple('pt%d' % index).set(position)
		else:
			parm = node.parm('mod_points')
			data = parm.eval()

			sourcePtnum = self.sourcePtnum(node, ptnum)

			geo = node.node('./SOURCE_ORIGINAL').geometry()
			original = geo.point(sourcePtnum).position()
			delta = position - original

			key = str(sourcePtnum)

			if delta.length() < 0.000001:
				data.pop(key, None)
			else:
				value = json.dumps(list(delta))
				data[key] = value

			parm.set(data)

	def removePoints(self, node, ptnums):
		for ptnum in sorted(ptnums, reverse=True):
			self.removePoint(node, ptnum)

	def removePoint(self, node, ptnum=None):
		if ptnum == None:
			ptnum = self.pointCount(node) - 1

		primsToDelete = []

		# Remove the point from all curves using it as vertex
		point = self.pointObject(node, ptnum)

		for prim in point.prims():
			restVertices = [p.number()
						 for p in prim.points() if p.number() != ptnum]
			self.setVertices(node, prim.number(), restVertices)
			if len(restVertices) <= 1:
				primsToDelete.append(prim.number())

		# Remove primitives with no vertex
		for primnum in sorted(primsToDelete, reverse=True):
			self.removePrim(node, primnum)

		# Preserve vertices number by decrement indices greater than the deleting ptnum by 1
		# if self.__pointOffset(node) <= ptnum:
		for primnum in xrange(self.primCount(node)):
			vertices = self.vertices(node, primnum)
			vertices = [v - 1 if v >
			    ptnum else v for v in vertices]
			self.setVertices(node, primnum, vertices)

		# Finally delete the point
		pointIndex = ptnum - self.__pointOffset(node)
		if pointIndex >= 0:
			pointsParm = node.parm('points')
			pointsParm.removeMultiParmInstance(pointIndex)
		else:
			parm = node.parm('mod_points')
			data = parm.eval()

			sourcePtnum = self.sourcePtnum(node, ptnum)
			key = str(sourcePtnum)
			data[key] = 'null'
			parm.set(data)

	def addPrim(self, node):
		primnum = self.primCount(node)
		index = primnum - self.__primOffset(node)
		primsParm = node.parm('prims')
		primsParm.insertMultiParmInstance(index)
		return primnum

	def removePrim(self, node, primnum):
		index = primnum - self.__primOffset(node)

		if index >= 0:
			primsParm = node.parm('prims')
			primsParm.removeMultiParmInstance(index)
		else:
			# The prim will be automatically deleted when it loses all vertices
			parm = node.parm('mod_prims')
			data = parm.eval()

			# But keep the information for some references
			sourcePrimnum = self.sourcePrimnum(node, primnum)
			key = str(sourcePrimnum)
			data[key] = 'null'

			parm.set(data)

	def vertices(self, node, primnum):
		index = primnum - self.__primOffset(node)

		vertices = None

		if index >= 0:
			parm = node.parm('prim%d' % index)
			vertices = [int(x) for x in filter(None, parm.eval().split(' '))]
		else:
			prim = self.primObject(node, primnum)
			vertices = [p.number() for p in prim.points()]

		return vertices

	def setVertices(self, node, primnum, vertices):
		index = primnum - self.__primOffset(node)
		if index >= 0:
			parm = node.parm('prim%d' % index)
			parm.set(' '.join([str(x) for x in vertices]))
		else:
			parm = node.parm('mod_prims')
			data = parm.eval()

			sourcePrimnum = self.sourcePrimnum(node, primnum)
			key = str(sourcePrimnum)

			original = self.__sourcePrimMod(node, sourcePrimnum)

			mod = None
			try:
				mod = json.loads(data[key]) if key in data else None
			except:
				pass
			if mod == None:
				mod = self.__sourcePrimMod(node, sourcePrimnum)

			mod[1] = vertices

			# Add only if mod is different from original
			if mod[0] != original[0] and mod[1] != original[1]:
				data[key] = json.dumps(mod)
			else:
				data.pop(key, None)

			parm.set(data)

	def addVertex(self, node, primnum, ptnum):
		self.insertVertex(node, primnum, ptnum)

	def insertVertex(self, node, primnum, ptnum, index=None):
		vertices = self.vertices(node, primnum)

		if index == None:
			vertices.append(ptnum)
		else:
			vertices.insert(index, ptnum)

		self.setVertices(node, primnum, vertices)

	def removeVertex(self, node, primnum, vtxnum):
		vertices = self.vertices(node, primnum)
		vertices.pop(vtxnum)
		self.setVertices(node, primnum, vertices)

	def setClosed(self, node, primnum, closed):
		print('set closed', primnum, closed)
		index = primnum - self.__primOffset(node)
		if index >= 0:
			node.parm('closed%d' % index).set(1 if closed else 0)
		else:
			parm = node.parm('mod_prims')
			data = parm.eval()

			sourcePrimnum = self.sourcePrimnum(node, primnum)
			key = str(sourcePrimnum)

			mod = None
			try:
				mod = json.loads(data[key]) if key in data else None
			except:
				pass
			if mod == None:
				mod = self.__sourcePrimMod(node, sourcePrimnum)

			mod[0] = closed
			data[key] = json.dumps(mod)

			parm.set(data)

	def closed(self, node, primnum):
		index = primnum - self.__primOffset(node)
		if index >= 0:
			return True if node.parm('closed%d' % index).evalAsInt() else False
		else:
			prim = self.primObject(node, primnum)
			return self.__primObjectClosed(prim)

	def joinPrims(self, node, source, target, sourceReversed, targetReversed):
		sourceVertices = self.vertices(node, source)
		tarvertices = self.vertices(node, target)

		if sourceReversed:
			sourceVertices.reverse()
		if targetReversed:
			tarvertices.reverse()

		sourceVertices += tarvertices

		self.setVertices(node, source, sourceVertices)
		self.removePrim(node, target)

		# Return the index of merged primitive
		return source if source < target else source - 1

	def cutPrim(self, node, ptnum):
		geo = node.geometry()
		prims = geo.point(ptnum).prims()
		primnums = [prim.number() for prim in prims]

		for primnum in primnums:
			points = self.vertices(node, primnum)
			vertex = points.index(ptnum)

			if self.closed(node, primnum):
				pos = self.pointObject(node, ptnum).position()
				addedPoint = self.addPoint(node, pos)
				points = points[vertex:] + points[:vertex] + [addedPoint]
				self.setVertices(node, primnum, points)
				self.setClosed(node, primnum, False)

			else:
				if not(vertex == 0 or vertex == len(points) - 1):
					pos = self.pointObject(node, ptnum).position()
					addedPoint = self.addPoint(node, pos)
					newPoints = [addedPoint] + points[vertex+1:]
					newPrim = self.addPrim(node)
					self.setVertices(node, newPrim, newPoints)

					points = points[:vertex+1]
					self.setVertices(node, primnum, points)

	def __pointOffset(self, node):
		return len(node.node('./SOURCE_DELETED').geometry().points())

	def __primOffset(self, node):
		return len(node.node('./SOURCE_DELETED').geometry().prims())

	def __primObjectClosed(self, prim):
		if isinstance(prim, hou.Face):
			points = prim.points()
			unrolled = len(points) > 0 and points[0] == points[len(points) - 1]
			return prim.isClosed() or unrolled
		else:
			return False

	def __sourcePrimMod(self, node, sourcePrimnum):
		prim = node.node('./SOURCE_ORIGINAL').geometry().prim(sourcePrimnum)

		vertices = [vertex.number() for vertex in prim.vertices()]
		closed = self.__primObjectClosed(prim)

		return [closed, vertices]


class MyState(object):
	def __init__(self, **kwargs):

		self.stateName = kwargs['state_name']  # state_name
		self.sceneViewer = kwargs['scene_viewer']  # scene_viewer

		self.initialized = False

		# Nodes
		self.node = None

		# Cursor
		self.watchDrag = False
		self.gi = None
		self.cursorPosition = None

		# Pointer
		self.pointer = PointingLabel()
		self.pointer.setAttribute(Qt.WA_ShowWithoutActivating)
		self.pointer.setOffset(0, 20)
		self.pointer.setFixedWidth(100)
		self.pointer.setOrientation(self.pointer.PointUp)

		# Guide
		self.guides = {}

	def initialize(self, node):
		global viewerState

		if self.initialized:
			return

		viewerState = self
		self.initialized = True
		self.node = node

		# Init state
		self.state('current_point', None)
		self.state('current_prim', None)
		self.state('draw_backward', False)
		self.state('selected_points', [])

		node.setCachedUserData('tool', None)
		self.state('tool', currentTool(node))

		# Init Guide

		# Init Line
		geo = node.node('./GUIDE_LINE').geometry()
		guide = hou.Drawable(self.sceneViewer, geo, 'line')
		guide.enable(True)
		guide.show(True)

		self.guides['line'] = guide

		# Init Anchor
		verb = hou.sopNodeTypeCategory().nodeVerb('sphere')
		geo = hou.Geometry()
		verb.setParms({
			'scale': 1
		})
		verb.execute(geo, [])
		geo.addAttrib(
			hou.attribType.Point, 'Cd', (1.0, 0.0, 0.0))
		geo.addAttrib(hou.attribType.Point, 'Alpha', 0.5)
		geo.addAttrib(hou.attribType.Global, 'gl_lit', 0)

		guide = hou.Drawable(self.sceneViewer, geo, 'anchor')
		guide.setDisplayMode(
			hou.drawableDisplayMode.CurrentViewportMode)
		guide.enable(True)
		guide.show(False)

		self.guides['anchor'] = guide

		# Init Intersection Object
		self.gi = su.GeometryIntersector(
			node.node('./INTERSECTION').geometry(), scene_viewer=self.sceneViewer)
		print(self.gi.snap_priorities)
		self.gi.snap_priorities = (
			hou.snappingPriority.GeoPoint,
			)
		self.gi.snap_mode = hou.snappingMode.Multi

	# State
	def state(self, key, *args):
		global state

		oldValue = state(self.node, key)
		result = state(self.node, key, *args)

		# Side effects on set
		if len(args) > 0:
			newValue = args[0]

			if key == 'tool':
				self.onToolChanged(oldValue, newValue)
			elif key == 'current_point':
				self.node.parm('current_point').set(newValue if newValue != None else -1)

			# Show/Hide handle
			if key in ('tool', 'selected_points'):
				selectedPoints = state(self.node, 'selected_points')
				numSelected = len(selectedPoints)
				show = self.state('tool') == 'edit' and numSelected > 0
				self.sceneViewer.showHandle('anchor_handle', show)
				self.sceneViewer.curViewport().draw()

		return result

	# Methods
	def editGuideLine(self, index, position):
		print('index', index, position)
		self.node.parmTuple('line_guide_pt%d' % index).set(position)

	def updateCursor(self, node, uiEvent):
		origin, direction = uiEvent.ray()
		position = None

		# snapping
		self.gi.intersect(origin, direction)

		if self.gi.snapped:
			position = self.gi.snapped_position

		else:
			intersected = -1
			inputs = node.inputs()

			# try intersecting geometry only if this node has 2nd input
			if inputs and len(inputs) >= 2 and inputs[1]:
				geometry = inputs[1].geometry()
				intersected, position, _, _ = stateutils.sopGeometryIntersection(
					geometry, origin, direction)

			# Project to cplane if it is visible
			if intersected == -1:
				if self.sceneViewer.constructionPlane().isVisible():
						position = stateutils.cplaneIntersection(
								self.sceneViewer, origin, direction)

				# Otherwise, use XZ plane of default viewport grid
				else:
						position = hou.hmath.intersectPlane(
								hou.Vector3(),          # plane_point
								hou.Vector3(0, 1, 0),   # plane_normal
								origin,                 # line_origin
								direction               # line_dir
						)

		self.cursorPosition = position

		# Update guide
		showAnchor = self.gi.snapped
		guideAnchor = self.guides['anchor']
		guideAnchor.show(showAnchor)

		if showAnchor:
			# Scale the anchor sphere so that it will be displayed in constant size on the viewport
			distance = (self.cursorPosition - origin).length()
			scale = distance * 0.003
			xform = hou.hmath.buildTransform({
				'scale': hou.Vector3(scale, scale, scale),
					'translate': self.cursorPosition
			})
			guideAnchor.setTransform(xform)

	def onToolChanged(self, oldTool, newTool):

		# Leave
		if oldTool == 'pen' and newTool != 'pen':
			self.endPath()
		elif oldTool == 'edit' and newTool != 'edit':
			self.state('selected_points', [])
			self.forceUpdateSelection()
			self.sceneViewer.triggerStateSelector(
				hou.triggerSelectorAction.Stop, 'select_points')

		# Enter
		if oldTool != 'edit' and newTool == 'edit':
			# Start Selecting anchor points
			self.sceneViewer.triggerStateSelector(
				hou.triggerSelectorAction.Start, 'select_points')

		# Update Interface
		with hou.undos.disabler():
			currentTool(self.node, newTool)

	def endPath(self):
		# Delete the primitive if its vertices is only one
		primnum = self.state('current_prim')

		if primnum != None:
			vertices = curves.vertices(self.node, primnum)

			if len(vertices) <= 1:
				curves.removePrim(self.node, primnum)

		self.state('current_prim', None)
		self.state('pen', None)
		self.guides['line'].show(False)
		self.sceneViewer.curViewport().draw()

	def forceUpdateSelection(self):
		points = [ptnum for (ptnum, _) in self.state('selected_points')]
		pattern = ' '.join([str(x) for x in points]) if len(points) > 0 else '!*'
		sel = hou.Selection(self.node.geometry(), hou.geometryType.Points, pattern)
		self.sceneViewer.setCurrentGeometrySelection(
			hou.geometryType.Points, (self.node,), (sel,))

	def trigger(self, event):
		if event == 'RESET_ALL':
			if self.state('tool') == 'pen':
				self.endPath()
			elif self.state('tool') == 'edit':
				self.state('selected_points', [])
				self.forceUpdateSelection()

		elif event == 'TOOL_CHANGED':
			self.state('tool', currentTool(self.node))

		elif event == 'SELECTION_CHANGED':
			points = self.state('selected_points')
			pattern = " ".join([str(ptnum) for (ptnum, _) in points])
			sel = hou.Selection(self.node.geometry(),
								hou.geometryType.Points, pattern)
			self.sceneViewer.setCurrentGeometrySelection(
				hou.geometryType.Points, (self.node,), (sel,))

	def detectOperation(self, node):

		tool = self.state('tool')

		result = {}

		if tool == 'pen':

			if self.gi.snapped:
				if self.gi.snap_priority == hou.snappingPriority.GeoPoint:

					point = curves.pointObject(node, self.gi.snapped_point_num)

					targetPrim = None
					isFirstVertex = None
					isLastVertex = None
					canExtend = None

					prims = point.prims()

					if len(prims) == 0:
						if self.state('current_prim') == None:
							# Create new path
							result['type'] = 'create_path'
							result['point'] = point.number()
						else:
							# Append the point to current path
							result['type'] = 'add_point'
							result['prim'] = self.state('current_prim')
							result['point'] = point.number()
							result['draw_backward'] = self.state('draw_backward')

					else:
						for prim in point.prims():
							vertex = point.vertices()[0]
							isFirstVertex = vertex.number() == 0
							isLastVertex = vertex.number() == prim.numVertices() - 1
							closed = curves.closed(node, prim.number())
							canExtend = not closed and (isFirstVertex or isLastVertex)
							targetPrim = prim.number()

							if canExtend:
								break

						if self.state('current_prim') == None:
							if canExtend:
								# Extend a existing path
								result['type'] = 'extend_path'
								result['prim'] = targetPrim
								result['point'] = self.gi.snapped_point_num
								result['position'] = self.cursorPosition
								result['draw_backward'] = isFirstVertex
							else:
								# Delete point
								result['type'] = 'delete_point'
								result['point'] = self.gi.snapped_point_num
						else:
							if canExtend:

								if self.state('current_prim') == targetPrim:
									# Close path
									result['type'] = 'close_path'
									result['prim'] = self.state('current_prim')
								else:
									# Join the target prim after current prim
									result['type'] = 'join_paths'
									result['source'] = self.state('current_prim')
									result['target'] = targetPrim
									result['source_reversed'] = self.state('draw_backward')
									result['target_reversed'] = isLastVertex

				elif self.gi.snap_priority == hou.snappingPriority.GeoEdge or self.gi.snap_priority == hou.snappingPriority.Midpont:
					# Insert new anchor point along edge
					edge = self.gi.snapped_edge
					prim = edge.prims()[0]
					vertices = []

					for pt in edge.points():
						for vertex in pt.vertices():
							if vertex.prim() == prim:
								vertices.append(vertex)
								break

					(v0, v1) = [v.number() for v in vertices]

					if abs(v1 - v0) >= 2:
						v0 = v0 % (prim.numVertices() - 1)
						v1 = v1 % (prim.numVertices() - 1)

					result['type'] = 'insert_point'
					result['prim'] = prim.number()
					result['position'] = curves.addPoint(node, self.cursorPosition)
					result['index'] = max(v0, v1)

			if len(result) == 0:
				pointSnapped = self.gi.snapped and self.gi.snap_priority == hou.snappingPriority.GeoPoint
				point = self.gi.snapped_point_num if pointSnapped else self.cursorPosition

				if self.state('current_prim') == None:
					# Create new path
					result['type'] = 'create_path'
					result['point'] = point

				else:
					# Add new point
					result['type'] = 'add_point'
					result['prim'] = self.state('current_prim')
					result['point'] = point
					result['draw_backward'] = self.state('draw_backward')

		if len(result) > 0:
			result['message'] = ' '.join(w.capitalize()
			                             for w in result['type'].split('_'))

		return result if len(result) > 0 else None

	def onMousemove(self, node, ui_event):
		# Update guides
		with hou.undos.disabler():
			if self.state('current_prim') == None:
				self.guides['line'].show(False)
			else:
				self.guides['line'].show(True)
				self.editGuideLine(1, self.cursorPosition)

		result = self.detectOperation(node)

		if result and not result['type'] in ('create_path', 'add_point'):
			pos = QtGui.QCursor.pos()
			self.pointer.pointAt(pos.x(), pos.y())
			self.pointer.setText(result['message'])
			self.pointer.show()
			self.pointer.repaint()
		else:
			self.pointer.hide()

	def onMousedown(self, node, ui_event):
		result = self.detectOperation(node)

		if result == None:
			return
		
		type = result['type']

		self.sceneViewer.beginStateUndo(result['message'])
		
		if type == 'extend_path':
			self.state('current_prim', result['prim'])
			self.state('current_point', result['point'])
			self.state('draw_backward', result['draw_backward'])
			self.editGuideLine(0, result['position'])
			self.editGuideLine(1, result['position'])
		
		elif type == 'delete_point':
			curves.removePoint(node, result['point'])
		
		elif type == 'close_path':
			curves.setClosed(node, result['prim'], True)
			self.endPath()
	
		elif type == 'join_paths':
			primnum = curves.joinPrims(node,
								source=result['source'],
								target=result['target'],
								sourceReversed=result['source_reversed'],
								targetReversed=result['target_reversed'])
			
			self.state('current_prim', primnum)
			self.endPath()
		
		elif type == 'insert_point':
			curves.insertVertex(result['prim'], result['position'], result['index'])
		
		elif type == 'create_path':
			prim = curves.addPrim(node)
			point = result['point']
			
			if isinstance(point, hou.Vector3):
				point = curves.addPoint(node, point)

			curves.addVertex(node, prim, point)

			self.state('current_prim', prim)
			self.state('current_point', point)
			self.state('draw_backward', False)
			self.watchDrag = True
		
		elif type == 'add_point':
			prim = result['prim']
			point = result['point']

			if isinstance(point, hou.Vector3):
				point = curves.addPoint(node, point)

			if result['draw_backward']:
				curves.insertVertex(node, prim, point, 0)
			else:
				curves.addVertex(node, prim, point)

			self.state('current_prim', prim)
			self.state('current_point', point)
			self.guides['line'].show(False)
			self.watchDrag = True

		if not self.watchDrag:
			self.sceneViewer.endStateUndo()


	def onMousedrag(self, node, ui_event):
		if not self.watchDrag:
			return

		if self.state('tool') == 'pen':
			if self.state('current_prim') != None:
				point = self.state('current_point')
				curves.setPoint(node, point, self.cursorPosition)

	def onMouseup(self, node, ui_event):
		print('onup', self.watchDrag)

		if not self.watchDrag:
			return
		

		if self.state('tool') == 'pen':
			if self.state('current_prim') != None:
				print('calling zero...')
				self.editGuideLine(0, self.cursorPosition)
				self.editGuideLine(1, self.cursorPosition)
				self.guides['line'].show(True)
		
		self.sceneViewer.endStateUndo()

	def onMouseclick(self, node, ui_event):

		if self.state('tool') == 'edit': 
			pointSnapped = self.gi.snapped and self.gi.snap_priority == hou.snappingPriority.GeoPoint

			if pointSnapped:
				position = curves.point(node, self.gi.snapped_point_num)
				self.state('selected_points', [(self.gi.snapped_point_num, position)])
				self.forceUpdateSelection()
				alignPivot(node)

			

	# Native Event Hooks
	def onEnter(self, kwargs):
		print('onEnter', kwargs['node'])
		self.initialize(kwargs['node'])

	def onExit(self, kwargs):
		global viewerState
		print('onExit', self.node)
		viewerState = None

	def onMouseEvent(self, kwargs):
		ui_event = kwargs['ui_event']
		node = kwargs['node']
		reason = ui_event.reason()
		device = ui_event.device()

		self.updateCursor(node, ui_event)
		
		mousePos = [device.mouseX(), device.mouseY()]

		prevMousePos = self.state('prev_mouse_pos') or [-1, -1]
		prevReason = self.state('prev_mouse_reason')
		
		if reason == hou.uiEventReason.Located:
			
			# Detect click in edit mode
			notMoved = mousePos[0] == prevMousePos[0] and mousePos[1] == prevMousePos[1]
			if prevReason == hou.uiEventReason.Located and notMoved:
				self.onMouseclick(node, ui_event)
			
			else:
				self.onMousemove(node, ui_event)

		elif reason == hou.uiEventReason.Picked:
			self.onMousedown(node, ui_event)
			self.onMouseup(node, ui_event)
			self.onMouseclick(node, ui_event)

		elif reason == hou.uiEventReason.Start:
			self.onMousedown(node, ui_event)

		elif reason == hou.uiEventReason.Active:
			self.onMousedrag(node, ui_event)

		elif reason == hou.uiEventReason.Changed:
			self.onMouseup(node, ui_event)
		
		
		self.state('prev_mouse_pos', mousePos)
		self.state('prev_mouse_reason', reason)

		# Deselect when selection has cleared
		if self.state('tool') == 'edit':
			sel = self.sceneViewer.currentGeometrySelection()
			isSelected = len(self.state('selected_points')) > 0
			if len(sel.selections()) == 0 and isSelected:
				self.state('selected_points', [])
				self.forceUpdateSelection()
	
	def onInterrupt(self, kwargs):
		self.pointer.hide()
	
	def onResume(self, kwargs):
		return

	def onHandleToState(self, kwargs):
		global curves

		uiEvent = kwargs['ui_event']
		node = kwargs['node']
		reason = uiEvent.reason()

		if reason == hou.uiEventReason.Start:
			self.sceneViewer.beginStateUndo('Move points')

		elif reason == hou.uiEventReason.Active:

			parms = kwargs['parms']
			translate = hou.Vector3(parms['tx'], parms['ty'], parms['tz'])
			rotate = hou.Vector3(parms['rx'], parms['ry'], parms['rz'])
			scale = hou.Vector3(parms['sx'], parms['sy'], parms['sz'])

			xform = buildXform(translate, rotate, scale)
			origXform = self.state('original_xform')

			deltaXform = origXform.inverted() * xform

			# Transform
			if node.parm('attach_to_geo').eval():
				for (ptnum, oldPos) in self.state('selected_points'):
					pos = oldPos * deltaXform
					curves.setPoint(node, ptnum, pos)

			# Update Interface
			node.parmTuple('t').set(translate)
			node.parmTuple('r').set(rotate)
			node.parmTuple('s').set(scale)

		elif reason == hou.uiEventReason.Changed:
			self.sceneViewer.endStateUndo()

	def onStateToHandle(self, kwargs):
		self.initialize(kwargs['node'])

		parms = kwargs['parms']
		node = kwargs['node']

		# Move points on UI's translate has chagned
		if self.state('tool') == 'edit':
			translate = node.parmTuple('t').eval()
			rotate = node.parmTuple('r').eval()
			scale = node.parmTuple('s').eval()

			parms['tx'] = translate[0]
			parms['ty'] = translate[1]
			parms['tz'] = translate[2]

			parms['rx'] = rotate[0]
			parms['ry'] = rotate[1]
			parms['rz'] = rotate[2]

			parms['sx'] = scale[0]
			parms['sy'] = scale[1]
			parms['sz'] = scale[2]

	def onSelection(self, kwargs):
		sel = kwargs['selection']
		selName = kwargs['name']
		node = kwargs['node']

		if selName == 'select_points':
			if len(sel.selections()) > 0:
				selection = sel.selections()[0]
				geo = node.geometry()
				points = [(point.number(), point.position())
						  for point in selection.points(geo)]

				with hou.undos.group('Select point'):
					self.state('selected_points', points)
					alignPivot(node)

		return False

	def onMenuPreOpen(self, kwargs):
		menu_id = kwargs['menu']
		menu_item_states = kwargs['menu_item_states']

		if menu_id == '%s_menu' % self.node.type().name():  # Root

			numSelected = len(self.state('selected_points'))
			
			tool = self.state('tool')
			pointSnapped = self.gi.snapped and self.gi.snap_priority == hou.snappingPriority.GeoPoint
			canDelete = (tool == 'pen' and pointSnapped) or (tool == 'edit' and numSelected > 0)
			canMerge = tool == 'edit' and numSelected >= 1

			menu_item_states['edit_mode']['value'] = tool == 'edit'

			menu_item_states['delete_points']['enable'] = canDelete
			menu_item_states['merge_points']['enable'] = canMerge
			menu_item_states['cut_path']['enable'] = tool == 'pen' and pointSnapped
			menu_item_states['move_pivot']['enable'] = tool == 'edit'
			menu_item_states['orient_pivot']['enable'] = tool == 'edit'

	def onMenuAction(self, kwargs):
		item = kwargs['menu_item']
		node = kwargs['node']
		ui_event = kwargs['ui_event']

		tool = self.state('tool')

		if item == 'edit_mode':
			value = kwargs['edit_mode']
			self.state('tool', 'edit' if value == True else 'pen')
		
		elif item == 'end_path':
			if tool == 'pen':
				self.endPath()
			else:
				self.state('selected_points', [])
				self.forceUpdateSelection()

		elif item == 'delete_points':
			if tool == 'pen':
				with hou.undos.group('Delete point'):
					curves.removePoint(node, self.gi.snapped_point_num)
					self.updateCursor(node, ui_event)

			if tool == 'edit':
				
				points = [ptnum for (ptnum, _) in self.state('selected_points')]
				isMultiple = len(points) > 1
				undoMsg = 'Delete points' if isMultiple else 'Delete point'

				with hou.undos.group(undoMsg):
					curves.removePoints(node, points)
					self.state('selected_points', [])
					self.forceUpdateSelection()

		elif item == 'merge_points':
			with hou.undos.group('Merge points'):
				points = [ptnum for (ptnum, _) in self.state('selected_points')]
				mergedPtnum = points[0]
				restPtnums = points[1:]

				# Move the point
				center = hou.Vector3(node.parmTuple('t').eval())
				curves.setPoint(node, mergedPtnum, center)

				for ptnum in restPtnums:
					point = curves.pointObject(node, ptnum)
					
					for prim in point.prims():
						primnum = prim.number()
						vertices = curves.vertices(node, primnum)

						# Replace with the merged point
						vertices = [x if x != ptnum else mergedPtnum for x in vertices]

						# Remove the repeated vertices
						for i in range(len(vertices) - 1, 0, -1):
							if vertices[i] == vertices[i - 1]:
								vertices.pop(i)
						
						# Delete the primitive if its number of vertices < 2
						if len(vertices) < 2:
							curves.removePrim(node, primnum)
						else:
							curves.setVertices(node, primnum, vertices)
					
				# Delete the left point
				curves.removePoints(node, restPtnums)

				# Update selection
				self.state('selected_points', [(mergedPtnum, center)])
				self.forceUpdateSelection()

		elif item == 'cut_path':
			with hou.undos.group('Cut path'):
				curves.cutPrim(node, self.gi.snapped_point_num)

		elif item == 'move_pivot':
			with hou.undos.group('Move pivot'):
				node.parmTuple('t').set(self.cursorPosition)
				resetPivotCache(node)

		elif item == 'orient_pivot':
			with hou.undos.group('Rotate pivot'):
				origin = hou.Vector3(node.parmTuple('t').eval())
				target = self.cursorPosition

				direction = (target - origin).normalized() # Direction
				rotate = calcAlginRotate(direction)

				node.parmTuple('r').set(rotate)
				resetPivotCache(node)

# -------------------------------------------------------
# Menu

def createMenu():

	nodetype = kwargs['type']

	keyContext = "h.pane.gview.state.sop.%s" % nodetype.name()
	hou.hotkeys.addContext(
			keyContext, "Draw Polyline Operation",
			"For Drawing Polyline"
	)

	# Build the menu
	menu = hou.ViewerStateMenu(
		'%s_menu' % nodetype.name(), 'Draw Polyline')

	hotkey = keyContext + '.switch_tool'
	description = "Switch Tool"
	hou.hotkeys.addCommand(hotkey, description, description, "V")
	menu.addToggleItem('edit_mode', 'Edit Mode', False, hotkey)

	hotkey = keyContext + '.end_path'
	description = "End Path"
	hou.hotkeys.addCommand(hotkey, description, description, ("Esc", 'Enter'))
	menu.addActionItem('end_path', description, hotkey)

	menu.addSeparator()

	hotkey = keyContext + '.delete_points'
	description = "Delete Selected Points"
	hou.hotkeys.addCommand(hotkey, description, description, ("Backspace",))
	menu.addActionItem('delete_points', description, hotkey)

	hotkey = keyContext + '.merge_points'
	description = "Merge Selected Points"
	hou.hotkeys.addCommand(hotkey, description, description, "M")
	menu.addActionItem('merge_points', description, hotkey)

	menu.addActionItem('cut_path', 'Cut Path at here')
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
	template.bindFactory(MyState)

	template.bindGeometrySelector(
		name='select_points',
		ordered=True,
		prompt='Edit Mode',
		geometry_types=(hou.geometryType.Points,),
		use_existing_selection=True,
		auto_start=False)

	template.bindHandle('sphere', 'anchor_handle', cache_previous_parms=True)
	template.bindMenu(createMenu())

	return template

# -------------------------------------------------------
# Per node setup

def initializeState(node):
	onSelectedPointsChangedByUI(node)

	translate = node.parmTuple('t').eval()
	rotate = node.parmTuple('r').eval()
	scale = node.parmTuple('s').eval()
	xform = buildXform(translate, rotate, scale)
	state(node, 'original_xform', xform)

# -------------------------------------------------------
# Global Actions

viewerState = None
curves = Curves()

def state(node, key, *args):
	if len(args) == 0:
		# Get
		return node.cachedUserData(key)

	else:
		# Set
		value = args[0]

		if key == 'selected_points':
			glob = ' '.join([str(pt[0]) for pt in value])
			node.parm('selection').set(glob)

		node.setCachedUserData(key, value)

def buildXform(translate, rotate, scale):
	xform = hou.hmath.buildTransform({
		'translate': translate,
		'rotate': rotate,
		'scale': scale
	})

	return xform

def calcAlginRotate(direction):
	z = direction
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

def resetPivotCache(node):
	translate = node.parmTuple('t').eval()
	rotate = node.parmTuple('r').eval()
	scale = node.parmTuple('s').eval()
	xform = buildXform(translate, rotate, scale)
	state(node, 'original_xform', xform)

	points = state(node, 'selected_points')
	points = [(ptnum, curves.point(node, ptnum))
			  for (ptnum, _) in points]
	state(node, 'selected_points', points)

def alignPivot(node):
	# Update position
	points = state(node, 'selected_points')
	points = [(ptnum, curves.point(node, ptnum))
			  for (ptnum, _) in points]
	numSelected = len(points)

	# Calculate the new pivot center
	pivotPos = node.parm('pivot_pos').evalAsString()
	pivotAlign = node.parm('pivot_orient').evalAsString()
	
	if numSelected == 0:
		translate = hou.Vector3()
		rotate = hou.Vector3()
		scale = hou.Vector3(1, 1, 1)
	else:
		translate = hou.Vector3()
		rotate = hou.Vector3()
		scale = hou.Vector3(1, 1, 1)

		# Calculate translate
		if pivotPos == 'centroid':
			translate = hou.Vector3()
			for (_, position) in points:
				translate += position
			translate /= numSelected

		elif pivotPos == 'first':
			ptnum, _ = points[0]
			translate = curves.point(node, ptnum)

		elif pivotPos == 'last':
			ptnum, _ = points[numSelected - 1]
			translate = curves.point(node, ptnum)

		# Calculate align
		if pivotAlign == 'auto':
			positions = None
			if numSelected == 1:
				point = curves.pointObject(node, points[0][0])
				vertices = point.vertices()

				# Only if the selected point is connected to one ptimitive
				if len(vertices) == 1:
					vertex = vertices[0]
					prim = vertex.prim()
					vtxnum = vertex.number()
					numvtx = prim.numVertices()

					pos = points[0][1]

					if numvtx > 0:
						if vtxnum == 0:
							positions = [pos, prim.vertex(1).point().position()]
						elif vtxnum == numvtx - 1:
							positions = [pos, prim.vertex(vtxnum - 1).point().position()]
						else:
							positions = [prim.vertex(vtxnum - 1).point().position(),
										 pos, prim.vertex(vtxnum + 1).point().position()]

			elif numSelected > 1:
				if pivotPos == 'centroid':
					if numSelected == 2:
						positions = [points[0][1], points[1][1]]
				elif pivotPos == 'first':
					if numSelected >= 2:
						positions = [points[0][1], points[1][1]]
				elif pivotPos == 'last':
					if numSelected >= 2:
						positions = [points[numSelected - 1]
									 [1], points[numSelected - 2][1]]

			if positions:
				direction = None
				if len(positions) == 2:
					direction = (positions[1] - positions[0]).normalized()
				elif len(positions) == 3:
					dirA = (positions[1] - positions[0]).normalized()
					dirB = (positions[2] - positions[1]).normalized()
					direction = (dirA + dirB).normalized()

				rotate = calcAlginRotate(direction)

	# Update interface
	if pivotPos != 'nochange':
		node.parmTuple('t').set(translate)

	if pivotAlign != 'nochange':
		node.parmTuple('r').set(rotate)
		node.parmTuple('s').set(scale)

	resetPivotCache(node)

def onSelectedPointsChangedByUI(node):
	pattern = node.parm('selection').eval().strip()
	geo = node.geometry()

	try:
		points = geo.globPoints(pattern) if pattern else []
	except:
		points = []

	# Update state
	points = [(p.number(), p.position()) for p in points]

	if viewerState:
		viewerState.state("selected_points", points)
	else:
		state(node, 'selected_points', points)


def currentTool(node, value=None):
	tools = ['pen', 'edit']
	if value == None:
		index = node.parm('tool1').eval()
		return tools[index]
	else:
		node.parm('tool1').set(tools.index(value))


def trigger(event, node=None):
	global curves

	if not curves:
		curves = Curves(node)
	
	if node == None:
		node = hou.pwd()

	if event == 'RESET_ALL':

		# Edit
		node.parm('selection').set('')
		node.parmTuple('t').set((0, 0, 0))
		node.parmTuple('r').set((0, 0, 0))
		node.parmTuple('s').set((1, 1, 1))

		# Add
		pointsParm = node.parm('points')
		numpt = pointsParm.evalAsInt()
		for _ in range(numpt):
			pointsParm.removeMultiParmInstance(0)

		primsParm = node.parm('prims')
		numprim = primsParm.evalAsInt()
		for _ in range(numprim):
			primsParm.removeMultiParmInstance(0)
		
		# Modify
		node.parm('mod_points').set(None)
		node.parm('mod_prims').set(None)

	elif event == 'EDIT_XFORM':
		points = state(node, 'selected_points')

		translate = node.parmTuple('t').eval()
		rotate = node.parmTuple('r').eval()
		scale = node.parmTuple('s').eval()

		xform = buildXform(translate, rotate, scale)
		origXform = state(node, 'original_xform')
		deltaXform = origXform.inverted() * xform

		# Move points when the action was triggered by changing parameter UI
		attachToGeo = node.parm('attach_to_geo').eval()

		if attachToGeo:
			for (ptnum, oldPos) in points:
				position = oldPos * deltaXform
				curves.setPoint(node, ptnum, position)

	elif event == 'SELECTION_CHANGED':
		with hou.undos.group('Select points'):
			onSelectedPointsChangedByUI(node)
			alignPivot(node)

	elif event == 'ALIGN_PIVOT':
		with hou.undos.group('Align pivot'):
			alignPivot(node)

	elif event == 'RESET_PIVOT':
		node.parmTuple('t').set((0, 0, 0))
		node.parmTuple('r').set((0, 0, 0))
		node.parmTuple('s').set((1, 1, 1))

	if viewerState != None:
		viewerState.trigger(event)
