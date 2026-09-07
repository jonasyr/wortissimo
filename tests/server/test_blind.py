"""Blind scoring: verdicts are withheld until the round ends.

The point of the mode is that you do not learn whether a word counted, so
these tests are mostly about what is NOT revealed.
"""

import sqlite3

import pytest

from wortissimo.generator.solve import Category, Solution
from wortissimo.generator.store import create_schema as create_puzzle_schema
from wortissimo.generator.store import insert_puzzle
from wortissimo.server.db import create_game, create_schema
from wortissimo.server.puzzles import PuzzleRepo
from wortissimo.server.room import Room

SOURCE = "strassenbahnhalte"
REVEALED = ["bahn", "halte", "strasse", "rasse"]


def build(tmp_path, blind: bool):
    ppath = tmp_path / "p.sqlite"
    pconn = sqlite3.connect(ppath)
    create_puzzle_schema(pconn)
    for i in range(3):
        insert_puzzle(pconn, SOURCE + ("n" * i), "mittel",
                      [Solution(w, Category.OBVIOUS_COMPONENT, 5.0) for w in REVEALED],
                      {}, accepted_only=["enbahn"])
    pconn.commit()
    pconn.close()
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    gid = create_game(conn, "ABCD", {})
    return Room(conn, PuzzleRepo(ppath), gid, "ABCD",
                {"rounds": 3, "round_seconds": 180, "blind": blind})


@pytest.fixture
def blind_room(tmp_path):
    return build(tmp_path, blind=True)


@pytest.fixture
def open_room(tmp_path):
    return build(tmp_path, blind=False)


def test_blind_ack_hides_the_verdict_for_a_wrong_word(blind_room):
    p = blind_room.join("A", None)
    blind_room.start_round(now_ms=0)
    ack = blind_room.submit(p.id, "u1", "quatschwort", 1000)
    assert ack.accepted is None
    assert ack.reason is None


def test_blind_ack_hides_the_verdict_for_a_right_word(blind_room):
    p = blind_room.join("A", None)
    blind_room.start_round(now_ms=0)
    ack = blind_room.submit(p.id, "u1", "bahn", 1000)
    assert ack.accepted is None


def test_blind_ack_hides_a_duplicate(blind_room):
    p = blind_room.join("A", None)
    blind_room.start_round(now_ms=0)
    blind_room.submit(p.id, "u1", "bahn", 1000)
    # A "schon gefunden" flash would give the game away just as surely.
    assert blind_room.submit(p.id, "u2", "bahn", 1100).accepted is None


def test_the_open_mode_still_reports_verdicts(open_room):
    p = open_room.join("A", None)
    open_room.start_round(now_ms=0)
    assert open_room.submit(p.id, "u1", "bahn", 1000).accepted is True
    assert open_room.submit(p.id, "u2", "quatschwort", 1100).accepted is False


def test_blind_mode_still_records_the_real_verdict(blind_room):
    p = blind_room.join("A", None)
    blind_room.start_round(now_ms=0)
    blind_room.submit(p.id, "u1", "bahn", 1000)
    blind_room.submit(p.id, "u2", "quatschwort", 1100)
    assert blind_room.snapshot(p.id).my_words == ["bahn"]


def test_blind_scoring_is_unchanged(blind_room):
    a, b = blind_room.join("A", None), blind_room.join("B", None)
    blind_room.start_round(now_ms=0)
    blind_room.submit(a.id, "u1", "bahn", 1000)
    blind_room.submit(b.id, "u2", "halte", 1000)
    ended = blind_room.end_round(now_ms=200_000)
    assert {s["points"] for s in ended.result["scores"]} == {2}


def test_progress_counts_entries_not_accepted_words(blind_room):
    """The leak this exists to prevent.

    If progress counted accepted words, the opponent's counter would tick
    only on valid entries - telling them exactly what blind mode is meant
    to withhold.
    """
    p = blind_room.join("A", None)
    blind_room.start_round(now_ms=0)
    blind_room.submit(p.id, "u1", "quatschwort", 1000)
    blind_room.submit(p.id, "u2", "nochquatsch", 1100)
    assert blind_room.entered_count(p.id) == 2
    assert blind_room.progress_count(p.id) == 0


def test_round_result_lists_words_that_were_wrong(blind_room):
    p = blind_room.join("A", None)
    blind_room.start_round(now_ms=0)
    blind_room.submit(p.id, "u1", "bahn", 1000)
    blind_room.submit(p.id, "u2", "quatschwort", 1100)
    ended = blind_room.end_round(now_ms=200_000)
    assert ended.result["rejected"][p.id] == ["quatschwort"]


def test_rejected_list_is_present_even_when_empty(blind_room):
    p = blind_room.join("A", None)
    blind_room.start_round(now_ms=0)
    blind_room.submit(p.id, "u1", "bahn", 1000)
    ended = blind_room.end_round(now_ms=200_000)
    assert ended.result["rejected"][p.id] == []


def test_rejected_words_are_not_duplicated(blind_room):
    p = blind_room.join("A", None)
    blind_room.start_round(now_ms=0)
    blind_room.submit(p.id, "u1", "quatschwort", 1000)
    blind_room.submit(p.id, "u2", "quatschwort", 1100)
    ended = blind_room.end_round(now_ms=200_000)
    assert ended.result["rejected"][p.id] == ["quatschwort"]


def test_blind_survives_a_reconnect(blind_room):
    """A reconnecting client must not silently fall back to live verdicts."""
    p = blind_room.join("A", None)
    blind_room.start_round(now_ms=0)
    assert blind_room.snapshot(p.id).blind is True


def test_open_mode_reports_blind_false(open_room):
    p = open_room.join("A", None)
    open_room.start_round(now_ms=0)
    assert open_room.snapshot(p.id).blind is False
