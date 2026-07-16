# _text.py — text preprocessing for the DECtalk engine.
#
# Python port of the Android project's DECtalkText.kt. Pure functions with no
# NVDA or engine dependency.

import unicodedata

# Non-ASCII characters are written as \u escapes on purpose: several are
# invisible, and tooling silently normalizes them as literals.
_PUNCT_MAP = {
	"‘": "'", "’": "'", "‚": "'", "‛": "'",  # curly single quotes
	"“": '"', "”": '"', "„": '"', "‟": '"',  # curly double quotes
	"«": '"', "»": '"',  # guillemets
	"–": "-", "―": "-", "−": "-",  # en dash, horizontal bar, minus
	"—": " - ",  # em dash
	"•": "-",  # bullet
	"·": ".",  # middle dot
	"…": "...",  # ellipsis
	" ": " ", " ": " ", " ": " ", " ": " ",  # no-break/thin spaces
	"﻿": "",  # BOM / zero-width no-break
}
_PUNCT_TABLE = str.maketrans(_PUNCT_MAP)


def engine_ascii(text):
	"""Fold `text` to the ASCII the engine understands.

	The DECtalk engine is ASCII/Latin-1 era: raw multi-byte UTF-8 (curly
	quotes, em-dashes, accented letters, ...) is spoken byte-by-byte as symbol
	names ("circumflex"). Map common smart punctuation to ASCII, strip
	diacritics, and drop anything else non-ASCII.
	"""
	text = text.translate(_PUNCT_TABLE)
	folded = unicodedata.normalize("NFKD", text)
	# Drop combining diacritics (U+0300..U+036F) entirely; replace any other
	# remaining non-ASCII with a space.
	return "".join(
		ch if ord(ch) < 128 else ("" if 0x0300 <= ord(ch) <= 0x036F else " ")
		for ch in folded
	)


def split_multi_case(text):
	"""Split mixed-case words so DECtalk pronounces the parts instead of
	guessing at the whole: "iOS" -> "i OS", "DECTalk" -> "DEC Talk".

	A space is inserted at a lower->UPPER boundary, and inside an uppercase
	run before the letter that starts a lowercased word. Text inside square
	brackets (inline DECtalk commands, phonemic input) is left untouched.
	"""
	out = []
	bracket_depth = 0
	for i, c in enumerate(text):
		if c == "[":
			bracket_depth += 1
		elif c == "]" and bracket_depth > 0:
			bracket_depth -= 1
		if i > 0 and bracket_depth == 0:
			prev = text[i - 1]
			boundary = (prev.islower() and c.isupper()) or (
				prev.isupper()
				and c.isupper()
				and i + 1 < len(text)
				and text[i + 1].islower()
			)
			if boundary:
				out.append(" ")
		out.append(c)
	return "".join(out)
