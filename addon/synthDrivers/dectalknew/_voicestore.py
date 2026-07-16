# _voicestore.py — persistent store for user-created DECtalk voices, and
# their .dtv exchange format.
#
# A custom voice is a complete voice definition: a base voice (one of the
# nine built-ins, giving the engine its starting point) plus a value for
# every [:dv] parameter. Custom voices never modify the built-ins — they are
# created by snapshotting the current parameters under a new name, and are
# stored in NVDA's configuration.
#
# The .dtv file format is JSON:
#   {"format": "dectalk-voice", "version": 1,
#    "name": "...", "base": "paul", "params": {"ap": 122, ...}}
# so files exported here can be imported into anyone else's copy of the
# add-on (or any other DECtalk front-end that adopts the format).

import json

import config

from . import _params

# Top-level config section for custom voices. "dectalknew" (not "dectalk")
# for the same collision-avoidance reason the synth uses that id — see
# SynthDriver in __init__.py.
CONF_SECTION = "dectalknew"
config.conf.spec[CONF_SECTION] = {
	# {"<name>": {"base": "<builtin id>", "params": {<all 28 dv codes>}}}
	"customVoices": "string(default='{}')",
}

DTV_FORMAT = "dectalk-voice"
DTV_VERSION = 1

#: Prefix of custom voice ids as they appear in the driver's voice list.
CUSTOM_PREFIX = "custom:"


class VoiceStoreError(Exception):
	pass


def _cleanParams(params):
	"""Validate and clamp a {code: value} mapping to a full parameter set."""
	if not isinstance(params, dict):
		raise VoiceStoreError("voice parameters must be an object")
	cleaned = {}
	for code, (lo, hi) in _params.VOICE_LIMITS.items():
		try:
			value = int(params[code])
		except KeyError:
			raise VoiceStoreError("missing parameter %r" % code)
		except (TypeError, ValueError):
			raise VoiceStoreError("parameter %r is not an integer" % code)
		cleaned[code] = max(lo, min(hi, value))
	return cleaned


def load():
	"""All custom voices, as {name: {"base": builtinId, "params": {...}}}."""
	try:
		data = json.loads(config.conf[CONF_SECTION]["customVoices"])
	except Exception:
		return {}
	voices = {}
	if isinstance(data, dict):
		for name, rec in data.items():
			try:
				base = rec.get("base", "paul")
				if base not in _params.VOICES:
					base = "paul"
				voices[str(name)] = {
					"base": base,
					"params": _cleanParams(rec.get("params")),
				}
			except (AttributeError, VoiceStoreError):
				continue
	return voices


def _save(voices):
	config.conf[CONF_SECTION]["customVoices"] = json.dumps(voices)


def create(name, base, params):
	"""Save a new custom voice (or overwrite one with the same name)."""
	name = (name or "").strip()
	if not name:
		raise VoiceStoreError("the voice needs a name")
	if base not in _params.VOICES:
		raise VoiceStoreError("unknown base voice %r" % base)
	voices = load()
	voices[name] = {"base": base, "params": _cleanParams(params)}
	_save(voices)
	return name


def delete(name):
	voices = load()
	if name in voices:
		del voices[name]
		_save(voices)


def exportDtv(name, path):
	"""Write custom voice `name` to `path` as a .dtv file."""
	voices = load()
	if name not in voices:
		raise VoiceStoreError("no custom voice named %r" % name)
	rec = voices[name]
	doc = {
		"format": DTV_FORMAT,
		"version": DTV_VERSION,
		"name": name,
		"base": rec["base"],
		"params": rec["params"],
	}
	with open(path, "w", encoding="utf-8") as f:
		json.dump(doc, f, indent=2, sort_keys=True)


def importDtv(path):
	"""Import a .dtv file; returns the (possibly deduplicated) voice name."""
	try:
		with open(path, "r", encoding="utf-8") as f:
			doc = json.load(f)
	except (OSError, ValueError) as e:
		raise VoiceStoreError("could not read voice file: %s" % e)
	if not isinstance(doc, dict) or doc.get("format") != DTV_FORMAT:
		raise VoiceStoreError("not a DECtalk voice (.dtv) file")
	if int(doc.get("version", 0)) > DTV_VERSION:
		raise VoiceStoreError("this voice file needs a newer version of the add-on")
	name = str(doc.get("name", "")).strip() or "Imported voice"
	base = doc.get("base", "paul")
	if base not in _params.VOICES:
		base = "paul"
	params = _cleanParams(doc.get("params"))
	voices = load()
	unique = name
	counter = 2
	while unique in voices:
		unique = "%s (%d)" % (name, counter)
		counter += 1
	voices[unique] = {"base": base, "params": params}
	_save(voices)
	return unique
