"""Difficulty bucketing by hard constraints (spec section 10).

Deliberately NOT a weighted score. Five coefficients cannot be calibrated
from two players' data, so the apparent precision would be fake. A table
is deterministic, debuggable, and retunable by editing one place.

The thresholds below were measured against the real corpus rather than
guessed. Sampling 40 source words per length band gave, as median / p75 / p90:

    length   solutions       cross-boundary   >=7 letters
    15-19    10 / 13 / 16      3 /  6            3 /  5
    20-24    14 / 17 / 20      5 /  8            5 /  7
    25-29    18 / 21 / 25      8 / 11            8 / 11
    30-40    19 / 23 / 26      9 / 10            9 / 11

Measured with Hunspell de_DE deciding solution membership. An earlier
corpus-frequency filter produced roughly 40% fewer solutions AND worse
ones: it admitted fragments like 'alk' and 'ska' while discarding ordinary
inflected forms such as 'auflagenpunkte'.

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
    Bucket(Difficulty.BRUTAL, 30, 40, 20, 40, 8, 9, 0.35),
    Bucket(Difficulty.SCHWER, 25, 29, 19, 30, 7, 8, 0.40),
    Bucket(Difficulty.MITTEL, 20, 24, 15, 24, 5, 5, 0.45),
    Bucket(Difficulty.LEICHT, 15, 19, 11, 20, 3, 3, 0.50),
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


def could_qualify(source: str, solutions: Sequence[Solution]) -> bool:
    """Cheap pre-check usable BEFORE compound segmentation has run.

    Length, solution count and long-word count do not depend on morpheme
    boundaries, so they can reject a candidate before paying for
    segmentation — which is by far the most expensive step and which most
    candidates do not survive anyway.

    Cross-boundary count and trivial share are deliberately NOT checked
    here: both change once boundaries are known, so testing them now would
    reject candidates that would have qualified.
    """
    m = metrics(source, solutions)
    return any(
        bucket.min_len <= m["length"] <= bucket.max_len
        and bucket.min_solutions <= m["solution_count"] <= bucket.max_solutions
        and m["long_count"] >= bucket.min_long
        for bucket in BUCKETS
    )
