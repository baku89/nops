hou = hou  # pylint: disable=undefined-variable
basestring = basestring  # pylint: disable=undefined-variable
xrange = xrange  # pylint: disable=undefined-variable
reload = reload # pylint: disable=undefined-variable

import stateutils  # pylint: disable=import-error
import viewerstate.utils as su  # pylint: disable=import-error

import baku_modules  # pylint: disable=import-error
reload(baku_modules)

from baku_modules import enterInteractiveEdit  # pylint: disable=import-error
from baku_modules import computeDirectionRotates  # pylint: disable=import-error
from baku_modules import computeDeltaXform  # pylint: disable=import-error
from baku_modules import buildXformByTRS  # pylint: disable=import-error
from baku_modules import Cursor  # pylint: disable=import-error
from baku_modules import EPSILON  # pylint: disable=import-error


viewerState = None


class Elements():

	def __init__(self, node):
		self.node = node
		self.geo = self.node.node('./RESULT').geometry()

	def transform(self, primnum):
		return self.geo.prim(primnum).fullTransform()

	def instanceIndex(self, primnum):
		prefix = self.__getPrefix(primnum)
		if prefix and prefix.startswith('add'):
			return self.node.parm(prefix + '_instanceindex').eval()
		else:
			return None

	def setTransform(self, primnum, xform):
		prefix = self.__getPrefix(primnum, createNew=True)

		sourceXform = self.__sourceTransform(primnum)
		xform = xform * sourceXform.inverted()

		self.__setTransformParm(prefix, xform)
		# self.__deleteModIfUnchanged(prefix)

	def setInstanceIndex(self, primnum, index):
		prefix = self.__getPrefix(primnum, createNew=True)

		if prefix.startswith('mod'):
			self.node.parm(prefix + '_instanceindex').set(index)
			self.__deleteModIfUnchanged(prefix)
		else:
			if index >= 0:
				self.node.parm(prefix + '_instanceindex').set(index)

	def add(self, xform, instanceIndex=None):
		index = self.node.parm('add').eval()
		self.node.parm('add').insertMultiParmInstance(index)
		prefix = 'add' + str(index + 1)

		self.__setTransformParm(prefix, xform)

		if instanceIndex != None:
			self.node.parm(prefix + '_instanceindex').set(instanceIndex)

		return len(self.geo.prims()) - 1

	def delete(self, prims):
		for primnum in sorted(prims, reverse=True):
			prefix = self.__getPrefix(primnum, createNew=True)
			if prefix.startswith('mod'):
				self.node.parm(prefix + '_delete').set(True)
			else:
				index = int(prefix[3:]) - 1
				self.node.parm('add').removeMultiParmInstance(index)

	def __deleteModIfUnchanged(self, prefix):
		delete = self.node.parm(prefix + '_delete').eval()
		if delete == 1:
			return

		instanceIndex = self.node.parm(prefix + '_instanceindex').eval()
		if instanceIndex != -1:
			return

		trans = self.node.parmTuple(prefix + '_trans').eval()
		if abs(trans[0]) > EPSILON or abs(trans[1]) > EPSILON or abs(trans[2]) > EPSILON:
			return

		rot = self.node.parmTuple(prefix + '_rot').eval()
		if abs(rot[0]) > EPSILON or abs(rot[1]) > EPSILON or abs(rot[2]) > EPSILON:
			return

		scale = self.node.parmTuple(prefix + '_scale').eval()
		if abs(scale[0] - 1) > EPSILON or abs(scale[1] - 1) > EPSILON or abs(scale[2] - 1) > EPSILON:
			return

		index = int(prefix[3:]) - 1
		self.node.parm('mod').removeMultiParmInstance(index)

	def __getPrefix(self, primnum, createNew=False):

		prefix = self.geo.prim(primnum).attribValue('__parm')

		if not prefix and createNew:
			sectionName = 'mod' if primnum < self.__primOffset() else 'add'
			index = self.node.parm(sectionName).eval()
			self.node.parm(sectionName).insertMultiParmInstance(index)
			prefix = sectionName + str(index + 1)

			if sectionName == 'mod':
				sourcePrimnum = self.geo.prim(
					primnum).intAttribValue('__source_prim')
				self.node.parm(prefix + '_prim').set(sourcePrimnum)

		return prefix

	def __setTransformParm(self, prefix, xform):
		components = xform.explode()
		trans = components['translate']
		rot = components['rotate']
		scale = components['scale']

		self.node.parmTuple(prefix + '_trans').set(trans)
		self.node.parmTuple(prefix + '_rot').set(rot)
		self.node.parmTuple(prefix + '_scale').set(scale)

	def __sourceTransform(self, primnum):
		sourcePrimnum = self.geo.prim(
			primnum).intAttribValue('__source_prim')

		if sourcePrimnum >= 0:
			return self.node.node('./SOURCE').geometry().prim(sourcePrimnum).fullTransform()
		else:
			return hou.Matrix4(1)

	def __primOffset(self):
		return len(self.node.node('./MODIFIED').geometry().prims())


