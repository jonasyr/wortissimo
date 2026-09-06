"""Difficulty bucketing by hard constraints (spec section 10).

Deliberately NOT a weighted score. Five coefficients cannot be calibrated
from two players' data, so the apparent precision would be fake. A table
is deterministic, debuggable, and retunable by editing one place.

The thresholds below were measured against the real corpus rather than
guessed. Sampling 40 source words per length band gave, as median / p75 / p90:

    length   solutions      cross-boundary   >=7 letters
    15-19     6 /  9 / 10      2 /  3            2 / 3
    20-24     8 / 11 / 13      3 /  5            3 / 4
    25-29    12 / 14 / 17      4 /  7            4 / 6
    30-40    14 / 17 / 18      5 /  7            5 / 7

These are the figures AFTER the length-dependent frequency floor removed
the three-letter fragment noise; counts are roughly 40% lower than with a
flat floor, but every remaining solution is a word a German speaker will
accept when it is revealed to them.

Each bucket targets roughly the top quartile of its band, so puzzles are
good rather than typical. The corpus has ~1M candidates, so being
selective costs nothing.

The originally specified table (Leicht 15-25 solutions, Brutal 30-60) was
unachievable: the observed maximum is 35 solutions, and only among the
3,617 words of 31-40 letters.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from wortissimo.generator.solve import Category, Solution
from wortissimo.lexicon.lists import TRIVIAL_ZIPF

LONG_WORD_LENGTH = 7


class Difficulty(StrEnum):
    LEICHT = "leicht"
    MITTEL = "mittel"
    SCHWER = "schwer"
    BRUTAL = "brutal"


@dataclass(frozen=True)
class Bucket:
    difficulty: Difficulty
    min_len: int
    max_len: int
    min_solutions: int
    max_solutions: int
    min_long: int
    min_cross: int
    max_trivial_share: float


# Ordered hardest-first. Length bands do not overlap, so exactly one bucket
# can match; the ordering is kept so that adding an overlapping band later
# still resolves to the harder one.
BUCKETS: tuple[Bucket, ...] = (
    Bucket(Difficulty.BRUTAL, 30, 40, 16, 30, 5, 6, 0.35),
    Bucket(Difficulty.SCHWER, 25, 29, 13, 20, 4, 5, 0.40),
    Bucket(Difficulty.MITTEL, 20, 24, 10, 16, 3, 3, 0.45),
    Bucket(Difficulty.LEICHT, 15, 19,  8, 14, 2, 2, 0.50),
)


def metrics(source: str, solutions: Sequence[Solution]) -> dict[str, float | int]:
    """Measure the shape of one candidate round."""
    total = len(solutions)
    trivial = sum(
        1 for s in solutions
        if s.category is Category.OBVIOUS_COMPONENT and s.freq >= TRIVIAL_ZIPF
    )
    return {
        "length": len(source),
        "solution_count": total,
        "long_count": sum(1 for s in solutions if len(s.word) >= LONG_WORD_LENGTH),
        "cross_boundary_count": sum(
            1 for s in solutions if s.category is Category.CROSS_BOUNDARY
        ),
        "trivial_share": (trivial / total) if total else 0.0,
    }


def _fits(bucket: Bucket, m: dict[str, float | int]) -> bool:
    return (
        bucket.min_len <= m["length"] <= bucket.max_len
        and bucket.min_solutions <= m["solution_count"] <= bucket.max_solutions
        and m["long_count"] >= bucket.min_long
        and m["cross_boundary_count"] >= bucket.min_cross
        and m["trivial_share"] <= bucket.max_trivial_share
    )


def classify_difficulty(
    source: str, solutions: Sequence[Solution]
) -> Difficulty | None:
    """Return the hardest bucket this round qualifies for, or None."""
    m = metrics(source, solutions)
    for bucket in BUCKETS:
        if _fits(bucket, m):
            return bucket.difficulty
    return None
