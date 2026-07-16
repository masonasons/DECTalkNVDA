# _dectalk.py — ctypes wrapper over DECtalk.dll's legacy TTS API.
#
# The NVDA sibling of the Apple/Android projects' dtk_shim.c: text in, signed
# 16-bit mono PCM out via the in-memory synthesis path (no audio device), plus
# index marks for cursor tracking. No NVDA imports here so it can be exercised
# from a plain Python interpreter.
#
# x64 hazard: the engine's callback passes the completed TTS_BUFFER_T pointer
# through a C `long` (32-bit on Win64), so the pointer arrives truncated.
# Buffers are recycled strictly FIFO (AddBuffer order == delivery order), so we
# track our own queue and never dereference the callback's pointer argument.

import ctypes
import os
import threading
from collections import deque
from ctypes import POINTER, Structure, byref, c_char_p, c_int, c_long, c_short, c_uint, c_ulong, c_void_p, c_wchar_p

DWORD = c_ulong
LPSTR = c_char_p

TTS_NORMAL = 0
TTS_FORCE = 1
WAVE_MAPPER = 0xFFFFFFFF
DO_NOT_USE_AUDIO_DEVICE = 0x80000000
WAVE_FORMAT_1M16 = 0x0004  # 11.025 kHz, mono, 16-bit

SAMPLE_RATE = 11025
BUFFER_COUNT = 4
BUFFER_BYTES = 16384  # ~0.37 s of 11025 Hz 16-bit mono per buffer
MAX_INDEX_MARKS = 128

#: The nine predefined speakers, in SPEAKER_T order.
SPEAKERS = (
	"Perfect Paul",
	"Beautiful Betty",
	"Huge Harry",
	"Frail Frank",
	"Doctor Dennis",
	"Kit the Kid",
	"Uppity Ursula",
	"Rough Rita",
	"Whispering Wendy",
)


class TTS_INDEX_T(Structure):
	_fields_ = [
		("dwIndexValue", DWORD),
		("dwIndexSampleNumber", DWORD),
		("dwReserved", DWORD),
	]


class TTS_BUFFER_T(Structure):
	_fields_ = [
		("lpData", c_void_p),
		("lpPhonemeArray", c_void_p),
		("lpIndexArray", POINTER(TTS_INDEX_T)),
		("dwMaximumBufferLength", DWORD),
		("dwMaximumNumberOfPhonemeChanges", DWORD),
		("dwMaximumNumberOfIndexMarks", DWORD),
		("dwBufferLength", DWORD),
		("dwNumberOfPhonemeChanges", DWORD),
		("dwNumberOfIndexMarks", DWORD),
		("dwReserved", DWORD),
	]


# SPDEFS (ttsapi.h): every field is a short. Fields we expose are named by
# their [:dv] code; engine-internal trailing fields keep descriptive names.
_SPDEFS_FIELDS = [
	"sx", "sm", "as", "ap", "pr", "br", "ri", "nf", "la", "hs",
	"f4", "b4", "f5", "b5", "parallel4_freq", "parallel5_freq",
	"gf", "gh", "gv", "gn", "g1", "g2", "g3", "g4",
	"lo", "ft", "bf", "lx", "qu", "hr", "sr",
	"avg_glot_open", "avg_glot_voicd_open", "avg_glot_unv_open",
	"area_chink", "open_quo", "output_gain_mult", "junk", "junk1",
]


class SPDEFS(Structure):
	_fields_ = [(("dv_" + name) if len(name) == 2 else name, c_short) for name in _SPDEFS_FIELDS]


#: [:dv] parameter codes readable from SPDEFS (all 28 the sibling apps expose).
DV_CODES = [name for name in _SPDEFS_FIELDS if len(name) == 2 and name != "lo"]

DtCallback = ctypes.CFUNCTYPE(None, c_long, c_long, DWORD, c_uint)


def default_lib_path():
	"""Path of the DECtalk.dll matching this process's architecture."""
	arch = "x64" if ctypes.sizeof(c_void_p) == 8 else "x86"
	return os.path.join(os.path.dirname(__file__), "lib", arch, "DECtalk.dll")


def default_dic_path():
	return os.path.join(os.path.dirname(__file__), "dtalk_us.dic")


class DECtalkError(RuntimeError):
	pass


