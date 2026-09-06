import json
import sqlite3
import time

import pytest
from fastapi.testclient import TestClient

from wortissimo.generator.solve import Category, Solution
from wortissimo.generator.store import create_schema as create_puzzle_schema
from wortissimo.generator.store import insert_puzzle
from wortissimo.server.app import create_app

SOURCE = "strassenbahnhalte"
REVEALED = ["bahn", "halte", "strasse", "rasse"]
ACCEPTED_ONLY = ["enbahn"]


@pytest.fixture
def client(tmp_path):
    ppath = tmp_path / "puzzles.sqlite"
    pconn = sqlite3.connect(ppath)
    create_puzzle_schema(pconn)
    for i in range(3):
        insert_puzzle(
            pconn, SOURCE + ("n" * i), "mittel",
            [Solution(w, Category.OBVIOUS_COMPONENT, 5.0) for w in REVEALED],
            {}, accepted_only=ACCEPTED_ONLY,
        )
    pconn.commit()
    pconn.close()
    app = create_app(puzzles_path=ppath, games_path=tmp_path / "games.sqlite",
                     static_dir=None)
    return TestClient(app)


def new_game(client, **config):
    body = {"difficulty": "mittel", "rounds": 2, "round_seconds": 180, **config}
    return client.post("/api/games", json=body).json()["code"]


def recv_until(ws, want, limit=25):
    for _ in range(limit):
        msg = json.loads(ws.receive_text())
        if msg["type"] == want:
            return msg
    raise AssertionError(f"never received {want}")


def join(ws, code, player="jw", token=None):
    payload = {"type": "join", "code": code, "player": player}
    if token:
        payload["rejoin_token"] = token
    ws.send_text(json.dumps(payload))
    return recv_until(ws, "joined")


def test_health_endpoint(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_creating_a_game_returns_a_code(client):
    assert len(new_game(client)) == 4


def test_game_codes_avoid_ambiguous_letters(client):
    for _ in range(5):
        assert not set(new_game(client)) & {"I", "O"}


def test_join_returns_a_rejoin_token(client):
    code = new_game(client)
    with client.websocket_connect("/ws") as ws:
        assert join(ws, code)["rejoin_token"]


def test_ping_returns_server_time_and_echoes_t0(client):
    code = new_game(client)
    with client.websocket_connect("/ws") as ws:
        join(ws, code)
        ws.send_text(json.dumps({"type": "ping", "t0": 12345}))
        pong = recv_until(ws, "pong")
        assert pong["t0"] == 12345
        assert pong["server_time"] > 0


def test_starting_a_round_broadcasts_the_source_word(client):
    code = new_game(client)
    with client.websocket_connect("/ws") as ws:
        join(ws, code)
        ws.send_text(json.dumps({"type": "start_round"}))
        started = recv_until(ws, "round_started")
        assert started["source_word"].startswith(SOURCE)
        assert started["round_ends_at"] > 0
        assert "solutions" not in started


def test_submitting_a_valid_word_is_acked(client):
    code = new_game(client)
    with client.websocket_connect("/ws") as ws:
        join(ws, code)
        ws.send_text(json.dumps({"type": "start_round"}))
        recv_until(ws, "round_started")
        ws.send_text(json.dumps({"type": "submit", "client_uuid": "u1",
                                 "word": "Bahn", "round_idx": 0}))
        ack = recv_until(ws, "ack")
        assert ack["accepted"] is True and ack["client_uuid"] == "u1"


def test_accepted_only_word_is_accepted_over_the_wire(client):
    code = new_game(client)
    with client.websocket_connect("/ws") as ws:
        join(ws, code)
        ws.send_text(json.dumps({"type": "start_round"}))
        recv_until(ws, "round_started")
        ws.send_text(json.dumps({"type": "submit", "client_uuid": "u1",
                                 "word": "enbahn", "round_idx": 0}))
        assert recv_until(ws, "ack")["accepted"] is True


def test_reconnect_resyncs_state_and_own_words(client):
    """The core iOS-suspension scenario: drop mid-round, come back."""
    code = new_game(client)
    with client.websocket_connect("/ws") as ws:
        token = join(ws, code)["rejoin_token"]
        ws.send_text(json.dumps({"type": "start_round"}))
        started = recv_until(ws, "round_started")
        ws.send_text(json.dumps({"type": "submit", "client_uuid": "u1",
                                 "word": "bahn", "round_idx": 0}))
        recv_until(ws, "ack")

    # Socket is gone, as it would be after the phone locked.
    with client.websocket_connect("/ws") as ws:
        join(ws, code, token=token)
        state = recv_until(ws, "state")
        assert state["round"]["source_word"] == started["source_word"]
        assert state["round"]["round_ends_at"] == started["round_ends_at"]
        assert state["my_words"] == ["bahn"]


def test_outbox_replay_after_reconnect_does_not_double_score(client):
    code = new_game(client)
    with client.websocket_connect("/ws") as ws:
        token = join(ws, code)["rejoin_token"]
        ws.send_text(json.dumps({"type": "start_round"}))
        recv_until(ws, "round_started")
        ws.send_text(json.dumps({"type": "submit", "client_uuid": "u1",
                                 "word": "bahn", "round_idx": 0}))
        recv_until(ws, "ack")

    with client.websocket_connect("/ws") as ws:
        join(ws, code, token=token)
        recv_until(ws, "state")
        # Replay the same UUID, as the outbox would on reconnect.
        ws.send_text(json.dumps({"type": "submit", "client_uuid": "u1",
                                 "word": "bahn", "round_idx": 0}))
        assert recv_until(ws, "ack")["accepted"] is True

    with client.websocket_connect("/ws") as ws:
        join(ws, code, token=token)
        assert recv_until(ws, "state")["my_words"] == ["bahn"]


def test_state_sync_never_contains_the_solution_set(client):
    code = new_game(client)
    with client.websocket_connect("/ws") as ws:
        join(ws, code)
        ws.send_text(json.dumps({"type": "start_round"}))
        recv_until(ws, "round_started")
        ws.send_text(json.dumps({"type": "join", "code": code, "player": "jw"}))
        recv_until(ws, "joined")
        state = recv_until(ws, "state")
        assert set(state["round"]) == {
            "idx", "source_word", "round_ends_at", "solution_count",
        }


def test_joining_an_unknown_code_errors(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "join", "code": "ZZZZ", "player": "jw"}))
        assert recv_until(ws, "error")["message"]


