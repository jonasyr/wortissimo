"""Compound segmentation via CharSplit, made recursive and lexicon-aware.

split_words.Splitter.split_compound() returns a ranked list of BINARY
splits only, and its top-ranked answer is often wrong:

    Autobahnraststätte -> (-0.71, 'Auto', 'Bahnraststätte')  <- top, wrong
                          (-0.94, 'Autobahn', 'Raststätte')  <- correct

We therefore re-rank the splitter's candidates by how many halves are
known words, and recurse into each half to find further boundaries.

Segmentation feeds difficulty bucketing ONLY. It never accepts or rejects
a player's word, so its error rate is cosmetic (spec section 9).
"""

from collections.abc import Container
from functools import lru_cache

from split_words import Splitter

MIN_PART = 4
# Candidate splits below this raw CharSplit score are ignored unless the
# lexicon confirms both halves.
SCORE_FLOOR = -1.0
TOP_N = 5


@lru_cache(maxsize=1)
def _default_splitter() -> Splitter:
    """Splitter loads a large ngram model; build it once per process."""
    return Splitter()


def _best_split(
    word: str, known: Container[str], splitter: Splitter, min_part: int
) -> int | None:
    """Return the best single boundary offset within `word`, or None."""
    if len(word) < 2 * min_part:
        return None

    try:
        candidates = splitter.split_compound(word)[:TOP_N]
    except Exception:
        return None

    best_offset: int | None = None
    best_key: tuple[int, float] | None = None

    for score, body, head in candidates:
        offset = len(body)
        if offset < min_part or len(word) - offset < min_part:
            continue
        if offset + len(head) != len(word):
            continue

        confirmed = int(body.casefold() in known) + int(head.casefold() in known)
        if confirmed == 0 and score < SCORE_FLOOR:
            continue

        # Lexicon confirmation dominates the raw score: a split whose two
        # halves are both real words beats a better-scoring split whose
        # halves are not.
        key = (confirmed, score)
        if best_key is None or key > best_key:
            best_key, best_offset = key, offset

    return best_offset


def segment(
    word: str,
    known: Container[str],
    splitter: Splitter | None = None,
    min_part: int = MIN_PART,
) -> tuple[int, ...]:
    """Return sorted morpheme boundary offsets within `word`.

    Offsets 0 and len(word) are excluded. An unsplittable word returns ().
    """
    splitter = splitter or _default_splitter()
    boundaries: set[int] = set()

    def recurse(start: int, end: int) -> None:
        part = word[start:end]
        offset = _best_split(part, known, splitter, min_part)
        if offset is None:
            return
        absolute = start + offset
        if absolute in boundaries:
            return
        boundaries.add(absolute)
        recurse(start, absolute)
        recurse(absolute, end)

    recurse(0, len(word))
    return tuple(sorted(boundaries))
