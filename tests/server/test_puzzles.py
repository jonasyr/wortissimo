import sqlite3

import pytest

from wortissimo.generator.solve import Category, Solution
from wortissimo.generator.store import create_schema, insert_puzzle
from wortissimo.server.puzzles import PuzzleRepo

REVEALED = [
    Solution("bahn", Category.OBVIOUS_COMPONENT, 5.0),
    Solution("halte", Category.CROSS_BOUNDARY, 4.8),
]
ACCEPTED_ONLY = ["enbahn", "nhalte"]


@pytest.fixture
def repo(tmp_path):
    path = tmp_path / "puzzles.sqlite"
    conn = sqlite3.connect(path)
    create_schema(conn)
    insert_puzzle(conn, "strassenbahnhalte", "mittel", REVEALED, {},
                  accepted_only=ACCEPTED_ONLY)
    insert_puzzle(conn, "bundesausbildungsgesetz", "schwer", REVEALED, {})
    conn.commit()
    conn.close()
    return PuzzleRepo(path)


def test_picks_a_puzzle_of_the_requested_difficulty(repo):
    puzzle = repo.pick("mittel", exclude=set())
    assert puzzle.difficulty == "mittel"
    assert puzzle.source_word == "strassenbahnhalte"


def test_revealed_holds_only_the_clean_solutions(repo):
    assert repo.pick("mittel", exclude=set()).revealed == frozenset({"bahn", "halte"})


def test_accepted_is_the_generous_superset(repo):
    """The bug this test exists for.

    Validating against `revealed` would reject ordinary inflected forms
    that the acceptance list knows. `accepted` must carry both tiers.
    """
    puzzle = repo.pick("mittel", exclude=set())
    assert puzzle.accepted == frozenset({"bahn", "halte", "enbahn", "nhalte"})
    assert puzzle.revealed < puzzle.accepted


def test_solution_count_counts_revealed_only(repo):
    puzzle = repo.pick("mittel", exclude=set())
    assert puzzle.solution_count == 2


def test_excludes_already_used_puzzles(repo):
    first = repo.pick("mittel", exclude=set())
    assert repo.pick("mittel", exclude={first.id}) is None


def test_returns_none_when_no_puzzle_matches(repo):
    assert repo.pick("brutal", exclude=set()) is None


def test_get_by_id_round_trips(repo):
    picked = repo.pick("schwer", exclude=set())
    assert repo.get(picked.id).source_word == picked.source_word


def test_get_raises_for_an_unknown_id(repo):
    with pytest.raises(KeyError):
        repo.get(9999)


def test_counts_available_puzzles_per_difficulty(repo):
    assert repo.count("mittel") == 1
    assert repo.count("brutal") == 0
