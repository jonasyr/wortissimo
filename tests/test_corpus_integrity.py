"""End-to-end invariants over a built corpus.

These run against data/puzzles.sqlite and are skipped when it is absent.
Unit tests cover each stage in isolation; this file checks the stages
agree with each other, which is where a pipeline actually breaks.
"""

import sqlite3
from pathlib import Path

import pytest

from wortissimo.generator.difficulty import BUCKETS
from wortissimo.rules.validate import validate_word

DB = Path("data/puzzles.sqlite")
pytestmark = pytest.mark.skipif(
    not DB.exists(), reason="no corpus; run scripts/build_puzzles.py"
)


@pytest.fixture(scope="module")
def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


@pytest.fixture(scope="module")
def puzzles(conn):
    return conn.execute(
        "SELECT id, source_word, difficulty, solution_count FROM puzzles"
    ).fetchall()


def words_of(conn, puzzle_id, revealed=None):
    clause = "" if revealed is None else f" AND revealed={revealed}"
    return [w for (w,) in conn.execute(
        f"SELECT word FROM solutions WHERE puzzle_id=?{clause}", (puzzle_id,))]


def test_corpus_is_not_empty(puzzles):
    assert len(puzzles) > 100


def test_every_difficulty_bucket_is_populated(conn):
    present = {r[0] for r in conn.execute("SELECT DISTINCT difficulty FROM puzzles")}
    assert present == {b.difficulty.value for b in BUCKETS}


def test_every_stored_word_validates_through_the_real_rules_path(conn, puzzles):
    """The generator and the live game must agree.

    A word stored as playable that validate_word() rejects would be
    revealed as a "word you missed" and then refused when typed.
    """
    failures = []
    for puzzle in puzzles[:400]:
        accepted = set(words_of(conn, puzzle["id"]))
        for word in accepted:
            verdict = validate_word(word, puzzle["source_word"], accepted)
            if not verdict.accepted:
                failures.append((puzzle["source_word"], word, verdict.reason))
    assert not failures, failures[:10]


def test_every_solution_is_a_substring_of_its_source(conn, puzzles):
    bad = []
    for puzzle in puzzles[:400]:
        for word in words_of(conn, puzzle["id"]):
            if word not in puzzle["source_word"]:
                bad.append((puzzle["source_word"], word))
    assert not bad, bad[:10]


def test_no_solution_equals_its_source_word(conn, puzzles):
    bad = [(p["source_word"], w) for p in puzzles[:400]
           for w in words_of(conn, p["id"]) if w == p["source_word"]]
    assert not bad, bad[:10]


def test_no_solution_is_shorter_than_the_minimum(conn, puzzles):
    bad = [(p["source_word"], w) for p in puzzles[:400]
           for w in words_of(conn, p["id"]) if len(w) < 3]
    assert not bad, bad[:10]


def test_solution_count_matches_the_revealed_rows(conn, puzzles):
    for puzzle in puzzles[:400]:
        revealed = words_of(conn, puzzle["id"], revealed=1)
        assert len(revealed) == puzzle["solution_count"], puzzle["source_word"]


def test_revealed_and_accepted_only_never_overlap(conn, puzzles):
    for puzzle in puzzles[:400]:
        revealed = set(words_of(conn, puzzle["id"], revealed=1))
        hidden = set(words_of(conn, puzzle["id"], revealed=0))
        assert not (revealed & hidden), puzzle["source_word"]


def test_every_puzzle_satisfies_the_bucket_it_was_filed_under(conn, puzzles):
    by_name = {b.difficulty.value: b for b in BUCKETS}
    bad = []
    for puzzle in puzzles:
        bucket = by_name[puzzle["difficulty"]]
        length = len(puzzle["source_word"])
        if not (bucket.min_len <= length <= bucket.max_len):
            bad.append((puzzle["source_word"], "length", length))
        if not (bucket.min_solutions <= puzzle["solution_count"]
                <= bucket.max_solutions):
            bad.append((puzzle["source_word"], "count", puzzle["solution_count"]))
    assert not bad, bad[:10]


def test_source_words_are_unique(conn):
    (dupes,) = conn.execute(
        "SELECT COUNT(*) FROM (SELECT source_word FROM puzzles"
        " GROUP BY source_word HAVING COUNT(*) > 1)"
    ).fetchone()
    assert dupes == 0
