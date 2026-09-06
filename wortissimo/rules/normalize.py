"""Canonical word form. Pure: no I/O, no state.

This is the single definition of "the same word" used by both the offline
generator and the live server. If these two ever disagreed, the game would
reveal solutions it would then refuse to accept.
"""

LETTERS = frozenset("abcdefghijklmnopqrstuvwxyzäöü")


def normalize(text: str) -> str:
    """Return the canonical form of a single German word.

    casefold() is required rather than lower(): it maps ß to ss, so
    "Straße" and "Strasse" canonicalise identically.

    Raises ValueError if the input is empty or contains anything that is
    not a German letter.
    """
    folded = text.strip().casefold()
    if not folded:
        raise ValueError("empty word")
    bad = set(folded) - LETTERS
    if bad:
        raise ValueError(f"invalid characters: {sorted(bad)!r}")
    return folded
