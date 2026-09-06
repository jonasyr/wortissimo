"""Adversarial two-player tests.

This is the case the game exists for, so it gets hostile treatment: same
names, empty names, reconnects mid-round, a player who never shows up, a
third wheel, and both players racing the same controls.
"""

import sqlite3

import pytest

from wortissimo.generator.solve import Category, Solution
from wortissimo.generator.store import create_schema as create_puzzle_schema
from wortissimo.generator.store import insert_puzzle
from wortissimo.rules.validate import Rejection
from wortissimo.server.db import create_game, create_schema
from wortissimo.server.puzzles import PuzzleRepo
from wortissimo.server.room import Room

SOURCE = "strassenbahnhalte"
REVEALED = ["bahn", "halte", "strasse", "rasse", "assen"]


@pytest.fixture
def room(tmp_path):
    ppath = tmp_path / "puzzles.sqlite"
    pconn = sqlite3.connect(ppath)
    create_puzzle_schema(pconn)
    for i in range(4):
        insert_puzzle(
            pconn, SOURCE + ("n" * i), "mittel",
            [Solution(w, Category.OBVIOUS_COMPONENT, 5.0) for w in REVEALED],
            {}, accepted_only=["enbahn"],
        )
    pconn.commit()
    pconn.close()

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    gid = create_game(conn, "ABCD", {})
    return Room(conn, PuzzleRepo(ppath), gid, "ABCD",
                {"difficulty": "mittel", "rounds": 3, "round_seconds": 180})


def scores_by_name(ended):
    return {s["name"]: s["points"] for s in ended.result["scores"]}


# ---------- identity ----------

def test_two_players_with_the_same_name_stay_separate(room):
    """The lobby sends "Spieler" when the name box is left empty.

    Keying identity on the name made both players one person: shared word
    list, no unique-word bonus, the two-player game silently became
    solitaire.
    """
    a = room.join("Spieler", None)
    b = room.join("Spieler", None)
    assert a.id != b.id
    assert len(room.roster()) == 2


def test_same_named_players_do_not_share_a_word_list(room):
    a = room.join("Spieler", None)
    b = room.join("Spieler", None)
    room.start_round(now_ms=0)
    room.submit(a.id, "u1", "bahn", 1000)
    assert room.snapshot(a.id).my_words == ["bahn"]
    assert room.snapshot(b.id).my_words == []


def test_same_named_players_still_score_the_unique_bonus(room):
    a = room.join("Spieler", None)
    b = room.join("Spieler", None)
    room.start_round(now_ms=0)
    room.submit(a.id, "u1", "bahn", 1000)
    room.submit(b.id, "u2", "halte", 1000)
    ended = room.end_round(now_ms=200_000)
    points = [s["points"] for s in ended.result["scores"]]
    assert points == [2, 2]


def test_a_players_display_name_survives_into_the_result(room):
    a = room.join("Jonas", None)
    room.join("Freundin", None)
    room.start_round(now_ms=0)
    room.submit(a.id, "u1", "bahn", 1000)
    ended = room.end_round(now_ms=200_000)
    assert set(scores_by_name(ended)) == {"Jonas", "Freundin"}


def test_rejoining_with_a_token_keeps_the_same_identity_and_words(room):
    a = room.join("Jonas", None)
    room.start_round(now_ms=0)
    room.submit(a.id, "u1", "bahn", 1000)
    again = room.join("Jonas", a.token)
    assert again.id == a.id
    assert room.snapshot(again.id).my_words == ["bahn"]
    assert len(room.roster()) == 1


def test_an_unknown_token_does_not_hijack_another_player(room):
    a = room.join("Jonas", None)
    b = room.join("Freundin", "not-a-real-token")
    assert b.id != a.id
    assert len(room.roster()) == 2


# ---------- scoring ----------

