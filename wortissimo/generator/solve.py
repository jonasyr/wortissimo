"""Enumerate and classify the solutions of one source word.

Cost: a source word of length n has n(n+1)/2 substrings; n=40 gives 820.
Across ~1M candidate source words that is a batch job measured in minutes,
once. This was never a scaling problem.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from wortissimo.lexicon.lists import Lexicon

MIN_LENGTH = 3


class Category(StrEnum):
    OBVIOUS_COMPONENT = "obvious_component"
    CROSS_BOUNDARY = "cross_boundary"


@dataclass(frozen=True)
class Solution:
    word: str
    category: Category
    freq: float


def _category(start: int, end: int, boundaries: Sequence[int]) -> Category:
    """CROSS_BOUNDARY if the span strictly contains a morpheme boundary."""
    if any(start < b < end for b in boundaries):
        return Category.CROSS_BOUNDARY
    return Category.OBVIOUS_COMPONENT


def find_solutions(
    source: str,
    lexicon: Lexicon,
    boundaries: tuple[int, ...],
    min_length: int = MIN_LENGTH,
) -> tuple[Solution, ...]:
    """Return every distinct solution word in `source`, classified.

    A word occurring at several positions appears once, classified by its
    most interesting occurrence (CROSS_BOUNDARY wins over
    OBVIOUS_COMPONENT), because that is the occurrence a player is
    credited for noticing.
    """
    n = len(source)
    best: dict[str, Category] = {}

    for start in range(n):
        for end in range(start + min_length, n + 1):
            word = source[start:end]
            if word == source:
                continue
            if word not in lexicon.solutions:
                continue
            if best.get(word) is Category.CROSS_BOUNDARY:
                continue
            best[word] = _category(start, end, boundaries)

    return tuple(
        Solution(word=word, category=best[word],
                 freq=lexicon.freq.get(word, 0.0))
        for word in sorted(best)
    )
