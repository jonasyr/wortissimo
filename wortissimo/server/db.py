"""Game persistence (spec section 12, games half).

submissions is append-only: rows are never updated or deleted. Scoring is
a projection over them, which is what makes reconnect-replay naturally
idempotent — the unique index on client_uuid does the deduplication.
"""

import json
import sqlite3
import time
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


def now_ms() -> int:
    return int(time.time() * 1000)


def create_game(conn: sqlite3.Connection, code: str, config: dict) -> int:
    cur = conn.execute(
        "INSERT INTO games (code, config_json, state, created_at)"
        " VALUES (?, ?, 'lobby', ?)",
        (code, json.dumps(config), now_ms()),
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


def rejected_words(conn: sqlite3.Connection, round_id: int) -> dict[str, list[str]]:
    """Words that did not count, per player, in submission order.

    These rows were always recorded; blind mode is simply the first thing
    that reads them back. Repeats of the same wrong word collapse — the
    player does not need to be told twice.
    """
    out: dict[str, list[str]] = {}
    seen: set[tuple[str, str]] = set()
    for row in conn.execute(
        "SELECT player, word FROM submissions"
        " WHERE round_id=? AND accepted=0 ORDER BY at, id",
        (round_id,),
    ):
        key = (row["player"], row["word"])
        if key in seen:
            continue
        seen.add(key)
        out.setdefault(row["player"], []).append(row["word"])
    return out
