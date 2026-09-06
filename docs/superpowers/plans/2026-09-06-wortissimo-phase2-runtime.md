# Wortissimo Phase 2 — Runtime and PWA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the two-player runtime — a FastAPI WebSocket server and an iOS-optimised PWA — that plays rounds out of the `puzzles.sqlite` produced by Phase 1, and survives iOS suspending the app mid-round.

**Architecture:** One FastAPI process serves the built static SPA and a single WebSocket endpoint. It imports `wortissimo.rules` (built in Phase 1) for all validation and scoring, and holds no dictionary beyond the current round's precomputed solution set. Every protocol decision follows from one fact: iOS kills the WebSocket when the screen locks, so the clock is an absolute timestamp rather than a tick count, and submissions go through an idempotent replayable outbox.

**Tech Stack:** Python 3.13, FastAPI, uvicorn, pydantic v2, pytest-asyncio, SQLite; React 19 + Vite + TypeScript, `vite-plugin-pwa`, Playwright; Docker Compose behind `tailscale serve`.

**Spec:** `docs/superpowers/specs/2026-09-06-wortissimo-design.md`

**Depends on:** `docs/superpowers/plans/2026-09-06-wortissimo-phase1-puzzle-pipeline.md` — all of its exit criteria must hold before starting.

## Global Constraints

Every task's requirements implicitly include these.

- **The client never receives the solution set until the round has ended** (spec §8.5). Not in a join payload, not in a resync, not in an opponent-progress message. Opponent progress is a *count only*.
- **The timer is never a tick count.** The server issues `round_ends_at` as absolute UTC milliseconds; the client renders `round_ends_at − (Date.now() + offset)` and recomputes on `visibilitychange` and `pageshow`. Any `setInterval` that accumulates elapsed time is a bug.
- **Every submission carries a client-generated UUID** and is persisted to `sessionStorage` before being sent. The server deduplicates by that UUID. Replay must be safe.
- `submissions` is append-only. No `UPDATE`, no `DELETE`. Scoring is a projection over it.
- The server is authoritative on round end. A disconnected player never blocks scoring.
- `wortissimo/rules/` stays pure and unmodified. If a rule needs changing, it changes there and Phase 1's tests must still pass.
- Word input must carry `autocorrect="off" autocapitalize="off" spellcheck="false"` and `font-size` ≥ 16px. Non-negotiable (spec §13).
- `touch-action: manipulation` on buttons only, **never on `html`** — on `html` it breaks the keyboard in iOS standalone mode.
- Layout offsets come from `visualViewport`, **never `100dvh`**.
- Commit after every task. Conventional commit messages.

---

### Task 1: Game persistence schema and repository

**Files:**
- Create: `wortissimo/server/__init__.py`
- Create: `wortissimo/server/db.py`
- Test: `tests/server/test_db.py`

**Interfaces:**
- Consumes: nothing from Phase 1 except that `puzzles.sqlite` exists.
- Produces:
  - `GAME_SCHEMA: str`
  - `connect(path: Path) -> sqlite3.Connection`
  - `create_game(conn, code: str, config: dict) -> int`
  - `get_game_by_code(conn, code: str) -> sqlite3.Row | None`
  - `create_round(conn, game_id: int, idx: int, puzzle_id: int, ends_at: int) -> int`
  - `record_submission(conn, round_id: int, player: str, word: str, client_uuid: str, accepted: bool, reason: str | None, at: int) -> bool` — returns `False` if the UUID was already recorded.
  - `accepted_words(conn, round_id: int) -> dict[str, list[str]]`

Spec §12: `games`, `rounds`, `submissions`. The unique index on `client_uuid` is what makes outbox replay idempotent.

- [ ] **Step 1: Write the failing test**

Create `tests/server/test_db.py`:

```python
import sqlite3

import pytest

from wortissimo.server.db import (
    accepted_words, create_game, create_round, create_schema,
    get_game_by_code, record_submission,
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/server/test_db.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wortissimo.server'`

- [ ] **Step 3: Write the implementation**

```bash
mkdir -p wortissimo/server tests/server
touch wortissimo/server/__init__.py tests/server/__init__.py
```

Create `wortissimo/server/db.py`:

```python
"""Game persistence (spec section 12, games half).

submissions is append-only: rows are never updated or deleted. Scoring is
a projection over them, which is what makes reconnect-replay naturally
idempotent — the unique index on client_uuid does the deduplication.
"""

import json
import sqlite3
from pathlib import Path

GAME_SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS games (
    id          INTEGER PRIMARY KEY,
    code        TEXT    NOT NULL UNIQUE,
    config_json TEXT    NOT NULL,
    state       TEXT    NOT NULL DEFAULT 'lobby',
    created_at  INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS rounds (
    id        INTEGER PRIMARY KEY,
    game_id   INTEGER NOT NULL REFERENCES games(id),
    idx       INTEGER NOT NULL,
    puzzle_id INTEGER NOT NULL,
    ends_at   INTEGER NOT NULL,
    UNIQUE (game_id, idx)
);

CREATE TABLE IF NOT EXISTS submissions (
    id          INTEGER PRIMARY KEY,
    round_id    INTEGER NOT NULL REFERENCES rounds(id),
    player      TEXT    NOT NULL,
    word        TEXT    NOT NULL,
    client_uuid TEXT    NOT NULL UNIQUE,
    accepted    INTEGER NOT NULL,
    reason      TEXT,
    at          INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_submissions_round ON submissions(round_id);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(GAME_SCHEMA)
    conn.commit()


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    create_schema(conn)
    return conn


def create_game(conn: sqlite3.Connection, code: str, config: dict) -> int:
    import time
    cur = conn.execute(
        "INSERT INTO games (code, config_json, state, created_at)"
        " VALUES (?, ?, 'lobby', ?)",
        (code, json.dumps(config), int(time.time() * 1000)),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_game_by_code(conn: sqlite3.Connection, code: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM games WHERE code=?", (code,)).fetchone()


def set_game_state(conn: sqlite3.Connection, game_id: int, state: str) -> None:
    conn.execute("UPDATE games SET state=? WHERE id=?", (state, game_id))
    conn.commit()


def create_round(
    conn: sqlite3.Connection, game_id: int, idx: int, puzzle_id: int, ends_at: int
) -> int:
    cur = conn.execute(
        "INSERT INTO rounds (game_id, idx, puzzle_id, ends_at) VALUES (?, ?, ?, ?)",
        (game_id, idx, puzzle_id, ends_at),
    )
    conn.commit()
    return int(cur.lastrowid)


def used_puzzle_ids(conn: sqlite3.Connection, game_id: int) -> set[int]:
    """Spec section 11: a source word is never repeated within a game."""
    return {
        r[0] for r in conn.execute(
            "SELECT puzzle_id FROM rounds WHERE game_id=?", (game_id,)
        )
    }


def record_submission(
    conn: sqlite3.Connection,
    round_id: int,
    player: str,
    word: str,
    client_uuid: str,
    accepted: bool,
    reason: str | None,
    at: int,
) -> bool:
    """Append one submission. Returns False if this UUID was already seen.

    Replay of an outbox after reconnect lands here repeatedly; the unique
    index makes that a no-op rather than a double score.
    """
    try:
        conn.execute(
            "INSERT INTO submissions"
            " (round_id, player, word, client_uuid, accepted, reason, at)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (round_id, player, word, client_uuid, int(accepted), reason, at),
        )
    except sqlite3.IntegrityError:
        return False
    conn.commit()
    return True


def accepted_words(conn: sqlite3.Connection, round_id: int) -> dict[str, list[str]]:
    """Accepted words per player, in submission order."""
    out: dict[str, list[str]] = {}
    for row in conn.execute(
        "SELECT player, word FROM submissions"
        " WHERE round_id=? AND accepted=1 ORDER BY at, id",
        (round_id,),
    ):
        out.setdefault(row["player"], []).append(row["word"])
    return out
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/server/test_db.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add wortissimo/server tests/server
git commit -m "feat: add game persistence with idempotent submissions"
```

---

### Task 2: Puzzle selection from the Phase 1 corpus

**Files:**
- Create: `wortissimo/server/puzzles.py`
- Test: `tests/server/test_puzzles.py`

**Interfaces:**
- Consumes: `puzzles.sqlite` schema from Phase 1 Task 9.
- Produces:
  - `@dataclass(frozen=True) class Puzzle` with fields `id: int`, `source_word: str`, `difficulty: str`, `solutions: frozenset[str]`.
  - `PuzzleRepo(path: Path)` with methods `pick(difficulty: str, exclude: set[int]) -> Puzzle | None` and `get(puzzle_id: int) -> Puzzle`.

The repo opens `puzzles.sqlite` read-only. Loading a puzzle loads *only that puzzle's* solution set — the server never holds a dictionary (spec §4.2).

- [ ] **Step 1: Write the failing test**

Create `tests/server/test_puzzles.py`:

```python
import sqlite3

import pytest

from wortissimo.generator.solve import Category, Solution
from wortissimo.generator.store import create_schema, insert_puzzle
from wortissimo.server.puzzles import PuzzleRepo


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "puzzles.sqlite"
    conn = sqlite3.connect(path)
    create_schema(conn)
    sols = [Solution("bahn", Category.OBVIOUS_COMPONENT, 5.0),
            Solution("halte", Category.CROSS_BOUNDARY, 4.8)]
    insert_puzzle(conn, "strassenbahnhalte", "mittel", sols, {})
    insert_puzzle(conn, "bundesausbildungsgesetz", "schwer", sols, {})
    conn.commit()
    conn.close()
    return PuzzleRepo(path)


def test_picks_a_puzzle_of_the_requested_difficulty(repo):
    puzzle = repo.pick("mittel", exclude=set())
    assert puzzle.difficulty == "mittel"
    assert puzzle.source_word == "strassenbahnhalte"


def test_loads_the_solution_set(repo):
    puzzle = repo.pick("mittel", exclude=set())
    assert puzzle.solutions == frozenset({"bahn", "halte"})


def test_excludes_already_used_puzzles(repo):
    first = repo.pick("mittel", exclude=set())
    assert repo.pick("mittel", exclude={first.id}) is None


def test_returns_none_when_no_puzzle_matches(repo):
    assert repo.pick("brutal", exclude=set()) is None


def test_get_by_id_round_trips(repo):
    picked = repo.pick("schwer", exclude=set())
    assert repo.get(picked.id).source_word == picked.source_word
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/server/test_puzzles.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wortissimo.server.puzzles'`

