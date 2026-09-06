import json
import sqlite3

from wortissimo.generator.solve import Category, Solution
from wortissimo.generator.store import create_schema, insert_puzzle


def conn():
    c = sqlite3.connect(":memory:")
    create_schema(c)
    return c


SOLUTIONS = [
    Solution("bahn", Category.OBVIOUS_COMPONENT, 5.04),
    Solution("enba", Category.CROSS_BOUNDARY, 3.7),
]


def test_inserts_and_reads_back_a_puzzle():
    c = conn()
    pid = insert_puzzle(c, "strassenbahn", "mittel", SOLUTIONS, {"length": 12})
    row = c.execute(
        "SELECT source_word, difficulty, solution_count FROM puzzles WHERE id=?",
        (pid,),
    ).fetchone()
    assert row == ("strassenbahn", "mittel", 2)


def test_inserts_all_solutions_linked_to_the_puzzle():
    c = conn()
    pid = insert_puzzle(c, "strassenbahn", "mittel", SOLUTIONS, {})
    rows = c.execute(
        "SELECT word, category, freq FROM solutions WHERE puzzle_id=? ORDER BY word",
        (pid,),
    ).fetchall()
    assert rows == [("bahn", "obvious_component", 5.04),
                    ("enba", "cross_boundary", 3.7)]


def test_meta_roundtrips_as_json():
    c = conn()
    pid = insert_puzzle(c, "strassenbahn", "mittel", SOLUTIONS, {"length": 12})
    (raw,) = c.execute("SELECT meta_json FROM puzzles WHERE id=?", (pid,)).fetchone()
    assert json.loads(raw)["length"] == 12


def test_source_word_is_unique():
    c = conn()
    insert_puzzle(c, "strassenbahn", "mittel", SOLUTIONS, {})
    try:
        insert_puzzle(c, "strassenbahn", "schwer", SOLUTIONS, {})
    except sqlite3.IntegrityError:
        return
    raise AssertionError("expected IntegrityError on duplicate source word")


def test_difficulty_is_indexed_for_round_selection():
    c = conn()
    names = {r[1] for r in c.execute("PRAGMA index_list(puzzles)")}
    assert any("difficulty" in n for n in names)


def test_accepted_only_words_are_stored_unrevealed():
    c = conn()
    pid = insert_puzzle(c, "strassenbahn", "mittel", SOLUTIONS, {},
                        accepted_only=["ssen", "enba"])
    revealed = {r[0] for r in c.execute(
        "SELECT word FROM solutions WHERE puzzle_id=? AND revealed=1", (pid,))}
    hidden = {r[0] for r in c.execute(
        "SELECT word FROM solutions WHERE puzzle_id=? AND revealed=0", (pid,))}
    assert revealed == {"bahn", "enba"}
    assert hidden == {"ssen"}


def test_solution_count_counts_only_revealed_words():
    c = conn()
    pid = insert_puzzle(c, "strassenbahn", "mittel", SOLUTIONS, {},
                        accepted_only=["ssen", "rass", "asse"])
    (count,) = c.execute(
        "SELECT solution_count FROM puzzles WHERE id=?", (pid,)).fetchone()
    assert count == 2
