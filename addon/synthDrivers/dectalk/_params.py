# _params.py — DECtalk parameter catalog for the NVDA driver.
#
# The same parameter surface the DECtalk Apple/Android apps expose: the global
# engine parameters plus every per-voice [:dv] parameter. Voice defaults and
# limits were extracted from the engine itself (TextToSpeechGetSpeakerParams,
# scripts in the repo history), so sliders start at each voice's true built-in
# value and cover the engine's real accepted range.

from collections import OrderedDict

#: (code, display name, category) for every [:dv] parameter, in the order the
#: sibling apps present them. Categories group the sliders in the docs.
VOICE_PARAMS = (
	# Pitch & intonation
	("ap", "Average pitch (Hz)", "Pitch & Intonation"),
	("pr", "Pitch range (%)", "Pitch & Intonation"),
	("as", "Assertiveness (%)", "Pitch & Intonation"),
	("bf", "Baseline fall (Hz)", "Pitch & Intonation"),
	("hr", "Hat rise (Hz)", "Pitch & Intonation"),
	("sr", "Stress rise (Hz)", "Pitch & Intonation"),
	# Voice quality
	("hs", "Head size (%)", "Voice Quality"),
	("sm", "Smoothness (%)", "Voice Quality"),
	("ri", "Richness (%)", "Voice Quality"),
	("br", "Breathiness (dB)", "Voice Quality"),
	("la", "Laryngealization (%)", "Voice Quality"),
	("lx", "Lax breathiness (%)", "Voice Quality"),
	("qu", "Quickness (%)", "Voice Quality"),
	("nf", "Fixed open-glottis samples", "Voice Quality"),
	("ft", "Spectral tilt (%)", "Voice Quality"),
	("sx", "Sex (0=female, 1=male)", "Voice Quality"),
	# Formants
	("f4", "Formant 4 frequency (Hz)", "Formants"),
	("b4", "Formant 4 bandwidth (Hz)", "Formants"),
	("f5", "Formant 5 frequency (Hz)", "Formants"),
	("b5", "Formant 5 bandwidth (Hz)", "Formants"),
	# Source gains
	("gv", "Gain: voicing (dB)", "Source Gains"),
	("gh", "Gain: aspiration (dB)", "Source Gains"),
	("gf", "Gain: frication (dB)", "Source Gains"),
	("gn", "Gain: nasalization (dB)", "Source Gains"),
	("g1", "Gain: cascade formant 1 (dB)", "Source Gains"),
	("g2", "Gain: cascade formant 2 (dB)", "Source Gains"),
	("g3", "Gain: cascade formant 3 (dB)", "Source Gains"),
	("g4", "Gain: cascade formant 4 (dB)", "Source Gains"),
)

#: Engine-reported lo/hi limits for each [:dv] parameter.
VOICE_LIMITS = {
	"sx": (0, 1), "sm": (0, 100), "as": (0, 200), "ap": (50, 350),
	"pr": (0, 250), "br": (0, 72), "ri": (0, 100), "nf": (0, 100),
	"la": (0, 100), "hs": (65, 145), "f4": (2000, 6000), "b4": (100, 6000),
	"f5": (2500, 6000), "b5": (100, 6000), "gf": (0, 87), "gh": (0, 87),
	"gv": (0, 87), "gn": (0, 87), "g1": (0, 87), "g2": (0, 87),
	"g3": (0, 87), "g4": (0, 87), "ft": (0, 100), "bf": (0, 90),
	"lx": (0, 100), "qu": (0, 100), "hr": (2, 100), "sr": (1, 100),
}

#: Voice id -> ([:name] letter, display name).
VOICES = OrderedDict((
	("paul", ("p", "Perfect Paul")),
	("betty", ("b", "Beautiful Betty")),
	("harry", ("h", "Huge Harry")),
	("frank", ("f", "Frail Frank")),
	("dennis", ("d", "Doctor Dennis")),
	("kit", ("k", "Kit the Kid")),
	("ursula", ("u", "Uppity Ursula")),
	("rita", ("r", "Rough Rita")),
	("wendy", ("w", "Whispering Wendy")),
))

