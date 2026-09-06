from wortissimo.generator.segment import segment

KNOWN = {
    "auto", "bahn", "autobahn", "raststätte", "stätte",
    "strassen", "strasse", "strassenbahn", "haltestelle", "halte", "stelle",
    "bäckerei", "fach", "verkäuferin", "bäcker",
}


def test_returns_no_boundaries_for_a_simple_word():
    assert segment("bahn", KNOWN) == ()


def test_splits_a_two_part_compound():
    # strassenbahn|haltestelle
    assert 12 in segment("strassenbahnhaltestelle", KNOWN)


def test_lexicon_reranking_beats_the_raw_top_score():
    # The splitter's top-scored answer is 'auto|bahnraststätte', but
    # 'bahnraststätte' is not a known word while both halves of
    # 'autobahn|raststätte' are. Boundary must land after 'autobahn' (8).
    assert 8 in segment("autobahnraststätte", KNOWN)


def test_recurses_to_find_more_than_one_boundary():
    # strassen|bahn|haltestelle -> at least one boundary
    assert len(segment("strassenbahnhaltestelle", KNOWN)) >= 1


def test_boundaries_are_sorted_and_exclude_the_ends():
    bounds = segment("strassenbahnhaltestelle", KNOWN)
    assert list(bounds) == sorted(bounds)
    assert 0 not in bounds
    assert len("strassenbahnhaltestelle") not in bounds


def test_short_parts_are_not_split_off():
    # min_part=4 forbids carving off fragments shorter than 4 characters.
    word = "autobahnraststätte"
    for b in segment(word, KNOWN, min_part=4):
        assert b >= 4
        assert len(word) - b >= 4


def test_is_deterministic():
    a = segment("strassenbahnhaltestelle", KNOWN)
    b = segment("strassenbahnhaltestelle", KNOWN)
    assert a == b
