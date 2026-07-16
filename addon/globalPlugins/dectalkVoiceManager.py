# DECtalk Voice Manager — design custom DECtalk voices, export/import them as
# .dtv files. NVDA menu -> Tools -> DECtalk Voice Manager.
#
# A custom voice is a base voice (one of the nine built-ins) plus a raw value
# for every one of the 28 [:dv] parameters. Voices are designed here — each
# parameter is a spin box showing the engine's real value, with the engine's
# real min/max — not by tweaking the live synthesizer. Saved voices appear in
# NVDA's Voice list next to the built-ins. SPF, sentence pause and comma pause
# are global and stay in NVDA's Speech settings.

import globalPluginHandler
import gui
import synthDriverHandler
import wx
from logHandler import log

try:
	from synthDrivers.dectalknew import _params, _voicestore
except Exception:
	_params = _voicestore = None
	log.exception("DECtalk voice manager: driver package unavailable")


def _activeDECtalk():
	synth = synthDriverHandler.getSynth()
	return synth if synth is not None and synth.name == "dectalknew" else None


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self):
		super().__init__()
		if _voicestore is None:
			return
		log.info("DECtalk Voice Manager loaded; custom voices available.")
		self._menuItem = gui.mainFrame.sysTrayIcon.toolsMenu.Append(
			wx.ID_ANY,
			"DECtalk &Voice Manager...",
			"Design custom DECtalk voices; export and import them",
		)
		gui.mainFrame.sysTrayIcon.Bind(wx.EVT_MENU, self._onManager, self._menuItem)

	def terminate(self):
		if _voicestore is None:
			return
		try:
			gui.mainFrame.sysTrayIcon.toolsMenu.Remove(self._menuItem)
		except Exception:
			pass

	def _onManager(self, evt):
		gui.mainFrame.prePopup()
		try:
			VoiceManagerDialog(gui.mainFrame).Show()
		finally:
			gui.mainFrame.postPopup()


