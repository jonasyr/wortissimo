"""Authoritative "is this a real German word?" oracle. Build-time only.

Backed by Hunspell de_DE (igerman98) — the dictionary LibreOffice and
Firefox use for German. This replaces the corpus-frequency heuristic for
deciding what may be REVEALED to a player, because frequency answers the
wrong question: it measures how often a string occurs, not whether it is a
word. That is why a flat frequency floor kept fragments like 'alk', 'ska'
and 'che' while dropping ordinary inflected forms.

Frequency is still used, but only for difficulty tuning, which is what it
is actually good at.

Licence note: igerman98 is GPL v2/v3. Private self-hosted use is
unencumbered; redistributing the dictionary files carries GPL obligations.
"""

from functools import lru_cache
from pathlib import Path

from spylls.hunspell import Dictionary

HUNSPELL_DIR = Path("data/raw/hunspell")
HUNSPELL_BASE = HUNSPELL_DIR / "index"
MAX_ESZETT_SITES = 3


def _eszett_sites(word: str) -> list[int]:
    """Non-overlapping positions of 'ss' in `word`."""
    sites: list[int] = []
    i = 0
    while i < len(word) - 1:
        if word[i:i + 2] == "ss":
            sites.append(i)
            i += 2
        else:
            i += 1
    return sites


def spelling_variants(word: str) -> list[str]:
    """Plausible real spellings of a normalized word.

    Normalization casefolds and maps ß to ss, which destroys the spelling
    Hunspell actually stores: 'strasse' is not in the dictionary but
    'Straße' is. We therefore probe the capitalised form (every German
    noun is capitalised) and the ß restorations.
    """
    variants = [word, word.capitalize()]
    sites = _eszett_sites(word)
    if 0 < len(sites) <= MAX_ESZETT_SITES:
        for mask in range(1, 1 << len(sites)):
            candidate = word
            for bit, position in reversed(list(enumerate(sites))):
                if mask >> bit & 1:
                    candidate = (candidate[:position] + "ß"
                                 + candidate[position + 2:])
            variants.append(candidate)
            variants.append(candidate.capitalize())
    return variants


class WordAuthority:
    """Memoized Hunspell lookup over normalized words."""

    def __init__(self, base: Path = HUNSPELL_BASE) -> None:
        self._dictionary = Dictionary.from_files(str(base))
        self._cache: dict[str, bool] = {}

    def is_word(self, normalized: str) -> bool:
        """True if any plausible spelling of `normalized` is real German."""
        cached = self._cache.get(normalized)
        if cached is not None:
            return cached
        result = any(
            self._dictionary.lookup(variant)
            for variant in spelling_variants(normalized)
        )
        self._cache[normalized] = result
        return result

    def __contains__(self, normalized: str) -> bool:
        return self.is_word(normalized)


@lru_cache(maxsize=1)
def default_authority() -> WordAuthority:
    """Shared instance; loading the dictionary takes a couple of seconds."""
    return WordAuthority()
