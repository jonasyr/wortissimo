"""Drive the full generation pipeline for a set of candidate source words."""

import random
import sqlite3
from array import array
from collections.abc import Callable, Iterable, Iterator, Mapping

from wortissimo.generator.difficulty import (
    classify_difficulty, could_qualify, metrics,
)
from wortissimo.generator.segment import segment
from wortissimo.generator.solve import find_accepted, find_solutions
from wortissimo.generator.store import insert_puzzle
from wortissimo.lexicon.lists import Lexicon
from wortissimo.lexicon.packed import PackedWordSet

COMMIT_EVERY = 50
MIN_SOURCE_LENGTH = 15
MAX_SOURCE_LENGTH = 40


def candidate_source_words(lexicon: Lexicon) -> list[str]:
    """Every dictionary word long enough to be a plausible round.

    Sorted for deterministic build output.
    """
    return sorted(
        w for w in lexicon.acceptance
        if MIN_SOURCE_LENGTH <= len(w) <= MAX_SOURCE_LENGTH
    )


def candidate_indices(acceptance: PackedWordSet, seed: int = 0) -> array:
    """Shuffled positions of every plausible source word.

    Holds indices, not strings: the packed acceptance set decodes on
    access, so materialising a million candidate strings would cost ~76MB
    where an index array costs ~4MB.

    Shuffling matters for correctness of the sample, not just fairness:
    scanning in sorted order takes every puzzle from the start of the
    alphabet and, because short words dominate, skews the corpus heavily
    towards the easiest bucket.
    """
    indices = array("I", (
        i for i in range(len(acceptance))
        if MIN_SOURCE_LENGTH <= len(acceptance.word_at(i)) <= MAX_SOURCE_LENGTH
    ))
    random.Random(seed).shuffle(indices)
    return indices


def iter_candidates(
    acceptance: PackedWordSet, indices: Iterable[int]
) -> Iterator[str]:
    """Decode candidate source words one at a time."""
    for index in indices:
        yield acceptance.word_at(index)


def shuffled_candidates(lexicon: Lexicon, seed: int = 0) -> list[str]:
    """Eager variant, for tests and small lexicons."""
    words = candidate_source_words(lexicon)
    random.Random(seed).shuffle(words)
    return words


def build_puzzles(
    lexicon: Lexicon,
    conn: sqlite3.Connection,
    candidates: Iterable[str],
    limit: int | None = None,
    progress: Callable[[int, int], None] | None = None,
    caps: Mapping[str, int] | None = None,
    already: Mapping[str, int] | None = None,
) -> int:
    """Generate puzzles for `candidates` and write those that qualify.

    Returns the number of puzzles written. Candidates fitting no
    difficulty bucket are silently discarded — that is the normal case for
    most long German words.

    `caps` limits how many puzzles are kept per difficulty and stops the
    scan once every capped bucket is full. Brutal candidates are ~0.4% of
    the yield, so without caps the corpus would be almost entirely Leicht.
    """
    written = 0
    # Rows already in the database count towards the caps, so an
    # interrupted build resumes instead of restarting.
    per_difficulty: dict[str, int] = dict(already or {})

    for seen, source in enumerate(candidates, start=1):
        if limit is not None and written >= limit:
            break
        if caps and all(per_difficulty.get(d, 0) >= c for d, c in caps.items()):
            break

        # Classify without boundaries first: segmentation is the expensive
        # step and most candidates fail on solution count alone.
        solutions = find_solutions(source, lexicon, ())
        if not could_qualify(source, solutions):
            continue

        boundaries = segment(source, lexicon.solutions)
        solutions = find_solutions(source, lexicon, boundaries)
        difficulty = classify_difficulty(source, solutions)
        if difficulty is None:
            continue
        if caps and per_difficulty.get(str(difficulty), 0) >= caps.get(
            str(difficulty), 1 << 30
        ):
            continue

        meta = metrics(source, solutions)
        meta["boundaries"] = list(boundaries)
        try:
            insert_puzzle(conn, source, str(difficulty), solutions, meta,
                          accepted_only=find_accepted(source, lexicon))
        except sqlite3.IntegrityError:
            continue  # already have this source word
        written += 1
        per_difficulty[str(difficulty)] = per_difficulty.get(str(difficulty), 0) + 1

        # Commit as we go. Committing only at the end meant an interrupted
        # build lost everything, which silently made --resume useless: there
        # was never any partial state left to resume from.
        if written % COMMIT_EVERY == 0:
            conn.commit()

        if progress and written % 200 == 0:
            progress(seen, written)

    conn.commit()
    return written
