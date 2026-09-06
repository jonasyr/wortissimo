"""The two word lists. Build-time only.

Spec section 6: one list cannot serve both runtime jobs.

  acceptance  decides whether a word the player typed scores. Generous.
              Wrongly rejecting a real German word is the worst failure
              mode in this genre, so marginal entries stay in.

  solutions   what the game reveals as "words you missed", and the basis
              for all difficulty computation. Clean. Revealing 'alk' as a
              word the player missed destroys trust in the game.

Membership of `solutions` is decided by Hunspell de_DE, not by corpus
frequency. Frequency answers "how often does this string occur", which is
the wrong question: it admitted fragments like 'alk', 'ska' and 'che'
while rejecting ordinary inflected forms such as 'auflagenpunkte'.
Frequency is retained only for difficulty tuning (see TRIVIAL_ZIPF).
"""

from collections.abc import Container, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path

from wordfreq import zipf_frequency

from wortissimo.lexicon.packed import PackedWordSet
from wortissimo.rules.normalize import normalize

# A solution counts as "trivial" — an obvious component the player will
# spot instantly — above this frequency. Used only by difficulty bucketing.
TRIVIAL_ZIPF = 5.0
MIN_LENGTH = 3
BLOCKLIST_PATH = Path("data/blocklist.txt")
ACCEPTANCE_CACHE = Path("data/acceptance.bin")


class FreqTable(dict):
    """Zipf frequencies, computed on demand and cached.

    Eagerly scoring all 2.15M acceptance words cost ~47s per run for data
    that only a few thousand words ever need.
    """

    def __missing__(self, word: str) -> float:
        value = zipf_frequency(word, "de")
        self[word] = value
        return value

    def get(self, word: str, default: float = 0.0) -> float:  # type: ignore[override]
        return self[word]


class SolutionOracle:
    """Lazy membership test for the revealed solution list.

    Hunspell lookups are ~700/s, so checking every acceptance word up front
    would take the better part of an hour. Only a few tens of thousands of
    distinct substrings are ever queried during a build, so the test is
    deferred and memoized instead.
    """

    MAX_CACHE = 400_000

    def __init__(self, acceptance: Container[str], authority: Container[str]) -> None:
        self._acceptance = acceptance
        self._authority = authority
        self._cache: dict[str, bool] = {}

    def __contains__(self, word: str) -> bool:
        cached = self._cache.get(word)
        if cached is not None:
            return cached
        result = word in self._acceptance and word in self._authority
        if len(self._cache) >= self.MAX_CACHE:
            self._cache.clear()
        self._cache[word] = result
        return result


@dataclass(frozen=True)
class Lexicon:
    acceptance: Container[str]
    solutions: Container[str]
    freq: Mapping[str, float]


def load_blocklist(path: Path = BLOCKLIST_PATH) -> frozenset[str]:
    """Read the manual blocklist: one normalized word per line, # comments.

    Still needed after Hunspell: igerman98 contains famous proper nouns
    (Berlin, Hamburg, Thomas, Genf) and treats them exactly like common
    nouns, so they cannot be detected automatically.
    """
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


def build_lexicon(
    words: Iterable[str],
    blocklist: Container[str],
    authority: Container[str] | None = None,
    min_length: int = MIN_LENGTH,
) -> Lexicon:
    """Split one normalized word set into the acceptance and solution lists.

    `authority` is any container answering "is this a real German word?" —
    in production a WordAuthority backed by Hunspell, in tests a plain set.
    """
    if authority is None:
        from wortissimo.lexicon.authority import default_authority
        authority = default_authority()

    acceptance = PackedWordSet.build(
        w for w in words
        if len(w) >= min_length and w not in blocklist
    )
    return Lexicon(
        acceptance=acceptance,
        solutions=SolutionOracle(acceptance, authority),
        freq=FreqTable(),
    )


def load_or_build_acceptance(
    words: Iterable[str],
    blocklist: Container[str],
    cache: Path = ACCEPTANCE_CACHE,
    min_length: int = MIN_LENGTH,
) -> PackedWordSet:
    """Load the packed acceptance set, building and caching it if absent.

    Building it costs a ~280MB transient peak (sorting 2.15M strings);
    loading the cached artifact costs ~40MB. On a memory-constrained
    machine that difference decides whether the build survives.
    """
    if cache.exists():
        return PackedWordSet.load(cache)
    packed = PackedWordSet.build(
        w for w in words if len(w) >= min_length and w not in blocklist
    )
    packed.save(cache)
    return packed


def lexicon_from_acceptance(
    acceptance: PackedWordSet,
    authority: Container[str] | None = None,
) -> Lexicon:
    """Assemble a Lexicon around an already-built acceptance set."""
    if authority is None:
        from wortissimo.lexicon.authority import default_authority
        authority = default_authority()
    return Lexicon(acceptance=acceptance,
                   solutions=SolutionOracle(acceptance, authority),
                   freq=FreqTable())