- [ ] **Step 3: Write the implementation**

Create `wortissimo/server/puzzles.py`:

```python
"""Read-only access to the Phase 1 puzzle corpus.

The server holds no dictionary. Per round it knows exactly one thing:
that puzzle's precomputed solution set (spec section 4.2).
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Puzzle:
    id: int
    source_word: str
    difficulty: str
    solutions: frozenset[str]


class PuzzleRepo:
    def __init__(self, path: Path) -> None:
        self._conn = sqlite3.connect(
            f"file:{path}?mode=ro", uri=True, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row

    def _load(self, row: sqlite3.Row) -> Puzzle:
        solutions = frozenset(
            r[0] for r in self._conn.execute(
                "SELECT word FROM solutions WHERE puzzle_id=?", (row["id"],)
            )
        )
        return Puzzle(
            id=row["id"],
            source_word=row["source_word"],
            difficulty=row["difficulty"],
            solutions=solutions,
        )

    def pick(self, difficulty: str, exclude: set[int]) -> Puzzle | None:
        """Random unused puzzle of this difficulty, or None if exhausted."""
        placeholders = ",".join("?" * len(exclude)) or "NULL"
        row = self._conn.execute(
            f"SELECT * FROM puzzles WHERE difficulty=?"
            f" AND id NOT IN ({placeholders}) ORDER BY RANDOM() LIMIT 1",
            (difficulty, *exclude),
        ).fetchone()
        return self._load(row) if row else None

    def get(self, puzzle_id: int) -> Puzzle:
        row = self._conn.execute(
            "SELECT * FROM puzzles WHERE id=?", (puzzle_id,)
        ).fetchone()
        if row is None:
            raise KeyError(puzzle_id)
        return self._load(row)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/server/test_puzzles.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Commit**

```bash
git add wortissimo/server/puzzles.py tests/server/test_puzzles.py
git commit -m "feat: add read-only puzzle repository"
```

---

### Task 3: Protocol message models

**Files:**
- Create: `wortissimo/server/protocol.py`
- Test: `tests/server/test_protocol.py`

**Interfaces:**
- Produces (pydantic v2 models, all with a literal `type` discriminator):
  - Client→server: `Join(type="join", code, player, rejoin_token: str | None)`, `Ping(type="ping", t0: int)`, `Submit(type="submit", client_uuid: str, word: str, round_idx: int)`, `StartRound(type="start_round")`
  - Server→client: `Joined(type="joined", player_id, rejoin_token, code, state)`, `Pong(type="pong", t0: int, server_time: int)`, `RoundStarted(type="round_started", idx, source_word, round_ends_at, solution_count)`, `Ack(type="ack", client_uuid, word, accepted, reason: str | None)`, `StateSync(type="state", state, round: RoundSnapshot | None, my_words: list[str], scores: dict[str, int])`, `OpponentProgress(type="opponent_progress", player, count)`, `RoundEnded(type="round_ended", idx, result: dict)`, `GameEnded(type="game_ended", scores: dict[str, int])`, `Error(type="error", message)`
  - `ClientMessage = Annotated[Join | Ping | Submit | StartRound, Field(discriminator="type")]`
  - `parse_client_message(raw: str) -> ClientMessage`

`OpponentProgress` carries a **count only** — never words. `RoundStarted` carries `solution_count` (how many exist) but not the solutions themselves.

- [ ] **Step 1: Write the failing test**

Create `tests/server/test_protocol.py`:

```python
import pytest
from pydantic import ValidationError

from wortissimo.server.protocol import (
    OpponentProgress, RoundStarted, Submit, parse_client_message,
)


def test_parses_a_submit_message():
    msg = parse_client_message(
        '{"type":"submit","client_uuid":"u1","word":"Bahn","round_idx":0}'
    )
    assert isinstance(msg, Submit)
    assert msg.word == "Bahn"


def test_parses_a_join_message():
    msg = parse_client_message('{"type":"join","code":"ABCD","player":"jw"}')
    assert msg.code == "ABCD"
    assert msg.rejoin_token is None


def test_rejects_an_unknown_message_type():
    with pytest.raises(ValidationError):
        parse_client_message('{"type":"launch_missiles"}')


def test_rejects_a_submit_missing_its_uuid():
    with pytest.raises(ValidationError):
        parse_client_message('{"type":"submit","word":"Bahn","round_idx":0}')


def test_round_started_does_not_expose_solutions():
    msg = RoundStarted(idx=0, source_word="strassenbahn",
                       round_ends_at=1000, solution_count=12)
    assert "solutions" not in msg.model_dump()
    assert msg.model_dump()["solution_count"] == 12


def test_opponent_progress_carries_a_count_only():
    dumped = OpponentProgress(player="gf", count=7).model_dump()
    assert dumped == {"type": "opponent_progress", "player": "gf", "count": 7}


def test_word_length_is_bounded():
    with pytest.raises(ValidationError):
        parse_client_message(
            '{"type":"submit","client_uuid":"u1","word":"' + "a" * 200
            + '","round_idx":0}'
        )
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/server/test_protocol.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wortissimo.server.protocol'`

- [ ] **Step 3: Write the implementation**

Create `wortissimo/server/protocol.py`:

```python
"""WebSocket message schema.

Invariant enforced by shape: no server-to-client message carries the
solution set before the round ends (spec section 8.5). RoundStarted has a
solution_count so the UI can show "3 / 27 gefunden", but not the words.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter

MAX_WORD_LENGTH = 64


# ---------- client -> server ----------

class Join(BaseModel):
    type: Literal["join"] = "join"
    code: str = Field(min_length=1, max_length=8)
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
    accepted: bool
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
    scores: dict[str, int]


class Error(BaseModel):
    type: Literal["error"] = "error"
    message: str
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/server/test_protocol.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add wortissimo/server/protocol.py tests/server/test_protocol.py
git commit -m "feat: add websocket protocol models"
```

---

### Task 4: The room — game state machine

**Files:**
- Create: `wortissimo/server/room.py`
- Test: `tests/server/test_room.py`

**Interfaces:**
- Consumes: `db` (Task 1), `PuzzleRepo`/`Puzzle` (Task 2), `validate_word`/`Rejection` (Phase 1 Task 2), `score_round` (Phase 1 Task 3).
- Produces:
  - `@dataclass class Player` with fields `id: str`, `name: str`, `token: str`.
  - `class Room` with:
    - `Room(conn, repo, game_id, code, config: dict)`
    - `join(name: str, token: str | None) -> Player`
    - `start_round(now_ms: int) -> RoundStarted | None`
    - `submit(player_id: str, client_uuid: str, word: str, now_ms: int) -> Ack`
    - `end_round(now_ms: int) -> RoundEnded`
    - `snapshot(player_id: str) -> StateSync`
    - properties `state: str`, `current_round_idx: int`, `is_finished: bool`, `progress_count(player_id) -> int`
  - `ROUND_SECONDS = 180`, `TOTAL_ROUNDS = 10`

The room owns all game logic and does **no networking** — that keeps it directly unit-testable without a WebSocket, which is what makes the disconnect tests in Task 6 tractable.

- [ ] **Step 1: Write the failing test**

Create `tests/server/test_room.py`:

```python
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
SOLUTION_WORDS = ["bahn", "halte", "strasse", "enbahn", "rasse"]


@pytest.fixture
def room(tmp_path):
    ppath = tmp_path / "puzzles.sqlite"
    pconn = sqlite3.connect(ppath)
    create_puzzle_schema(pconn)
    insert_puzzle(
        pconn, SOURCE, "mittel",
        [Solution(w, Category.OBVIOUS_COMPONENT, 5.0) for w in SOLUTION_WORDS],
        {},
    )
    pconn.commit()
    pconn.close()

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    gid = create_game(conn, "ABCD", {"difficulty": "mittel", "rounds": 2})
    return Room(conn, PuzzleRepo(ppath), gid, "ABCD",
                {"difficulty": "mittel", "rounds": 2, "round_seconds": 180})


def test_joining_returns_a_player_with_a_token(room):
    p = room.join("jw", None)
    assert p.name == "jw"
    assert p.token


def test_rejoining_with_a_token_returns_the_same_player(room):
    first = room.join("jw", None)
    again = room.join("jw", first.token)
    assert again.id == first.id


def test_joining_without_a_token_creates_a_new_player(room):
    a = room.join("jw", None)
    b = room.join("gf", None)
    assert a.id != b.id


def test_starting_a_round_reveals_the_source_word_but_not_solutions(room):
    room.join("jw", None)
    started = room.start_round(now_ms=0)
    assert started.source_word == SOURCE
    assert started.solution_count == len(SOLUTION_WORDS)
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


def test_replaying_the_same_uuid_returns_the_same_ack_without_double_scoring(room):
    p = room.join("jw", None)
    room.start_round(now_ms=0)
    first = room.submit(p.id, "u1", "Bahn", 1000)
    replay = room.submit(p.id, "u1", "Bahn", 1000)
    assert replay.accepted == first.accepted
    assert room.progress_count(p.id) == 1


def test_scoring_a_round_awards_two_points_for_unique_words(room):
    a = room.join("jw", None)
    b = room.join("gf", None)
    room.start_round(now_ms=0)
    room.submit(a.id, "u1", "bahn", 1000)
    room.submit(b.id, "u2", "halte", 1000)
    ended = room.end_round(now_ms=200_000)
    scores = {s["player"]: s["points"] for s in ended.result["scores"]}
    assert scores["jw"] == 2
    assert scores["gf"] == 2


def test_scoring_awards_one_point_for_a_shared_word(room):
    a = room.join("jw", None)
    b = room.join("gf", None)
    room.start_round(now_ms=0)
    room.submit(a.id, "u1", "bahn", 1000)
    room.submit(b.id, "u2", "bahn", 1000)
    ended = room.end_round(now_ms=200_000)
    scores = {s["player"]: s["points"] for s in ended.result["scores"]}
    assert scores["jw"] == 1


def test_round_end_reveals_the_missed_words(room):
    a = room.join("jw", None)
    room.start_round(now_ms=0)
    room.submit(a.id, "u1", "bahn", 1000)
    ended = room.end_round(now_ms=200_000)
    assert "halte" in ended.result["missed_words"]


def test_a_source_word_is_never_repeated_within_a_game(room):
    room.join("jw", None)
    room.start_round(now_ms=0)
    room.end_round(now_ms=200_000)
    # Only one puzzle exists, so the second round cannot be built.
    assert room.start_round(now_ms=300_000) is None


def test_snapshot_never_leaks_the_solution_set(room):
    p = room.join("jw", None)
    room.start_round(now_ms=0)
    dumped = room.snapshot(p.id).model_dump()
    assert "solutions" not in str(dumped)
    assert "halte" not in str(dumped)


def test_snapshot_returns_the_players_own_accepted_words(room):
    p = room.join("jw", None)
    room.start_round(now_ms=0)
    room.submit(p.id, "u1", "bahn", 1000)
    assert room.snapshot(p.id).my_words == ["bahn"]


def test_game_finishes_after_the_configured_round_count(room):
    room.join("jw", None)
    room.start_round(now_ms=0)
    room.end_round(now_ms=200_000)
    assert room.current_round_idx == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/server/test_room.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wortissimo.server.room'`

