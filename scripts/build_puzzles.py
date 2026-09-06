"""Build data/puzzles.sqlite from the German word list.

Usage:
    python scripts/build_puzzles.py [--limit N] [--out PATH] [--scan N]
"""

import argparse
import sqlite3
import time
from pathlib import Path

from wortissimo.generator.build import (
    build_puzzles, candidate_indices, iter_candidates,
)
from wortissimo.generator.store import create_schema
from wortissimo.lexicon.lists import (
    lexicon_from_acceptance, load_blocklist, load_or_build_acceptance,
)
from wortissimo.lexicon.source import iter_normalized

DEFAULT_OUT = Path("data/puzzles.sqlite")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="stop after writing N puzzles")
    parser.add_argument("--scan", type=int, default=None,
                        help="only consider the first N candidate source words")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--per-difficulty", type=int, default=500,
                        help="max puzzles to keep per difficulty (0 = no cap)")
    args = parser.parse_args()

    started = time.monotonic()
    print("Loading dictionary...")
    acceptance = load_or_build_acceptance(iter_normalized(), load_blocklist())
    lexicon = lexicon_from_acceptance(acceptance)
    print(f"  acceptance {len(lexicon.acceptance):,}"
          "  (solutions decided lazily by Hunspell)")

    indices = candidate_indices(acceptance)
    print(f"  candidate source words {len(indices):,}")
    if args.scan:
        indices = indices[: args.scan]
        print(f"  scanning first {len(indices):,}")
    candidates = iter_candidates(acceptance, indices)

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        args.out.unlink()
    conn = sqlite3.connect(args.out)
    create_schema(conn)

    def progress(seen: int, written: int) -> None:
        rate = seen / max(1e-9, time.monotonic() - started)
        print(f"  {seen:,} scanned / {written:,} written  ({rate:.0f}/s)",
              flush=True)

    caps = None
    if args.per_difficulty:
        caps = {d: args.per_difficulty
                for d in ("leicht", "mittel", "schwer", "brutal")}

    written = build_puzzles(lexicon, conn, candidates, limit=args.limit,
                            progress=progress, caps=caps)

    rows = conn.execute(
        "SELECT difficulty, COUNT(*) FROM puzzles GROUP BY difficulty"
    ).fetchall()
    conn.close()

    print(f"\nWrote {written:,} puzzles to {args.out} "
          f"in {time.monotonic() - started:.0f}s")
    for difficulty, count in sorted(rows):
        print(f"  {difficulty:8s} {count:,}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