class VoiceManagerDialog(wx.Dialog):
	"""Lists custom voices; New/Edit open the editor, plus export/import/delete."""

	def __init__(self, parent):
		super().__init__(parent, title="DECtalk Voice Manager")
		main = wx.BoxSizer(wx.VERTICAL)

		main.Add(wx.StaticText(self, label="Custom &voices:"), flag=wx.ALL, border=8)
		self.voiceList = wx.ListBox(self, size=(340, 180))
		main.Add(self.voiceList, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)
		self.voiceList.Bind(wx.EVT_LISTBOX_DCLICK, self.onEdit)

		row = wx.BoxSizer(wx.HORIZONTAL)
		self.newButton = wx.Button(self, label="&New...")
		self.editButton = wx.Button(self, label="&Edit...")
		self.deleteButton = wx.Button(self, label="&Delete")
		self.exportButton = wx.Button(self, label="E&xport...")
		self.importButton = wx.Button(self, label="&Import...")
		for b in (self.newButton, self.editButton, self.deleteButton,
				  self.exportButton, self.importButton):
			row.Add(b, flag=wx.RIGHT, border=6)
		main.Add(row, flag=wx.ALL, border=8)
		main.Add(self.CreateButtonSizer(wx.CLOSE), flag=wx.ALL | wx.ALIGN_RIGHT, border=8)

		self.newButton.Bind(wx.EVT_BUTTON, self.onNew)
		self.editButton.Bind(wx.EVT_BUTTON, self.onEdit)
		self.deleteButton.Bind(wx.EVT_BUTTON, self.onDelete)
		self.exportButton.Bind(wx.EVT_BUTTON, self.onExport)
		self.importButton.Bind(wx.EVT_BUTTON, self.onImport)
		self.Bind(wx.EVT_BUTTON, lambda e: self.Destroy(), id=wx.ID_CLOSE)
		self.EscapeId = wx.ID_CLOSE

		self.SetSizerAndFit(main)
		self._refresh()
		self.CentreOnScreen()

	def _refresh(self, select=None):
		names = sorted(_voicestore.load())
		self.voiceList.Set(names)
		if names:
			self.voiceList.SetSelection(names.index(select) if select in names else 0)
		for b in (self.editButton, self.deleteButton, self.exportButton):
			b.Enable(bool(names))

	def _selectedName(self):
		i = self.voiceList.GetSelection()
		return self.voiceList.GetString(i) if i != wx.NOT_FOUND else None

	def _syncSynth(self, activate=None):
		synth = _activeDECtalk()
		if synth is None:
			return
		try:
			synth.refreshVoices()
			if activate is not None:
				synth.voice = _voicestore.CUSTOM_PREFIX + activate
				synth.saveSettings()
		except Exception:
			log.exception("DECtalk: could not sync voice with synth")

	def onNew(self, evt):
		dlg = VoiceEditorDialog(self, existing=None)
		if dlg.ShowModal() == wx.ID_OK:
			self._refresh(select=dlg.savedName)
			self._syncSynth(activate=dlg.savedName)
		dlg.Destroy()

	def onEdit(self, evt):
		name = self._selectedName()
		if not name:
			return
		dlg = VoiceEditorDialog(self, existing=name)
		if dlg.ShowModal() == wx.ID_OK:
			self._refresh(select=dlg.savedName)
			self._syncSynth()
		dlg.Destroy()

	def onDelete(self, evt):
		name = self._selectedName()
		if not name:
			return
		if gui.messageBox(
			"Delete the custom voice %s?" % name,
			"DECtalk Voice Manager", wx.YES_NO | wx.ICON_WARNING, self,
		) != wx.YES:
			return
		synth = _activeDECtalk()
		vid = _voicestore.CUSTOM_PREFIX + name
		if synth is not None and getattr(synth, "voice", None) == vid:
			try:
				synth.voice = synth._voiceBase()
				synth.saveSettings()
			except Exception:
				log.exception("DECtalk: could not reset voice after delete")
		_voicestore.delete(name)
		self._refresh()
		self._syncSynth()

	def onExport(self, evt):
		name = self._selectedName()
		if not name:
			return
		with wx.FileDialog(
			self, "Export DECtalk voice", wildcard="DECtalk voice (*.dtv)|*.dtv",
			defaultFile=name + ".dtv", style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
		) as fd:
			if fd.ShowModal() != wx.ID_OK:
				return
			try:
				_voicestore.exportDtv(name, fd.GetPath())
			except (_voicestore.VoiceStoreError, OSError) as e:
				gui.messageBox(str(e), "DECtalk Voice Manager", wx.OK | wx.ICON_ERROR, self)

	def onImport(self, evt):
		with wx.FileDialog(
			self, "Import DECtalk voice", wildcard="DECtalk voice (*.dtv)|*.dtv",
			style=wx.FD_OPEN | wx.FD_FILE_MUST_EXIST,
		) as fd:
			if fd.ShowModal() != wx.ID_OK:
				return
			try:
				name = _voicestore.importDtv(fd.GetPath())
			except _voicestore.VoiceStoreError as e:
				gui.messageBox(str(e), "DECtalk Voice Manager", wx.OK | wx.ICON_ERROR, self)
				return
		self._refresh(select=name)
		self._syncSynth()