class State():
	WATCH_PARMS = ('selection', 'tool', 'tx', 'ty', 'tz',
				   'rx', 'ry', 'rz', 'sx', 'sy', 'sz', 'instanceindex', 'attach_to_geo')

	TOOL_EDIT = 0
	TOOL_ADD = 1

	def __init__(self, **kwargs):
		self.stateName = kwargs['state_name']
		self.sceneViewer = kwargs['scene_viewer']

		self.initialized = False

	def initialize(self, node):
		if self.initialized:
			return
		self.initialized = True

		self.node = node
		self.elements = Elements(self.node)

		# Init Cursor
		geo = self.node.node('./ADD_GUIDE').geometry()
		guide = hou.Drawable(self.sceneViewer, geo, 'cursor')
		guide.enable(True)
		guide.show(True)
		self.cursorGuide = guide

		geo = hou.Geometry()
		self.cursor = Cursor({
			'node': self.node,
			'scene_viewer': self.sceneViewer,
			'reference_geo': self.node.inputs()[4].geometry() if len(self.node.inputs()) >= 5 else None
		})

		# Initialize selection
		self.node.parm('selection').set('')
		self.setState('selected_prims', [])
		self.onChangeTool()

		# Init pivot cahce
		self.updatePivotCache()

		for name in State.WATCH_PARMS:
			self.setState('cache_%s' % name, self.node.parm(name).eval())

	def setState(self, key, value):
		self.node.setCachedUserData(key, value)

	def state(self, key):
		return self.node.cachedUserData(key)

	def onChangeTool(self):
		isEdit = self.node.parm('tool').eval() == State.TOOL_EDIT

		selectorAction = hou.triggerSelectorAction.Start if isEdit else hou.triggerSelectorAction.Stop
		self.sceneViewer.triggerStateSelector(selectorAction, 'select_prims')

		if not isEdit:
			self.sceneViewer.setPromptMessage('Add Mode')

	def applyInstanceIndex(self):
		index = self.node.parm('instanceindex').eval()

		for primnum in self.state('selected_prims'):
			self.elements.setInstanceIndex(primnum, index)

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
			self.updateSelection(
				selection, updateParm=False, updateViewer=True)

		if 'tool' in changed:
			self.updateSelection([])
			self.onChangeTool()

		for key in ('tx', 'ty', 'tz', 'rx', 'ry', 'rz', 'sx', 'sy', 'sz'):
			if key in changed:
				# On either transform component has changed
				t = hou.Vector3(self.node.parmTuple('t').eval())
				r = hou.Vector3(self.node.parmTuple('r').eval())
				s = hou.Vector3(self.node.parmTuple('s').eval())
				xform = buildXformByTRS(t, r, s)
				self.transformWithPivot(xform)
				break

		if 'attach_to_geo' in changed:
			if changed['attach_to_geo']['value']:
				self.updatePivotCache()

	def onEnter(self, kwargs):
		global viewerState
		viewerState = self
		self.initialize(kwargs['node'])

		with hou.undos.disabler():
			self.node.parm('viewerstate_enabled').set(True)

	def onExit(self, kwargs):
		global viewerState
		if self.node:
			with hou.undos.disabler():
				self.node.parm('viewerstate_enabled').set(False)
		viewerState = None

	def onInterrupt(self, kwargs):
		self.cursorGuide.show(False)

	def onResume(self, kwargs):
		self.cursorGuide.show(True)

	def updateCursor(self, uiEvent):

		options = {
			'ui_event': uiEvent
		}
		self.cursor.update(options)

		# Update status
		xform = hou.hmath.buildTransform({
			'translate': self.cursor.position
		})
		self.cursorGuide.setTransform(xform)

	def onMouseEvent(self, kwargs):
		uiEvent = kwargs['ui_event']
		reason = uiEvent.reason()

		tool = self.node.parm('tool').eval()

		self.updateCursor(uiEvent)

		if reason == hou.uiEventReason.Picked or reason == hou.uiEventReason.Start:

			if tool == State.TOOL_ADD:

				rotate = hou.Vector3(self.node.parmTuple('r').eval())
				scale = hou.Vector3(self.node.parmTuple('s').eval())

				xform = buildXformByTRS(self.cursor.position, rotate, scale)
				instanceIndex = self.node.parm('instanceindex').eval()

				with hou.undos.group('Add an instance'):
					primnum = self.elements.add(xform, instanceIndex)
					self.updateSelection([primnum])

		
		if reason == hou.uiEventReason.Located:

			if tool == State.TOOL_ADD and self.cursor.normal != None:
				rotate = computeDirectionRotates(self.cursor.normal)

				with hou.undos.disabler():
					self.movePivotWithoutTransform(rotate=rotate)


			# Deselect when selection has cleared
			sel = self.sceneViewer.currentGeometrySelection()
			if sel and len(sel.selections()) == 0 and len(self.state('selected_prims')) > 0:
				with hou.undos.group('Clear selection'):
					self.updateSelection([])

	def onSelection(self, kwargs):
		sel = kwargs['selection']
		name = kwargs['name']

		if name == 'select_prims' and len(sel.selections()) > 0:
			selection = sel.selections()[0]
			self.updateSelection(selection)

		return False

	def updateSelection(self, selection=[], updateParm=True, updateViewer=False):

		geo = self.node.geometry()

		if isinstance(selection, basestring):
			selection = hou.Selection(self.node.geometry(),
									  hou.geometryType.Primitives, selection)

		elif not isinstance(selection, hou.Selection):
			prims = [geo.prim(primnum) for primnum in selection]
			selection = hou.Selection(prims)

		selectedPrims = [prim.number() for prim in selection.prims(geo)]
		isSelected = len(selectedPrims) > 0
		selectionString = selection.selectionString(
			geo, asterisk_to_select_all=True)

		instanceIndex = -1

		if len(selectedPrims) > 0:
			instanceIndex = self.elements.instanceIndex(selectedPrims[0])

			for i in xrange(1, len(selectedPrims)):
				if instanceIndex != self.elements.instanceIndex(selectedPrims[i]):
					instanceIndex = -1
					break

		with hou.undos.group('Select primitives' if isSelected else 'Clear selection'):

			self.setState('selected_prims', selectedPrims)

			self.setState('cache_selection', selectionString)

			if updateParm:
				self.node.parm('selection').set(selectionString)

			self.node.parm('instanceindex').set(instanceIndex)

			self.alignPivot()

			if updateViewer and self.sceneViewer.currentGeometrySelection() != None:
				self.sceneViewer.setCurrentGeometrySelection(
					hou.geometryType.Primitives, (self.node,), (selection,))

			self.sceneViewer.showHandle('edit_xform', isSelected)

	def alignPivot(self):
		selection = self.state('selected_prims')
		numSelected = len(selection)

		pivotPos = self.node.parm('pivot_pos').evalAsString()
		pivotAlign = self.node.parm('pivot_orient').evalAsString()

		translate = hou.Vector3(self.node.parmTuple('t').eval())
		rotate = hou.Vector3(self.node.parmTuple('r').eval())
		scale = hou.Vector3(self.node.parmTuple('s').eval())

		if pivotPos == 'centroid':
			centroidNode = self.node.node('./CENTROID')
			translate = centroidNode.geometry().attribValue('centroid')

		elif pivotPos == 'first' and numSelected > 0:
			primnum = selection[0]
			translate = self.elements.transform(primnum).extractTranslates()

		elif pivotPos == 'last' and numSelected > 0:
			primnum = selection[numSelected - 1]
			translate = self.elements.transform(primnum).extractTranslates()

		if pivotAlign == 'auto':
			if numSelected == 1:
				xform = self.elements.transform(selection[0])
				components = xform.explode()
				rotate = components['rotate']
				scale = components['scale']
			else:
				rotate = hou.Vector3()
				scale = hou.Vector3(1, 1, 1)

		xform = buildXformByTRS(translate, rotate, scale)

		# Update interface
		self.movePivotWithoutTransform(translate, rotate, scale)
		self.updatePivotCache(xform)

	def updatePivotCache(self, pivotXform=None):

		if pivotXform == None:
			translate = hou.Vector3(self.node.parmTuple('t').eval())
			rotate = hou.Vector3(self.node.parmTuple('r').eval())
			scale = hou.Vector3(self.node.parmTuple('s').eval())
			pivotXform = buildXformByTRS(translate, rotate, scale)

		selection = self.state('selected_prims')
		xforms = [self.elements.transform(primnum)
				  for primnum in selection]
		self.setState('selection_xforms', xforms)
		self.setState('pivot_original_xform', pivotXform)

	def transformWithPivot(self, pivotXform):
		# print('transform')
		if self.node.parm('./attach_to_geo').eval():
			pivotOrigXform = self.state('pivot_original_xform')

			# TODO: If initial xform cannot be inverted as scale it set to zero,
			# ignore scale
			pivotDeltaXform = computeDeltaXform(pivotOrigXform, pivotXform)

			xformMode = self.node.parm('xform_mode').evalAsString()

			if xformMode == 'individual':
				pivotDeltaXform.setAt(3, 0, 0)
				pivotDeltaXform.setAt(3, 1, 0)
				pivotDeltaXform.setAt(3, 2, 0)

			selection = self.state('selected_prims')
			xforms = self.state('selection_xforms')

			for (i, primnum) in enumerate(selection):
				xform = xforms[i]

				if xformMode == 'individual':
					xform = hou.Matrix4(xform.asTuple())
					t = xform.extractTranslates()
					xform.setAt(3, 0, 0)
					xform.setAt(3, 1, 0)
					xform.setAt(3, 2, 0)
					xform *= pivotDeltaXform
					xform.setAt(3, 0, t[0])
					xform.setAt(3, 1, t[1])
					xform.setAt(3, 2, t[2])
				elif xformMode == 'translate':
					t = (xform * pivotDeltaXform).extractTranslates()
					xform = hou.Matrix4(xform.asTuple())
					xform.setAt(3, 0, t[0])
					xform.setAt(3, 1, t[1])
					xform.setAt(3, 2, t[2])
				else:
					xform = xform * pivotDeltaXform

				self.elements.setTransform(primnum, xform)

	def onHandleToState(self, kwargs):
		uiEvent = kwargs['ui_event']
		reason = uiEvent.reason()
		handle = kwargs['handle']

		if handle == 'edit_xform':

			parms = kwargs['parms']
			translate = hou.Vector3(parms['tx'], parms['ty'], parms['tz'])
			rotate = hou.Vector3(parms['rx'], parms['ry'], parms['rz'])
			scale = hou.Vector3(parms['sx'], parms['sy'], parms['sz'])
			handleXform = buildXformByTRS(translate, rotate, scale)

			if reason == hou.uiEventReason.Start:
				self.sceneViewer.beginStateUndo('Transform elements')
				self.updatePivotCache(handleXform)
				self.cursorGuide.show(False)

			self.movePivotWithoutTransform(translate, rotate, scale)

			if reason == hou.uiEventReason.Active:
				self.transformWithPivot(handleXform)

			if reason == hou.uiEventReason.Changed:
				self.updatePivotCache(handleXform)
				self.cursorGuide.show(True)
				self.sceneViewer.endStateUndo()

	def onStateToHandle(self, kwargs):
		# print('state -> handle')

		self.initialize(kwargs['node'])

		self.detectParmChange()

		handle = kwargs['handle']

		if handle == 'edit_xform':

			parms = kwargs['parms']

			translate = self.node.parmTuple('t').eval()
			rotate = self.node.parmTuple('r').eval()
			scale = self.node.parmTuple('s').eval()

			parms['tx'] = translate[0]
			parms['ty'] = translate[1]
			parms['tz'] = translate[2]

			parms['rx'] = rotate[0]
			parms['ry'] = rotate[1]
			parms['rz'] = rotate[2]

			parms['sx'] = scale[0]
			parms['sy'] = scale[1]
			parms['sz'] = scale[2]

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

	def onMenuPreOpen(self, kwargs):

		menu_id = kwargs['menu']
		menu_item_states = kwargs['menu_item_states']

		if menu_id == self.node.type().name() + '_menu':  # Root

			numSelected = len(self.state('selected_prims'))
			tool = self.node.parm('tool').eval()

			menu_item_states['edit_mode']['value'] = tool == State.TOOL_EDIT
			menu_item_states['delete']['enable'] = numSelected > 0
			menu_item_states['duplicate']['enable'] = numSelected > 0

	def onMenuAction(self, kwargs):
		item = kwargs['menu_item']

		if item == 'edit_mode':
			parm = self.node.parm('tool')
			isEdit = kwargs['edit_mode'] == State.TOOL_EDIT
			parm.set(State.TOOL_ADD if isEdit else State.TOOL_EDIT)

		elif item == 'delete':
			with hou.undos.group('Delete Primitives'):
				selection = self.state('selected_prims')
				self.elements.delete(selection)
				self.node.parm('selection').set('')

		elif item == 'duplicate':
			with hou.undos.group('Duplicate Primitives'):
				for primnum in self.state('selected_prims'):
					xform = self.elements.transform(primnum)
					instanceIndex = self.elements.instanceIndex(primnum)
					self.elements.add(xform, instanceIndex)

		elif item == 'move_pivot':
			with hou.undos.group('Move Pivot'):
				self.movePivotWithoutTransform(translate=self.cursor.position)
				self.updatePivotCache()

		elif item == 'orient_pivot':
			with hou.undos.group('Orient Pivot'):
				origin = hou.Vector3(self.node.parmTuple('t').eval())
				target = self.cursor.position

				direction = (target - origin).normalized()  # Direction
				rotate = computeDirectionRotates(direction)

				self.movePivotWithoutTransform(rotate=rotate)
				self.updatePivotCache()


