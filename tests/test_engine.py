"""Engine smoke tests: real, non-silent synthesis through the built DLL.

Runs against a plain Python interpreter (no NVDA needed):

    python tests/test_engine.py
"""
import importlib.util
import os
import struct
import threading
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "_dectalk", os.path.join(_ROOT, "addon", "synthDrivers", "dectalknew", "_dectalk.py")
)
dt = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(dt)


def rms(pcm):
    n = len(pcm) // 2
    if not n:
        return 0
    vals = struct.unpack("<%dh" % n, pcm[: n * 2])
    return (sum(v * v for v in vals) / n) ** 0.5


def main():
    eng = dt.Engine()
    print("engine started")

    # 1. Basic synthesis with index marks
    chunks, marks = [], []

    def sink(pcm, mk):
        chunks.append(pcm)
        marks.extend(mk)

    eng.speak(
        "[:index mark 1] Hello from DECtalk on NVDA. [:index mark 2] "
        "Second sentence here. [:index mark 3]",
        sink,
    )
    pcm = b"".join(chunks)
    total = len(pcm) // 2
    print(f"samples={total} ({total / dt.SAMPLE_RATE:.2f}s) rms={rms(pcm):.0f} marks={marks}")
    assert rms(pcm) > 100, "audio is silent!"
    assert [v for v, _ in marks] == [1, 2, 3], "index marks missing/misordered"
    assert marks[-1][1] == total, "final mark should land at the end of the audio"

    # 2. Per-speaker params readable after the pipeline processes the change
    eng.set_speaker(1)  # Betty
    eng.speak(".", lambda p, m: None)
    cur, lo, hi = eng.speaker_params()
    assert cur["ap"] == 208 and cur["sx"] == 0, cur
    print("speaker params OK (Betty ap=%d)" % cur["ap"])

    # 3. Inline [:dv] + voice switching synthesizes non-silence
    chunks2 = []
    eng.set_speaker(0)
    eng.speak(
        "[:nb][:dv ap 300 hs 120] Betty customized. [:np] and back to Paul.",
        lambda p, m: chunks2.append(p),
    )
    assert rms(b"".join(chunks2)) > 100

    # 4. stop() from another thread cancels promptly under backpressure
    got = []

    def slow_sink(p, m):
        got.append(p)
        time.sleep(0.05)  # simulate audio-player backpressure

    th = threading.Thread(
        target=lambda: eng.speak("This is a very long sentence. " * 60, slow_sink)
    )
    t0 = time.time()
    th.start()
    time.sleep(0.3)
    eng.stop()
    th.join(timeout=5)
    assert not th.is_alive(), "speak() did not return after stop()"
    assert time.time() - t0 < 3, "cancel too slow"
    print("cancel OK (%.2fs)" % (time.time() - t0))

    # 5. Engine survives cancel
    chunks3 = []
    eng.speak("Recovered after cancel.", lambda p, m: chunks3.append(p))
    assert rms(b"".join(chunks3)) > 100
    print("post-cancel synthesis OK")

    # 6. [:say letter] is sticky engine state; [:say clause] resets it.
    def dur(text):
        acc = []
        eng.speak(text, lambda p, m: acc.append(p))
        return sum(len(c) for c in acc) / 2 / dt.SAMPLE_RATE

    plain = dur("hello")
    spelled = dur("[:say letter]hello")
    sticky = dur("hello")  # letter mode persists from the previous utterance
    reset = dur("[:say clause]hello")
    print(f"say-mode durations: plain={plain:.2f}s spelled={spelled:.2f}s "
          f"sticky={sticky:.2f}s reset={reset:.2f}s")
    assert spelled > plain * 1.8, "letter mode did not spell"
    assert sticky > plain * 1.8, "expected letter mode to persist (engine state)"
    assert reset < plain * 1.3, "[:say clause] did not reset letter mode"

    # 6b. TTS_FORCE's clause marker (0x0B) is announced as "vertical tab"
    # when an utterance ends in letter mode; a trailing [:say clause] fixes
    # it without stopping earlier letters from being spelled.
    spell_reset = dur("[:say letter]hello[:say clause]")
    print(f"spell+reset={spell_reset:.2f}s (no-reset was {spelled:.2f}s)")
    assert plain * 1.8 < spell_reset < spelled - 1.0, (
        "trailing [:say clause] should drop the spoken force marker "
        "while still spelling: %.2fs" % spell_reset
    )

    # 7. should_abort skips synthesis entirely
    aborted = []
    eng.speak("This must not be spoken.", lambda p, m: aborted.append(p),
              should_abort=lambda: True)
    assert not aborted, "should_abort did not prevent synthesis"
    print("should_abort OK")

    # 8. stop() while idle must not break the following utterance
    eng.stop()
    chunks4 = []
    eng.speak("Still speaking after an idle stop.", lambda p, m: chunks4.append(p))
    assert rms(b"".join(chunks4)) > 100
    print("idle-stop OK")

    eng.close()
    print("ALL ENGINE TESTS PASSED")


if __name__ == "__main__":
    main()
