"""Word validation. Pure: no I/O, no state."""

from collections.abc import Container
from dataclasses import dataclass
from enum import StrEnum

from wortissimo.rules.normalize import normalize

MIN_LENGTH = 3


class Rejection(StrEnum):
    TOO_SHORT = "too_short"
    NOT_A_SUBSTRING = "not_a_substring"
    NOT_IN_DICTIONARY = "not_in_dictionary"
    IS_SOURCE_WORD = "is_source_word"
    MALFORMED = "malformed"
    # Produced by the server (round state), not by validate_word.
    DUPLICATE = "duplicate"
    TOO_LATE = "too_late"


@dataclass(frozen=True)
class Verdict:
    word: str
    accepted: bool
    reason: Rejection | None


def validate_word(
    raw: str,
    source_word: str,
    acceptance: Container[str],
    min_length: int = MIN_LENGTH,
) -> Verdict:
    """Decide whether `raw` scores against `source_word`.

    Checks run cheapest-and-most-actionable first, so the player gets the
    most useful single reason rather than an arbitrary one.
    """
    try:
        word = normalize(raw)
    except ValueError:
        return Verdict(word=raw.strip().casefold(), accepted=False,
                       reason=Rejection.MALFORMED)

    source = normalize(source_word)

    if len(word) < min_length:
        return Verdict(word, False, Rejection.TOO_SHORT)
    if word == source:
        return Verdict(word, False, Rejection.IS_SOURCE_WORD)
    if word not in source:
        return Verdict(word, False, Rejection.NOT_A_SUBSTRING)
    if word not in acceptance:
        return Verdict(word, False, Rejection.NOT_IN_DICTIONARY)
    return Verdict(word, True, None)
