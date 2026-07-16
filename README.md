# DECtalk for NVDA

The classic **DECtalk** formant speech synthesizer — Dennis Klatt's Perfect
Paul, Beautiful Betty, and friends — as a **speech synthesizer add-on for
NVDA**, with full control over every voice parameter.

The Windows sibling of [DECtalk for Apple](../DECTalkApple) and
[DECtalk for Android](../DECTalkAndroid): the same
[`dectalk/dectalk`](https://github.com/dectalk/dectalk) C engine, here built
with its native VS2022 projects as a **64-bit `DECtalk.dll`** (matching NVDA
2026.1+'s move to x64; a 32-bit DLL is bundled too, so older 32-bit NVDA
releases work as well).

## Architecture

```
DECtalk.dll (x64 + x86)      upstream "DECtalk API" project, MSBuilt natively
        ▲                    in-memory TTS API (no audio device)
_dectalk.py                  ctypes wrapper: text → PCM + index marks
        ▲                    (FIFO buffer tracking; Win64-safe callbacks)
synthDrivers/dectalk         NVDA SynthDriver: 9 voices, index marks for
                             cursor tracking, all parameters, per-voice
```

| Layer | Path |
|-------|------|
| Engine build (MSBuild, x64 + x86) | `scripts/build.bat` |
| ctypes engine wrapper | `addon/synthDrivers/dectalk/_dectalk.py` |
| NVDA synth driver | `addon/synthDrivers/dectalk/__init__.py` |
| Parameter catalog + engine-verified voice defaults | `addon/synthDrivers/dectalk/_params.py` |
| Text preprocessing (ASCII folding, multi-case split) | `addon/synthDrivers/dectalk/_text.py` |
| Add-on manifest | `addon/manifest.ini` |
| Packaging | `scripts/package.py` |
| Dependency bootstrap | `scripts/bootstrap.bat` |

The DECtalk engine sources, the compiled `DECtalk.dll`, and the `.dic`
dictionary are **not** committed (proprietary + large). `bootstrap.bat` fetches
the sources; `build.bat` builds the rest.

## Getting started

```bat
git clone https://github.com/masonasons/DECTalkNVDA.git && cd DECTalkNVDA
scripts\bootstrap.bat         :: clones the engine sources
scripts\build.bat             :: builds DECtalk.dll (x64 + x86) + dtalk_us.dic
                              :: (needs VS2022 Build Tools with the C++ workload)
python scripts\package.py     :: writes dist\DECtalk-vX.Y.Z.nvda-addon
```

Install the `.nvda-addon` from the NVDA add-on store dialog (**NVDA menu →
Tools → Add-on store → Install from external source**) or just press Enter on
the file, then pick **DECtalk** in **NVDA menu → Preferences → Settings →
Speech → Change synthesizer**.

## Settings

Full DECtalk parameter control, the same surface as the Apple/Android apps,
all in NVDA's Speech settings panel:

- **Standard NVDA sliders:** Rate (maps to `[:rate]`, the engine's full 75–600 wpm range), Volume
  (`[:vo set]`), Pitch (scales the voice's average pitch, 0.5×–2×), and
  Inflection (scales the voice's pitch range). **Rate boost** uses NVDA's
  bundled Sonic time-stretcher (as in the built-in SAPI 5 rate boost), with
  its own **Rate boost multiplier** slider (100–600%) independent of the
  rate slider — so any DECtalk engine rate can be time-stretched on top,
  pitch-correct, well past the engine's 600 wpm ceiling. NVDA 2025.1+'s own
  Sonic module is used when present; older NVDA versions (back to 2023) get
  the add-on's **bundled `sonic.dll`** (built from
  [waywardgeek/sonic](https://github.com/waywardgeek/sonic), Apache-2.0 —
  redistributable, unlike the engine).
- **Global:** SPF `[:spf]` (also in the synth settings ring), Sentence pause
  `[:pp]`, Comma pause `[:cp]`, "Split mixed-case words" (DECTalk → DEC Talk), and "Allow inline DECtalk commands" (on by
  default — `[:np]`, `[:rate 300]`, phonemic `[hxae<300,10>piy]` singing, and
  everything else works in any spoken text; turn it off to speak brackets
  literally, e.g. when reading code).
- **Per-voice `[:dv]` parameters** (28, each of the nine voices customizable
  independently): pitch, pitch range, assertiveness, head size, smoothness,
  richness, breathiness, formants, source gains, and more. Values start at
  the voice's engine built-in and any you change are stored per voice —
  matching the mobile apps' "auto unless overridden" behavior. Slider ranges
  are the engine's own reported limits.

Voice parameter changes apply from the next utterance. Index marks
(`[:index mark N]`) are wired into NVDA's cursor tracking, so say-all and
"speak to cursor" behave like any first-class synthesizer.

## Notes & limits

- **License:** the upstream engine (`upstream/LICENCE`) is **proprietary
  FONIX**, provided "as is" with no distribution grant — which is why it's
  fetched, not committed. Fine for personal/experimental builds;
  **redistribution requires rights clearance.**
- Currently ships **US English** (`dtalk_us.dic`); the engine also builds
  UK / SP / GR / LA / FR dictionaries.
- Engine output is 11025 Hz 16-bit mono, fed straight to NVDA's audio player.
- The engine is ASCII-era: the driver folds smart punctuation and accents to
  ASCII before synthesis (`_text.engine_ascii`).
- The x64 build sidesteps a real Win64 hazard in the legacy callback API (the
  buffer pointer is passed through a 32-bit `long`): buffers are tracked FIFO
  and the truncated pointer is never dereferenced.

## Continuous integration

`.github/workflows/ci.yml` runs on every push/PR/tag: bootstraps the engine,
builds both DLLs, runs the engine smoke tests, packages the add-on, and
uploads it as a workflow artifact. Tags publish a GitHub release with the
`.nvda-addon`.