- [ ] **Step 3: Write the implementation**

Create `wortissimo/server/room.py`:

```python
"""Game state machine. Does no networking, so it is directly unit-testable.

The server is authoritative on round end (spec section 8.4): submissions
whose server-receipt time is past round_ends_at are rejected, and scoring
never waits for a disconnected player.
"""

import secrets
import sqlite3
from dataclasses import dataclass, field

from wortissimo.rules.scoring import score_round
from wortissimo.rules.validate import Rejection, validate_word
from wortissimo.server import db
from wortissimo.server.protocol import (
    Ack, RoundEnded, RoundSnapshot, RoundStarted, StateSync,
)
from wortissimo.server.puzzles import Puzzle, PuzzleRepo

ROUND_SECONDS = 180
TOTAL_ROUNDS = 10

STATE_LOBBY = "lobby"
STATE_PLAYING = "playing"
STATE_BETWEEN = "between"
STATE_FINISHED = "finished"


@dataclass
class Player:
    id: str
    name: str
    token: str


@dataclass
class ActiveRound:
    idx: int
    row_id: int
    puzzle: Puzzle
    ends_at: int
    seen_uuids: dict[str, Ack] = field(default_factory=dict)


class Room:
    def __init__(
        self,
        conn: sqlite3.Connection,
        repo: PuzzleRepo,
        game_id: int,
        code: str,
        config: dict,
    ) -> None:
        self._conn = conn
        self._repo = repo
        self.game_id = game_id
        self.code = code
        self.config = config
        self.players: dict[str, Player] = {}
        self._by_token: dict[str, str] = {}
        self.state = STATE_LOBBY
        self.current_round_idx = 0
        self.round: ActiveRound | None = None
        self.totals: dict[str, int] = {}

    # ----- players -----

    def join(self, name: str, token: str | None) -> Player:
        """Join, or rejoin as an existing player when the token matches."""
        if token and token in self._by_token:
            return self.players[self._by_token[token]]
        player = Player(id=name, name=name, token=secrets.token_urlsafe(16))
        self.players[player.id] = player
        self._by_token[player.token] = player.id
        self.totals.setdefault(player.id, 0)
        return player

    # ----- rounds -----

    @property
    def difficulty(self) -> str:
        return self.config.get("difficulty", "mittel")

    @property
    def total_rounds(self) -> int:
        return int(self.config.get("rounds", TOTAL_ROUNDS))

    @property
    def round_seconds(self) -> int:
        return int(self.config.get("round_seconds", ROUND_SECONDS))

    @property
    def is_finished(self) -> bool:
        return self.state == STATE_FINISHED

    def start_round(self, now_ms: int) -> RoundStarted | None:
        """Begin the next round. None if the corpus or the game is exhausted."""
        if self.current_round_idx >= self.total_rounds:
            self.state = STATE_FINISHED
            return None

        used = db.used_puzzle_ids(self._conn, self.game_id)
        puzzle = self._repo.pick(self.difficulty, exclude=used)
        if puzzle is None:
            self.state = STATE_FINISHED
            return None

        ends_at = now_ms + self.round_seconds * 1000
        row_id = db.create_round(
            self._conn, self.game_id, self.current_round_idx, puzzle.id, ends_at
        )
        self.round = ActiveRound(
            idx=self.current_round_idx, row_id=row_id, puzzle=puzzle, ends_at=ends_at
        )
        self.state = STATE_PLAYING
        db.set_game_state(self._conn, self.game_id, self.state)

        return RoundStarted(
            idx=self.round.idx,
            source_word=puzzle.source_word,
            round_ends_at=ends_at,
            solution_count=len(puzzle.solutions),
        )

    def submit(self, player_id: str, client_uuid: str, word: str, now_ms: int) -> Ack:
        """Validate and record one submission. Idempotent on client_uuid."""
        if self.round is None or self.state != STATE_PLAYING:
            return Ack(client_uuid=client_uuid, word=word, accepted=False,
                       reason=Rejection.TOO_LATE)

        # Replay after reconnect: return the original verdict unchanged.
        if client_uuid in self.round.seen_uuids:
            return self.round.seen_uuids[client_uuid]

        if now_ms > self.round.ends_at:
            ack = Ack(client_uuid=client_uuid, word=word, accepted=False,
                      reason=Rejection.TOO_LATE)
            self.round.seen_uuids[client_uuid] = ack
            return ack

        verdict = validate_word(
            word, self.round.puzzle.source_word, self.round.puzzle.solutions
        )

        if verdict.accepted:
            already = db.accepted_words(self._conn, self.round.row_id)
            if verdict.word in already.get(player_id, []):
                ack = Ack(client_uuid=client_uuid, word=verdict.word,
                          accepted=False, reason=Rejection.DUPLICATE)
                self.round.seen_uuids[client_uuid] = ack
                db.record_submission(self._conn, self.round.row_id, player_id,
                                     verdict.word, client_uuid, False,
                                     str(Rejection.DUPLICATE), now_ms)
                return ack

        db.record_submission(
            self._conn, self.round.row_id, player_id, verdict.word, client_uuid,
            verdict.accepted, str(verdict.reason) if verdict.reason else None,
            now_ms,
        )
        ack = Ack(client_uuid=client_uuid, word=verdict.word,
                  accepted=verdict.accepted,
                  reason=str(verdict.reason) if verdict.reason else None)
        self.round.seen_uuids[client_uuid] = ack
        return ack

    def progress_count(self, player_id: str) -> int:
        if self.round is None:
            return 0
        return len(db.accepted_words(self._conn, self.round.row_id).get(player_id, []))

    def end_round(self, now_ms: int) -> RoundEnded:
        """Score the round. Does not wait for disconnected players."""
        assert self.round is not None, "no active round"
        accepted = db.accepted_words(self._conn, self.round.row_id)
        for player_id in self.players:
            accepted.setdefault(player_id, [])

        result = score_round(accepted, self.round.puzzle.solutions)
        for score in result.scores:
            self.totals[score.player] = self.totals.get(score.player, 0) + score.points

        payload = {
            "source_word": self.round.puzzle.source_word,
            "solution_count": len(self.round.puzzle.solutions),
            "scores": [
                {"player": s.player, "points": s.points,
                 "words": list(s.words), "unique_words": list(s.unique_words)}
                for s in result.scores
            ],
            "shared_words": list(result.shared_words),
            "missed_words": list(result.missed_words),
            "totals": dict(self.totals),
        }

        idx = self.round.idx
        self.round = None
        self.current_round_idx += 1
        self.state = (STATE_FINISHED
                      if self.current_round_idx >= self.total_rounds
                      else STATE_BETWEEN)
        db.set_game_state(self._conn, self.game_id, self.state)
        return RoundEnded(idx=idx, result=payload)

    # ----- resync -----

    def snapshot(self, player_id: str) -> StateSync:
        """Full state for one player after (re)connecting.

        Carries the player's OWN accepted words only. The opponent's words
        and the solution set are never included (spec section 8.5).
        """
        round_snapshot = None
        my_words: list[str] = []
        if self.round is not None:
            round_snapshot = RoundSnapshot(
                idx=self.round.idx,
                source_word=self.round.puzzle.source_word,
                round_ends_at=self.round.ends_at,
                solution_count=len(self.round.puzzle.solutions),
            )
            my_words = db.accepted_words(
                self._conn, self.round.row_id
            ).get(player_id, [])

        return StateSync(state=self.state, round=round_snapshot,
                         my_words=my_words, scores=dict(self.totals))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/server/test_room.py -v`
Expected: PASS (17 tests)

- [ ] **Step 5: Commit**

```bash
git add wortissimo/server/room.py tests/server/test_room.py
git commit -m "feat: add room state machine with idempotent submissions"
```

---

### Task 5: FastAPI app and WebSocket endpoint

**Files:**
- Create: `wortissimo/server/app.py`
- Create: `wortissimo/server/hub.py`
- Test: `tests/server/test_ws.py`

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `wortissimo.server.hub.Hub` with `get_or_create(code: str, config: dict) -> Room`, `connect(code, player_id, ws)`, `disconnect(code, player_id, ws)`, `broadcast(code, message, exclude: str | None = None)`, `send(code, player_id, message)`.
  - `wortissimo.server.app.create_app(puzzles_path: Path, games_path: Path, static_dir: Path | None) -> FastAPI` with `POST /api/games`, `GET /api/health`, `WS /ws`.

