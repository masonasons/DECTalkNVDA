"""Validate the bundled sonic.dll through _sonic_fallback (no NVDA needed).

    python tests/test_sonic.py
"""
import ctypes
import importlib.util
import math
import os
import struct

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "_sonic_fallback",
    os.path.join(_ROOT, "addon", "synthDrivers", "dectalk", "_sonic_fallback.py"),
)
sf = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sf)


def main():
    sf.initialize()
    s = sf.SonicStream(11025, 1)
    s.speed = 2.0
    assert abs(s.speed - 2.0) < 0.001

    # 1 second of 440 Hz sine -> ~0.5 s out at 2x speed, non-silent
    n = 11025
    pcm = struct.pack(
        "<%dh" % n,
        *(int(20000 * math.sin(2 * math.pi * 440 * i / 11025)) for i in range(n)),
    )
    buf = (ctypes.c_short * n).from_buffer_copy(pcm)
    s.writeShort(ctypes.cast(buf, ctypes.POINTER(ctypes.c_short)), n)
    s.flush()
    out = s.readShort()
    ratio = len(out) / n
    print(f"in={n} samples, out={len(out)} samples, ratio={ratio:.3f} (expect ~0.5)")
    assert 0.4 < ratio < 0.6, ratio
    assert max(abs(v) for v in out[:400]) > 5000, "stretched audio is silent"
    assert s.samplesAvailable == 0

    # streaming reads between writes work too
    s.speed = 3.0
    for _ in range(4):
        s.writeShort(ctypes.cast(buf, ctypes.POINTER(ctypes.c_short)), n)
        s.readShort()
    s.flush()
    s.readShort()

    # independent second stream; destructor must not crash
    s2 = sf.SonicStream(22050, 1)
    s2.speed = 4.0
    del s2
    print("SONIC FALLBACK TESTS PASSED")


if __name__ == "__main__":
    main()
