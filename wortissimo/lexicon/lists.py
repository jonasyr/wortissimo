"""The two word lists. Build-time only.

Spec section 6: one list cannot serve both runtime jobs.

  acceptance  decides whether a word the player typed scores. Generous.
              Wrongly rejecting a real German word is the worst failure
              mode in this genre, so marginal entries stay in.

  solutions   what the game reveals as "words you missed", and the basis
              for all difficulty computation. Clean. Revealing 'aer' as a
              word the player missed destroys trust in the game.
"""

from collections.abc import Container, Mapping
from dataclasses import dataclass
from pathlib import Path

from wordfreq import zipf_frequency

from wortissimo.rules.normalize import normalize

# Measured against the real 2.15M-word corpus, not guessed. The floor trades
# solution-list cleanliness against puzzle density:
#   3.5 -> 16,441 solutions, median 7 per source word  (too sparse to play)
#   2.5 -> 72,829 solutions, median 10                 (chosen)
#   1.5 -> 235,321 solutions, median 11                (junk, barely denser)
# At 2.5 the marginal words are still real German (entwaffnung, ruppig,
# ausbaden); below it, place names and noise dominate (tuhh, paulinzella).
SOLUTION_ZIPF_FLOOR = 2.5
TRIVIAL_ZIPF = 5.0
MIN_LENGTH = 3
BLOCKLIST_PATH = Path("data/blocklist.txt")


@dataclass(frozen=True)
class Lexicon:
    acceptance: frozenset[str]
    solutions: frozenset[str]
    freq: Mapping[str, float]


def load_blocklist(path: Path = BLOCKLIST_PATH) -> frozenset[str]:
    """Read the manual blocklist: one normalized word per line, # comments."""
    if not path.exists():
        return frozenset()
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = line.split("#", 1)[0].strip()
        if not entry:
            continue
        try:
            out.add(normalize(entry))
        except ValueError:
            continue
    return frozenset(out)


# Short strings need a much higher bar. wordfreq scores three-letter
# fragments highly because they occur as abbreviations and truncations in
# real corpora, so a single global floor admits 'alk', 'ska', 'che' and
# 'tel' alongside genuine short words like 'art' (5.51) and 'ort' (5.31).
# Revealing the former as words the player "missed" is exactly the failure
# spec section 6 exists to prevent.
LENGTH_ZIPF_FLOOR: dict[int, float] = {3: 4.5, 4: 3.5, 5: 3.0}


def solution_floor(word: str, base: float = SOLUTION_ZIPF_FLOOR) -> float:
    """The frequency a word of this length must clear to be a solution."""
    return LENGTH_ZIPF_FLOOR.get(len(word), base)


def build_lexicon(
    words: set[str],
    blocklist: Container[str],
    solution_zipf_floor: float = SOLUTION_ZIPF_FLOOR,
    min_length: int = MIN_LENGTH,
) -> Lexicon:
    """Split one normalized word set into the acceptance and solution lists.

    Acceptance is deliberately generous. Solutions must clear a
    length-dependent frequency floor, because short fragments and long
    words need very different bars to be considered real.
    """
    acceptance = frozenset(
        w for w in words
        if len(w) >= min_length and w not in blocklist
    )
    freq = {w: zipf_frequency(w, "de") for w in acceptance}
    solutions = frozenset(
        w for w in acceptance
        if freq[w] >= solution_floor(w, solution_zipf_floor)
    )
    return Lexicon(acceptance=acceptance, solutions=solutions, freq=freq)