def test_a_word_both_players_find_scores_one_each(room):
    a, b = room.join("A", None), room.join("B", None)
    room.start_round(now_ms=0)
    room.submit(a.id, "u1", "bahn", 1000)
    room.submit(b.id, "u2", "bahn", 1100)
    ended = room.end_round(now_ms=200_000)
    assert scores_by_name(ended) == {"A": 1, "B": 1}
    assert ended.result["shared_words"] == ["bahn"]


def test_order_of_submission_does_not_change_the_score(room):
    a, b = room.join("A", None), room.join("B", None)
    room.start_round(now_ms=0)
    room.submit(b.id, "u1", "bahn", 1000)
    room.submit(a.id, "u2", "bahn", 2000)
    assert scores_by_name(room.end_round(now_ms=200_000)) == {"A": 1, "B": 1}


def test_a_player_who_never_submits_scores_zero_and_still_appears(room):
    a, b = room.join("A", None), room.join("B", None)
    room.start_round(now_ms=0)
    room.submit(a.id, "u1", "bahn", 1000)
    ended = room.end_round(now_ms=200_000)
    assert scores_by_name(ended) == {"A": 2, "B": 0}


def test_totals_accumulate_across_rounds_for_both_players(room):
    a, b = room.join("A", None), room.join("B", None)
    room.start_round(now_ms=0)
    room.submit(a.id, "u1", "bahn", 1000)
    room.end_round(now_ms=200_000)
    room.start_round(now_ms=300_000)
    room.submit(b.id, "u2", "halte", 301_000)
    ended = room.end_round(now_ms=500_000)
    totals = ended.result["totals"]
    assert totals[a.id] == 2 and totals[b.id] == 2


def test_one_player_cannot_score_the_same_word_twice(room):
    a, b = room.join("A", None), room.join("B", None)
    room.start_round(now_ms=0)
    room.submit(a.id, "u1", "bahn", 1000)
    assert room.submit(a.id, "u2", "bahn", 2000).reason == Rejection.DUPLICATE
    assert scores_by_name(room.end_round(now_ms=200_000))["A"] == 2


# ---------- round control ----------

def test_only_one_round_starts_when_both_players_tap_start(room):
    room.join("A", None)
    room.join("B", None)
    first = room.start_round(now_ms=0)
    assert room.start_round(now_ms=10) is None
    assert room.round is not None and room.round.idx == first.idx


def test_a_late_submission_from_either_player_is_refused(room):
    a, b = room.join("A", None), room.join("B", None)
    room.start_round(now_ms=0)
    assert room.submit(a.id, "u1", "bahn", 999_999).reason == Rejection.TOO_LATE
    assert room.submit(b.id, "u2", "halte", 999_999).reason == Rejection.TOO_LATE


def test_a_source_word_never_repeats_across_a_whole_game(room):
    room.join("A", None)
    seen = []
    for i in range(3):
        started = room.start_round(now_ms=i * 300_000)
        assert started is not None, i
        seen.append(started.source_word)
        room.end_round(now_ms=i * 300_000 + 200_000)
    assert len(set(seen)) == len(seen)


def test_the_game_ends_after_the_configured_round_count(room):
    room.join("A", None)
    for i in range(3):
        assert room.start_round(now_ms=i * 300_000) is not None
        room.end_round(now_ms=i * 300_000 + 200_000)
    assert room.is_finished
    assert room.start_round(now_ms=9_000_000) is None


# ---------- late arrival ----------

def test_a_player_joining_mid_round_sees_the_word_but_no_solutions(room):
    room.join("A", None)
    started = room.start_round(now_ms=0)
    late = room.join("B", None)
    snap = room.snapshot(late.id)
    assert snap.round is not None
    assert snap.round.source_word == started.source_word
    assert snap.my_words == []


def test_a_player_joining_mid_round_can_still_score(room):
    room.join("A", None)
    room.start_round(now_ms=0)
    late = room.join("B", None)
    assert room.submit(late.id, "u1", "bahn", 5000).accepted is True
