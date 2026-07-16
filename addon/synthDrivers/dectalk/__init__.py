# DECtalk synthesizer driver for NVDA.
#
# The NVDA sibling of the DECtalk Apple/Android projects: drives the classic
# DECtalk formant engine (built from dectalk/dectalk as a native x64/x86
# DECtalk.dll) through its in-memory TTS API, and exposes the same parameter
# surface as the mobile apps — global rate/volume/SPF/pauses plus all 28
# per-voice [:dv] parameters, persisted per voice.
#
# Architecture: speak() converts NVDA's speech sequence into DECtalk inline
# command text with [:index mark N] marks and queues it for a worker thread.
# The worker runs the blocking in-memory synthesis; PCM buffers are fed to an
# nvwave.WavePlayer whose backpressure paces the engine, and index marks are
# attached to the PCM slice they fall in via feed(onDone=...).

import ctypes
import json
import queue
import threading
from collections import OrderedDict
from functools import partial

import config
import nvwave
from autoSettingsUtils.driverSetting import BooleanDriverSetting, NumericDriverSetting
from logHandler import log
from speech.commands import (
	BreakCommand,
	CharacterModeCommand,
	IndexCommand,
	LangChangeCommand,
	PitchCommand,
	RateCommand,
	VolumeCommand,
)
from synthDriverHandler import SynthDriver as BaseSynthDriver
from synthDriverHandler import VoiceInfo, synthDoneSpeaking, synthIndexReached

try:
	# NVDA's bundled Sonic time-stretcher (synthDrivers/_sonic.py, NVDA
	# 2025.1+), used for rate boost. Older NVDA versions get the add-on's
	# own bundled sonic.dll via _sonic_fallback (same library, same API);
	# if even that fails to load, boost falls back to doubling the engine
	# rate.
	from synthDrivers import _sonic
except ImportError:
	try:
		from . import _sonic_fallback as _sonic
	except Exception:
		_sonic = None

from . import _dectalk, _params, _text

_CONF_SECTION = "dectalk"
config.conf.spec[_CONF_SECTION] = {
	# JSON: {"<voiceId>": {"<dvCode>": value, ...}, ...} — only values that
	# differ from the voice's built-in defaults are stored ("auto" otherwise).
	"voiceParams": "string(default='{}')",
}


def _clamp(value, lo, hi):
	return max(lo, min(hi, value))


