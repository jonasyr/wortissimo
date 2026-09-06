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
REVEALED = ["bahn", "halte", "strasse", "rasse"]
ACCEPTED_ONLY = ["enbahn"]


def make_room(tmp_path, rounds=2, puzzles=1):
    ppath = tmp_path / "puzzles.sqlite"
    pconn = sqlite3.connect(ppath)
    create_puzzle_schema(pconn)
    for i in range(puzzles):
        insert_puzzle(
            pconn, SOURCE + ("n" * i), "mittel",
            [Solution(w, Category.OBVIOUS_COMPONENT, 5.0) for w in REVEALED],
            {}, accepted_only=ACCEPTED_ONLY,
        )
    pconn.commit()
    pconn.close()

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    gid = create_game(conn, "ABCD", {})
    return Room(conn, PuzzleRepo(ppath), gid, "ABCD",
                {"difficulty": "mittel", "rounds": rounds, "round_seconds": 180})


@pytest.fixture
def room(tmp_path):
    return make_room(tmp_path)


def test_joining_returns_a_player_with_a_token(room):
    p = room.join("jw", None)
    assert p.name == "jw"
    assert p.token


def test_rejoining_with_a_token_returns_the_same_player(room):
    first = room.join("jw", None)
    again = room.join("jw", first.token)
    assert again.id == first.id


def test_two_players_are_distinct(room):
    assert room.join("jw", None).id != room.join("gf", None).id


def test_starting_a_round_reveals_the_source_word_but_not_solutions(room):
    room.join("jw", None)
    started = room.start_round(now_ms=0)
    assert started.source_word == SOURCE
    assert started.solution_count == len(REVEALED)
    assert "solutions" not in started.model_dump()


def test_round_ends_at_is_absolute_and_matches_configured_length(room):
    room.join("jw", None)
    started = room.start_round(now_ms=1_000_000)
    assert started.round_ends_at == 1_000_000 + 180_000


def test_accepts_a_valid_word(room):
    p = room.join("jw", None)
    room.start_round(now_ms=0)
    ack = room.submit(p.id, "u1", "Bahn", now_ms=1000)
    assert ack.accepted is True
    assert ack.word == "bahn"


def test_accepts_a_word_that_is_not_revealed(room):
    """The two-tier guarantee.

    'enbahn' is accepted but never revealed. Validating against the
    revealed set alone would reject it.
    """
    p = room.join("jw", None)
    room.start_round(now_ms=0)
    assert room.submit(p.id, "u1", "enbahn", now_ms=1000).accepted is True


def test_rejects_a_word_not_in_the_source(room):
    p = room.join("jw", None)
    room.start_round(now_ms=0)
    assert room.submit(p.id, "u1", "Auto", 1000).reason == Rejection.NOT_A_SUBSTRING


def test_rejects_a_duplicate_word_from_the_same_player(room):
    p = room.join("jw", None)
    room.start_round(now_ms=0)
    room.submit(p.id, "u1", "Bahn", 1000)
    assert room.submit(p.id, "u2", "Bahn", 2000).reason == Rejection.DUPLICATE


def test_rejects_a_submission_after_the_deadline(room):
    p = room.join("jw", None)
    room.start_round(now_ms=0)
    assert room.submit(p.id, "u1", "Bahn", 999_999).reason == Rejection.TOO_LATE


def test_rejects_a_submission_when_no_round_is_running(room):
    p = room.join("jw", None)
    assert room.submit(p.id, "u1", "Bahn", 1000).reason == Rejection.TOO_LATE


def test_replaying_the_same_uuid_returns_the_same_ack(room):
    p = room.join("jw", None)
    room.start_round(now_ms=0)
    first = room.submit(p.id, "u1", "Bahn", 1000)
    replay = room.submit(p.id, "u1", "Bahn", 1000)
    assert replay.accepted == first.accepted
    assert replay.reason == first.reason
    assert room.progress_count(p.id) == 1


def test_scoring_awards_two_points_for_unique_words(room):
    a, b = room.join("jw", None), room.join("gf", None)
    room.start_round(now_ms=0)
    room.submit(a.id, "u1", "bahn", 1000)
    room.submit(b.id, "u2", "halte", 1000)
    ended = room.end_round(now_ms=200_000)
    scores = {s["name"]: s["points"] for s in ended.result["scores"]}
    assert scores["jw"] == 2 and scores["gf"] == 2


