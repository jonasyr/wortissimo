"""Download and extract the Free German Dictionary (public domain).

Source: https://sourceforge.net/projects/germandict/
~2 million entries including inflected forms. Public domain, so no
attribution or licence obligation attaches to the generated puzzles.

Usage: python scripts/fetch_dictionary.py
"""

import shutil
import sys
import urllib.request
from pathlib import Path

import py7zr

URL = "https://sourceforge.net/projects/germandict/files/german.7z/download"
RAW_DIR = Path("data/raw")
ARCHIVE = RAW_DIR / "german.7z"
# german.dic is the ~2.15M entry word list. The archive ALSO contains a
# german.txt, but that is a small unrelated 4k-line file — picking it up by
# accident yields a dictionary that looks plausible and is 500x too small.
TARGET = RAW_DIR / "german.dic"


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if not ARCHIVE.exists():
        print(f"Downloading {URL}")
        req = urllib.request.Request(URL, headers={"User-Agent": "wortissimo"})
        with urllib.request.urlopen(req) as resp, ARCHIVE.open("wb") as out:
            shutil.copyfileobj(resp, out)
        print(f"Saved {ARCHIVE} ({ARCHIVE.stat().st_size:,} bytes)")

    print(f"Extracting into {RAW_DIR}")
    with py7zr.SevenZipFile(ARCHIVE, mode="r") as archive:
        archive.extractall(path=RAW_DIR)

    if not TARGET.exists():
        print(f"ERROR: {TARGET.name} not found in archive; contents: "
              f"{sorted(p.name for p in RAW_DIR.iterdir())}", file=sys.stderr)
        return 1

    line_count = sum(1 for _ in TARGET.open("r", encoding="latin-1"))
    print(f"{TARGET}: {line_count:,} lines")
    if line_count < 1_000_000:
        print("WARNING: expected ~2M lines; archive layout may have changed",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
