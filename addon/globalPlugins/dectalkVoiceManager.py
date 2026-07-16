# DECtalk Voice Manager — create, export (.dtv), import and delete custom
# DECtalk voices. Lives in NVDA menu -> Tools.
#
# The voice data itself is managed by synthDrivers.dectalk._voicestore; this
# module is only the UI. Custom voices are snapshots of the current DECtalk
# parameters saved under a new name — the built-in voices are never modified.

import globalPluginHandler
import gui
import synthDriverHandler
import wx
from logHandler import log

try:
	from synthDrivers.dectalk import _voicestore
except Exception:
	_voicestore = None
	log.exception("DECtalk voice manager: driver package unavailable")


class GlobalPlugin(globalPluginHandler.GlobalPlugin):
	def __init__(self):
		super().__init__()
		if _voicestore is None:
			return
		toolsMenu = gui.mainFrame.sysTrayIcon.toolsMenu
		self._menuItem = toolsMenu.Append(
			wx.ID_ANY,
			"DECtalk &Voice Manager...",
			"Create, export and import custom DECtalk voices",
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


def _activeDECtalk():
	"""The running DECtalk SynthDriver instance, or None."""
	synth = synthDriverHandler.getSynth()
	return synth if synth is not None and synth.name == "dectalk" else None


class VoiceManagerDialog(wx.Dialog):
	def __init__(self, parent):
		super().__init__(parent, title="DECtalk Voice Manager")
		main = wx.BoxSizer(wx.VERTICAL)

		listLabel = wx.StaticText(self, label="Custom &voices:")
		main.Add(listLabel, flag=wx.ALL, border=8)
		self.voiceList = wx.ListBox(self, size=(320, 160))
		main.Add(self.voiceList, proportion=1, flag=wx.EXPAND | wx.LEFT | wx.RIGHT, border=8)

		buttons = wx.BoxSizer(wx.HORIZONTAL)
		self.saveButton = wx.Button(self, label="&Save current voice as new...")
		self.exportButton = wx.Button(self, label="&Export...")
		self.importButton = wx.Button(self, label="&Import...")
		self.deleteButton = wx.Button(self, label="&Delete")
		for b in (self.saveButton, self.exportButton, self.importButton, self.deleteButton):
			buttons.Add(b, flag=wx.RIGHT, border=6)
		main.Add(buttons, flag=wx.ALL, border=8)
		main.Add(self.CreateButtonSizer(wx.CLOSE), flag=wx.ALL | wx.ALIGN_RIGHT, border=8)

		self.saveButton.Bind(wx.EVT_BUTTON, self.onSave)
		self.exportButton.Bind(wx.EVT_BUTTON, self.onExport)
		self.importButton.Bind(wx.EVT_BUTTON, self.onImport)
		self.deleteButton.Bind(wx.EVT_BUTTON, self.onDelete)
		self.Bind(wx.EVT_BUTTON, lambda evt: self.Destroy(), id=wx.ID_CLOSE)
		self.EscapeId = wx.ID_CLOSE

		self.SetSizerAndFit(main)
		self._refresh()
		self.CentreOnScreen()

	def _refresh(self, select=None):
		names = sorted(_voicestore.load())
		self.voiceList.Set(names)
		if names:
			idx = names.index(select) if select in names else 0
			self.voiceList.SetSelection(idx)
		hasAny = bool(names)
		self.exportButton.Enable(hasAny)
		self.deleteButton.Enable(hasAny)

	def _selectedName(self):
		idx = self.voiceList.GetSelection()
		return self.voiceList.GetString(idx) if idx != wx.NOT_FOUND else None

	def _refreshSynthVoiceList(self):
		# The voice list shown in NVDA's speech settings is re-read from the
		# driver; drop any cached copy so new voices appear immediately.
		synth = _activeDECtalk()
		if synth is not None:
			try:
				synth.invalidateCache()
			except Exception:
				pass

	def onSave(self, evt):
		synth = _activeDECtalk()
		if synth is None:
			gui.messageBox(
				"Switch NVDA's synthesizer to DECtalk first — the new voice "
				"is a snapshot of the parameters you are currently using.",
				"DECtalk Voice Manager", wx.OK | wx.ICON_INFORMATION, self,
			)
			return
		name = wx.GetTextFromUser(
			"Name for the new voice (its current parameters — including any "
			"slider tweaks — will be saved; the built-in voices are not changed):",
			"Save voice", "", self,
		).strip()
		if not name:
			return
		if name in _voicestore.load():
			if gui.messageBox(
				"A custom voice named %s already exists. Overwrite it?" % name,
				"DECtalk Voice Manager", wx.YES_NO | wx.ICON_WARNING, self,
			) != wx.YES:
				return
		base, params = synth.snapshotVoice()
		try:
			_voicestore.create(name, base, params)
		except _voicestore.VoiceStoreError as e:
			gui.messageBox(str(e), "DECtalk Voice Manager", wx.OK | wx.ICON_ERROR, self)
			return
		self._refresh(select=name)
		self._refreshSynthVoiceList()

	def onExport(self, evt):
		name = self._selectedName()
		if not name:
			return
		with wx.FileDialog(
			self, "Export DECtalk voice", wildcard="DECtalk voice (*.dtv)|*.dtv",
			defaultFile=name + ".dtv",
			style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT,
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
		self._refreshSynthVoiceList()

	def onDelete(self, evt):
		name = self._selectedName()
		if not name:
			return
		if gui.messageBox(
			"Delete the custom voice %s?" % name,
			"DECtalk Voice Manager", wx.YES_NO | wx.ICON_WARNING, self,
		) != wx.YES:
			return
		_voicestore.delete(name)
		self._refresh()
		self._refreshSynthVoiceList()