def test_malformed_message_errors_without_closing(client):
    code = new_game(client)
    with client.websocket_connect("/ws") as ws:
        join(ws, code)
        ws.send_text("{not json")
        assert recv_until(ws, "error")["message"]
        # Connection still usable afterwards.
        ws.send_text(json.dumps({"type": "ping", "t0": 1}))
        assert recv_until(ws, "pong")["t0"] == 1


def test_submitting_before_joining_errors(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "submit", "client_uuid": "u1",
                                 "word": "bahn", "round_idx": 0}))
        assert recv_until(ws, "error")["message"]


def test_opponent_sees_a_progress_count_but_no_words(client):
    code = new_game(client)
    with client.websocket_connect("/ws") as a, client.websocket_connect("/ws") as b:
        join(a, code, player="jw")
        join(b, code, player="gf")
        a.send_text(json.dumps({"type": "start_round"}))
        recv_until(a, "round_started")
        recv_until(b, "round_started")
        a.send_text(json.dumps({"type": "submit", "client_uuid": "u1",
                                "word": "bahn", "round_idx": 0}))
        recv_until(a, "ack")
        progress = recv_until(b, "opponent_progress")
        # The id is opaque now; what matters is that only a count travels.
        assert set(progress) == {"type", "player", "count"}
        assert progress["count"] == 1


def test_flagging_a_round_appends_to_the_configured_file(client, tmp_path, monkeypatch):
    from wortissimo.server import app as app_module

    target = tmp_path / "state" / "flagged.txt"
    monkeypatch.setattr(app_module, "FLAGGED_PATH", target)
    assert client.post("/api/flag", json={"source_word": "kalkulation"}).json()["ok"]
    assert target.read_text(encoding="utf-8").strip() == "kalkulation"


def test_round_seconds_accepts_the_full_one_to_thirty_minute_range(client):
    for seconds in (60, 600, 1800):
        res = client.post("/api/games", json={"difficulty": "mittel",
                                              "rounds": 3,
                                              "round_seconds": seconds})
        assert res.status_code == 200, seconds


def test_round_seconds_outside_the_range_is_rejected(client):
    for seconds in (0, 59, 1801, -30):
        res = client.post("/api/games", json={"difficulty": "mittel",
                                              "rounds": 3,
                                              "round_seconds": seconds})
        assert res.status_code == 422, seconds


def test_the_configured_length_is_what_the_round_actually_uses(client):
    code = client.post("/api/games", json={"difficulty": "mittel", "rounds": 2,
                                           "round_seconds": 900}).json()["code"]
    with client.websocket_connect("/ws") as ws:
        join(ws, code)
        ws.send_text(json.dumps({"type": "start_round"}))
        started = recv_until(ws, "round_started")
        # 15 minutes from now, within a generous scheduling margin.
        expected = int(time.time() * 1000) + 900_000
        assert abs(started["round_ends_at"] - expected) < 5_000
