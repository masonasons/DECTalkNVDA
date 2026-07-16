# _sonic_fallback.py — minimal SonicStream over the bundled sonic.dll.
#
# NVDA 2025.1+ ships synthDrivers/_sonic.py + sonic.dll for rate boost; on
# older NVDA versions this module provides the same (subset of the) API over
# our own bundled copy of the Sonic library (third_party/sonic, Apache-2.0,
# built by scripts/build.bat into lib/<arch>/sonic.dll).

import ctypes
import os
from ctypes import POINTER, c_float, c_int, c_short, c_void_p

_dll = None


def _lib_dir():
	arch = "x64" if ctypes.sizeof(c_void_p) == 8 else "x86"
	return os.path.join(os.path.dirname(__file__), "lib", arch)


def initialize():
	"""Load the bundled sonic.dll. Raises OSError if it is missing."""
	global _dll
	if _dll is not None:
		return
	dll = ctypes.CDLL(os.path.join(_lib_dir(), "sonic.dll"))
	dll.sonicCreateStream.restype = c_void_p
	dll.sonicCreateStream.argtypes = [c_int, c_int]
	dll.sonicDestroyStream.argtypes = [c_void_p]
	dll.sonicWriteShortToStream.restype = c_int
	dll.sonicWriteShortToStream.argtypes = [c_void_p, POINTER(c_short), c_int]
	dll.sonicReadShortFromStream.restype = c_int
	dll.sonicReadShortFromStream.argtypes = [c_void_p, POINTER(c_short), c_int]
	dll.sonicFlushStream.restype = c_int
	dll.sonicFlushStream.argtypes = [c_void_p]
	dll.sonicSamplesAvailable.restype = c_int
	dll.sonicSamplesAvailable.argtypes = [c_void_p]
	dll.sonicGetSpeed.restype = c_float
	dll.sonicGetSpeed.argtypes = [c_void_p]
	dll.sonicSetSpeed.argtypes = [c_void_p, c_float]
	dll.sonicGetNumChannels.restype = c_int
	dll.sonicGetNumChannels.argtypes = [c_void_p]
	_dll = dll


class SonicStream:
	"""API-compatible with NVDA's synthDrivers._sonic.SonicStream (the subset
	the DECtalk driver uses: writeShort/readShort/flush/samplesAvailable and
	the speed property)."""

	def __init__(self, sampleRate, channels):
		if _dll is None:
			initialize()
		self._stream = _dll.sonicCreateStream(sampleRate, channels)
		if not self._stream:
			raise MemoryError("sonicCreateStream failed")
		self._channels = channels

	def __del__(self):
		if getattr(self, "_stream", None):
			_dll.sonicDestroyStream(self._stream)
			self._stream = None

	def writeShort(self, data, numSamples):
		if not _dll.sonicWriteShortToStream(self._stream, data, numSamples):
			raise MemoryError("sonicWriteShortToStream failed")

	def readShort(self):
		n = self.samplesAvailable
		buf = (c_short * (n * self._channels))()
		got = _dll.sonicReadShortFromStream(
			self._stream, ctypes.cast(buf, POINTER(c_short)), n
		)
		return (c_short * (got * self._channels)).from_buffer(buf)

	def flush(self):
		if not _dll.sonicFlushStream(self._stream):
			raise MemoryError("sonicFlushStream failed")

	@property
	def samplesAvailable(self):
		return _dll.sonicSamplesAvailable(self._stream)

	@property
	def speed(self):
		return _dll.sonicGetSpeed(self._stream)

	@speed.setter
	def speed(self, value):
		_dll.sonicSetSpeed(self._stream, value)
