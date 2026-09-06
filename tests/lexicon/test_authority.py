import pytest

from wortissimo.lexicon.authority import (
    WordAuthority, _eszett_sites, spelling_variants,
)

pytestmark = pytest.mark.skipif(
    not __import__("pathlib").Path("data/raw/hunspell/index.dic").exists(),
    reason="hunspell dictionary not fetched; run scripts/fetch_hunspell.py",
)


@pytest.fixture(scope="module")
def authority():
    return WordAuthority()


def test_finds_non_overlapping_eszett_sites():
    assert _eszett_sites("strasse") == [4]
    assert _eszett_sites("massstrasse") == [2, 8]
    assert _eszett_sites("haus") == []


def test_variants_include_capitalised_and_eszett_forms():
    variants = spelling_variants("strasse")
    assert "Straße" in variants
    assert "Strasse" in variants


def test_variants_of_a_plain_word_are_just_the_two_cases():
    assert spelling_variants("bahn") == ["bahn", "Bahn"]


def test_accepts_real_words(authority):
    for word in ["haus", "gesetz", "kalkulation", "ruppig", "ausbaden",
                 "auflagenpunkte", "medizin", "transport"]:
        assert authority.is_word(word), word


def test_rejects_fragments_a_frequency_floor_would_admit(authority):
    # These all clear a naive corpus-frequency floor but are not words.
    for word in ["alk", "ska", "che", "senbah", "nde", "kationen", "touris"]:
        assert not authority.is_word(word), word


def test_handles_eszett_words_that_normalization_would_break(authority):
    # normalize() maps ß->ss, so a naive lookup of these fails outright.
    for word in ["strasse", "fuss", "mass", "pflegemassnahmen"]:
        assert authority.is_word(word), word


def test_rejects_uncommon_proper_nouns(authority):
    for word in ["runge", "chester", "marin", "rothe", "ilm"]:
        assert not authority.is_word(word), word


def test_is_memoized(authority):
    authority.is_word("haus")
    assert "haus" in authority._cache


def test_container_protocol(authority):
    assert "haus" in authority
    assert "alk" not in authority
