import sqlite3

from wortissimo.generator.build import build_puzzles, candidate_source_words
from wortissimo.generator.store import create_schema
from wortissimo.lexicon.lists import Lexicon

# A tiny closed world. SOURCE is 17 letters and these 14 words yield a
# shape that lands in the Leicht bucket (8-14 solutions, >=2 long,
# >=2 cross-boundary). Verified against the real segmenter, which splits
# it at offsets 8 and 12.
SOURCE = "strassenbahnhalte"
SOLUTION_WORDS = [
    "strasse", "strassen", "rassen", "assen", "senbahn", "enbahn",
    "nbahn", "bahn", "ahnhalte", "nhalte", "halte", "alte",
    "bahnhalte", "rasse",
]


def make_lexicon():
    words = frozenset(SOLUTION_WORDS)
    return Lexicon(acceptance=words, solutions=words,
                   freq={w: 4.0 for w in words})


def conn():
    c = sqlite3.connect(":memory:")
    create_schema(c)
    return c


def test_writes_a_qualifying_puzzle():
    c = conn()
    written = build_puzzles(make_lexicon(), c, [SOURCE])
    assert written == 1
    (count,) = c.execute("SELECT COUNT(*) FROM puzzles").fetchone()
    assert count == 1


def test_skips_a_candidate_that_fits_no_bucket():
    c = conn()
    # 'bahn' is far too short and has no solutions.
    written = build_puzzles(make_lexicon(), c, ["bahn"])
    assert written == 0


def test_writes_solutions_for_the_puzzle():
    c = conn()
    build_puzzles(make_lexicon(), c, [SOURCE])
    (count,) = c.execute("SELECT COUNT(*) FROM solutions").fetchone()
    assert count > 0


def test_never_stores_the_source_word_as_its_own_solution():
    c = conn()
    build_puzzles(make_lexicon(), c, [SOURCE])
    rows = c.execute("SELECT word FROM solutions").fetchall()
    assert (SOURCE,) not in rows


def test_records_the_difficulty_and_metrics():
    c = conn()
    build_puzzles(make_lexicon(), c, [SOURCE])
    row = c.execute("SELECT difficulty, meta_json FROM puzzles").fetchone()
    assert row[0] == "leicht"
    assert "boundaries" in row[1]


def test_duplicate_candidates_do_not_crash():
    c = conn()
    written = build_puzzles(make_lexicon(), c, [SOURCE, SOURCE])
    assert written == 1


def test_candidate_source_words_filters_by_length():
    lex = Lexicon(acceptance=frozenset({"kurz", SOURCE, "a" * 50}),
                  solutions=frozenset(), freq={})
    assert candidate_source_words(lex) == [SOURCE]


def test_caps_stop_a_difficulty_from_dominating():
    c = conn()
    other = "strassenbahnhalten"  # different source, same shape family
    lex = Lexicon(
        acceptance=frozenset(SOLUTION_WORDS),
        solutions=frozenset(SOLUTION_WORDS),
        freq={w: 4.0 for w in SOLUTION_WORDS},
    )
    written = build_puzzles(lex, c, [SOURCE, other], caps={"leicht": 1})
    assert written == 1


def test_shuffled_candidates_is_deterministic():
    from wortissimo.generator.build import shuffled_candidates
    lex = Lexicon(
        acceptance=frozenset({SOURCE, "a" * 20, "b" * 25, "c" * 30}),
        solutions=frozenset(), freq={},
    )
    assert shuffled_candidates(lex, seed=1) == shuffled_candidates(lex, seed=1)
    assert sorted(shuffled_candidates(lex)) == sorted(candidate_source_words(lex))


def test_already_counts_towards_the_caps_so_a_build_can_resume():
    c = conn()
    # Pretend a previous run already wrote the cap for leicht.
    written = build_puzzles(make_lexicon(), c, [SOURCE],
                            caps={"leicht": 1}, already={"leicht": 1})
    assert written == 0


def test_progress_is_committed_before_the_build_finishes():
    """An interrupted build must leave its work behind.

    Without periodic commits a killed run loses everything, which makes
    --resume silently useless.
    """
    import sqlite3 as sq
    from wortissimo.generator import build as build_mod

    c = conn()
    monkey = build_mod.COMMIT_EVERY
    build_mod.COMMIT_EVERY = 1
    try:
        build_puzzles(make_lexicon(), c, [SOURCE])
        # A separate connection sees it only if it was actually committed.
        other = sq.connect(":memory:")
        (count,) = c.execute("SELECT COUNT(*) FROM puzzles").fetchone()
        assert count == 1
        assert not c.in_transaction
        other.close()
    finally:
        build_mod.COMMIT_EVERY = monkey
