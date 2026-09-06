"""Read-only access to the Phase 1 puzzle corpus.

The server holds no dictionary. Per round it knows exactly two things:
that puzzle's revealed solutions and its accepted words (spec section 4.2).

Both tiers matter and they are not interchangeable:

  revealed  the clean list. Shown as "words you missed", and the
            denominator in "7 / 21 gefunden".

  accepted  the generous superset. What a player's input is validated
            against. Validating against `revealed` instead would reject
            ordinary inflected forms such as 'auflagenpunkte' — the exact
            failure the two-tier design exists to prevent.
"""

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Puzzle:
    id: int
    source_word: str
    difficulty: str
    revealed: frozenset[str]
    accepted: frozenset[str]

    @property
    def solution_count(self) -> int:
        """How many solutions exist, for the progress display."""
        return len(self.revealed)


class PuzzleRepo:
    def __init__(self, path: Path) -> None:
        self._conn = sqlite3.connect(
            f"file:{path}?mode=ro", uri=True, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row

    def _load(self, row: sqlite3.Row) -> Puzzle:
        revealed: set[str] = set()
        accepted: set[str] = set()
        for word, is_revealed in self._conn.execute(
            "SELECT word, revealed FROM solutions WHERE puzzle_id=?", (row["id"],)
        ):
            accepted.add(word)
            if is_revealed:
                revealed.add(word)
        return Puzzle(
            id=row["id"],
            source_word=row["source_word"],
            difficulty=row["difficulty"],
            revealed=frozenset(revealed),
            accepted=frozenset(accepted),
        )

    def pick(self, difficulty: str, exclude: set[int]) -> Puzzle | None:
        """Random unused puzzle of this difficulty, or None if exhausted."""
        # The exclusion clause is omitted entirely when there is nothing to
        # exclude: `id NOT IN (NULL)` evaluates to NULL, not true, so it
        # would silently match no rows and break the first round of every
        # game.
        clause, params = "", [difficulty]
        if exclude:
            clause = f" AND id NOT IN ({','.join('?' * len(exclude))})"
            params.extend(exclude)
        row = self._conn.execute(
            f"SELECT * FROM puzzles WHERE difficulty=?{clause}"
            " ORDER BY RANDOM() LIMIT 1",
            params,
        ).fetchone()
        return self._load(row) if row else None

    def get(self, puzzle_id: int) -> Puzzle:
        row = self._conn.execute(
            "SELECT * FROM puzzles WHERE id=?", (puzzle_id,)
        ).fetchone()
        if row is None:
            raise KeyError(puzzle_id)
        return self._load(row)

    def count(self, difficulty: str) -> int:
        (n,) = self._conn.execute(
            "SELECT COUNT(*) FROM puzzles WHERE difficulty=?", (difficulty,)
        ).fetchone()
        return int(n)