#: Each voice's built-in [:dv] values, read back from the engine.
VOICE_DEFAULTS = {
	"paul": {
		"sx": 1, "sm": 3, "as": 100, "ap": 122, "pr": 100, "br": 0, "ri": 70,
		"nf": 0, "la": 0, "hs": 100, "f4": 3300, "b4": 260, "f5": 3650,
		"b5": 330, "gf": 70, "gh": 70, "gv": 65, "gn": 74, "g1": 68, "g2": 60,
		"g3": 48, "g4": 64, "ft": 75, "bf": 18, "lx": 0, "qu": 40, "hr": 18,
		"sr": 32,
	},
	"betty": {
		"sx": 0, "sm": 4, "as": 35, "ap": 208, "pr": 240, "br": 0, "ri": 40,
		"nf": 0, "la": 0, "hs": 100, "f4": 4450, "b4": 260, "f5": 6000,
		"b5": 6000, "gf": 72, "gh": 70, "gv": 65, "gn": 72, "g1": 69, "g2": 65,
		"g3": 50, "g4": 56, "ft": 75, "bf": 0, "lx": 80, "qu": 55, "hr": 14,
		"sr": 20,
	},
	"harry": {
		"sx": 1, "sm": 12, "as": 100, "ap": 89, "pr": 80, "br": 0, "ri": 86,
		"nf": 10, "la": 0, "hs": 115, "f4": 3300, "b4": 200, "f5": 3850,
		"b5": 240, "gf": 70, "gh": 70, "gv": 65, "gn": 73, "g1": 71, "g2": 60,
		"g3": 52, "g4": 62, "ft": 60, "bf": 9, "lx": 0, "qu": 10, "hr": 20,
		"sr": 30,
	},
	"frank": {
		"sx": 1, "sm": 46, "as": 65, "ap": 155, "pr": 90, "br": 50, "ri": 40,
		"nf": 0, "la": 5, "hs": 90, "f4": 3650, "b4": 280, "f5": 4200,
		"b5": 300, "gf": 68, "gh": 68, "gv": 63, "gn": 75, "g1": 63, "g2": 58,
		"g3": 56, "g4": 66, "ft": 100, "bf": 9, "lx": 50, "qu": 0, "hr": 20,
		"sr": 22,
	},
	"dennis": {
		"sx": 1, "sm": 100, "as": 100, "ap": 110, "pr": 135, "br": 38, "ri": 0,
		"nf": 10, "la": 0, "hs": 105, "f4": 3200, "b4": 240, "f5": 3600,
		"b5": 280, "gf": 68, "gh": 68, "gv": 63, "gn": 76, "g1": 75, "g2": 60,
		"g3": 52, "g4": 61, "ft": 100, "bf": 9, "lx": 70, "qu": 50, "hr": 20,
		"sr": 22,
	},
	"kit": {
		"sx": 0, "sm": 5, "as": 65, "ap": 306, "pr": 210, "br": 47, "ri": 40,
		"nf": 0, "la": 0, "hs": 80, "f4": 6000, "b4": 6000, "f5": 6000,
		"b5": 6000, "gf": 72, "gh": 70, "gv": 65, "gn": 71, "g1": 69, "g2": 69,
		"g3": 52, "g4": 50, "ft": 75, "bf": 0, "lx": 75, "qu": 50, "hr": 20,
		"sr": 22,
	},
	"ursula": {
		"sx": 0, "sm": 60, "as": 100, "ap": 240, "pr": 135, "br": 0, "ri": 100,
		"nf": 10, "la": 0, "hs": 95, "f4": 4450, "b4": 260, "f5": 6000,
		"b5": 6000, "gf": 70, "gh": 70, "gv": 65, "gn": 74, "g1": 67, "g2": 65,
		"g3": 51, "g4": 58, "ft": 100, "bf": 8, "lx": 50, "qu": 30, "hr": 20,
		"sr": 32,
	},
	"rita": {
		"sx": 0, "sm": 24, "as": 65, "ap": 106, "pr": 80, "br": 46, "ri": 20,
		"nf": 0, "la": 4, "hs": 95, "f4": 4000, "b4": 250, "f5": 6000,
		"b5": 6000, "gf": 72, "gh": 70, "gv": 65, "gn": 73, "g1": 69, "g2": 72,
		"g3": 48, "g4": 54, "ft": 0, "bf": 0, "lx": 0, "qu": 30, "hr": 20,
		"sr": 32,
	},
	"wendy": {
		"sx": 0, "sm": 100, "as": 50, "ap": 200, "pr": 175, "br": 55, "ri": 0,
		"nf": 10, "la": 0, "hs": 100, "f4": 4500, "b4": 400, "f5": 6000,
		"b5": 6000, "gf": 70, "gh": 68, "gv": 51, "gn": 75, "g1": 69, "g2": 62,
		"g3": 53, "g4": 55, "ft": 100, "bf": 0, "lx": 80, "qu": 10, "hr": 20,
		"sr": 22,
	},
}

# Global (voice-independent) parameter ranges, matching the sibling apps.
RATE_RANGE = (75, 600)  # words per minute; [:rate N]
VOLUME_RANGE = (0, 99)  # [:vo set N]
SPF_RANGE = (0, 100)  # [:spf N]
SENTENCE_PAUSE_RANGE = (-380, 2000)  # ms added to the period pause; [:pp N]
COMMA_PAUSE_RANGE = (-40, 2000)  # ms added to the comma pause; [:cp N]
