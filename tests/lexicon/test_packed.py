import pytest

from wortissimo.lexicon.packed import PackedWordSet

WORDS = ["haus", "bahn", "strasse", "bäcker", "übung", "abc", "zzz"]


@pytest.fixture
def packed():
    return PackedWordSet.build(WORDS)


def test_contains_every_word(packed):
    for word in WORDS:
        assert word in packed, word


def test_rejects_absent_words(packed):
    for word in ["haux", "bah", "hausx", "", "zzzz", "aaa"]:
        assert word not in packed, word


def test_rejects_a_prefix_of_a_stored_word(packed):
    # A naive blob search would match 'strass' inside 'strasse'.
    assert "strass" not in packed
    assert "stras" not in packed


def test_handles_umlauts_and_eszett_roundtrip(packed):
    assert "bäcker" in packed
    assert "übung" in packed


def test_deduplicates(packed):
    assert len(PackedWordSet.build(["haus", "haus", "bahn"])) == 2


def test_length(packed):
    assert len(packed) == len(WORDS)


def test_iteration_yields_sorted_words(packed):
    listed = list(packed)
    assert listed == sorted(WORDS)


def test_empty_set_behaves():
    empty = PackedWordSet.build([])
    assert len(empty) == 0
    assert "haus" not in empty


def test_non_string_lookup_is_false(packed):
    assert 42 not in packed


def test_save_and_load_roundtrip(tmp_path, packed):
    path = tmp_path / "words.bin"
    packed.save(path)
    revived = PackedWordSet.load(path)
    assert len(revived) == len(packed)
    for word in WORDS:
        assert word in revived
    assert "nope" not in revived


def test_load_rejects_a_foreign_file(tmp_path):
    path = tmp_path / "bad.bin"
    path.write_bytes(b"not a packed set")
    with pytest.raises(ValueError):
        PackedWordSet.load(path)