class SynthDriver(BaseSynthDriver):
	name = "dectalk"
	description = "DECtalk"

	supportedSettings = (
		BaseSynthDriver.VoiceSetting(),
		BaseSynthDriver.RateSetting(),
	) + (
		# Not present on older NVDA versions.
		(BaseSynthDriver.RateBoostSetting(),)
		if hasattr(BaseSynthDriver, "RateBoostSetting")
		else ()
	) + (
		NumericDriverSetting(
			# Sonic time-stretch factor applied on top of the DECtalk rate
			# while rate boost is on — independent of the rate slider, so
			# any engine rate can be boosted.
			"rateBoostMultiplier", "Rate boost multiplier (%)", defaultVal=200,
			minVal=100, maxVal=600, normalStep=25,
			availableInSettingsRing=True,
		),
		BaseSynthDriver.PitchSetting(),
		BaseSynthDriver.InflectionSetting(),
		BaseSynthDriver.VolumeSetting(),
		NumericDriverSetting(
			# SPF scales output duration linearly (100 = normal, lower =
			# faster); near 0 speech collapses to a blip with no spoken way
			# to recover, so the slider floors at 10. Inline [:spf] and a
			# hand-edited config can still go lower.
			"spf", "SPF (duration scale, 100 = normal)", defaultVal=100,
			minVal=10, maxVal=_params.SPF_RANGE[1],
			availableInSettingsRing=True,
		),
		NumericDriverSetting(
			"sentencePause", "Sentence pause (ms)", defaultVal=0,
			minVal=_params.SENTENCE_PAUSE_RANGE[0], maxVal=_params.SENTENCE_PAUSE_RANGE[1],
		),
		NumericDriverSetting(
			"commaPause", "Comma pause (ms)", defaultVal=0,
			minVal=_params.COMMA_PAUSE_RANGE[0], maxVal=_params.COMMA_PAUSE_RANGE[1],
		),
		BooleanDriverSetting(
			"splitMultiCase", "Split mixed-case words (DECTalk -> DEC Talk)",
			defaultVal=True,
		),
		BooleanDriverSetting(
			"inlineCommands", "Allow inline DECtalk commands in spoken text",
			defaultVal=True,
		),
	) + tuple(
		NumericDriverSetting(
			"dv_" + code, label,
			defaultVal=_params.VOICE_DEFAULTS["paul"][code],
			minVal=_params.VOICE_LIMITS[code][0],
			maxVal=_params.VOICE_LIMITS[code][1],
			availableInSettingsRing=False,
		)
		for code, label, _category in _params.VOICE_PARAMS
	)

	supportedCommands = {
		IndexCommand,
		CharacterModeCommand,
		LangChangeCommand,
		BreakCommand,
		PitchCommand,
		RateCommand,
		VolumeCommand,
	}
	supportedNotifications = {synthIndexReached, synthDoneSpeaking}

	@classmethod
	def check(cls):
		import os
		return os.path.isfile(_dectalk.default_lib_path()) and os.path.isfile(
			_dectalk.default_dic_path()
		)

	def __init__(self):
		self._engine = _dectalk.Engine()
		self._player = self._createPlayer()

		self._sonicStream = None
		if _sonic is not None:
			try:
				_sonic.initialize()
				self._sonicStream = _sonic.SonicStream(_dectalk.SAMPLE_RATE, 1)
			except Exception:
				log.exception("DECtalk: Sonic unavailable; rate boost falls back to engine rate")
		self._sonicActive = False  # stream in use for the current utterance

		self._voice = "paul"
		self._ratePct = 50  # NVDA 0..100 -> 75..300 wpm
		self._rateBoost = False
		self._rateBoostMultiplier = 200  # % Sonic stretch while boost is on
		self._pitch = 50  # NVDA 0..100; 50 = the voice's own pitch
		self._inflection = 50  # NVDA 0..100; 50 = the voice's own pitch range
		self._volume = 72  # [:vo set], 0..99
		self._spf = 100
		self._sentencePause = 0
		self._commaPause = 0
		self._splitMultiCase = True
		self._inlineCommands = True
		self._voiceParams = self._loadVoiceParams()

		self._queue = queue.Queue()
		self._generation = 0
		self._genLock = threading.Lock()
		self._thread = threading.Thread(
			target=self._workerLoop, name="DECtalkSynth", daemon=True
		)
		self._thread.start()

	def terminate(self):
		self.cancel()
		self._queue.put(None)
		self._thread.join(timeout=5)
		self._player.close()
		self._engine.close()

	def _createPlayer(self):
		try:
			device = config.conf["audio"]["outputDevice"]  # NVDA 2025.1+
		except KeyError:
			device = config.conf["speech"]["outputDevice"]
		return nvwave.WavePlayer(
			channels=1,
			samplesPerSec=_dectalk.SAMPLE_RATE,
			bitsPerSample=16,
			outputDevice=device,
		)

	# -- speech ------------------------------------------------------------

	def speak(self, speechSequence):
		ops = self._buildOps(speechSequence)
		self._queue.put((self._generation, ops))

	def cancel(self):
		with self._genLock:
			self._generation += 1
		try:
			while True:
				self._queue.get_nowait()
		except queue.Empty:
			pass
		self._player.stop()
		self._engine.stop()

	def pause(self, switch):
		self._player.pause(switch)

	def _buildOps(self, speechSequence):
		"""Convert a speech sequence to worker ops:
		("text", str) — synthesize; ("silence", ms) — insert real silence.
		"""
		ops = []
		parts = [self._commandPrefix()]
		hasContent = False
		sayLetter = False
		pitchMul = 1.0
		rateMul = 1.0
		volumeMul = 1.0

		def flush():
			nonlocal parts, hasContent
			if hasContent:
				if sayLetter:
					# End in clause mode: TTS_FORCE appends a control char
					# (0x0B) to flush the clause, and in letter mode the
					# engine announces it as "vertical tab".
					parts.append("[:say clause]")
				ops.append(("text", "".join(parts)))
			parts = [self._commandPrefix(rateMul, pitchMul, volumeMul)]
			if sayLetter:
				parts.append("[:say letter]")
			hasContent = False

		for item in speechSequence:
			if isinstance(item, str):
				text = _text.engine_ascii(item)
				if self._splitMultiCase:
					text = _text.split_multi_case(text)
				if not self._inlineCommands:
					text = text.replace("[", " ").replace("]", " ")
				if text.strip():
					parts.append(text)
					hasContent = True
				else:
					parts.append(" ")
			elif isinstance(item, IndexCommand):
				parts.append("[:index mark %d]" % item.index)
				hasContent = True
			elif isinstance(item, CharacterModeCommand):
				sayLetter = item.state
				parts.append("[:say letter]" if item.state else "[:say clause]")
			elif isinstance(item, BreakCommand):
				flush()
				ops.append(("silence", item.time))
			elif isinstance(item, PitchCommand):
				pitchMul = item.multiplier
				parts.append("[:dv ap %d]" % self._effectiveAp(pitchMul))
			elif isinstance(item, RateCommand):
				rateMul = item.multiplier
				parts.append("[:rate %d]" % self._effectiveRate(rateMul))
			elif isinstance(item, VolumeCommand):
				volumeMul = item.multiplier
				parts.append("[:vo set %d]" % self._effectiveVolume(volumeMul))
			elif isinstance(item, LangChangeCommand):
				pass  # US English only
		flush()
		return ops

	#: Words-per-minute span of the rate slider: the engine's full [:rate]
	#: range. The rate slider always drives the engine's [:rate]; rate boost
	#: is an independent Sonic time-stretch on top (rateBoostMultiplier %),
	#: so any engine rate can be boosted.
	_RATE_WPM = _params.RATE_RANGE

	def _sonicBoostActive(self):
		return (
			self._rateBoost
			and self._sonicStream is not None
			and self._rateBoostMultiplier != 100
		)

	def _sonicSpeed(self):
		return self._rateBoostMultiplier / 100.0 if self._sonicBoostActive() else 1.0

	def _currentWpm(self):
		lo, hi = self._RATE_WPM
		wpm = lo + self._ratePct * (hi - lo) / 100.0
		if self._rateBoost and self._sonicStream is None:
			# No Sonic on this NVDA version: boost doubles the engine rate.
			wpm *= 2
		return _clamp(int(round(wpm)), *_params.RATE_RANGE)

	def _effectiveRate(self, mul=1.0):
		return _clamp(int(self._currentWpm() * mul), *_params.RATE_RANGE)

	def _effectiveVolume(self, mul=1.0):
		return _clamp(int(self._volume * mul), *_params.VOLUME_RANGE)

	def _effectiveAp(self, pitchCommandMul=1.0):
		"""Average pitch: the voice's (possibly overridden) ap scaled by the
		NVDA pitch slider (50 = unchanged, exponential 0.5x..2x) and any
		inline PitchCommand multiplier (capital pitch change etc.)."""
		base = self._currentParams()["ap"]
		factor = 2.0 ** ((self._pitch - 50) / 50.0) * pitchCommandMul
		return _clamp(int(round(base * factor)), *_params.VOICE_LIMITS["ap"])

	def _effectivePr(self):
		"""Pitch range scaled by the NVDA inflection slider (50 = unchanged)."""
		base = self._currentParams()["pr"]
		return _clamp(
			int(round(base * self._inflection / 50.0)), *_params.VOICE_LIMITS["pr"]
		)

	def _commandPrefix(self, rateMul=1.0, pitchMul=1.0, volumeMul=1.0):
		"""The inline command prefix applying every current setting, mirroring
		DECtalkSettings.commandPrefix in the Android app."""
		letter = _params.VOICES[self._voice][0]
		sb = [
			"[:n%s]" % letter,
			# Character mode is engine state that outlives an utterance;
			# reset it every time (flush() re-enters letter mode as needed).
			"[:say clause]",
			"[:rate %d]" % self._effectiveRate(rateMul),
			"[:vo set %d]" % self._effectiveVolume(volumeMul),
			"[:spf %d]" % self._spf,
			"[:pp %d :cp %d]" % (self._sentencePause, self._commaPause),
		]
		# Emit only parameters that differ from the voice's built-ins, in
		# catalog order — plus ap/pr whenever the NVDA pitch/inflection
		# sliders are off-center.
		defaults = _params.VOICE_DEFAULTS[self._voice]
		params = self._currentParams()
		dv = OrderedDict(
			(code, params[code])
			for code, _label, _cat in _params.VOICE_PARAMS
			if params[code] != defaults[code]
		)
		ap = self._effectiveAp(pitchMul)
		if ap != defaults["ap"]:
			dv["ap"] = ap
		elif "ap" in dv:
			dv["ap"] = ap
		pr = self._effectivePr()
		if pr != defaults["pr"]:
			dv["pr"] = pr
		elif "pr" in dv:
			dv["pr"] = pr
		if dv:
			sb.append("[:dv %s]" % " ".join("%s %d" % kv for kv in dv.items()))
		return "".join(sb)

	# -- worker thread -------------------------------------------------------

	def _workerLoop(self):
		while True:
			item = self._queue.get()
			if item is None:
				break
			generation, ops = item
			if generation != self._generation:
				continue
			try:
				self._processUtterance(generation, ops)
			except Exception:
				log.exception("DECtalk: error processing utterance")

	def _processUtterance(self, generation, ops):
		self._sonicActive = self._sonicBoostActive()
		if self._sonicActive:
			# Drop anything a cancelled utterance left in the stream. A
			# cancel can leave audio in BOTH of Sonic's queues: processed
			# output nobody read, and written-but-unprocessed input that
			# would otherwise surface at this utterance's first flush.
			# Flush the stragglers through, then discard everything.
			self._sonicStream.flush()
			self._drainSonic(discard=True)
			self._sonicStream.speed = self._sonicSpeed()
		speed = self._sonicSpeed() if self._sonicActive else 1.0
		for kind, payload in ops:
			if generation != self._generation:
				return
			if kind == "text":
				state = {"fed": 0}
				self._engine.speak(
					payload,
					on_buffer=partial(self._onBuffer, generation, state),
					should_abort=lambda: generation != self._generation,
				)
				if self._sonicActive and generation == self._generation:
					self._flushSonic(generation)
			elif kind == "silence":
				frames = int(_dectalk.SAMPLE_RATE * payload / 1000.0 / speed)
				if frames > 0 and generation == self._generation:
					self._player.feed(b"\x00\x00" * frames)
		if generation != self._generation:
			return
		self._player.idle()
		if generation == self._generation:
			synthDoneSpeaking.notify(synth=self)

	# -- Sonic time-stretch (rate boost) --------------------------------------

	def _drainSonic(self, discard=False, onDone=None):
		"""Feed the player everything Sonic has processed so far."""
		stream = self._sonicStream
		if stream.samplesAvailable > 0:
			data = stream.readShort()
			if not discard:
				self._player.feed(
					ctypes.string_at(data, len(data) * 2), onDone=onDone
				)
				return
		if onDone is not None:
			onDone()

	def _flushSonic(self, generation, onDone=None):
		self._sonicStream.flush()
		self._drainSonic(discard=generation != self._generation, onDone=onDone)

	def _feed(self, generation, pcm, onDone=None):
		"""Feed PCM to the player, through Sonic when rate boost is active."""
		if not self._sonicActive:
			if pcm:
				self._player.feed(pcm, onDone=onDone)
			elif onDone is not None:
				onDone()
			return
		stream = self._sonicStream
		if pcm:
			n = len(pcm) // 2
			buf = (ctypes.c_short * n).from_buffer_copy(pcm)
			stream.writeShort(ctypes.cast(buf, ctypes.POINTER(ctypes.c_short)), n)
		if onDone is not None:
			# Tighten index timing: flush so the mark rides the audio that
			# precedes it (marks fall at clause boundaries, where the flush
			# distortion Sonic warns about is inaudible).
			self._flushSonic(generation, onDone=onDone)
		else:
			self._drainSonic()

	def _onBuffer(self, generation, state, pcm, marks):
		"""Feed one engine buffer to the player, splitting it at index marks
		so each mark's notification fires when its audio finishes playing."""
		if generation != self._generation:
			return
		start = state["fed"]
		pos = 0
		for value, sample in marks:
			off = _clamp((sample - start) * 2, 0, len(pcm)) & ~1
			if off > pos:
				self._feed(
					generation, pcm[pos:off],
					onDone=partial(self._notifyIndex, generation, value),
				)
				pos = off
			else:
				# The mark's audio was already fed (mark at the buffer edge).
				self._notifyIndex(generation, value)
		if pos < len(pcm):
			self._feed(generation, pcm[pos:])
		state["fed"] = start + len(pcm) // 2

	def _notifyIndex(self, generation, value):
		if generation == self._generation:
			synthIndexReached.notify(synth=self, index=value)

	# -- voices & settings ---------------------------------------------------

	def _getAvailableVoices(self):
		return OrderedDict(
			(vid, VoiceInfo(vid, displayName, "en"))
			for vid, (_letter, displayName) in _params.VOICES.items()
		)

	def _get_voice(self):
		return self._voice

	def _set_voice(self, value):
		if value not in _params.VOICES:
			value = "paul"
		self._voice = value

	def _get_rate(self):
		return self._ratePct

	def _set_rate(self, value):
		self._ratePct = _clamp(value, 0, 100)

	def _get_rateBoost(self):
		return self._rateBoost

	def _set_rateBoost(self, value):
		self._rateBoost = bool(value)

	def _get_rateBoostMultiplier(self):
		return self._rateBoostMultiplier

	def _set_rateBoostMultiplier(self, value):
		self._rateBoostMultiplier = _clamp(value, 100, 600)

	def _get_pitch(self):
		return self._pitch

	def _set_pitch(self, value):
		self._pitch = _clamp(value, 0, 100)

	def _get_inflection(self):
		return self._inflection

	def _set_inflection(self, value):
		self._inflection = _clamp(value, 0, 100)

	def _get_volume(self):
		return int(round(self._volume * 100.0 / _params.VOLUME_RANGE[1]))

	def _set_volume(self, value):
		self._volume = _clamp(
			int(round(value * _params.VOLUME_RANGE[1] / 100.0)), *_params.VOLUME_RANGE
		)

	def _get_spf(self):
		return self._spf

	def _set_spf(self, value):
		self._spf = _clamp(value, *_params.SPF_RANGE)

	def _get_sentencePause(self):
		return self._sentencePause

	def _set_sentencePause(self, value):
		self._sentencePause = _clamp(value, *_params.SENTENCE_PAUSE_RANGE)

	def _get_commaPause(self):
		return self._commaPause

	def _set_commaPause(self, value):
		self._commaPause = _clamp(value, *_params.COMMA_PAUSE_RANGE)

	def _get_splitMultiCase(self):
		return self._splitMultiCase

	def _set_splitMultiCase(self, value):
		self._splitMultiCase = bool(value)

	def _get_inlineCommands(self):
		return self._inlineCommands

	def _set_inlineCommands(self, value):
		self._inlineCommands = bool(value)

	# -- per-voice [:dv] parameters -------------------------------------------

	def _loadVoiceParams(self):
		try:
			data = json.loads(config.conf[_CONF_SECTION]["voiceParams"])
			return {
				voice: {
					code: int(val)
					for code, val in params.items()
					if code in _params.VOICE_LIMITS
				}
				for voice, params in data.items()
				if voice in _params.VOICES
			}
		except Exception:
			log.exception("DECtalk: could not parse saved voice parameters")
			return {}

	def _saveVoiceParams(self):
		config.conf[_CONF_SECTION]["voiceParams"] = json.dumps(
			{v: p for v, p in self._voiceParams.items() if p}
		)

	def _currentParams(self):
		"""The current voice's effective [:dv] values (built-ins + overrides)."""
		merged = dict(_params.VOICE_DEFAULTS[self._voice])
		merged.update(self._voiceParams.get(self._voice, {}))
		return merged

	def _getDvParam(self, code):
		return self._currentParams()[code]

	def _setDvParam(self, code, value):
		value = _clamp(int(value), *_params.VOICE_LIMITS[code])
		overrides = self._voiceParams.setdefault(self._voice, {})
		if value == _params.VOICE_DEFAULTS[self._voice][code]:
			overrides.pop(code, None)  # back to "auto"
		else:
			overrides[code] = value
		self._saveVoiceParams()

	# Generate _get_dv_xx/_set_dv_xx accessors for every [:dv] parameter.
	# These must be created in the class body: AutoPropertyObject's metaclass
	# turns _get_*/_set_* into properties at class creation time only.
	_ns = locals()
	for _code, _label, _cat in _params.VOICE_PARAMS:
		_ns["_get_dv_" + _code] = (lambda code: lambda self: self._getDvParam(code))(_code)
		_ns["_set_dv_" + _code] = (
			lambda code: lambda self, value: self._setDvParam(code, value)
		)(_code)
	del _ns, _code, _label, _cat
