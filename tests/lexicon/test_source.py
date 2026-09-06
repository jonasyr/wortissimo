from pathlib import Path

from wortissimo.lexicon.source import load_normalized, load_raw_words


def write_latin1(tmp_path: Path, lines: list[str]) -> Path:
    p = tmp_path / "german.txt"
    p.write_bytes("\r\n".join(lines).encode("latin-1"))
    return p


def test_reads_latin1_umlauts_correctly(tmp_path):
    path = write_latin1(tmp_path, ["Bäcker", "Straße", "Übung"])
    assert list(load_raw_words(path)) == ["Bäcker", "Straße", "Übung"]


def test_normalizes_entries(tmp_path):
    path = write_latin1(tmp_path, ["Bäcker", "Straße"])
    assert load_normalized(path) == {"bäcker", "strasse"}


def test_drops_entries_the_normalizer_rejects(tmp_path):
    path = write_latin1(tmp_path, ["Haus", "Groß-Gerau", "d'accord", "A1"])
    assert load_normalized(path) == {"haus"}


def test_drops_blank_lines(tmp_path):
    path = write_latin1(tmp_path, ["Haus", "", "  ", "Bahn"])
    assert load_normalized(path) == {"haus", "bahn"}


def test_collapses_case_duplicates(tmp_path):
    # germandict lists both noun and verb forms; after casefolding these
    # collapse, which is correct.
    path = write_latin1(tmp_path, ["Reise", "reise"])
    assert load_normalized(path) == {"reise"}