The round timer is a single `asyncio` task per room that sleeps until `ends_at` and then calls `room.end_round()`. It runs server-side, so it is unaffected by either client being suspended.

- [ ] **Step 1: Write the failing test**

Create `tests/server/test_ws.py`:

```python
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from wortissimo.generator.solve import Category, Solution
from wortissimo.generator.store import create_schema as create_puzzle_schema
from wortissimo.generator.store import insert_puzzle
from wortissimo.server.app import create_app

SOURCE = "strassenbahnhalte"
WORDS = ["bahn", "halte", "strasse", "enbahn", "rasse"]


@pytest.fixture
def client(tmp_path):
    ppath = tmp_path / "puzzles.sqlite"
    pconn = sqlite3.connect(ppath)
    create_puzzle_schema(pconn)
    insert_puzzle(pconn, SOURCE, "mittel",
                  [Solution(w, Category.OBVIOUS_COMPONENT, 5.0) for w in WORDS], {})
    pconn.commit()
    pconn.close()
    app = create_app(puzzles_path=ppath, games_path=tmp_path / "games.sqlite",
                     static_dir=None)
    return TestClient(app)


def new_game(client, **config):
    body = {"difficulty": "mittel", "rounds": 1, "round_seconds": 180, **config}
    return client.post("/api/games", json=body).json()["code"]


def recv_until(ws, want):
    for _ in range(20):
        msg = json.loads(ws.receive_text())
        if msg["type"] == want:
            return msg
    raise AssertionError(f"never received {want}")


def test_health_endpoint(client):
    assert client.get("/api/health").json()["status"] == "ok"


def test_creating_a_game_returns_a_code(client):
    code = new_game(client)
    assert len(code) == 4


def test_join_returns_a_rejoin_token(client):
    code = new_game(client)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "join", "code": code, "player": "jw"}))
        joined = recv_until(ws, "joined")
        assert joined["rejoin_token"]


def test_ping_returns_server_time_and_echoes_t0(client):
    code = new_game(client)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "join", "code": code, "player": "jw"}))
        recv_until(ws, "joined")
        ws.send_text(json.dumps({"type": "ping", "t0": 12345}))
        pong = recv_until(ws, "pong")
        assert pong["t0"] == 12345
        assert pong["server_time"] > 0


def test_starting_a_round_broadcasts_the_source_word(client):
    code = new_game(client)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "join", "code": code, "player": "jw"}))
        recv_until(ws, "joined")
        ws.send_text(json.dumps({"type": "start_round"}))
        started = recv_until(ws, "round_started")
        assert started["source_word"] == SOURCE
        assert started["round_ends_at"] > 0
        assert "solutions" not in started


def test_submitting_a_valid_word_is_acked(client):
    code = new_game(client)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "join", "code": code, "player": "jw"}))
        recv_until(ws, "joined")
        ws.send_text(json.dumps({"type": "start_round"}))
        recv_until(ws, "round_started")
        ws.send_text(json.dumps({"type": "submit", "client_uuid": "u1",
                                 "word": "Bahn", "round_idx": 0}))
        ack = recv_until(ws, "ack")
        assert ack["accepted"] is True
        assert ack["client_uuid"] == "u1"


def test_reconnect_resyncs_state_and_own_words(client):
    """The core iOS-suspension scenario: drop mid-round, come back."""
    code = new_game(client)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "join", "code": code, "player": "jw"}))
        joined = recv_until(ws, "joined")
        token = joined["rejoin_token"]
        ws.send_text(json.dumps({"type": "start_round"}))
        started = recv_until(ws, "round_started")
        ws.send_text(json.dumps({"type": "submit", "client_uuid": "u1",
                                 "word": "bahn", "round_idx": 0}))
        recv_until(ws, "ack")

    # Socket is gone, as it would be after the phone locked.
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "join", "code": code, "player": "jw",
                                 "rejoin_token": token}))
        recv_until(ws, "joined")
        state = recv_until(ws, "state")
        assert state["round"]["source_word"] == SOURCE
        assert state["round"]["round_ends_at"] == started["round_ends_at"]
        assert state["my_words"] == ["bahn"]


def test_outbox_replay_after_reconnect_does_not_double_score(client):
    code = new_game(client)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "join", "code": code, "player": "jw"}))
        token = recv_until(ws, "joined")["rejoin_token"]
        ws.send_text(json.dumps({"type": "start_round"}))
        recv_until(ws, "round_started")
        ws.send_text(json.dumps({"type": "submit", "client_uuid": "u1",
                                 "word": "bahn", "round_idx": 0}))
        recv_until(ws, "ack")

    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "join", "code": code, "player": "jw",
                                 "rejoin_token": token}))
        recv_until(ws, "joined")
        recv_until(ws, "state")
        # Replay the same UUID, as the outbox would.
        ws.send_text(json.dumps({"type": "submit", "client_uuid": "u1",
                                 "word": "bahn", "round_idx": 0}))
        ack = recv_until(ws, "ack")
        assert ack["accepted"] is True
        ws.send_text(json.dumps({"type": "join", "code": code, "player": "jw",
                                 "rejoin_token": token}))
        recv_until(ws, "joined")
        state = recv_until(ws, "state")
        assert state["my_words"] == ["bahn"]


def test_state_sync_never_contains_the_solution_set(client):
    code = new_game(client)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "join", "code": code, "player": "jw"}))
        recv_until(ws, "joined")
        ws.send_text(json.dumps({"type": "start_round"}))
        recv_until(ws, "round_started")
        ws.send_text(json.dumps({"type": "join", "code": code, "player": "jw"}))
        raw = ws.receive_text()
        assert "halte" not in raw
        assert "rasse" not in raw


def test_joining_an_unknown_code_errors(client):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "join", "code": "ZZZZ", "player": "jw"}))
        assert recv_until(ws, "error")["message"]


def test_malformed_message_errors_without_closing(client):
    code = new_game(client)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"type": "join", "code": code, "player": "jw"}))
        recv_until(ws, "joined")
        ws.send_text("{not json")
        assert recv_until(ws, "error")["message"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/server/test_ws.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wortissimo.server.app'`

- [ ] **Step 3: Write the hub**

Create `wortissimo/server/hub.py`:

```python
"""Live connection registry. One Room per game code, N sockets per player."""

import asyncio
import sqlite3
from pathlib import Path

from fastapi import WebSocket
from pydantic import BaseModel

from wortissimo.server import db
from wortissimo.server.puzzles import PuzzleRepo
from wortissimo.server.room import Room


class Hub:
    def __init__(self, conn: sqlite3.Connection, puzzles_path: Path) -> None:
        self._conn = conn
        self._repo = PuzzleRepo(puzzles_path)
        self._rooms: dict[str, Room] = {}
        self._sockets: dict[str, dict[str, set[WebSocket]]] = {}
        self._timers: dict[str, asyncio.Task] = {}

    def get_room(self, code: str) -> Room | None:
        if code in self._rooms:
            return self._rooms[code]
        row = db.get_game_by_code(self._conn, code)
        if row is None:
            return None
        import json
        room = Room(self._conn, self._repo, row["id"], code,
                    json.loads(row["config_json"]))
        self._rooms[code] = room
        return room

    def connect(self, code: str, player_id: str, ws: WebSocket) -> None:
        self._sockets.setdefault(code, {}).setdefault(player_id, set()).add(ws)

    def disconnect(self, code: str, player_id: str, ws: WebSocket) -> None:
        self._sockets.get(code, {}).get(player_id, set()).discard(ws)

    async def send(self, code: str, player_id: str, message: BaseModel) -> None:
        payload = message.model_dump_json()
        for ws in list(self._sockets.get(code, {}).get(player_id, ())):
            try:
                await ws.send_text(payload)
            except Exception:
                self.disconnect(code, player_id, ws)

    async def broadcast(
        self, code: str, message: BaseModel, exclude: str | None = None
    ) -> None:
        for player_id in list(self._sockets.get(code, {})):
            if player_id == exclude:
                continue
            await self.send(code, player_id, message)

    def schedule_round_end(self, code: str, ends_at: int, on_end) -> None:
        """Server-side round timer. Unaffected by either client suspending."""
        self.cancel_round_end(code)

        async def runner() -> None:
            import time
            delay = max(0.0, (ends_at - int(time.time() * 1000)) / 1000)
            await asyncio.sleep(delay)
            await on_end()

        self._timers[code] = asyncio.create_task(runner())

    def cancel_round_end(self, code: str) -> None:
        task = self._timers.pop(code, None)
        if task and not task.done():
            task.cancel()
```

- [ ] **Step 4: Write the app**

Create `wortissimo/server/app.py`:

