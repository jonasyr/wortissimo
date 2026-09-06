"""Loading the raw German word list. Build-time only."""

from collections.abc import Iterator
from pathlib import Path

from wortissimo.rules.normalize import normalize

RAW_DIR = Path("data/raw")
# The archive contains several files. german.dic is the actual ~2.15M entry
# word list; the german.txt inside the same archive is a small unrelated
# 4k-line file, which is an easy and silent mistake to make.
GERMANDICT_TXT = RAW_DIR / "german.dic"

# The Free German Dictionary ships as ANSI/Latin-1 with Windows line
# endings. Reading it as UTF-8 corrupts every umlaut, silently.
ENCODING = "latin-1"


def load_raw_words(path: Path = GERMANDICT_TXT) -> Iterator[str]:
    """Yield each non-empty line of the word list, unmodified."""
    with path.open("r", encoding=ENCODING, newline="") as fh:
        for line in fh:
            word = line.strip()
            if word:
                yield word


def load_normalized(path: Path = GERMANDICT_TXT) -> set[str]:
    """Return the word list in canonical form.

    Entries containing hyphens, apostrophes, digits or spaces are dropped:
    Wortissimo only ever deals in single unhyphenated words.
    """
    words: set[str] = set()
    for raw in load_raw_words(path):
        try:
            words.add(normalize(raw))
        except ValueError:
            continue
    return words
