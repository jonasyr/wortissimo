import pytest
from pydantic import ValidationError

from wortissimo.server.protocol import (
    Join, OpponentProgress, RoundStarted, StateSync, Submit,
    parse_client_message,
)


def test_parses_a_submit_message():
    msg = parse_client_message(
        '{"type":"submit","client_uuid":"u1","word":"Bahn","round_idx":0}'
    )
    assert isinstance(msg, Submit)
    assert msg.word == "Bahn"


def test_parses_a_join_message():
    msg = parse_client_message('{"type":"join","code":"ABCD","player":"jw"}')
    assert isinstance(msg, Join)
    assert msg.code == "ABCD"
    assert msg.rejoin_token is None


def test_rejects_an_unknown_message_type():
    with pytest.raises(ValidationError):
        parse_client_message('{"type":"launch_missiles"}')


def test_rejects_a_submit_missing_its_uuid():
    with pytest.raises(ValidationError):
        parse_client_message('{"type":"submit","word":"Bahn","round_idx":0}')


def test_rejects_malformed_json():
    with pytest.raises(ValidationError):
        parse_client_message("{not json")


def test_round_started_does_not_expose_solutions():
    msg = RoundStarted(idx=0, source_word="strassenbahn",
                       round_ends_at=1000, solution_count=12)
    dumped = msg.model_dump()
    assert "solutions" not in dumped
    assert "revealed" not in dumped
    assert "accepted" not in dumped
    assert dumped["solution_count"] == 12


def test_opponent_progress_carries_a_count_only():
    dumped = OpponentProgress(player="gf", count=7).model_dump()
    assert dumped == {"type": "opponent_progress", "player": "gf", "count": 7}


def test_state_sync_carries_only_the_players_own_words():
    dumped = StateSync(state="playing", my_words=["bahn"]).model_dump()
    assert dumped["my_words"] == ["bahn"]
    assert "opponent_words" not in dumped
    assert "revealed" not in dumped


def test_word_length_is_bounded():
    with pytest.raises(ValidationError):
        parse_client_message(
            '{"type":"submit","client_uuid":"u1","word":"' + "a" * 200
            + '","round_idx":0}'
        )


def test_code_length_is_bounded():
    with pytest.raises(ValidationError):
        parse_client_message(
            '{"type":"join","code":"' + "A" * 40 + '","player":"jw"}'
        )
