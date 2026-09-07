"""WebSocket message schema.

An invariant is enforced by shape here: no server-to-client message
carries the solution set before the round ends (spec section 8.5).
RoundStarted has a solution_count so the UI can show "3 / 27 gefunden",
but never the words. StateSync carries the player's OWN accepted words
only — never the opponent's.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

MAX_WORD_LENGTH = 64
MAX_CODE_LENGTH = 8


# ---------- client -> server ----------

class Join(BaseModel):
    type: Literal["join"] = "join"
    code: str = Field(min_length=1, max_length=MAX_CODE_LENGTH)
    player: str = Field(min_length=1, max_length=32)
    rejoin_token: str | None = None


class Ping(BaseModel):
    type: Literal["ping"] = "ping"
    t0: int


class Submit(BaseModel):
    type: Literal["submit"] = "submit"
    client_uuid: str = Field(min_length=1, max_length=64)
    word: str = Field(min_length=1, max_length=MAX_WORD_LENGTH)
    round_idx: int


class StartRound(BaseModel):
    type: Literal["start_round"] = "start_round"


ClientMessage = Annotated[
    Join | Ping | Submit | StartRound, Field(discriminator="type")
]
_client_adapter: TypeAdapter[ClientMessage] = TypeAdapter(ClientMessage)


def parse_client_message(raw: str | bytes) -> ClientMessage:
    return _client_adapter.validate_json(raw)


# ---------- server -> client ----------

class PlayerInfo(BaseModel):
    id: str
    name: str


class Players(BaseModel):
    """Who is in the room. Broadcast whenever somebody joins or rejoins."""

    type: Literal["players"] = "players"
    players: list[PlayerInfo] = Field(default_factory=list)


class Joined(BaseModel):
    type: Literal["joined"] = "joined"
    player_id: str
    rejoin_token: str
    code: str
    state: str


class Pong(BaseModel):
    type: Literal["pong"] = "pong"
    t0: int
    server_time: int


class RoundStarted(BaseModel):
    type: Literal["round_started"] = "round_started"
    idx: int
    source_word: str
    round_ends_at: int
    solution_count: int


class Ack(BaseModel):
    type: Literal["ack"] = "ack"
    client_uuid: str
    word: str
    # None in blind mode: the verdict exists and is recorded, it is simply
    # not reported until the round ends.
    accepted: bool | None
    reason: str | None = None


class RoundSnapshot(BaseModel):
    idx: int
    source_word: str
    round_ends_at: int
    solution_count: int


class StateSync(BaseModel):
    type: Literal["state"] = "state"
    state: str
    round: RoundSnapshot | None = None
    my_words: list[str] = Field(default_factory=list)
    scores: dict[str, int] = Field(default_factory=dict)
    players: list[PlayerInfo] = Field(default_factory=list)
    round_seconds: int = 180
    total_rounds: int = 10
    blind: bool = False


class OpponentProgress(BaseModel):
    type: Literal["opponent_progress"] = "opponent_progress"
    player: str
    count: int


class RoundEnded(BaseModel):
    type: Literal["round_ended"] = "round_ended"
    idx: int
    result: dict


class GameEnded(BaseModel):
    type: Literal["game_ended"] = "game_ended"
    stats: dict


class Error(BaseModel):
    type: Literal["error"] = "error"
    message: str
