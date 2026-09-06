"""Round scoring. Pure: no I/O, no state.

Scoring is a projection over the set of accepted words. It is deliberately
a pure function of its inputs so it can be recomputed at any time from the
append-only submissions table.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

POINTS_SHARED = 1
POINTS_UNIQUE = 2


@dataclass(frozen=True)
class PlayerScore:
    player: str
    points: int
    words: tuple[str, ...]
    unique_words: tuple[str, ...]


@dataclass(frozen=True)
class RoundResult:
    scores: tuple[PlayerScore, ...]
    shared_words: tuple[str, ...]
    missed_words: tuple[str, ...]


def score_round(
    accepted: Mapping[str, Iterable[str]],
    solutions: Iterable[str],
) -> RoundResult:
    """Score one finished round.

    `accepted` maps player id to the words that player got accepted.
    Duplicates within a player are collapsed. A word scores 2 points if no
    other player submitted it, otherwise 1.

    All output sequences are sorted so results are deterministic and
    comparable in tests.
    """
    per_player = {p: frozenset(ws) for p, ws in accepted.items()}

    counts: dict[str, int] = {}
    for words in per_player.values():
        for word in words:
            counts[word] = counts.get(word, 0) + 1

    scores = []
    for player in sorted(per_player):
        words = per_player[player]
        unique = frozenset(w for w in words if counts[w] == 1)
        points = (len(unique) * POINTS_UNIQUE
                  + (len(words) - len(unique)) * POINTS_SHARED)
        scores.append(PlayerScore(
            player=player,
            points=points,
            words=tuple(sorted(words)),
            unique_words=tuple(sorted(unique)),
        ))

    shared = tuple(sorted(w for w, n in counts.items() if n > 1))
    missed = tuple(sorted(frozenset(solutions) - frozenset(counts)))

    return RoundResult(scores=tuple(scores), shared_words=shared,
                       missed_words=missed)
