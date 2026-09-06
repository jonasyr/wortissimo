"""Play one Wortissimo round in the terminal against the real pipeline.

This exists to validate puzzle quality before any UI is built. It uses the
same rules package the server will use in Phase 2, and the same two-tier
word lists: input is validated against the puzzle's ACCEPTED set, while
only the REVEALED solutions are shown as words you missed.

Usage:
    python scripts/play.py [--difficulty mittel] [--seconds 180]
"""

import argparse
import sqlite3
import time
from pathlib import Path

from wortissimo.rules.scoring import score_round
from wortissimo.rules.validate import validate_word

DEFAULT_DB = Path("data/puzzles.sqlite")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--difficulty", default=None)
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    where = " WHERE difficulty=?" if args.difficulty else ""
    params = (args.difficulty,) if args.difficulty else ()
    row = conn.execute(
        f"SELECT id, source_word, difficulty FROM puzzles{where}"
        " ORDER BY RANDOM() LIMIT 1",
        params,
    ).fetchone()
    if row is None:
        print("no puzzles found - run scripts/build_puzzles.py first")
        return 1
    puzzle_id, source, difficulty = row

    revealed = [w for (w,) in conn.execute(
        "SELECT word FROM solutions WHERE puzzle_id=? AND revealed=1",
        (puzzle_id,))]
    accepted = {w for (w,) in conn.execute(
        "SELECT word FROM solutions WHERE puzzle_id=?", (puzzle_id,))}

    print(f"\n  {source.upper()}   [{difficulty}]\n")
    print(f"  {len(revealed)} Lösungen. {args.seconds} Sekunden.")
    print("  Leere Eingabe beendet die Runde.\n")

    deadline = time.monotonic() + args.seconds
    found: list[str] = []

    while True:
        remaining = int(deadline - time.monotonic())
        if remaining <= 0:
            print("\n  Zeit abgelaufen!")
            break
        try:
            raw = input(f"  [{remaining:3d}s] > ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if not raw:
            break
        if time.monotonic() >= deadline:
            print("        zu spät")
            break

        verdict = validate_word(raw, source, accepted)
        if not verdict.accepted:
            print(f"        abgelehnt: {verdict.reason}")
        elif verdict.word in found:
            print("        schon gefunden")
        else:
            found.append(verdict.word)
            bonus = "" if verdict.word in revealed else "  (nicht in der Lösungsliste)"
            print(f"        ok ({len(found)}){bonus}")

    result = score_round({"du": found}, revealed)
    score = result.scores[0]
    print(f"\n  {score.points} Punkte - {len(found)} gefunden "
          f"von {len(revealed)} Lösungen\n")
    if result.missed_words:
        print("  verpasst:")
        line = "   "
        for word in result.missed_words:
            if len(line) + len(word) > 74:
                print(line)
                line = "   "
            line += f" {word}"
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