```python
"""FastAPI application: static SPA, health, game creation, WebSocket."""

import secrets
import time
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from wortissimo.server import db
from wortissimo.server.hub import Hub
from wortissimo.server.protocol import (
    Error, Joined, OpponentProgress, Ping, Pong, Submit, Join, StartRound,
    parse_client_message,
)

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # no I or O: unreadable on a phone
CODE_LENGTH = 4


class NewGame(BaseModel):
    difficulty: str = "mittel"
    rounds: int = Field(default=10, ge=1, le=50)
    round_seconds: int = Field(default=180, ge=30, le=900)


def now_ms() -> int:
    return int(time.time() * 1000)


def create_app(
    puzzles_path: Path, games_path: Path, static_dir: Path | None
) -> FastAPI:
    app = FastAPI(title="Wortissimo")
    conn = db.connect(games_path)
    hub = Hub(conn, puzzles_path)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/api/games")
    def create_game(body: NewGame) -> dict:
        for _ in range(20):
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if db.get_game_by_code(conn, code) is None:
                db.create_game(conn, code, body.model_dump())
                return {"code": code}
        raise RuntimeError("could not allocate a game code")

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        code: str | None = None
        player_id: str | None = None

        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = parse_client_message(raw)
                except (ValidationError, ValueError) as exc:
                    await ws.send_text(Error(message=str(exc)[:200]).model_dump_json())
                    continue

                if isinstance(msg, Ping):
                    await ws.send_text(
                        Pong(t0=msg.t0, server_time=now_ms()).model_dump_json()
                    )
                    continue

                if isinstance(msg, Join):
                    room = hub.get_room(msg.code)
                    if room is None:
                        await ws.send_text(
                            Error(message=f"unknown game code {msg.code}")
                            .model_dump_json()
                        )
                        continue
                    player = room.join(msg.player, msg.rejoin_token)
                    code, player_id = msg.code, player.id
                    hub.connect(code, player_id, ws)
                    await ws.send_text(Joined(
                        player_id=player.id, rejoin_token=player.token,
                        code=code, state=room.state,
                    ).model_dump_json())
                    # Resync immediately: this is what makes a phone that
                    # locked mid-round pick up exactly where it left off.
                    await ws.send_text(room.snapshot(player.id).model_dump_json())
                    continue

                if code is None or player_id is None:
                    await ws.send_text(
                        Error(message="join first").model_dump_json()
                    )
                    continue

                room = hub.get_room(code)
                assert room is not None

                if isinstance(msg, StartRound):
                    started = room.start_round(now_ms())
                    if started is None:
                        await hub.broadcast(code, Error(message="no rounds left"))
                        continue

                    async def end_now(code=code, room=room) -> None:
                        ended = room.end_round(now_ms())
                        await hub.broadcast(code, ended)

                    hub.schedule_round_end(code, started.round_ends_at, end_now)
                    await hub.broadcast(code, started)
                    continue

                if isinstance(msg, Submit):
                    ack = room.submit(player_id, msg.client_uuid, msg.word, now_ms())
                    await ws.send_text(ack.model_dump_json())
                    if ack.accepted:
                        await hub.broadcast(
                            code,
                            OpponentProgress(player=player_id,
                                             count=room.progress_count(player_id)),
                            exclude=player_id,
                        )
                    continue

        except WebSocketDisconnect:
            pass
        finally:
            if code and player_id:
                hub.disconnect(code, player_id, ws)

    if static_dir is not None and static_dir.exists():
        app.mount("/assets", StaticFiles(directory=static_dir / "assets"),
                  name="assets")

        @app.get("/{path:path}")
        def spa(path: str) -> FileResponse:
            candidate = static_dir / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(static_dir / "index.html")

    return app
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/server/test_ws.py -v`
Expected: PASS (11 tests). `test_reconnect_resyncs_state_and_own_words` and `test_outbox_replay_after_reconnect_does_not_double_score` are the two that matter most — they are the iOS-suspension scenario.

- [ ] **Step 6: Commit**

```bash
git add wortissimo/server/app.py wortissimo/server/hub.py tests/server/test_ws.py
git commit -m "feat: add websocket endpoint with resync and idempotent replay"
```

---

### Task 6: Frontend scaffold with the iOS foundation

**Files:**
- Create: `web/package.json`, `web/vite.config.ts`, `web/tsconfig.json`
- Create: `web/index.html`
- Create: `web/src/main.tsx`, `web/src/App.tsx`, `web/src/styles.css`

**Interfaces:**
- Produces: a Vite dev server proxying `/api` and `/ws` to the Python server, and the CSS foundation every later task builds on.

Every constraint from spec §13 is established here, once, so no later task can forget one.

- [ ] **Step 1: Scaffold**

```bash
mkdir -p web/src
cd web && npm create vite@latest . -- --template react-ts && npm install \
  && npm install -D vite-plugin-pwa && cd ..
```

- [ ] **Step 2: Configure Vite**

Replace `web/vite.config.ts`:

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      manifest: {
        name: "Wortissimo",
        short_name: "Wortissimo",
        lang: "de",
        display: "standalone",
        background_color: "#12111a",
        theme_color: "#12111a",
        start_url: "/",
        icons: [
          { src: "/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icon-512.png", sizes: "512x512", type: "image/png" },
        ],
      },
      workbox: {
        // App shell only. Game state is never cached (spec section 13).
        globPatterns: ["**/*.{js,css,html,png,svg,woff2}"],
        navigateFallback: "/index.html",
      },
    }),
  ],
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
});
```

- [ ] **Step 3: Write `index.html` with the required viewport**

Replace `web/index.html`:

```html
<!doctype html>
<html lang="de">
  <head>
    <meta charset="UTF-8" />
    <!-- viewport-fit=cover is required for env(safe-area-inset-*) to
         resolve to anything but 0 on notched iPhones. -->
    <meta
      name="viewport"
      content="width=device-width, initial-scale=1, viewport-fit=cover"
    />
    <meta name="apple-mobile-web-app-capable" content="yes" />
    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent" />
    <meta name="apple-mobile-web-app-title" content="Wortissimo" />
    <title>Wortissimo</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 4: Write the CSS foundation**

Replace `web/src/styles.css`:

```css
/* iOS foundation. Every rule here exists because of a specific documented
   Safari behaviour (spec section 13). Do not "clean these up". */

:root {
  --bg: #12111a;
  --fg: #f4f1ea;
  --muted: #8b8798;
  --accent: #d4a24c;
  --ok: #4caf7d;
  --bad: #d2544f;
  --bar-height: 64px;
  color-scheme: dark;
}

* { box-sizing: border-box; }

html {
  /* NEVER put touch-action: manipulation here. On <html> it prevents the
     keyboard from appearing for inputs in iOS standalone mode. */
  -webkit-text-size-adjust: 100%;
}

body {
  margin: 0;
  background: var(--bg);
  color: var(--fg);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  /* Kill rubber-band scrolling, which in standalone mode looks broken. */
  overscroll-behavior: none;
}

button {
  /* Correct place for it: removes the 300ms tap delay on controls only. */
  touch-action: manipulation;
  font-size: 17px;
  min-height: 48px;
  border-radius: 12px;
  border: 0;
  background: var(--accent);
  color: #1a1710;
  font-weight: 600;
  padding: 0 20px;
}

input,
textarea,
select {
  /* iOS force-zooms the whole page when a focused input is under 16px.
     There is no way to undo that zoom programmatically. */
  font-size: 17px;
  touch-action: auto;
}

.app {
  min-height: 100%;
  padding: env(safe-area-inset-top) env(safe-area-inset-right) 0
    env(safe-area-inset-left);
}

/* The input bar is positioned from visualViewport via a JS-set custom
   property, NOT from 100dvh: in standalone mode dvh stays shrunk after the
   keyboard dismisses and leaves a dead band at the bottom. */
.input-bar {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  transform: translateY(calc(-1 * var(--keyboard-inset, 0px)));
  display: flex;
  gap: 8px;
  padding: 8px 12px calc(8px + env(safe-area-inset-bottom));
  background: var(--bg);
  border-top: 1px solid #262233;
}

.input-bar input {
  flex: 1;
  min-width: 0;
  background: #1c1926;
  border: 1px solid #2f2a3d;
  border-radius: 12px;
  color: var(--fg);
  padding: 12px 14px;
}

.source-word {
  font-size: clamp(22px, 7vw, 40px);
  font-weight: 700;
  letter-spacing: 0.04em;
  word-break: break-all;
  text-align: center;
  padding: 16px 12px;
}

.timer { font-variant-numeric: tabular-nums; font-size: 20px; }
.timer.urgent { color: var(--bad); }
.word-list { display: flex; flex-wrap: wrap; gap: 6px; padding: 0 12px 120px; }
.chip { background: #1c1926; border-radius: 999px; padding: 6px 12px; font-size: 15px; }
.chip.bad { color: var(--bad); }
```

- [ ] **Step 5: Verify the dev server boots**

Run in one terminal:
`.venv/Scripts/python.exe -m uvicorn "wortissimo.server.app:create_app" --factory --host 127.0.0.1 --port 8000`

Note: `--factory` needs argument defaults; add a module-level `app = create_app(Path("data/puzzles.sqlite"), Path("data/games.sqlite"), Path("web/dist"))` to `wortissimo/server/app.py` and run `uvicorn wortissimo.server.app:app` instead.

Run in another: `cd web && npm run dev`
Expected: `http://localhost:5173` serves the page; `curl http://localhost:5173/api/health` returns `{"status":"ok"}` through the proxy.

- [ ] **Step 6: Commit**

```bash
git add web
git commit -m "feat: scaffold PWA frontend with iOS viewport and CSS foundation"
```

---

### Task 7: Client connection layer — clock, outbox, reconnect

**Files:**
- Create: `web/src/lib/clock.ts`
- Create: `web/src/lib/outbox.ts`
- Create: `web/src/lib/connection.ts`
- Test: `web/src/lib/clock.test.ts`, `web/src/lib/outbox.test.ts`

**Interfaces:**
- Produces:
  - `clock.ts`: `class Clock { offset: number; observe(t0: number, serverTime: number, t1: number): void; remaining(endsAt: number): number }`
  - `outbox.ts`: `class Outbox { add(word: string): {clientUuid: string, word: string}; ack(clientUuid: string): void; pending(): Entry[] }` backed by `sessionStorage`.
  - `connection.ts`: `class Connection` with `connect()`, `submit(word)`, `startRound()`, and an `on(event, handler)` subscription.

This is the task that implements spec §8. Install Vitest first: `cd web && npm install -D vitest`, and add `"test": "vitest run"` to `package.json` scripts.

- [ ] **Step 1: Write the failing clock test**

Create `web/src/lib/clock.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { Clock } from "./clock";

describe("Clock", () => {
  it("computes offset from a round trip", () => {
    const c = new Clock();
    // Sent at 1000, server said 5500, reply seen at 1200.
    // Midpoint of the round trip is 1100, so the server is 4400 ahead.
    c.observe(1000, 5500, 1200);
    expect(c.offset).toBe(4400);
  });

  it("computes remaining time from an absolute deadline", () => {
    const c = new Clock();
    c.observe(1000, 5500, 1200);
    // Server deadline 9400 -> local 5000. At local 4000, 1000ms remain.
    expect(c.remaining(9400, 4000)).toBe(1000);
  });

  it("never reports negative remaining time", () => {
    const c = new Clock();
    expect(c.remaining(1000, 99999)).toBe(0);
  });

  it("prefers the sample with the lowest round-trip time", () => {
    const c = new Clock();
    c.observe(0, 1000, 400); // rtt 400, noisy
    c.observe(1000, 2000, 1020); // rtt 20, trustworthy -> offset 990
    expect(c.offset).toBe(990);
  });

  it("works before any sample, assuming zero offset", () => {
    const c = new Clock();
    expect(c.remaining(5000, 4000)).toBe(1000);
  });
});
```