class Engine:
	"""One DECtalk engine instance doing in-memory synthesis.

	speak() is blocking and must be called from a single worker thread;
	stop() may be called from any thread to flush queued speech.
	"""

	def __init__(self, lib_path=None, dic_path=None):
		self._lib = ctypes.CDLL(lib_path or default_lib_path())
		self._handle = c_void_p()
		self._speak_lock = threading.Lock()
		self._cb_lock = threading.Lock()
		self._stop_lock = threading.Lock()
		self._speaking = False
		self._session_open = False
		self._fifo = deque()
		self._on_buffer = None
		# On WIN32 the callback's message IDs are registered window messages,
		# not the TTS_MSG_* constants (those are the POSIX builds' values).
		user32 = ctypes.windll.user32
		self._msg_buffer = user32.RegisterWindowMessageA(b"DECtalkBufferMessage")
		self._msg_index = user32.RegisterWindowMessageA(b"DECtalkIndexMessage")
		# The ctypes callback object must outlive the engine handle.
		self._callback = DtCallback(self._dt_callback)

		lib = self._lib
		# The dictionary name parameter is declared TCHAR* but the desktop
		# WIN32 code path copies it with a narrow strcpy — pass ANSI bytes.
		lib.TextToSpeechStartupExFonix.argtypes = [
			POINTER(c_void_p), c_uint, DWORD, DtCallback, c_long, c_char_p,
		]
		lib.TextToSpeechStartupExFonix.restype = c_uint
		lib.TextToSpeechShutdown.argtypes = [c_void_p]
		lib.TextToSpeechSpeak.argtypes = [c_void_p, LPSTR, DWORD]
		lib.TextToSpeechSync.argtypes = [c_void_p]
		lib.TextToSpeechReset.argtypes = [c_void_p, c_int]
		lib.TextToSpeechSetSpeaker.argtypes = [c_void_p, DWORD]
		lib.TextToSpeechSetRate.argtypes = [c_void_p, DWORD]
		lib.TextToSpeechOpenInMemory.argtypes = [c_void_p, DWORD]
		lib.TextToSpeechCloseInMemory.argtypes = [c_void_p]
		lib.TextToSpeechAddBuffer.argtypes = [c_void_p, POINTER(TTS_BUFFER_T)]
		lib.TextToSpeechReturnBuffer.argtypes = [c_void_p, POINTER(POINTER(TTS_BUFFER_T))]
		lib.TextToSpeechGetSpeakerParams.argtypes = [
			c_void_p, c_uint,
			POINTER(POINTER(SPDEFS)), POINTER(POINTER(SPDEFS)),
			POINTER(POINTER(SPDEFS)), POINTER(POINTER(SPDEFS)),
		]
		for name in (
			"TextToSpeechSpeak", "TextToSpeechSync", "TextToSpeechReset",
			"TextToSpeechSetSpeaker", "TextToSpeechSetRate",
			"TextToSpeechOpenInMemory", "TextToSpeechCloseInMemory",
			"TextToSpeechAddBuffer", "TextToSpeechReturnBuffer",
			"TextToSpeechGetSpeakerParams",
		):
			getattr(lib, name).restype = c_uint

		dic = dic_path or default_dic_path()
		if not os.path.isfile(dic):
			raise DECtalkError("dictionary not found: %s" % dic)
		rc = lib.TextToSpeechStartupExFonix(
			byref(self._handle), WAVE_MAPPER, DO_NOT_USE_AUDIO_DEVICE,
			self._callback, 0, os.fsencode(dic),
		)
		if rc != 0 or not self._handle:
			raise DECtalkError("TextToSpeechStartupExFonix failed (rc=%d)" % rc)

		self._buffers = []
		self._index_arrays = []
		self._data_arrays = []
		for _ in range(BUFFER_COUNT):
			data = ctypes.create_string_buffer(BUFFER_BYTES)
			marks = (TTS_INDEX_T * MAX_INDEX_MARKS)()
			buf = TTS_BUFFER_T()
			buf.lpData = ctypes.cast(data, c_void_p)
			buf.lpPhonemeArray = None
			buf.lpIndexArray = ctypes.cast(marks, POINTER(TTS_INDEX_T))
			buf.dwMaximumBufferLength = BUFFER_BYTES
			buf.dwMaximumNumberOfPhonemeChanges = 0
			buf.dwMaximumNumberOfIndexMarks = MAX_INDEX_MARKS
			self._data_arrays.append(data)
			self._index_arrays.append(marks)
			self._buffers.append(buf)

	def close(self):
		if self._handle:
			self._lib.TextToSpeechShutdown(self._handle)
			self._handle = c_void_p()

	# -- synthesis ---------------------------------------------------------

	def _consume(self, buf):
		"""Deliver one completed buffer's PCM and index marks together."""
		if not self._on_buffer:
			return
		if not (buf.dwBufferLength or buf.dwNumberOfIndexMarks):
			return
		pcm = ctypes.string_at(buf.lpData, buf.dwBufferLength) if buf.dwBufferLength else b""
		marks = [
			(int(buf.lpIndexArray[i].dwIndexValue), int(buf.lpIndexArray[i].dwIndexSampleNumber))
			for i in range(buf.dwNumberOfIndexMarks)
		]
		self._on_buffer(pcm, marks)

	def _dt_callback(self, param1, param2, user, msg):
		if msg != self._msg_buffer:
			return
		with self._cb_lock:
			# A callback straggling in after its speak() session ended must
			# not touch the FIFO: recycling its buffer into a new session
			# would double-queue it and desync buffer order for good.
			if not self._session_open or not self._fifo:
				return
			buf = self._fifo.popleft()
			try:
				self._consume(buf)
			finally:
				# Recycle so synthesis can keep filling.
				buf.dwBufferLength = 0
				buf.dwNumberOfIndexMarks = 0
				buf.dwNumberOfPhonemeChanges = 0
				self._fifo.append(buf)
				self._lib.TextToSpeechAddBuffer(self._handle, byref(buf))

	def speak(self, text, on_buffer, should_abort=None):
		"""Synthesize `text` (str or bytes), blocking until complete.

		on_buffer(pcm_bytes, marks) receives 16-bit mono PCM at SAMPLE_RATE
		plus the [:index mark N] marks that fall within it, as a list of
		(value, absolute_sample_number) tuples. If `should_abort` is given
		and returns True just before synthesis starts, nothing is spoken —
		this closes the stop() race where a cancel lands between buffer
		setup and TextToSpeechSpeak (Reset would strip the freshly queued
		buffers and Sync would stall waiting for them).
		"""
		if isinstance(text, str):
			text = text.encode("ascii", "replace")
		with self._speak_lock:
			self._on_buffer = on_buffer
			lib = self._lib
			rc = lib.TextToSpeechOpenInMemory(self._handle, WAVE_FORMAT_1M16)
			if rc != 0:
				self._on_buffer = None
				raise DECtalkError("TextToSpeechOpenInMemory failed (rc=%d)" % rc)
			try:
				with self._cb_lock:
					self._fifo.clear()
					for buf in self._buffers:
						buf.dwBufferLength = 0
						buf.dwNumberOfIndexMarks = 0
						buf.dwNumberOfPhonemeChanges = 0
						self._fifo.append(buf)
						lib.TextToSpeechAddBuffer(self._handle, byref(buf))
					self._session_open = True
				if should_abort and should_abort():
					return
				with self._stop_lock:
					self._speaking = True
				try:
					# TTS_NORMAL, not TTS_FORCE: FORCE hard-terminates the
					# clause, giving unpunctuated fragments sentence-final
					# prosody. The Sync() below flushes pending speech anyway.
					lib.TextToSpeechSpeak(self._handle, text, TTS_NORMAL)
					lib.TextToSpeechSync(self._handle)
				finally:
					with self._stop_lock:
						self._speaking = False
				with self._cb_lock:
					self._session_open = False
				# Drain buffers holding samples that never reached the callback.
				for _ in range(BUFFER_COUNT):
					pbuf = POINTER(TTS_BUFFER_T)()
					if lib.TextToSpeechReturnBuffer(self._handle, byref(pbuf)) != 0 or not pbuf:
						break
					with self._cb_lock:
						buf = self._match(pbuf)
						if buf is not None:
							self._consume(buf)
			finally:
				with self._cb_lock:
					self._session_open = False
				lib.TextToSpeechCloseInMemory(self._handle)
				self._on_buffer = None

	def _match(self, pbuf):
		"""Map a TTS_BUFFER_T pointer returned by the engine back to ours."""
		addr = ctypes.cast(pbuf, c_void_p).value
		for i, buf in enumerate(self._buffers):
			if ctypes.addressof(buf) == addr:
				try:
					self._fifo.remove(buf)
				except ValueError:
					pass
				return buf
		return None

	def stop(self):
		"""Flush queued speech. Safe to call from any thread.

		Reset is only issued while synthesis is actually between Speak and
		Sync; outside that window there is nothing to flush, and a Reset
		could strip buffers a concurrent speak() has just queued.
		"""
		if not self._handle:
			return
		with self._stop_lock:
			if self._speaking:
				self._lib.TextToSpeechReset(self._handle, 0)

	# -- parameters --------------------------------------------------------

	def set_speaker(self, index):
		self._lib.TextToSpeechSetSpeaker(self._handle, index)

	def set_rate(self, wpm):
		self._lib.TextToSpeechSetRate(self._handle, wpm)

	def speaker_params(self):
		"""[:dv] values of the voice the synthesis pipeline last used.

		Returns (current, lo_limit, hi_limit) dicts keyed by [:dv] code. The
		engine applies a voice change only when text flows through the
		pipeline, so speak something after set_speaker() before reading.
		"""
		cur = POINTER(SPDEFS)()
		lo = POINTER(SPDEFS)()
		hi = POINTER(SPDEFS)()
		default = POINTER(SPDEFS)()
		rc = self._lib.TextToSpeechGetSpeakerParams(
			self._handle, 0, byref(cur), byref(lo), byref(hi), byref(default),
		)
		if rc != 0 or not cur:
			raise DECtalkError("TextToSpeechGetSpeakerParams failed (rc=%d)" % rc)
		try:
			return tuple(
				{code: getattr(p.contents, "dv_" + code) for code in DV_CODES}
				for p in (cur, lo, hi)
			)
		finally:
			# GetSpeakerParams CoTaskMemAlloc's all four structs for the caller.
			free = ctypes.windll.ole32.CoTaskMemFree
			for p in (cur, lo, hi, default):
				if p:
					free(ctypes.cast(p, c_void_p))
