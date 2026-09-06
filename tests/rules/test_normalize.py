import pytest
from hypothesis import given, strategies as st

from wortissimo.rules.normalize import normalize


def test_casefolds():
    assert normalize("HAUS") == "haus"


def test_eszett_becomes_ss():
    # casefold() already does this; this test pins the behaviour so a
    # future switch to .lower() would fail loudly.
    assert normalize("Straße") == "strasse"


def test_umlauts_are_preserved_not_expanded():
    assert normalize("Bäcker") == "bäcker"
    assert normalize("Übung") == "übung"


def test_strips_surrounding_whitespace():
    assert normalize("  Haus \n") == "haus"


def test_rejects_non_letters():
    with pytest.raises(ValueError):
        normalize("Haus1")
    with pytest.raises(ValueError):
        normalize("Haus-Tür")
    with pytest.raises(ValueError):
        normalize("zwei Wörter")


def test_rejects_empty():
    with pytest.raises(ValueError):
        normalize("   ")


@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyzäöü", min_size=1))
def test_is_idempotent(word):
    once = normalize(word)
    assert normalize(once) == once