- [ ] **Step 2: Write the failing outbox test**

Create `web/src/lib/outbox.test.ts`:

```ts
import { beforeEach, describe, expect, it } from "vitest";
import { Outbox } from "./outbox";

describe("Outbox", () => {
  beforeEach(() => sessionStorage.clear());

  it("returns a uuid for each added word", () => {
    const o = new Outbox("round-0");
    const a = o.add("bahn");
    const b = o.add("halte");
    expect(a.clientUuid).not.toBe(b.clientUuid);
  });

  it("keeps unacked words pending", () => {
    const o = new Outbox("round-0");
    o.add("bahn");
    expect(o.pending().map((e) => e.word)).toEqual(["bahn"]);
  });

  it("drops a word once acked", () => {
    const o = new Outbox("round-0");
    const e = o.add("bahn");
    o.ack(e.clientUuid);
    expect(o.pending()).toEqual([]);
  });

  it("survives being rebuilt from sessionStorage", () => {
    // This is the iOS case: the tab was suspended and the object is gone,
    // but the words the player typed must not be.
    const o = new Outbox("round-0");
    o.add("bahn");
    const revived = new Outbox("round-0");
    expect(revived.pending().map((e) => e.word)).toEqual(["bahn"]);
  });

  it("keeps separate queues per round", () => {
    new Outbox("round-0").add("bahn");
    expect(new Outbox("round-1").pending()).toEqual([]);
  });

  it("ignores an ack for an unknown uuid", () => {
    const o = new Outbox("round-0");
    o.add("bahn");
    o.ack("nope");
    expect(o.pending()).toHaveLength(1);
  });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd web && npx vitest run --environment jsdom`
Expected: FAIL — cannot resolve `./clock` and `./outbox`.

- [ ] **Step 4: Write `clock.ts`**

```ts
/**
 * Server-anchored clock.
 *
 * The timer must NEVER be a tick count: iOS freezes timers when the tab
 * is suspended, so accumulated elapsed time drifts arbitrarily. Instead
 * the server issues an absolute deadline and we render the difference
 * against corrected local time (spec section 8.1).
 */
export class Clock {
  offset = 0;
  private bestRtt = Number.POSITIVE_INFINITY;

  /** Fold in one ping/pong round trip. */
  observe(t0: number, serverTime: number, t1: number): void {
    const rtt = t1 - t0;
    if (rtt > this.bestRtt) return;
    this.bestRtt = rtt;
    this.offset = serverTime - (t0 + rtt / 2);
  }

  /** Milliseconds left until an absolute server deadline. Never negative. */
  remaining(endsAt: number, now: number = Date.now()): number {
    return Math.max(0, endsAt - (now + this.offset));
  }
}
```

- [ ] **Step 5: Write `outbox.ts`**

```ts
/**
 * Durable submission queue.
 *
 * A word is persisted BEFORE it is sent and removed only when the server
 * acknowledges it. If iOS suspends the app between those two moments the
 * word survives, and is replayed on reconnect. The server deduplicates by
 * clientUuid, so replay is free (spec section 8.2).
 */
export interface Entry {
  clientUuid: string;
  word: string;
}

export class Outbox {
  private readonly key: string;

  constructor(roundKey: string) {
    this.key = `wortissimo.outbox.${roundKey}`;
  }

  private read(): Entry[] {
    try {
      return JSON.parse(sessionStorage.getItem(this.key) ?? "[]") as Entry[];
    } catch {
      return [];
    }
  }

  private write(entries: Entry[]): void {
    try {
      sessionStorage.setItem(this.key, JSON.stringify(entries));
    } catch {
      /* Private mode or quota. The in-flight send still happens; we just
         lose the crash-safety net rather than blocking the player. */
    }
  }

  add(word: string): Entry {
    const entry: Entry = { clientUuid: crypto.randomUUID(), word };
    this.write([...this.read(), entry]);
    return entry;
  }

  ack(clientUuid: string): void {
    this.write(this.read().filter((e) => e.clientUuid !== clientUuid));
  }

  pending(): Entry[] {
    return this.read();
  }
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd web && npx vitest run --environment jsdom`
Expected: PASS (11 tests)

- [ ] **Step 7: Write `connection.ts`**

```ts
import { Clock } from "./clock";
import { Outbox } from "./outbox";

type Handler = (msg: any) => void;

const TOKEN_KEY = "wortissimo.rejoin";

/**
 * WebSocket client that assumes it will be killed.
 *
 * iOS terminates the socket when the screen locks, so this reconnects on
 * backoff AND immediately when the page becomes visible again, then
 * replays the outbox (spec section 8.3).
 */
export class Connection {
  readonly clock = new Clock();
  private ws: WebSocket | null = null;
  private handlers = new Map<string, Set<Handler>>();
  private backoff = 500;
  private outbox: Outbox | null = null;
  private closed = false;

  constructor(
    private readonly code: string,
    private readonly player: string,
  ) {}

  on(type: string, handler: Handler): void {
    if (!this.handlers.has(type)) this.handlers.set(type, new Set());
    this.handlers.get(type)!.add(handler);
  }

  private emit(msg: any): void {
    this.handlers.get(msg.type)?.forEach((h) => h(msg));
  }

  connect(): void {
    this.closed = false;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws`);
    this.ws = ws;

    ws.onopen = () => {
      this.backoff = 500;
      this.send({
        type: "join",
        code: this.code,
        player: this.player,
        rejoin_token: localStorage.getItem(TOKEN_KEY),
      });
      this.ping();
      this.replay();
    };

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "joined") localStorage.setItem(TOKEN_KEY, msg.rejoin_token);
      if (msg.type === "pong") this.clock.observe(msg.t0, msg.server_time, Date.now());
      if (msg.type === "ack") this.outbox?.ack(msg.client_uuid);
      if (msg.type === "round_started") this.outbox = new Outbox(`r${msg.idx}`);
      if (msg.type === "state" && msg.round) this.outbox = new Outbox(`r${msg.round.idx}`);
      this.emit(msg);
    };

    ws.onclose = () => {
      if (this.closed) return;
      setTimeout(() => this.connect(), this.backoff);
      this.backoff = Math.min(this.backoff * 2, 10_000);
    };
  }

  /** Reconnect the moment the phone comes back, not on the next backoff tick. */
  watchVisibility(): () => void {
    const wake = () => {
      if (document.visibilityState !== "visible") return;
      if (this.ws?.readyState !== WebSocket.OPEN) this.connect();
      else this.ping();
    };
    document.addEventListener("visibilitychange", wake);
    window.addEventListener("pageshow", wake);
    return () => {
      document.removeEventListener("visibilitychange", wake);
      window.removeEventListener("pageshow", wake);
    };
  }

  private send(payload: unknown): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(payload));
    }
  }

  private ping(): void {
    this.send({ type: "ping", t0: Date.now() });
  }

  private replay(): void {
    for (const entry of this.outbox?.pending() ?? []) {
      this.send({
        type: "submit",
        client_uuid: entry.clientUuid,
        word: entry.word,
        round_idx: 0,
      });
    }
  }

  submit(word: string): void {
    if (!this.outbox) return;
    const entry = this.outbox.add(word);
    this.send({
      type: "submit",
      client_uuid: entry.clientUuid,
      word: entry.word,
      round_idx: 0,
    });
  }

  startRound(): void {
    this.send({ type: "start_round" });
  }

  close(): void {
    this.closed = true;
    this.ws?.close();
  }
}
```

- [ ] **Step 8: Commit**

```bash
git add web/src/lib web/package.json
git commit -m "feat: add server-anchored clock, durable outbox, reconnecting socket"
```

---

### Task 8: Game screens

**Files:**
- Create: `web/src/hooks/useKeyboardInset.ts`
- Create: `web/src/screens/Lobby.tsx`, `web/src/screens/Round.tsx`, `web/src/screens/Results.tsx`
- Modify: `web/src/App.tsx`

**Interfaces:**
- Consumes: `Connection` (Task 7).
- Produces: the three screens and `useKeyboardInset()`, which sets the `--keyboard-inset` custom property from `visualViewport`.

- [ ] **Step 1: Write the keyboard inset hook**

Create `web/src/hooks/useKeyboardInset.ts`:

```ts
import { useEffect } from "react";

/**
 * Track the on-screen keyboard using visualViewport.
 *
 * 100dvh cannot be used for this: in iOS standalone mode dvh stays
 * reduced after the keyboard is dismissed, leaving a dead band at the
 * bottom of the screen (spec section 13). visualViewport recovers.
 */
export function useKeyboardInset(): void {
  useEffect(() => {
    const vv = window.visualViewport;
    if (!vv) return;

    const update = () => {
      const inset = Math.max(0, window.innerHeight - vv.height - vv.offsetTop);
      document.documentElement.style.setProperty("--keyboard-inset", `${inset}px`);
    };

    update();
    vv.addEventListener("resize", update);
    vv.addEventListener("scroll", update);
    return () => {
      vv.removeEventListener("resize", update);
      vv.removeEventListener("scroll", update);
    };
  }, []);
}
```

- [ ] **Step 2: Write the round screen**

Create `web/src/screens/Round.tsx`:

```tsx
import { useEffect, useRef, useState } from "react";
import type { Connection } from "../lib/connection";
import { useKeyboardInset } from "../hooks/useKeyboardInset";

interface Props {
  connection: Connection;
  sourceWord: string;
  endsAt: number;
  solutionCount: number;
  opponentCount: number;
}