class VoiceEditorDialog(wx.Dialog):
	"""Design one voice: name, base voice, and a spin box per [:dv] parameter,
	with a Test button (Alt+T) that speaks the current values."""

	def __init__(self, parent, existing=None):
		self.existing = existing
		self.savedName = None
		title = "Edit voice" if existing else "New voice"
		super().__init__(parent, title=title, style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)

		record = _voicestore.load().get(existing) if existing else None
		baseId = record["base"] if record else "paul"
		values = dict(_params.VOICE_DEFAULTS[baseId])
		if record:
			values.update(record["params"])

		main = wx.BoxSizer(wx.VERTICAL)

		top = wx.BoxSizer(wx.HORIZONTAL)
		top.Add(wx.StaticText(self, label="&Name:"), flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
		self.nameCtrl = wx.TextCtrl(self, value=existing or "", size=(180, -1))
		top.Add(self.nameCtrl, flag=wx.RIGHT, border=16)
		top.Add(wx.StaticText(self, label="&Base voice:"), flag=wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, border=6)
		self._baseIds = list(_params.VOICES)
		self.baseChoice = wx.Choice(
			self, choices=[_params.VOICES[v][1] for v in self._baseIds]
		)
		self.baseChoice.SetSelection(self._baseIds.index(baseId))
		self.baseChoice.Bind(wx.EVT_CHOICE, self.onBaseChanged)
		top.Add(self.baseChoice, flag=wx.ALIGN_CENTER_VERTICAL)
		main.Add(top, flag=wx.ALL, border=8)

		# Scrolled grid of spin boxes, grouped by category.
		panel = wx.ScrolledWindow(self, size=(420, 340), style=wx.VSCROLL)
		panel.SetScrollRate(0, 12)
		grid = wx.BoxSizer(wx.VERTICAL)
		self.spins = {}
		lastCat = None
		for code, label, category in _params.VOICE_PARAMS:
			if category != lastCat:
				cap = wx.StaticText(panel, label=category)
				f = cap.GetFont()
				f.SetWeight(wx.FONTWEIGHT_BOLD)
				cap.SetFont(f)
				grid.Add(cap, flag=wx.TOP | wx.LEFT, border=8)
				lastCat = category
			lo, hi = _params.VOICE_LIMITS[code]
			line = wx.BoxSizer(wx.HORIZONTAL)
			line.Add(
				wx.StaticText(panel, label="%s (%d–%d):" % (label, lo, hi), size=(240, -1)),
				flag=wx.ALIGN_CENTER_VERTICAL | wx.LEFT, border=16,
			)
			spin = wx.SpinCtrl(panel, min=lo, max=hi, initial=int(values[code]))
			spin.SetToolTip("[:dv %s] — range %d to %d" % (code, lo, hi))
			line.Add(spin, flag=wx.LEFT, border=6)
			grid.Add(line, flag=wx.TOP, border=2)
			self.spins[code] = spin
		panel.SetSizer(grid)
		main.Add(panel, proportion=1, flag=wx.EXPAND | wx.ALL, border=8)

		btns = wx.BoxSizer(wx.HORIZONTAL)
		self.testButton = wx.Button(self, label="&Test")
		btns.Add(self.testButton, flag=wx.RIGHT, border=12)
		btns.AddStretchSpacer()
		sizer = self.CreateButtonSizer(wx.OK | wx.CANCEL)
		if sizer:
			btns.Add(sizer)
		main.Add(btns, flag=wx.EXPAND | wx.ALL, border=8)

		self.testButton.Bind(wx.EVT_BUTTON, self.onTest)
		self.Bind(wx.EVT_BUTTON, self.onOk, id=wx.ID_OK)

		# Alt+T anywhere in the dialog triggers Test (the button label already
		# assigns Alt+T, but this also covers focus inside the spin grid).
		accel = wx.AcceleratorTable([
			(wx.ACCEL_ALT, ord("T"), self.testButton.GetId()),
		])
		self.SetAcceleratorTable(accel)

		self.SetSizerAndFit(main)
		self.SetMinSize((460, 480))
		self.CentreOnScreen()
		self.nameCtrl.SetFocus()

	def _currentBase(self):
		return self._baseIds[self.baseChoice.GetSelection()]

	def _currentParams(self):
		return {code: spin.GetValue() for code, spin in self.spins.items()}

	def onBaseChanged(self, evt):
		# Reset spin boxes to the newly chosen base voice's defaults, so picking
		# a base is a clean starting point.
		defaults = _params.VOICE_DEFAULTS[self._currentBase()]
		for code, spin in self.spins.items():
			spin.SetValue(defaults[code])

	def onTest(self, evt):
		synth = _activeDECtalk()
		if synth is None:
			gui.messageBox(
				"Switch NVDA's synthesizer to DECtalk to hear a preview.",
				"DECtalk Voice Manager", wx.OK | wx.ICON_INFORMATION, self,
			)
			return
		try:
			synth.previewVoice(self._currentBase(), self._currentParams())
		except Exception:
			log.exception("DECtalk: preview failed")

	def onOk(self, evt):
		name = self.nameCtrl.GetValue().strip()
		if not name:
			gui.messageBox("The voice needs a name.", "DECtalk Voice Manager",
						   wx.OK | wx.ICON_ERROR, self)
			self.nameCtrl.SetFocus()
			return
		existingNames = _voicestore.load()
		if name != self.existing and name in existingNames:
			if gui.messageBox(
				"A custom voice named %s already exists. Overwrite it?" % name,
				"DECtalk Voice Manager", wx.YES_NO | wx.ICON_WARNING, self,
			) != wx.YES:
				return
		try:
			# Renaming: drop the old record after saving the new one.
			_voicestore.create(name, self._currentBase(), self._currentParams())
			if self.existing and self.existing != name:
				_voicestore.delete(self.existing)
		except _voicestore.VoiceStoreError as e:
			gui.messageBox(str(e), "DECtalk Voice Manager", wx.OK | wx.ICON_ERROR, self)
			return
		self.savedName = name
		self.EndModal(wx.ID_OK)