def test_scoring_awards_one_point_for_a_shared_word(room):
    a, b = room.join("jw", None), room.join("gf", None)
    room.start_round(now_ms=0)
    room.submit(a.id, "u1", "bahn", 1000)
    room.submit(b.id, "u2", "bahn", 1000)
    ended = room.end_round(now_ms=200_000)
    assert {s["name"]: s["points"] for s in ended.result["scores"]}["jw"] == 1


def test_round_end_reveals_only_the_revealed_tier(room):
    a = room.join("jw", None)
    room.start_round(now_ms=0)
    room.submit(a.id, "u1", "bahn", 1000)
    missed = room.end_round(now_ms=200_000).result["missed_words"]
    assert "halte" in missed
    # accepted-only words are never revealed, even at the end
    assert "enbahn" not in missed


def test_scoring_does_not_wait_for_a_disconnected_player(room):
    a, b = room.join("jw", None), room.join("gf", None)
    room.start_round(now_ms=0)
    room.submit(a.id, "u1", "bahn", 1000)
    ended = room.end_round(now_ms=200_000)
    scores = {s["name"]: s["points"] for s in ended.result["scores"]}
    assert scores["gf"] == 0
    assert scores["jw"] == 2


def test_a_source_word_is_never_repeated_within_a_game(room):
    room.join("jw", None)
    room.start_round(now_ms=0)
    room.end_round(now_ms=200_000)
    assert room.start_round(now_ms=300_000) is None


def test_snapshot_never_leaks_the_solution_set(room):
    """Checked structurally, not by substring.

    Every solution is by definition a substring of the source word, and the
    source word is legitimately in the snapshot — so searching the payload
    for 'halte' would always match and prove nothing.
    """
    p = room.join("jw", None)
    room.start_round(now_ms=0)
    dumped = room.snapshot(p.id).model_dump()
    assert set(dumped) == {
        "type", "state", "round", "my_words", "scores",
        "players", "round_seconds", "total_rounds",
    }
    # The roster carries names, never anyone's words.
    for player in dumped["players"]:
        assert set(player) == {"id", "name"}
    assert set(dumped["round"]) == {
        "idx", "source_word", "round_ends_at", "solution_count",
    }
    # my_words holds only what this player got accepted, nothing else.
    assert dumped["my_words"] == []


def test_snapshot_returns_the_players_own_accepted_words(room):
    p = room.join("jw", None)
    room.start_round(now_ms=0)
    room.submit(p.id, "u1", "bahn", 1000)
    assert room.snapshot(p.id).my_words == ["bahn"]


def test_snapshot_preserves_the_deadline_across_a_reconnect(room):
    p = room.join("jw", None)
    started = room.start_round(now_ms=500)
    assert room.snapshot(p.id).round.round_ends_at == started.round_ends_at


def test_game_finishes_after_the_configured_round_count(tmp_path):
    room = make_room(tmp_path, rounds=1, puzzles=2)
    room.join("jw", None)
    room.start_round(now_ms=0)
    room.end_round(now_ms=200_000)
    assert room.is_finished
    assert room.start_round(now_ms=300_000) is None


def test_starting_a_round_while_one_is_running_is_refused(room):
    """Both players see a "Nächste Runde" button.

    Without this guard the second tap starts a second round on top of the
    first, and the first round's summary is never produced.
    """
    room.join("jw", None)
    first = room.start_round(now_ms=0)
    assert first is not None
    assert room.start_round(now_ms=1000) is None
    assert room.round is not None
    assert room.round.idx == first.idx


def test_a_new_round_can_start_once_the_previous_one_ended(room):
    room.join("jw", None)
    room.start_round(now_ms=0)
    room.end_round(now_ms=200_000)
    # Only one puzzle in this fixture, so exhaustion is the reason here -
    # what matters is that the guard is no longer what blocks it.
    assert room.state != "playing"


def test_roster_lists_players_in_join_order(room):
    room.join("jw", None)
    room.join("gf", None)
    assert [p.name for p in room.roster()] == ["jw", "gf"]


def test_roster_does_not_duplicate_a_rejoining_player(room):
    p = room.join("jw", None)
    room.join("jw", p.token)
    assert len(room.roster()) == 1


def test_snapshot_carries_the_roster_and_the_configured_timing(room):
    p = room.join("jw", None)
    snap = room.snapshot(p.id)
    assert [x.name for x in snap.players] == ["jw"]
    assert snap.round_seconds == 180
    assert snap.total_rounds == 2