export function Round({
  connection, sourceWord, endsAt, solutionCount, opponentCount,
}: Props) {
  useKeyboardInset();
  const [remaining, setRemaining] = useState(() => connection.clock.remaining(endsAt));
  const [words, setWords] = useState<string[]>([]);
  const [flash, setFlash] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  // Recompute from the absolute deadline. The interval is only a repaint
  // trigger; it never accumulates elapsed time (spec section 8.1).
  useEffect(() => {
    const tick = () => setRemaining(connection.clock.remaining(endsAt));
    const id = window.setInterval(tick, 250);
    document.addEventListener("visibilitychange", tick);
    window.addEventListener("pageshow", tick);
    return () => {
      window.clearInterval(id);
      document.removeEventListener("visibilitychange", tick);
      window.removeEventListener("pageshow", tick);
    };
  }, [connection, endsAt]);

  useEffect(() => {
    connection.on("ack", (msg) => {
      if (msg.accepted) setWords((prev) => [msg.word, ...prev]);
      else setFlash(reasonText(msg.reason));
    });
    connection.on("state", (msg) => setWords(msg.my_words.slice().reverse()));
  }, [connection]);

  useEffect(() => {
    if (!flash) return;
    const id = window.setTimeout(() => setFlash(null), 1400);
    return () => window.clearTimeout(id);
  }, [flash]);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const word = draft.trim();
    if (!word) return;
    connection.submit(word);
    setDraft("");
    inputRef.current?.focus(); // keep the keyboard up between words
  };

  const seconds = Math.ceil(remaining / 1000);

  return (
    <div className="app">
      <header style={{ display: "flex", justifyContent: "space-between", padding: 12 }}>
        <span className={`timer${seconds <= 20 ? " urgent" : ""}`}>
          {Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, "0")}
        </span>
        <span>{words.length} / {solutionCount}</span>
        <span style={{ color: "var(--muted)" }}>Sie: {opponentCount}</span>
      </header>

      <div className="source-word">{sourceWord.toUpperCase()}</div>

      {flash && <div className="chip bad" style={{ margin: "0 12px" }}>{flash}</div>}

      <div className="word-list">
        {words.map((w) => <span className="chip" key={w}>{w}</span>)}
      </div>

      <form className="input-bar" onSubmit={submit}>
        <input
          ref={inputRef}
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          /* All four are required. iOS autocorrect will silently rewrite
             German words as they are typed and the player will blame the
             game for the rejection (spec section 13). */
          autoCorrect="off"
          autoCapitalize="off"
          spellCheck={false}
          autoComplete="off"
          enterKeyHint="send"
          inputMode="text"
          lang="de"
          placeholder="Wort eingeben"
          disabled={seconds === 0}
        />
        <button type="submit" disabled={seconds === 0}>OK</button>
      </form>
    </div>
  );
}

function reasonText(reason: string): string {
  const map: Record<string, string> = {
    too_short: "zu kurz",
    not_a_substring: "nicht enthalten",
    not_in_dictionary: "kein bekanntes Wort",
    is_source_word: "das ist das Rätselwort",
    malformed: "ungültige Eingabe",
    duplicate: "schon gefunden",
    too_late: "zu spät",
  };
  return map[reason] ?? reason;
}
```

- [ ] **Step 3: Write the lobby screen**

Create `web/src/screens/Lobby.tsx`:

```tsx
import { useState } from "react";

interface Props {
  onJoin: (code: string, player: string) => void;
}

const DIFFICULTIES = ["leicht", "mittel", "schwer", "brutal"] as const;

export function Lobby({ onJoin }: Props) {
  const [player, setPlayer] = useState("");
  const [code, setCode] = useState("");
  const [difficulty, setDifficulty] = useState<string>("mittel");

  const create = async () => {
    const res = await fetch("/api/games", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ difficulty, rounds: 10, round_seconds: 180 }),
    });
    const { code: newCode } = await res.json();
    onJoin(newCode, player || "Spieler");
  };

  return (
    <div className="app" style={{ padding: 20, display: "grid", gap: 16 }}>
      <h1>Wortissimo</h1>

      <input
        value={player}
        onChange={(e) => setPlayer(e.target.value)}
        placeholder="Dein Name"
        autoCorrect="off"
        autoCapitalize="words"
        spellCheck={false}
      />

      <div style={{ display: "grid", gap: 8 }}>
        <label>Schwierigkeit</label>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          {DIFFICULTIES.map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDifficulty(d)}
              style={{ opacity: difficulty === d ? 1 : 0.45 }}
            >
              {d}
            </button>
          ))}
        </div>
      </div>

      <button onClick={create}>Neues Spiel</button>

      <hr style={{ borderColor: "#262233", width: "100%" }} />

      <input
        value={code}
        onChange={(e) => setCode(e.target.value.toUpperCase())}
        placeholder="Code"
        autoCorrect="off"
        autoCapitalize="characters"
        spellCheck={false}
        maxLength={4}
      />
      <button onClick={() => onJoin(code, player || "Spieler")} disabled={code.length !== 4}>
        Beitreten
      </button>
    </div>
  );
}
```

- [ ] **Step 4: Write the results screen**

Create `web/src/screens/Results.tsx`:

```tsx
interface Score {
  player: string;
  points: number;
  words: string[];
  unique_words: string[];
}

interface Props {
  result: {
    source_word: string;
    solution_count: number;
    scores: Score[];
    shared_words: string[];
    missed_words: string[];
    totals: Record<string, number>;
  };
  onNext: () => void;
  onFlagRound: () => void;
}

