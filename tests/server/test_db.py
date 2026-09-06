import sqlite3

import pytest

from wortissimo.server.db import (
    accepted_words, create_game, create_round, create_schema,
    get_game_by_code, record_submission, used_puzzle_ids,
)


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    create_schema(c)
    return c


def test_creates_and_finds_a_game(conn):
    create_game(conn, "ABCD", {"rounds": 10, "difficulty": "mittel"})
    row = get_game_by_code(conn, "ABCD")
    assert row["code"] == "ABCD"
    assert row["state"] == "lobby"


def test_unknown_code_returns_none(conn):
    assert get_game_by_code(conn, "ZZZZ") is None


def test_game_code_is_unique(conn):
    create_game(conn, "ABCD", {})
    with pytest.raises(sqlite3.IntegrityError):
        create_game(conn, "ABCD", {})


def test_records_a_submission(conn):
    gid = create_game(conn, "ABCD", {})
    rid = create_round(conn, gid, 0, puzzle_id=1, ends_at=1000)
    assert record_submission(conn, rid, "jw", "bahn", "uuid-1", True, None, 500)


def test_replaying_the_same_uuid_is_ignored(conn):
    """The core reconnect guarantee: replay must not double-score."""
    gid = create_game(conn, "ABCD", {})
    rid = create_round(conn, gid, 0, 1, 1000)
    assert record_submission(conn, rid, "jw", "bahn", "uuid-1", True, None, 500)
    assert not record_submission(conn, rid, "jw", "bahn", "uuid-1", True, None, 600)
    (count,) = conn.execute("SELECT COUNT(*) FROM submissions").fetchone()
    assert count == 1


def test_accepted_words_groups_by_player(conn):
    gid = create_game(conn, "ABCD", {})
    rid = create_round(conn, gid, 0, 1, 1000)
    record_submission(conn, rid, "jw", "bahn", "u1", True, None, 1)
    record_submission(conn, rid, "jw", "halte", "u2", True, None, 2)
    record_submission(conn, rid, "gf", "bahn", "u3", True, None, 3)
    assert accepted_words(conn, rid) == {"jw": ["bahn", "halte"], "gf": ["bahn"]}


def test_rejected_submissions_are_stored_but_not_scored(conn):
    gid = create_game(conn, "ABCD", {})
    rid = create_round(conn, gid, 0, 1, 1000)
    record_submission(conn, rid, "jw", "xxx", "u1", False, "not_in_dictionary", 1)
    assert accepted_words(conn, rid) == {}
    (count,) = conn.execute("SELECT COUNT(*) FROM submissions").fetchone()
    assert count == 1


def test_round_index_is_unique_per_game(conn):
    gid = create_game(conn, "ABCD", {})
    create_round(conn, gid, 0, 1, 1000)
    with pytest.raises(sqlite3.IntegrityError):
        create_round(conn, gid, 0, 2, 2000)


def test_used_puzzle_ids_prevents_repeats_within_a_game(conn):
    gid = create_game(conn, "ABCD", {})
    create_round(conn, gid, 0, 7, 1000)
    create_round(conn, gid, 1, 9, 2000)
    assert used_puzzle_ids(conn, gid) == {7, 9}


def test_used_puzzle_ids_is_scoped_to_one_game(conn):
    a = create_game(conn, "AAAA", {})
    b = create_game(conn, "BBBB", {})
    create_round(conn, a, 0, 7, 1000)
    assert used_puzzle_ids(conn, b) == set()
