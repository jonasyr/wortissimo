"""puzzles.sqlite schema and writes (spec section 12, puzzles half)."""

import json
import sqlite3
from collections.abc import Sequence

from wortissimo.generator.solve import Solution

SCHEMA = """
CREATE TABLE IF NOT EXISTS puzzles (
    id             INTEGER PRIMARY KEY,
    source_word    TEXT    NOT NULL UNIQUE,
    difficulty     TEXT    NOT NULL,
    solution_count INTEGER NOT NULL,
    meta_json      TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS solutions (
    puzzle_id INTEGER NOT NULL REFERENCES puzzles(id) ON DELETE CASCADE,
    word      TEXT    NOT NULL,
    category  TEXT    NOT NULL,
    freq      REAL    NOT NULL,
    -- revealed=1: clean solution, shown as a "word you missed" and counted
    -- in solution_count. revealed=0: accepted if the player types it, but
    -- never revealed. Spec section 6, two-tier lists.
    revealed  INTEGER NOT NULL DEFAULT 1,
    PRIMARY KEY (puzzle_id, word)
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_puzzles_difficulty ON puzzles(difficulty);
"""


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)
    conn.commit()


def insert_puzzle(
    conn: sqlite3.Connection,
    source_word: str,
    difficulty: str,
    solutions: Sequence[Solution],
    meta: dict,
    accepted_only: Sequence[str] = (),
) -> int:
    """Insert one puzzle, its revealed solutions, and its accepted-only words.

    `accepted_only` are substrings a player may score but which are never
    revealed, because they are below the solution list's quality bar.
    """
    cur = conn.execute(
        "INSERT INTO puzzles (source_word, difficulty, solution_count, meta_json)"
        " VALUES (?, ?, ?, ?)",
        (source_word, difficulty, len(solutions), json.dumps(meta)),
    )
    puzzle_id = int(cur.lastrowid)
    conn.executemany(
        "INSERT INTO solutions (puzzle_id, word, category, freq, revealed)"
        " VALUES (?, ?, ?, ?, ?)",
        [(puzzle_id, s.word, str(s.category), s.freq, 1) for s in solutions],
    )
    revealed = {s.word for s in solutions}
    conn.executemany(
        "INSERT INTO solutions (puzzle_id, word, category, freq, revealed)"
        " VALUES (?, ?, ?, ?, ?)",
        [(puzzle_id, w, "accepted_only", 0.0, 0)
         for w in sorted(set(accepted_only) - revealed)],
    )
    return puzzle_id
