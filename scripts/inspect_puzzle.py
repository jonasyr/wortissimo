"""Print one puzzle and its full solution list, for eyeballing quality.

Usage:
    python scripts/inspect_puzzle.py [--difficulty schwer] [--db PATH] [-n 1]
"""

import argparse
import json
import sqlite3
from pathlib import Path

DEFAULT_DB = Path("data/puzzles.sqlite")


def show(conn: sqlite3.Connection, row: sqlite3.Row) -> None:
    pid, source, difficulty, meta_json = row
    meta = json.loads(meta_json)
    boundaries = meta.get("boundaries", [])
    marked = source
    for offset in reversed(boundaries):
        marked = marked[:offset] + "|" + marked[offset:]

    print(f"\n{source.upper()}  [{difficulty}]")
    print(f"  segmented: {marked}")
    print(f"  solutions={meta.get('solution_count')} "
          f"cross={meta.get('cross_boundary_count')} "
          f"long={meta.get('long_count')} "
          f"trivial={meta.get('trivial_share', 0):.0%}")

    print("  REVEALED (shown as \"words you missed\"; * = cross-boundary):")
    for word, category, freq in conn.execute(
        "SELECT word, category, freq FROM solutions"
        " WHERE puzzle_id=? AND revealed=1 ORDER BY LENGTH(word) DESC, word",
        (pid,),
    ):
        flag = "*" if category == "cross_boundary" else " "
        print(f"   {flag} {word:<28} zipf {freq:.2f}")

    hidden = [w for (w,) in conn.execute(
        "SELECT word FROM solutions WHERE puzzle_id=? AND revealed=0"
        " ORDER BY LENGTH(word) DESC, word", (pid,))]
    if hidden:
        print("  ACCEPTED ONLY (scored if typed, never revealed):")
        print("    " + ", ".join(hidden))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--difficulty", default=None)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("-n", type=int, default=1, help="how many to show")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    where = " WHERE difficulty=?" if args.difficulty else ""
    params = (args.difficulty,) if args.difficulty else ()
    rows = conn.execute(
        f"SELECT id, source_word, difficulty, meta_json FROM puzzles{where}"
        f" ORDER BY RANDOM() LIMIT {args.n}",
        params,
    ).fetchall()

    if not rows:
        print("no puzzles found")
        return 1
    for row in rows:
        show(conn, row)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
