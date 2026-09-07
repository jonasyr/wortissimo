"""Single-device mode: two stateless endpoints, no room, no game record."""

import sqlite3

import pytest
from fastapi.testclient import TestClient

from wortissimo.generator.solve import Category, Solution
from wortissimo.generator.store import create_schema as create_puzzle_schema
from wortissimo.generator.store import insert_puzzle
from wortissimo.server.app import create_app

SOURCE = "strassenbahnhalte"
REVEALED = ["bahn", "halte", "strasse", "rasse"]


@pytest.fixture
def client(tmp_path):
    ppath = tmp_path / "puzzles.sqlite"
    pconn = sqlite3.connect(ppath)
    create_puzzle_schema(pconn)
    insert_puzzle(pconn, SOURCE, "mittel",
                  [Solution(w, Category.OBVIOUS_COMPONENT, 5.0) for w in REVEALED],
                  {}, accepted_only=["enbahn"])
    pconn.commit()
    pconn.close()
    return TestClient(create_app(puzzles_path=ppath,
                                 games_path=tmp_path / "games.sqlite",
                                 static_dir=None))


def test_solo_puzzle_returns_a_playable_round(client):
    body = client.get("/api/solo/puzzle?difficulty=mittel").json()
    assert body["source_word"] == SOURCE
    assert body["solution_count"] == len(body["solutions"])
    assert body["solution_count"] > 0


def test_solo_puzzle_ships_the_solutions(client):
    # Acceptable here and only here: one device, one room, revealed anyway.
    assert set(client.get("/api/solo/puzzle?difficulty=mittel").json()["solutions"]) \
        == set(REVEALED)


def test_solo_puzzle_never_ships_accepted_only_words(client):
    # Those are scored if typed but never shown, and this screen shows
    # everything it is given.
    assert "enbahn" not in client.get(
        "/api/solo/puzzle?difficulty=mittel").json()["solutions"]


def test_solo_puzzle_rejects_an_unknown_difficulty(client):
    assert client.get("/api/solo/puzzle?difficulty=unmoeglich").status_code == 404


def test_solo_score_awards_the_unique_bonus(client):
    body = client.post("/api/solo/score", json={
        "solutions": ["bahn", "halte", "strasse"],
        "claims": {"Jonas": ["bahn"], "Freundin": ["halte"]},
    }).json()
    assert {s["player"]: s["points"] for s in body["scores"]} == {
        "Jonas": 2, "Freundin": 2}


def test_solo_score_halves_the_bonus_for_a_shared_word(client):
    body = client.post("/api/solo/score", json={
        "solutions": ["bahn", "halte"],
        "claims": {"Jonas": ["bahn"], "Freundin": ["bahn"]},
    }).json()
    assert {s["points"] for s in body["scores"]} == {1}
    assert body["shared_words"] == ["bahn"]
    assert body["missed_words"] == ["halte"]


def test_solo_score_matches_the_live_game_for_the_same_words(client):
    """One definition of scoring, or two people argue at a table."""
    from wortissimo.rules.scoring import score_round

    solutions = ["bahn", "halte", "strasse", "rasse"]
    claims = {"Jonas": ["bahn", "halte"], "Freundin": ["halte"]}
    body = client.post("/api/solo/score",
                       json={"solutions": solutions, "claims": claims}).json()
    expected = score_round(claims, solutions)
    assert {s["player"]: s["points"] for s in body["scores"]} == {
        s.player: s.points for s in expected.scores}
    assert body["missed_words"] == list(expected.missed_words)


def test_solo_score_handles_a_player_who_found_nothing(client):
    body = client.post("/api/solo/score", json={
        "solutions": ["bahn"],
        "claims": {"Jonas": ["bahn"], "Freundin": []},
    }).json()
    assert {s["player"]: s["points"] for s in body["scores"]} == {
        "Jonas": 2, "Freundin": 0}


def test_solo_score_handles_three_players(client):
    body = client.post("/api/solo/score", json={
        "solutions": ["bahn", "halte", "strasse"],
        "claims": {"A": ["bahn"], "B": ["bahn"], "C": ["halte"]},
    }).json()
    points = {s["player"]: s["points"] for s in body["scores"]}
    assert points == {"A": 1, "B": 1, "C": 2}


def test_solo_endpoints_create_no_game_record(client, tmp_path):
    client.get("/api/solo/puzzle?difficulty=mittel")
    client.post("/api/solo/score", json={"solutions": ["bahn"],
                                         "claims": {"A": ["bahn"]}})
    conn = sqlite3.connect(tmp_path / "games.sqlite")
    (games,) = conn.execute("SELECT COUNT(*) FROM games").fetchone()
    assert games == 0
