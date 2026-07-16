#!/usr/bin/env python3
"""package.py — build the .nvda-addon bundle.

Zips the contents of addon/ (manifest.ini at the archive root) into
dist/DECtalk-v<version>.nvda-addon. Requires scripts/build.ps1 to have been
run first so the engine DLLs and dictionary are present.

    python scripts/package.py
"""
import configparser
import os
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ADDON = os.path.join(ROOT, "addon")
DIST = os.path.join(ROOT, "dist")


def main():
    cp = configparser.ConfigParser()
    with open(os.path.join(ADDON, "manifest.ini"), encoding="utf-8") as f:
        cp.read_string("[addon]\n" + f.read())
    version = cp["addon"]["version"].strip("\"'")

    required = [
        os.path.join(ADDON, "synthDrivers", "dectalknew", "lib", "x64", "DECtalk.dll"),
        os.path.join(ADDON, "synthDrivers", "dectalknew", "lib", "x64", "sonic.dll"),
        os.path.join(ADDON, "synthDrivers", "dectalknew", "dtalk_us.dic"),
    ]
    missing = [p for p in required if not os.path.isfile(p)]
    if missing:
        sys.exit(
            "Missing build artifacts:\n  " + "\n  ".join(missing)
            + "\nRun scripts/build.ps1 first."
        )

    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, "DECtalk-v%s.nvda-addon" % version)
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for base, _dirs, files in os.walk(ADDON):
            if "__pycache__" in base:
                continue
            for name in files:
                if name.endswith((".pyc", ".exp", ".lib")):
                    continue
                path = os.path.join(base, name)
                z.write(path, os.path.relpath(path, ADDON))
    print("wrote", out, "(%d KB)" % (os.path.getsize(out) // 1024))


if __name__ == "__main__":
    main()