# -------------------------------------------------------
# Callbacks by UI


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


def applyInstanceIndex():
	global viewerState

	if not viewerState:
		return

	viewerState.applyInstanceIndex()


def alignPivot():
	global viewerState

	if not viewerState:
		return

	with hou.undos.group('Align pivot'):
		viewerState.alignPivot()


def updatePivotCache():
	global viewerState

	if not viewerState:
		return

	with hou.undos.disabler():
		viewerState.updatePivotCache()


def resetAll():
	node = hou.pwd()
	node.parm('mod').revertToDefaults()
	node.parm('add').revertToDefaults()
	node.parm('selection').revertToDefaults()


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
	menu.addToggleItem('edit_mode', 'Edit Mode', False, hotkey)

	hotkey = keyContext + '.delete'
	description = "Delete Selected Primitives"
	hou.hotkeys.addCommand(hotkey, description, description, ("Backspace",))
	menu.addActionItem('delete', description, hotkey)

	hotkey = keyContext + '.duplicate'
	description = "Duplicate Selected Primitives"
	hou.hotkeys.addCommand(hotkey, description, description, ("Ctrl+D",))
	menu.addActionItem('duplicate', description, hotkey)

	menu.addActionItem('move_pivot', 'Move Pivot to Here')
	menu.addActionItem('orient_pivot', 'Orient Pivot to Here')

	return menu

# -------------------------------------------------------
# Initialize


viewerState = None


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
		name='select_prims',
		ordered=True,
		prompt='Edit Packed Primitive',
		geometry_types=(hou.geometryType.Primitives,),
		primitive_types=(hou.primType.PackedGeometry,),
		auto_start=False)

	template.bindHandle('sphere', 'edit_xform')
	template.bindHandle('domain', 'do_not_hide')

	template.bindMenu(createMenu())

	return template
