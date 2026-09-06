"""Download the Hunspell de_DE (igerman98) dictionary.

This is the authority for "is this a real German word?" — the same
dictionary LibreOffice and Firefox use. Source: the wooorm/dictionaries
repository, which republishes igerman98 normalised to UTF-8.

LICENCE: igerman98 is GPL v2/v3. Using it locally to build a puzzle corpus
is unencumbered. Redistributing these files carries GPL obligations.

Usage: python scripts/fetch_hunspell.py
"""

import sys
import urllib.request
from pathlib import Path

BASE = "https://raw.githubusercontent.com/wooorm/dictionaries/main/dictionaries/de"
TARGET_DIR = Path("data/raw/hunspell")
FILES = ("index.aff", "index.dic", "license")


def main() -> int:
    TARGET_DIR.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        target = TARGET_DIR / name
        url = f"{BASE}/{name}"
        request = urllib.request.Request(url, headers={"User-Agent": "wortissimo"})
        with urllib.request.urlopen(request) as response:
            target.write_bytes(response.read())
        print(f"{target}: {target.stat().st_size:,} bytes")

    entries = sum(1 for _ in (TARGET_DIR / "index.dic").open(encoding="utf-8"))
    print(f"{entries:,} dictionary entries")
    if entries < 50_000:
        print("WARNING: expected ~76k entries; source layout may have changed",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