export function Results({ result, onNext, onFlagRound }: Props) {
  const found = new Set(result.scores.flatMap((s) => s.words)).size;

  return (
    <div className="app" style={{ padding: 16, paddingBottom: 120 }}>
      <div className="source-word">{result.source_word.toUpperCase()}</div>
      <p style={{ textAlign: "center", color: "var(--muted)" }}>
        {found} von {result.solution_count} gefunden
      </p>

      {result.scores.map((s) => (
        <section key={s.player} style={{ marginTop: 20 }}>
          <h3>
            {s.player} — {s.points} Punkte
            <span style={{ color: "var(--muted)", fontWeight: 400 }}>
              {" "}(gesamt {result.totals[s.player] ?? 0})
            </span>
          </h3>
          <div className="word-list" style={{ padding: 0 }}>
            {s.words.map((w) => (
              <span
                className="chip"
                key={w}
                style={{
                  color: s.unique_words.includes(w) ? "var(--ok)" : undefined,
                }}
              >
                {w}
                {s.unique_words.includes(w) ? " ×2" : ""}
              </span>
            ))}
          </div>
        </section>
      ))}

      <section style={{ marginTop: 24 }}>
        <h3 style={{ color: "var(--muted)" }}>Verpasst</h3>
        <div className="word-list" style={{ padding: 0 }}>
          {result.missed_words.map((w) => (
            <span className="chip" key={w} style={{ color: "var(--muted)" }}>{w}</span>
          ))}
        </div>
      </section>

      <div style={{ display: "flex", gap: 8, marginTop: 24 }}>
        <button onClick={onNext}>Nächste Runde</button>
        <button
          onClick={onFlagRound}
          style={{ background: "transparent", color: "var(--muted)",
                   border: "1px solid #2f2a3d" }}
        >
          Schlechte Runde
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Wire `App.tsx`**

Replace `web/src/App.tsx`:

```tsx
import { useEffect, useRef, useState } from "react";
import { Connection } from "./lib/connection";
import { Lobby } from "./screens/Lobby";
import { Round } from "./screens/Round";
import { Results } from "./screens/Results";
import "./styles.css";

type View =
  | { kind: "lobby" }
  | { kind: "round"; sourceWord: string; endsAt: number; solutionCount: number }
  | { kind: "results"; result: any };

export default function App() {
  const [view, setView] = useState<View>({ kind: "lobby" });
  const [opponentCount, setOpponentCount] = useState(0);
  const connectionRef = useRef<Connection | null>(null);

  const join = (code: string, player: string) => {
    const connection = new Connection(code, player);
    connectionRef.current = connection;

    connection.on("round_started", (m) => {
      setOpponentCount(0);
      setView({
        kind: "round", sourceWord: m.source_word,
        endsAt: m.round_ends_at, solutionCount: m.solution_count,
      });
    });
    connection.on("state", (m) => {
      if (m.round) {
        setView({
          kind: "round", sourceWord: m.round.source_word,
          endsAt: m.round.round_ends_at, solutionCount: m.round.solution_count,
        });
      }
    });
    connection.on("opponent_progress", (m) => setOpponentCount(m.count));
    connection.on("round_ended", (m) => setView({ kind: "results", result: m.result }));

    connection.connect();
  };

  useEffect(() => connectionRef.current?.watchVisibility(), [view.kind]);

  if (view.kind === "lobby") return <Lobby onJoin={join} />;

  if (view.kind === "round") {
    return (
      <Round
        connection={connectionRef.current!}
        sourceWord={view.sourceWord}
        endsAt={view.endsAt}
        solutionCount={view.solutionCount}
        opponentCount={opponentCount}
      />
    );
  }

  return (
    <Results
      result={view.result}
      onNext={() => connectionRef.current?.startRound()}
      onFlagRound={() => {
        void fetch("/api/flag", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ source_word: view.result.source_word }),
        });
      }}
    />
  );
}
```

- [ ] **Step 6: Add the flag endpoint to the server**

Add to `wortissimo/server/app.py`, inside `create_app`, next to the other routes:

```python
    class FlagRound(BaseModel):
        source_word: str

    @app.post("/api/flag")
    def flag_round(body: FlagRound) -> dict:
        """Append a flagged round for manual blocklist review (spec section 11)."""
        path = Path("data/flagged.txt")
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"{body.source_word}\n")
        return {"ok": True}
```

- [ ] **Step 7: Run the full suite and build**

Run: `.venv/Scripts/python.exe -m pytest -v && cd web && npx vitest run --environment jsdom && npm run build`
Expected: all Python tests pass, all Vitest tests pass, `web/dist/` is produced.

- [ ] **Step 8: Commit**

```bash
git add web/src wortissimo/server/app.py
git commit -m "feat: add lobby, round, and results screens"
```

---

### Task 9: Deployment on the home server

**Files:**
- Create: `Dockerfile`
- Create: `docker-compose.yml`
- Create: `README.md`
- Create: `tests/e2e/reconnect.spec.ts`, `web/playwright.config.ts`

**Interfaces:**
- Produces: a running container reachable at `https://<host>.<tailnet>.ts.net`.

Spec §16 open item resolved here: `puzzles.sqlite` is **generated during the image build**, not committed — it is a large derived artifact and the raw dictionary is a 6MB download.

- [ ] **Step 1: Write the Playwright reconnect test**

Create `web/playwright.config.ts`:

```ts
import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  testDir: "../tests/e2e",
  use: { baseURL: "http://127.0.0.1:8000", ...devices["iPhone 14"] },
});
```

Create `tests/e2e/reconnect.spec.ts`:

```ts
import { expect, test } from "@playwright/test";

test("a word submitted while offline survives reconnection", async ({ page, context }) => {
  await page.goto("/");
  await page.getByPlaceholder("Dein Name").fill("jw");
  await page.getByRole("button", { name: "Neues Spiel" }).click();
  await page.getByRole("button", { name: "Nächste Runde" }).click().catch(() => {});

  const source = await page.locator(".source-word").innerText();
  expect(source.length).toBeGreaterThan(10);

  // Simulate the phone locking: kill connectivity, type anyway, restore.
  await context.setOffline(true);
  await page.getByPlaceholder("Wort eingeben").fill(source.slice(0, 4).toLowerCase());
  await page.getByRole("button", { name: "OK" }).click();
  await context.setOffline(false);

  // The outbox replays on reconnect; the word must appear as accepted.
  await expect(page.locator(".chip")).toHaveCount(1, { timeout: 15_000 });
});

test("the timer is recomputed from the absolute deadline after backgrounding", async ({ page }) => {
  await page.goto("/");
  await page.getByPlaceholder("Dein Name").fill("jw");
  await page.getByRole("button", { name: "Neues Spiel" }).click();

  const before = await page.locator(".timer").innerText();
  await page.evaluate(() => document.dispatchEvent(new Event("visibilitychange")));
  await page.waitForTimeout(2000);
  const after = await page.locator(".timer").innerText();
  expect(after).not.toBe(before);
});
```

- [ ] **Step 2: Write the Dockerfile**

Create `Dockerfile`:

```dockerfile
# --- frontend build ---
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# --- puzzle corpus build ---
FROM python:3.13-slim AS puzzles
WORKDIR /app
RUN pip install --no-cache-dir split-words==0.1.3 wordfreq==3.1.1 py7zr
COPY pyproject.toml ./
COPY wortissimo/ ./wortissimo/
COPY scripts/ ./scripts/
COPY data/blocklist.txt ./data/blocklist.txt
# puzzles.sqlite is a large derived artifact, so it is generated here
# rather than committed to the repository (spec section 16).
RUN python scripts/fetch_dictionary.py && python scripts/build_puzzles.py

# --- runtime ---
FROM python:3.13-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi uvicorn[standard] pydantic
COPY pyproject.toml ./
COPY wortissimo/ ./wortissimo/
COPY --from=puzzles /app/data/puzzles.sqlite ./data/puzzles.sqlite
COPY --from=web /web/dist ./web/dist
ENV WORTISSIMO_PUZZLES=/app/data/puzzles.sqlite \
    WORTISSIMO_GAMES=/app/data/games.sqlite \
    WORTISSIMO_STATIC=/app/web/dist
EXPOSE 8000
CMD ["uvicorn", "wortissimo.server.app:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 3: Make the app read its paths from the environment**

Add to the bottom of `wortissimo/server/app.py`:

```python
import os

app = create_app(
    puzzles_path=Path(os.environ.get("WORTISSIMO_PUZZLES", "data/puzzles.sqlite")),
    games_path=Path(os.environ.get("WORTISSIMO_GAMES", "data/games.sqlite")),
    static_dir=Path(os.environ["WORTISSIMO_STATIC"])
    if os.environ.get("WORTISSIMO_STATIC") else None,
)
```

- [ ] **Step 4: Write the compose file**

Create `docker-compose.yml`:

```yaml
services:
  wortissimo:
    build: .
    restart: unless-stopped
    ports:
      - "127.0.0.1:8000:8000"
    volumes:
      - wortissimo-data:/app/data

volumes:
  wortissimo-data:
```

Binding to `127.0.0.1` is deliberate: the only way in is `tailscale serve`, so the game is never exposed on the LAN or the internet.

- [ ] **Step 5: Build and run**

```bash
docker compose build
docker compose up -d
curl http://127.0.0.1:8000/api/health
```
Expected: `{"status":"ok"}`. The build takes a while — the puzzle stage downloads the dictionary and runs the full generator.

- [ ] **Step 6: Publish over Tailscale**

```bash
sudo tailscale serve --bg --https=443 http://127.0.0.1:8000
tailscale serve status
```
Expected: a `https://<host>.<tailnet>.ts.net` URL. Open it on the iPhone. Confirm the padlock — without a real certificate the service worker will not register and the PWA cannot be installed.

- [ ] **Step 7: Verify on the actual devices**

This is the acceptance gate and cannot be automated. On both the iPhone and the iPad:

1. Open the `ts.net` URL in Safari. Share → **Zum Home-Bildschirm**.
2. Launch from the home screen icon. Confirm no Safari chrome, and no content under the notch or home indicator.
3. Start a round. Confirm the input does **not** zoom the page when focused.
4. Type a word with an umlaut. Confirm iOS does not autocorrect it.
5. Confirm the keyboard stays up after submitting, and the input bar sits directly above it.
6. **Lock the phone for 30 seconds mid-round. Unlock.** The timer must show the correct remaining time immediately, not a frozen or drifted value, and previously accepted words must still be listed.
7. Enable airplane mode, submit a word, disable airplane mode. The word must appear as accepted within a few seconds.
8. Play a full round on both devices simultaneously and confirm scoring, unique-word bonuses, and the missed-words list.

- [ ] **Step 8: Write the README**

Create `README.md`:

```markdown
# Wortissimo

Zwei-Spieler-Wortspiel. Finde deutsche Wörter, die als zusammenhängende
Zeichenfolge in einem langen Ausgangswort stecken.

## Betrieb

    docker compose up -d --build
    sudo tailscale serve --bg --https=443 http://127.0.0.1:8000

Danach die `*.ts.net`-Adresse auf dem iPhone öffnen und über
"Zum Home-Bildschirm" installieren.

## Entwicklung

    python -m venv .venv
    .venv/Scripts/python.exe -m pip install -e ".[dev]"
    .venv/Scripts/python.exe scripts/fetch_dictionary.py
    .venv/Scripts/python.exe scripts/build_puzzles.py
    .venv/Scripts/python.exe -m uvicorn wortissimo.server.app:app --reload
    cd web && npm run dev

## Tests

    .venv/Scripts/python.exe -m pytest
    cd web && npx vitest run --environment jsdom
    cd web && npx playwright test

## Schlechte Wörter

Runden, die über "Schlechte Runde" gemeldet wurden, landen in
`data/flagged.txt`. Wörter daraus nach Prüfung in `data/blocklist.txt`
eintragen und `scripts/build_puzzles.py` erneut laufen lassen.

## Wörterbuch

Free German Dictionary (gemeinfrei), <https://sourceforge.net/projects/germandict/>.
Häufigkeiten aus `wordfreq`.
```

- [ ] **Step 9: Commit**

```bash
git add Dockerfile docker-compose.yml README.md web/playwright.config.ts tests/e2e
git commit -m "feat: add container build, tailscale deployment, and e2e reconnect tests"
```

---

## Phase 2 Exit Criteria

1. `pytest` and `vitest` pass with no skips.
2. Both reconnect tests in `tests/server/test_ws.py` pass.
3. `test_state_sync_never_contains_the_solution_set` passes — the anti-cheat invariant.
4. All eight manual device checks in Task 9 Step 7 pass on a real iPhone **and** a real iPad.
5. A full 10-round game has been played on two devices simultaneously.
6. `wortissimo/rules/` is unchanged since Phase 1, or its Phase 1 tests still pass.

## Self-Review Notes

Spec coverage check against `2026-09-06-wortissimo-design.md`:

- §4.2 runtime holds no dictionary → Task 2; `PuzzleRepo` loads one puzzle's solutions.
- §5 module boundaries → `server/` imports `rules`, never the reverse.
- §8.1 clock → Task 5 (`Pong`), Task 7 (`Clock`), Task 8 (recompute on visibility).
- §8.2 outbox → Task 7 (`Outbox`), Task 1 (unique `client_uuid`), Task 4 (`seen_uuids`).
- §8.3 reconnect → Task 7 (`watchVisibility`), Task 5 (resync on join).
- §8.4 authority → Task 4 (`TOO_LATE`, `end_round` ignores absent players), Task 5 (server-side timer).
- §8.5 anti-cheat → Task 3 (message shape), Task 4 (`snapshot`), tested in Task 5.
- §11 rules and reject button → Task 4 (`DUPLICATE`), Task 8 (flag button + endpoint).
- §12 data model → Task 1.
- §13 Apple requirements → Task 6 (viewport, CSS), Task 8 (input attributes, `useKeyboardInset`), Task 9 Step 7 (device verification).
- §14 testing → Tasks 1-5 (pytest), Task 7 (vitest), Task 9 (Playwright).
- §16 open items → all resolved: `wordfreq` (Phase 1 Task 5), compose + `tailscale serve` (Task 9), `puzzles.sqlite` built in the image rather than committed (Task 9 Step 2).

Known follow-ups deliberately not in this plan:

- `round_idx` is hardcoded to 0 in `Connection.submit`. Harmless because the server validates against its own active round, but it should carry the real index once more than one round has been played end to end.
- The room registry is in-memory: restarting the container drops in-flight rounds. Games and submissions are persisted, so a restart between rounds is safe. Full mid-round recovery is not worth building for two players.
