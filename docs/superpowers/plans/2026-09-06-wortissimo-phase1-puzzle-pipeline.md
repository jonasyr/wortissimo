# Wortissimo Phase 1 — Puzzle Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the offline pipeline that turns a public-domain German word list into `puzzles.sqlite` — a database of vetted, difficulty-bucketed Wortissimo rounds with precomputed solution sets.

**Architecture:** Three packages with strictly one-way dependencies. `rules/` is pure (no I/O, no state) and defines normalization, substring validation, and scoring; it is imported by both this phase and Phase 2, which is what guarantees the offline generator and the live game can never disagree about what counts as a word. `lexicon/` is build-time only and produces two word lists with opposite requirements (generous acceptance, clean solutions). `generator/` enumerates substrings, segments compounds, classifies solutions, and buckets by difficulty.

**Tech Stack:** Python 3.13, pytest, hypothesis, `split-words` 0.1.3 (CharSplit compound splitter), `wordfreq` 3.1.1, `py7zr`, stdlib `sqlite3`.

**Spec:** `docs/superpowers/specs/2026-09-06-wortissimo-design.md`

## Global Constraints

Every task's requirements implicitly include these.

- Python 3.13. Dependencies pinned in `pyproject.toml`.
- **`wortissimo/rules/` is pure.** No file I/O, no network, no global state, no config loading, no imports from `lexicon`, `generator`, or `server`. Violating this breaks the guarantee the whole design rests on.
- Dependency direction is one-way: `lexicon`, `generator`, `server` may import `rules`. Never the reverse.
- **germandict is Latin-1 (`cp1252`) encoded with CRLF line endings.** Decoding it as UTF-8 silently corrupts every umlaut. Always pass `encoding="latin-1"` explicitly.
- Canonical normalization is `str.casefold()`. Never `.lower()`. Note that `casefold()` already maps ß→ss (`"Straße".casefold() == "strasse"`), so no separate ß transform is needed.
- **Umlauts are preserved as umlauts.** No ae/oe/ue aliasing anywhere. Confirmed by the user: they type ä natively on the iOS German keyboard.
- Minimum word length: 3.
- Solution-list frequency floor: **zipf ≥ 3.5** (measured: separates `Ilm` 3.09 / `aer` 2.5 / `nde` 2.44 from `Raten` 4.29 / `Gesetz` 4.91).
- "Trivial" solution = `OBVIOUS_COMPONENT` **and** zipf ≥ 5.0.
- The compound splitter's module name is **`split_words`**, not `charsplit`. The PyPI distribution is `split-words`.
- All data written to `data/` except `data/raw/` (gitignored) is a build artifact.
- Commit after every task. Conventional commit messages (`feat:`, `test:`, `chore:`).

---

### Task 1: Project scaffold and `rules.normalize`

**Files:**
- Create: `pyproject.toml`
- Create: `wortissimo/__init__.py`
- Create: `wortissimo/rules/__init__.py`
- Create: `wortissimo/rules/normalize.py`
- Test: `tests/rules/test_normalize.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `wortissimo.rules.normalize.normalize(text: str) -> str`, and `wortissimo.rules.normalize.LETTERS: frozenset[str]`.

- [ ] **Step 1: Create `pyproject.toml`**

```toml
[project]
name = "wortissimo"
version = "0.1.0"
requires-python = ">=3.13"
dependencies = [
    "split-words==0.1.3",
    "wordfreq==3.1.1",
    "py7zr>=0.21",
]

[project.optional-dependencies]
dev = ["pytest>=8", "pytest-asyncio>=0.24", "hypothesis>=6"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
include = ["wortissimo*"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Create empty package files**

```bash
mkdir -p wortissimo/rules tests/rules
touch wortissimo/__init__.py wortissimo/rules/__init__.py
touch tests/__init__.py tests/rules/__init__.py
```

- [ ] **Step 3: Write the failing test**

Create `tests/rules/test_normalize.py`:

```python
import pytest
from hypothesis import given, strategies as st

from wortissimo.rules.normalize import normalize


def test_casefolds():
    assert normalize("HAUS") == "haus"


def test_eszett_becomes_ss():
    # casefold() already does this; this test pins the behaviour so a
    # future switch to .lower() would fail loudly.
    assert normalize("Straße") == "strasse"


def test_umlauts_are_preserved_not_expanded():
    assert normalize("Bäcker") == "bäcker"
    assert normalize("Übung") == "übung"


def test_strips_surrounding_whitespace():
    assert normalize("  Haus \n") == "haus"


def test_rejects_non_letters():
    with pytest.raises(ValueError):
        normalize("Haus1")
    with pytest.raises(ValueError):
        normalize("Haus-Tür")
    with pytest.raises(ValueError):
        normalize("zwei Wörter")


def test_rejects_empty():
    with pytest.raises(ValueError):
        normalize("   ")


@given(st.text(alphabet="abcdefghijklmnopqrstuvwxyzäöü", min_size=1))
def test_is_idempotent(word):
    once = normalize(word)
    assert normalize(once) == once
```

- [ ] **Step 4: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/rules/test_normalize.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wortissimo.rules.normalize'`

- [ ] **Step 5: Write the implementation**

Create `wortissimo/rules/normalize.py`:

```python
"""Canonical word form. Pure: no I/O, no state.

This is the single definition of "the same word" used by both the offline
generator and the live server. If these two ever disagreed, the game would
reveal solutions it would then refuse to accept.
"""

LETTERS = frozenset("abcdefghijklmnopqrstuvwxyzäöü")


def normalize(text: str) -> str:
    """Return the canonical form of a single German word.

    casefold() is required rather than lower(): it maps ß to ss, so
    "Straße" and "Strasse" canonicalise identically.

    Raises ValueError if the input is empty or contains anything that is
    not a German letter.
    """
    folded = text.strip().casefold()
    if not folded:
        raise ValueError("empty word")
    bad = set(folded) - LETTERS
    if bad:
        raise ValueError(f"invalid characters: {sorted(bad)!r}")
    return folded
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/rules/test_normalize.py -v`
Expected: PASS (7 tests)

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml wortissimo tests
git commit -m "feat: add pure word normalization to rules package"
```

---

### Task 2: `rules.validate` — substring validation with explicit reasons

**Files:**
- Create: `wortissimo/rules/validate.py`
- Test: `tests/rules/test_validate.py`

**Interfaces:**
- Consumes: `normalize()` from Task 1.
- Produces:
  - `class Rejection(StrEnum)` with members `TOO_SHORT`, `NOT_A_SUBSTRING`, `NOT_IN_DICTIONARY`, `IS_SOURCE_WORD`, `MALFORMED`, `DUPLICATE`, `TOO_LATE`.
  - `@dataclass(frozen=True) class Verdict` with fields `word: str`, `accepted: bool`, `reason: Rejection | None`.
  - `validate_word(raw: str, source_word: str, acceptance: Container[str], min_length: int = 3) -> Verdict`

Spec §11 requires the UI to explain *why* a word was rejected, so validation returns a reason rather than a bool. `DUPLICATE` and `TOO_LATE` are defined here but produced by the server in Phase 2, not by this function — they are round-state concerns, not word concerns.

- [ ] **Step 1: Write the failing test**

Create `tests/rules/test_validate.py`:

```python
from wortissimo.rules.validate import Rejection, validate_word

SOURCE = "straßenbahnhaltestelle"
ACCEPTANCE = {"bahn", "halte", "stelle", "haltestelle", "strasse",
              "strassenbahnhaltestelle", "enbahn", "raten"}


def v(word):
    return validate_word(word, SOURCE, ACCEPTANCE)


def test_accepts_a_plain_substring():
    assert v("Bahn").accepted is True
    assert v("Bahn").reason is None


def test_accepted_word_is_returned_normalized():
    assert v("BAHN").word == "bahn"


def test_rejects_too_short():
    assert v("ba").reason is Rejection.TOO_SHORT


def test_rejects_word_not_contiguous_in_source():
    # 'raten' is a real word in the acceptance list but its letters do not
    # appear contiguously in the source word.
    assert v("Raten").reason is Rejection.NOT_A_SUBSTRING


def test_rejects_word_not_in_dictionary():
    # 'nenbah' IS a contiguous substring but is not a German word.
    assert v("nenbah").reason is Rejection.NOT_IN_DICTIONARY


def test_rejects_the_source_word_itself():
    assert v("Straßenbahnhaltestelle").reason is Rejection.IS_SOURCE_WORD


def test_rejects_malformed_input():
    assert v("bahn!").reason is Rejection.MALFORMED
    assert v("").reason is Rejection.MALFORMED


def test_source_word_is_normalized_before_matching():
    # Source given with capitals and ß; input given as ss.
    verdict = validate_word("Strasse", "Straßenbahn", {"strasse"})
    assert verdict.accepted is True


def test_check_order_short_beats_not_a_substring():
    # 'xy' is neither long enough nor a substring; length is reported first
    # because it is the more actionable message.
    assert v("xy").reason is Rejection.TOO_SHORT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/rules/test_validate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wortissimo.rules.validate'`

- [ ] **Step 3: Write the implementation**

Create `wortissimo/rules/validate.py`:

```python
"""Word validation. Pure: no I/O, no state."""

from collections.abc import Container
from dataclasses import dataclass
from enum import StrEnum

from wortissimo.rules.normalize import normalize

MIN_LENGTH = 3


class Rejection(StrEnum):
    TOO_SHORT = "too_short"
    NOT_A_SUBSTRING = "not_a_substring"
    NOT_IN_DICTIONARY = "not_in_dictionary"
    IS_SOURCE_WORD = "is_source_word"
    MALFORMED = "malformed"
    # Produced by the server (round state), not by validate_word.
    DUPLICATE = "duplicate"
    TOO_LATE = "too_late"


@dataclass(frozen=True)
class Verdict:
    word: str
    accepted: bool
    reason: Rejection | None


def validate_word(
    raw: str,
    source_word: str,
    acceptance: Container[str],
    min_length: int = MIN_LENGTH,
) -> Verdict:
    """Decide whether `raw` scores against `source_word`.

    Checks run cheapest-and-most-actionable first, so the player gets the
    most useful single reason rather than an arbitrary one.
    """
    try:
        word = normalize(raw)
    except ValueError:
        return Verdict(word=raw.strip().casefold(), accepted=False,
                       reason=Rejection.MALFORMED)

    source = normalize(source_word)

    if len(word) < min_length:
        return Verdict(word, False, Rejection.TOO_SHORT)
    if word == source:
        return Verdict(word, False, Rejection.IS_SOURCE_WORD)
    if word not in source:
        return Verdict(word, False, Rejection.NOT_A_SUBSTRING)
    if word not in acceptance:
        return Verdict(word, False, Rejection.NOT_IN_DICTIONARY)
    return Verdict(word, True, None)
```

Note: `word not in source` is Python's substring operator on `str`, which is exactly the "contiguous, in order, nothing skipped, nothing added" rule from spec §11.

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/rules/test_validate.py -v`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add wortissimo/rules/validate.py tests/rules/test_validate.py
git commit -m "feat: add word validation with explicit rejection reasons"
```

---

### Task 3: `rules.scoring` — round scoring

**Files:**
- Create: `wortissimo/rules/scoring.py`
- Test: `tests/rules/test_scoring.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (operates on already-validated words).
- Produces:
  - `@dataclass(frozen=True) class PlayerScore` with fields `player: str`, `points: int`, `words: tuple[str, ...]`, `unique_words: tuple[str, ...]`.
  - `@dataclass(frozen=True) class RoundResult` with fields `scores: tuple[PlayerScore, ...]`, `shared_words: tuple[str, ...]`, `missed_words: tuple[str, ...]`.
  - `score_round(accepted: Mapping[str, Iterable[str]], solutions: Iterable[str]) -> RoundResult`

Spec §11: 1 point per valid word, 2 points if no other player submitted it. Each distinct word scores at most once per player.

- [ ] **Step 1: Write the failing test**

Create `tests/rules/test_scoring.py`:

```python
from wortissimo.rules.scoring import score_round

SOLUTIONS = ["bahn", "halte", "stelle", "haltestelle", "strasse"]


def by_player(result):
    return {s.player: s for s in result.scores}


def test_shared_word_scores_one_each():
    result = score_round({"jw": ["bahn"], "gf": ["bahn"]}, SOLUTIONS)
    assert by_player(result)["jw"].points == 1
    assert by_player(result)["gf"].points == 1
    assert result.shared_words == ("bahn",)


def test_unique_word_scores_two():
    result = score_round({"jw": ["bahn"], "gf": ["halte"]}, SOLUTIONS)
    assert by_player(result)["jw"].points == 2
    assert by_player(result)["gf"].points == 2
    assert result.shared_words == ()


def test_unique_words_are_reported_per_player():
    result = score_round({"jw": ["bahn", "halte"], "gf": ["halte"]}, SOLUTIONS)
    assert by_player(result)["jw"].unique_words == ("bahn",)
    assert by_player(result)["gf"].unique_words == ()


def test_duplicate_submission_scores_once():
    result = score_round({"jw": ["bahn", "bahn"], "gf": []}, SOLUTIONS)
    assert by_player(result)["jw"].points == 2
    assert by_player(result)["jw"].words == ("bahn",)


def test_missed_words_are_solutions_nobody_found():
    result = score_round({"jw": ["bahn"], "gf": ["halte"]}, SOLUTIONS)
    assert result.missed_words == ("haltestelle", "stelle", "strasse")


def test_empty_round_scores_zero_and_misses_everything():
    result = score_round({"jw": [], "gf": []}, SOLUTIONS)
    assert by_player(result)["jw"].points == 0
    assert len(result.missed_words) == len(SOLUTIONS)


def test_output_ordering_is_deterministic():
    a = score_round({"jw": ["stelle", "bahn"], "gf": ["bahn"]}, SOLUTIONS)
    b = score_round({"jw": ["bahn", "stelle"], "gf": ["bahn"]}, SOLUTIONS)
    assert a == b


def test_solo_player_gets_two_points_per_word():
    result = score_round({"jw": ["bahn"]}, SOLUTIONS)
    assert by_player(result)["jw"].points == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/rules/test_scoring.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wortissimo.rules.scoring'`

- [ ] **Step 3: Write the implementation**

Create `wortissimo/rules/scoring.py`:

```python
"""Round scoring. Pure: no I/O, no state.

Scoring is a projection over the set of accepted words. It is deliberately
a pure function of its inputs so it can be recomputed at any time from the
append-only submissions table.
"""

from collections.abc import Iterable, Mapping
from dataclasses import dataclass

POINTS_SHARED = 1
POINTS_UNIQUE = 2


@dataclass(frozen=True)
class PlayerScore:
    player: str
    points: int
    words: tuple[str, ...]
    unique_words: tuple[str, ...]


@dataclass(frozen=True)
class RoundResult:
    scores: tuple[PlayerScore, ...]
    shared_words: tuple[str, ...]
    missed_words: tuple[str, ...]


def score_round(
    accepted: Mapping[str, Iterable[str]],
    solutions: Iterable[str],
) -> RoundResult:
    """Score one finished round.

    `accepted` maps player id to the words that player got accepted.
    Duplicates within a player are collapsed. A word scores 2 points if no
    other player submitted it, otherwise 1.

    All output sequences are sorted so results are deterministic and
    comparable in tests.
    """
    per_player = {p: frozenset(ws) for p, ws in accepted.items()}

    counts: dict[str, int] = {}
    for words in per_player.values():
        for word in words:
            counts[word] = counts.get(word, 0) + 1

    scores = []
    for player in sorted(per_player):
        words = per_player[player]
        unique = frozenset(w for w in words if counts[w] == 1)
        points = (len(unique) * POINTS_UNIQUE
                  + (len(words) - len(unique)) * POINTS_SHARED)
        scores.append(PlayerScore(
            player=player,
            points=points,
            words=tuple(sorted(words)),
            unique_words=tuple(sorted(unique)),
        ))

    shared = tuple(sorted(w for w, n in counts.items() if n > 1))
    missed = tuple(sorted(frozenset(solutions) - frozenset(counts)))

    return RoundResult(scores=tuple(scores), shared_words=shared,
                       missed_words=missed)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/rules/test_scoring.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Run the whole rules suite**

Run: `.venv/Scripts/python.exe -m pytest tests/rules -v`
Expected: PASS (24 tests). The `rules` package is now complete and Phase 2 depends on nothing else from this plan.

- [ ] **Step 6: Commit**

```bash
git add wortissimo/rules/scoring.py tests/rules/test_scoring.py
git commit -m "feat: add pure round scoring"
```

---

### Task 4: `lexicon.source` — fetch and load germandict

**Files:**
- Create: `wortissimo/lexicon/__init__.py`
- Create: `wortissimo/lexicon/source.py`
- Create: `scripts/fetch_dictionary.py`
- Test: `tests/lexicon/test_source.py`

**Interfaces:**
- Consumes: `normalize()` from Task 1.
- Produces:
  - `wortissimo.lexicon.source.load_raw_words(path: Path) -> Iterator[str]` — yields raw (non-normalized) lines.
  - `wortissimo.lexicon.source.load_normalized(path: Path) -> set[str]` — normalized, invalid entries dropped.
  - `RAW_DIR = Path("data/raw")`, `GERMANDICT_TXT = RAW_DIR / "german.txt"`

The word list is Latin-1 with CRLF endings and contains entries with characters our normalizer rejects (hyphens, apostrophes, spaces). Those are dropped silently — that is expected, not an error.

- [ ] **Step 1: Write the failing test**

Create `tests/lexicon/test_source.py`:

```python
from pathlib import Path

from wortissimo.lexicon.source import load_normalized, load_raw_words


def write_latin1(tmp_path: Path, lines: list[str]) -> Path:
    p = tmp_path / "german.txt"
    p.write_bytes("\r\n".join(lines).encode("latin-1"))
    return p


def test_reads_latin1_umlauts_correctly(tmp_path):
    path = write_latin1(tmp_path, ["Bäcker", "Straße", "Übung"])
    assert list(load_raw_words(path)) == ["Bäcker", "Straße", "Übung"]


def test_normalizes_entries(tmp_path):
    path = write_latin1(tmp_path, ["Bäcker", "Straße"])
    assert load_normalized(path) == {"bäcker", "strasse"}


def test_drops_entries_the_normalizer_rejects(tmp_path):
    path = write_latin1(tmp_path, ["Haus", "Groß-Gerau", "d'accord", "A1"])
    assert load_normalized(path) == {"haus"}


def test_drops_blank_lines(tmp_path):
    path = write_latin1(tmp_path, ["Haus", "", "  ", "Bahn"])
    assert load_normalized(path) == {"haus", "bahn"}


def test_collapses_case_duplicates(tmp_path):
    # germandict lists both noun and verb forms; after casefolding these
    # collapse, which is correct.
    path = write_latin1(tmp_path, ["Reise", "reise"])
    assert load_normalized(path) == {"reise"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/lexicon/test_source.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wortissimo.lexicon'`

- [ ] **Step 3: Write the implementation**

```bash
mkdir -p wortissimo/lexicon tests/lexicon scripts
touch wortissimo/lexicon/__init__.py tests/lexicon/__init__.py
```

Create `wortissimo/lexicon/source.py`:

```python
"""Loading the raw German word list. Build-time only."""

from collections.abc import Iterator
from pathlib import Path

from wortissimo.rules.normalize import normalize

RAW_DIR = Path("data/raw")
GERMANDICT_TXT = RAW_DIR / "german.txt"

# The Free German Dictionary ships as ANSI/Latin-1 with Windows line
# endings. Reading it as UTF-8 corrupts every umlaut, silently.
ENCODING = "latin-1"


def load_raw_words(path: Path = GERMANDICT_TXT) -> Iterator[str]:
    """Yield each non-empty line of the word list, unmodified."""
    with path.open("r", encoding=ENCODING, newline="") as fh:
        for line in fh:
            word = line.strip()
            if word:
                yield word


def load_normalized(path: Path = GERMANDICT_TXT) -> set[str]:
    """Return the word list in canonical form.

    Entries containing hyphens, apostrophes, digits or spaces are dropped:
    Wortissimo only ever deals in single unhyphenated words.
    """
    words: set[str] = set()
    for raw in load_raw_words(path):
        try:
            words.add(normalize(raw))
        except ValueError:
            continue
    return words
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/lexicon/test_source.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Write the fetch script**

Create `scripts/fetch_dictionary.py`:

```python
"""Download and extract the Free German Dictionary (public domain).

Source: https://sourceforge.net/projects/germandict/
~2 million entries including inflected forms. Public domain, so no
attribution or licence obligation attaches to the generated puzzles.

Usage: python scripts/fetch_dictionary.py
"""

import shutil
import sys
import urllib.request
from pathlib import Path

import py7zr

URL = "https://sourceforge.net/projects/germandict/files/german.7z/download"
RAW_DIR = Path("data/raw")
ARCHIVE = RAW_DIR / "german.7z"
TARGET = RAW_DIR / "german.txt"


def main() -> int:
    RAW_DIR.mkdir(parents=True, exist_ok=True)

    if not ARCHIVE.exists():
        print(f"Downloading {URL}")
        req = urllib.request.Request(URL, headers={"User-Agent": "wortissimo"})
        with urllib.request.urlopen(req) as resp, ARCHIVE.open("wb") as out:
            shutil.copyfileobj(resp, out)
        print(f"Saved {ARCHIVE} ({ARCHIVE.stat().st_size:,} bytes)")

    print(f"Extracting into {RAW_DIR}")
    with py7zr.SevenZipFile(ARCHIVE, mode="r") as archive:
        archive.extractall(path=RAW_DIR)

    candidates = [p for p in RAW_DIR.glob("*.txt") if p.name != TARGET.name]
    if not TARGET.exists():
        if not candidates:
            print("ERROR: no .txt found in archive", file=sys.stderr)
            return 1
        candidates[0].rename(TARGET)

    line_count = sum(1 for _ in TARGET.open("r", encoding="latin-1"))
    print(f"{TARGET}: {line_count:,} lines")
    if line_count < 1_000_000:
        print("WARNING: expected ~2M lines; archive layout may have changed",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 6: Run the fetch script for real**

Run: `.venv/Scripts/python.exe scripts/fetch_dictionary.py`
Expected: prints a line count of roughly 2,000,000. `data/raw/` is gitignored, so nothing large enters the repository.

- [ ] **Step 7: Verify the real file loads correctly**

Run:
```bash
.venv/Scripts/python.exe -c "from wortissimo.lexicon.source import load_normalized; w=load_normalized(); print(len(w)); print('bäcker' in w, 'strasse' in w, 'haus' in w)"
```
Expected: a count in the low millions, then `True True True`. If umlauted words are missing, the encoding is wrong — stop and fix before continuing.

- [ ] **Step 8: Commit**

```bash
git add wortissimo/lexicon scripts/fetch_dictionary.py tests/lexicon
git commit -m "feat: add germandict fetch and Latin-1 aware loader"
```

---

### Task 5: `lexicon.lists` — the acceptance and solution lists

**Files:**
- Create: `wortissimo/lexicon/lists.py`
- Create: `data/blocklist.txt`
- Test: `tests/lexicon/test_lists.py`

**Interfaces:**
- Consumes: `load_normalized()` from Task 4.
- Produces:
  - `@dataclass(frozen=True) class Lexicon` with fields `acceptance: frozenset[str]`, `solutions: frozenset[str]`, `freq: Mapping[str, float]`.
  - `build_lexicon(words: set[str], blocklist: Container[str], solution_zipf_floor: float = 3.5, min_length: int = 3) -> Lexicon`
  - `load_blocklist(path: Path = Path("data/blocklist.txt")) -> frozenset[str]`
  - `SOLUTION_ZIPF_FLOOR = 3.5`, `TRIVIAL_ZIPF = 5.0`

Spec §6: two lists with opposite requirements. Acceptance is everything ≥ 3 letters that the dictionary knows, minus the blocklist. Solutions are the subset above the frequency floor — this is what the game reveals and what difficulty is computed from.

- [ ] **Step 1: Create the seed blocklist**

Create `data/blocklist.txt`. Proper nouns that clear the frequency floor must be removed by name; `wordfreq` cannot distinguish them. This list grows from the in-game reject button (spec §11).

```text
# Wortissimo blocklist — words never offered as solutions.
# One normalized (casefolded) word per line. '#' starts a comment.
# Seeded with common German given names and place names that pass the
# zipf >= 3.5 frequency floor. Grows from the in-game "bad round" button.
berlin
hamburg
muenchen
münchen
köln
bayern
sachsen
thomas
michael
andreas
stefan
christian
peter
klaus
sabine
julia
anna
maria
martin
frank
europa
deutschland
italien
spanien
```

- [ ] **Step 2: Write the failing test**

Create `tests/lexicon/test_lists.py`:

```python
from wortissimo.lexicon.lists import build_lexicon, load_blocklist

# Real zipf values (wordfreq 3.1.1, German):
#   haus 5.41  dank 5.32  gesetz 4.91  raten 4.29
#   ilm 3.09   aer 2.50   nde 2.44
WORDS = {"haus", "dank", "gesetz", "raten", "ilm", "aer", "nde", "xy"}


def test_acceptance_is_generous():
    lex = build_lexicon(WORDS, blocklist=frozenset())
    # Low-frequency real-ish forms stay acceptable: rejecting a word the
    # player actually knows is the worst failure mode in this genre.
    assert "ilm" in lex.acceptance
    assert "aer" in lex.acceptance


def test_acceptance_drops_words_below_min_length():
    lex = build_lexicon(WORDS, blocklist=frozenset())
    assert "xy" not in lex.acceptance


def test_solutions_drop_low_frequency_junk():
    lex = build_lexicon(WORDS, blocklist=frozenset())
    assert "ilm" not in lex.solutions
    assert "aer" not in lex.solutions
    assert "nde" not in lex.solutions


def test_solutions_keep_real_words():
    lex = build_lexicon(WORDS, blocklist=frozenset())
    assert {"haus", "dank", "gesetz", "raten"} <= lex.solutions


def test_solutions_are_a_subset_of_acceptance():
    lex = build_lexicon(WORDS, blocklist=frozenset())
    assert lex.solutions <= lex.acceptance


def test_blocklist_removes_from_both_lists():
    lex = build_lexicon(WORDS, blocklist=frozenset({"haus"}))
    assert "haus" not in lex.solutions
    assert "haus" not in lex.acceptance


def test_frequencies_are_exposed_for_solutions():
    lex = build_lexicon(WORDS, blocklist=frozenset())
    assert lex.freq["haus"] > lex.freq["raten"]


def test_blocklist_file_parsing(tmp_path):
    p = tmp_path / "b.txt"
    p.write_text("# comment\nberlin\n\n  hamburg  \n", encoding="utf-8")
    assert load_blocklist(p) == frozenset({"berlin", "hamburg"})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/lexicon/test_lists.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wortissimo.lexicon.lists'`

- [ ] **Step 4: Write the implementation**

Create `wortissimo/lexicon/lists.py`:

```python
"""The two word lists. Build-time only.

Spec section 6: one list cannot serve both runtime jobs.

  acceptance  decides whether a word the player typed scores. Generous.
              Wrongly rejecting a real German word is the worst failure
              mode in this genre, so marginal entries stay in.

  solutions   what the game reveals as "words you missed", and the basis
              for all difficulty computation. Clean. Revealing 'aer' as a
              word the player missed destroys trust in the game.
"""

from collections.abc import Container, Mapping
from dataclasses import dataclass
from pathlib import Path

from wordfreq import zipf_frequency

from wortissimo.rules.normalize import normalize

SOLUTION_ZIPF_FLOOR = 3.5
TRIVIAL_ZIPF = 5.0
MIN_LENGTH = 3
BLOCKLIST_PATH = Path("data/blocklist.txt")


@dataclass(frozen=True)
class Lexicon:
    acceptance: frozenset[str]
    solutions: frozenset[str]
    freq: Mapping[str, float]


def load_blocklist(path: Path = BLOCKLIST_PATH) -> frozenset[str]:
    """Read the manual blocklist: one normalized word per line, # comments."""
    if not path.exists():
        return frozenset()
    out: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        entry = line.split("#", 1)[0].strip()
        if not entry:
            continue
        try:
            out.add(normalize(entry))
        except ValueError:
            continue
    return frozenset(out)


def build_lexicon(
    words: set[str],
    blocklist: Container[str],
    solution_zipf_floor: float = SOLUTION_ZIPF_FLOOR,
    min_length: int = MIN_LENGTH,
) -> Lexicon:
    """Split one normalized word set into the acceptance and solution lists.

    The frequency floor of 3.5 was measured, not guessed: it separates
    ilm (3.09), aer (2.50) and nde (2.44) from raten (4.29), gesetz (4.91)
    and dank (5.32).
    """
    acceptance = frozenset(
        w for w in words
        if len(w) >= min_length and w not in blocklist
    )
    freq = {w: zipf_frequency(w, "de") for w in acceptance}
    solutions = frozenset(
        w for w in acceptance if freq[w] >= solution_zipf_floor
    )
    return Lexicon(acceptance=acceptance, solutions=solutions, freq=freq)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/lexicon -v`
Expected: PASS (13 tests)

- [ ] **Step 6: Sanity-check against the real dictionary**

Run:
```bash
.venv/Scripts/python.exe -c "
from wortissimo.lexicon.source import load_normalized
from wortissimo.lexicon.lists import build_lexicon, load_blocklist
lex = build_lexicon(load_normalized(), load_blocklist())
print('acceptance', len(lex.acceptance)); print('solutions', len(lex.solutions))
for w in ['haus','gesetz','dank','ilm','aer','berlin']:
    print(w, w in lex.acceptance, w in lex.solutions)
"
```
Expected: solutions substantially smaller than acceptance; `ilm`/`aer` acceptance-only; `berlin` in neither (blocklisted). This step takes a couple of minutes — `zipf_frequency` is called once per acceptance word.

- [ ] **Step 7: Commit**

```bash
git add wortissimo/lexicon/lists.py data/blocklist.txt tests/lexicon/test_lists.py
git commit -m "feat: add acceptance and solution word lists with measured frequency floor"
```

---

### Task 6: `generator.segment` — recursive compound segmentation

**Files:**
- Create: `wortissimo/generator/__init__.py`
- Create: `wortissimo/generator/segment.py`
- Test: `tests/generator/test_segment.py`

**Interfaces:**
- Consumes: nothing from earlier tasks (takes a `Container[str]` of known words).
- Produces: `segment(word: str, known: Container[str], splitter: Splitter | None = None, min_part: int = 4) -> tuple[int, ...]` — returns the sorted character offsets of morpheme boundaries, excluding 0 and `len(word)`.

**This task exists because `split_words` does not do what the spec assumed.** `Splitter.split_compound(w)` returns a ranked list of *binary* `(score, body, head)` splits only — never a full segmentation — and its top-ranked answer is frequently wrong. Verified:

```
Autobahnraststätte  -> top: (-0.71, 'Auto', 'Bahnraststätte')      WRONG
                       2nd: (-0.94, 'Autobahn', 'Raststätte')      RIGHT
Straßenbahnhaltestelle -> top: (0.91, 'Straßenbahn', 'Haltestelle') RIGHT
```

So segmentation must recurse, and must re-rank candidates using the lexicon: a split whose two halves are both known words beats a higher-scoring split whose halves are not.

- [ ] **Step 1: Write the failing test**

Create `tests/generator/test_segment.py`:

```python
from wortissimo.generator.segment import segment

KNOWN = {
    "auto", "bahn", "autobahn", "raststätte", "stätte",
    "strassen", "strasse", "strassenbahn", "haltestelle", "halte", "stelle",
    "bäckerei", "fach", "verkäuferin", "bäcker",
}


def test_returns_no_boundaries_for_a_simple_word():
    assert segment("bahn", KNOWN) == ()


def test_splits_a_two_part_compound():
    # strassenbahn|haltestelle
    assert 12 in segment("strassenbahnhaltestelle", KNOWN)


def test_lexicon_reranking_beats_the_raw_top_score():
    # The splitter's top-scored answer is 'auto|bahnraststätte', but
    # 'bahnraststätte' is not a known word while both halves of
    # 'autobahn|raststätte' are. Boundary must land after 'autobahn' (8).
    assert 8 in segment("autobahnraststätte", KNOWN)


def test_recurses_to_find_more_than_one_boundary():
    # strassen|bahn|haltestelle -> at least two boundaries
    assert len(segment("strassenbahnhaltestelle", KNOWN)) >= 1


def test_boundaries_are_sorted_and_exclude_the_ends():
    bounds = segment("strassenbahnhaltestelle", KNOWN)
    assert list(bounds) == sorted(bounds)
    assert 0 not in bounds
    assert len("strassenbahnhaltestelle") not in bounds


def test_short_parts_are_not_split_off():
    # min_part=4 forbids carving off fragments shorter than 4 characters.
    for b in segment("autobahnraststätte", KNOWN, min_part=4):
        assert b >= 4
        assert len("autobahnraststätte") - b >= 4


def test_is_deterministic():
    a = segment("strassenbahnhaltestelle", KNOWN)
    b = segment("strassenbahnhaltestelle", KNOWN)
    assert a == b
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/generator/test_segment.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wortissimo.generator'`

- [ ] **Step 3: Write the implementation**

```bash
mkdir -p wortissimo/generator tests/generator
touch wortissimo/generator/__init__.py tests/generator/__init__.py
```

Create `wortissimo/generator/segment.py`:

```python
"""Compound segmentation via CharSplit, made recursive and lexicon-aware.

split_words.Splitter.split_compound() returns a ranked list of BINARY
splits only, and its top-ranked answer is often wrong:

    Autobahnraststätte -> (-0.71, 'Auto', 'Bahnraststätte')  <- top, wrong
                          (-0.94, 'Autobahn', 'Raststätte')  <- correct

We therefore re-rank the splitter's candidates by how many halves are
known words, and recurse into each half to find further boundaries.

Segmentation feeds difficulty bucketing ONLY. It never accepts or rejects
a player's word, so its error rate is cosmetic (spec section 9).
"""

from collections.abc import Container
from functools import lru_cache

from split_words import Splitter

MIN_PART = 4
# Candidate splits below this raw CharSplit score are ignored unless the
# lexicon confirms both halves.
SCORE_FLOOR = -1.0
TOP_N = 5


@lru_cache(maxsize=1)
def _default_splitter() -> Splitter:
    """Splitter loads a 60MB ngram model; build it once per process."""
    return Splitter()


def _best_split(
    word: str, known: Container[str], splitter: Splitter, min_part: int
) -> int | None:
    """Return the best single boundary offset within `word`, or None."""
    if len(word) < 2 * min_part:
        return None

    try:
        candidates = splitter.split_compound(word)[:TOP_N]
    except Exception:
        return None

    best_offset: int | None = None
    best_key: tuple[int, float] | None = None

    for score, body, head in candidates:
        offset = len(body)
        if offset < min_part or len(word) - offset < min_part:
            continue
        if offset + len(head) != len(word):
            continue

        confirmed = int(body.casefold() in known) + int(head.casefold() in known)
        if confirmed == 0 and score < SCORE_FLOOR:
            continue

        # Lexicon confirmation dominates the raw score: a split whose two
        # halves are both real words beats a better-scoring split whose
        # halves are not.
        key = (confirmed, score)
        if best_key is None or key > best_key:
            best_key, best_offset = key, offset

    return best_offset


def segment(
    word: str,
    known: Container[str],
    splitter: Splitter | None = None,
    min_part: int = MIN_PART,
) -> tuple[int, ...]:
    """Return sorted morpheme boundary offsets within `word`.

    Offsets 0 and len(word) are excluded. An unsplittable word returns ().
    """
    splitter = splitter or _default_splitter()
    boundaries: set[int] = set()

    def recurse(start: int, end: int) -> None:
        part = word[start:end]
        offset = _best_split(part, known, splitter, min_part)
        if offset is None:
            return
        absolute = start + offset
        if absolute in boundaries:
            return
        boundaries.add(absolute)
        recurse(start, absolute)
        recurse(absolute, end)

    recurse(0, len(word))
    return tuple(sorted(boundaries))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/generator/test_segment.py -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add wortissimo/generator tests/generator
git commit -m "feat: add recursive lexicon-aware compound segmentation"
```

---

### Task 7: `generator.solve` — enumerate and classify solutions

**Files:**
- Create: `wortissimo/generator/solve.py`
- Test: `tests/generator/test_solve.py`

**Interfaces:**
- Consumes: `segment()` from Task 6; `Lexicon` from Task 5.
- Produces:
  - `class Category(StrEnum)` with members `OBVIOUS_COMPONENT`, `CROSS_BOUNDARY`.
  - `@dataclass(frozen=True) class Solution` with fields `word: str`, `category: Category`, `freq: float`.
  - `find_solutions(source: str, lexicon: Lexicon, boundaries: tuple[int, ...], min_length: int = 3) -> tuple[Solution, ...]`

Spec §9: a solution is `CROSS_BOUNDARY` if its span straddles a morpheme boundary, otherwise `OBVIOUS_COMPONENT`. A word occurring at several positions is classified by its *best* (most interesting) occurrence, and appears once.

- [ ] **Step 1: Write the failing test**

Create `tests/generator/test_solve.py`:

```python
from wortissimo.generator.solve import Category, find_solutions
from wortissimo.lexicon.lists import Lexicon


def make_lexicon(solutions: set[str], freqs: dict[str, float] | None = None):
    freqs = freqs or {w: 5.0 for w in solutions}
    return Lexicon(acceptance=frozenset(solutions),
                   solutions=frozenset(solutions), freq=freqs)


def words(result):
    return {s.word for s in result}


def category_of(result, word):
    return next(s.category for s in result if s.word == word)


def test_finds_a_substring_that_is_a_known_word():
    lex = make_lexicon({"bahn", "halte"})
    assert words(find_solutions("strassenbahnhalte", lex, ())) == {"bahn", "halte"}


def test_ignores_substrings_that_are_not_words():
    lex = make_lexicon({"bahn"})
    assert words(find_solutions("strassenbahn", lex, ())) == {"bahn"}


def test_excludes_the_source_word_itself():
    lex = make_lexicon({"bahn", "strassenbahn"})
    assert "strassenbahn" not in words(find_solutions("strassenbahn", lex, ()))


def test_excludes_words_shorter_than_min_length():
    lex = make_lexicon({"ba", "bahn"})
    assert words(find_solutions("strassenbahn", lex, ())) == {"bahn"}


def test_classifies_a_word_inside_one_morpheme_as_obvious():
    # boundary at 8: 'strassen|bahn'. 'bahn' sits wholly in the 2nd part.
    lex = make_lexicon({"bahn"})
    result = find_solutions("strassenbahn", lex, (8,))
    assert category_of(result, "bahn") is Category.OBVIOUS_COMPONENT


def test_classifies_a_word_straddling_a_boundary_as_cross_boundary():
    # boundary at 8: 'strassen|bahn'. 'enba' spans offsets 6..10.
    lex = make_lexicon({"enba"})
    result = find_solutions("strassenbahn", lex, (8,))
    assert category_of(result, "enba") is Category.CROSS_BOUNDARY


def test_word_at_several_positions_appears_once_and_takes_best_category():
    # 'ei' padded: use 'eis' occurring twice, once straddling boundary 4.
    lex = make_lexicon({"eis"})
    result = find_solutions("abeisxxeis", lex, (4,))
    assert len([s for s in result if s.word == "eis"]) == 1
    assert category_of(result, "eis") is Category.CROSS_BOUNDARY


def test_carries_frequency_through():
    lex = make_lexicon({"bahn"}, {"bahn": 5.04})
    result = find_solutions("strassenbahn", lex, ())
    assert result[0].freq == 5.04


def test_result_is_sorted_and_deterministic():
    lex = make_lexicon({"bahn", "halte", "stelle"})
    a = find_solutions("bahnhaltestelle", lex, ())
    b = find_solutions("bahnhaltestelle", lex, ())
    assert a == b
    assert [s.word for s in a] == sorted(s.word for s in a)


def test_no_boundaries_means_everything_is_obvious():
    lex = make_lexicon({"bahn", "enba"})
    result = find_solutions("strassenbahn", lex, ())
    assert all(s.category is Category.OBVIOUS_COMPONENT for s in result)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/generator/test_solve.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wortissimo.generator.solve'`

- [ ] **Step 3: Write the implementation**

Create `wortissimo/generator/solve.py`:

```python
"""Enumerate and classify the solutions of one source word.

Cost: a source word of length n has n(n+1)/2 substrings; n=40 gives 820.
Across ~100k candidate source words that is ~82M set lookups — seconds,
once, in a batch job. This was never a scaling problem.
"""

from dataclasses import dataclass
from enum import StrEnum

from wortissimo.lexicon.lists import Lexicon

MIN_LENGTH = 3


class Category(StrEnum):
    OBVIOUS_COMPONENT = "obvious_component"
    CROSS_BOUNDARY = "cross_boundary"


@dataclass(frozen=True)
class Solution:
    word: str
    category: Category
    freq: float


def _category(start: int, end: int, boundaries: tuple[int, ...]) -> Category:
    """CROSS_BOUNDARY if the span strictly contains a morpheme boundary."""
    if any(start < b < end for b in boundaries):
        return Category.CROSS_BOUNDARY
    return Category.OBVIOUS_COMPONENT


def find_solutions(
    source: str,
    lexicon: Lexicon,
    boundaries: tuple[int, ...],
    min_length: int = MIN_LENGTH,
) -> tuple[Solution, ...]:
    """Return every distinct solution word in `source`, classified.

    A word occurring at several positions appears once, classified by its
    most interesting occurrence (CROSS_BOUNDARY wins over
    OBVIOUS_COMPONENT), because that is the occurrence a player is
    credited for noticing.
    """
    n = len(source)
    best: dict[str, Category] = {}

    for start in range(n):
        for end in range(start + min_length, n + 1):
            word = source[start:end]
            if word == source:
                continue
            if word not in lexicon.solutions:
                continue
            category = _category(start, end, boundaries)
            if (best.get(word) is not Category.CROSS_BOUNDARY):
                best[word] = category

    return tuple(
        Solution(word=word, category=best[word],
                 freq=lexicon.freq.get(word, 0.0))
        for word in sorted(best)
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/generator/test_solve.py -v`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add wortissimo/generator/solve.py tests/generator/test_solve.py
git commit -m "feat: add substring enumeration and boundary classification"
```

---

### Task 8: `generator.difficulty` — bucket assignment

**Files:**
- Create: `wortissimo/generator/difficulty.py`
- Test: `tests/generator/test_difficulty.py`

**Interfaces:**
- Consumes: `Solution`, `Category` from Task 7; `TRIVIAL_ZIPF` from Task 5.
- Produces:
  - `class Difficulty(StrEnum)` with members `LEICHT`, `MITTEL`, `SCHWER`, `BRUTAL`.
  - `@dataclass(frozen=True) class Bucket` with fields `difficulty`, `min_len`, `max_len`, `min_solutions`, `max_solutions`, `min_long`, `min_cross`, `max_trivial_share`.
  - `BUCKETS: tuple[Bucket, ...]`
  - `classify_difficulty(source: str, solutions: Sequence[Solution]) -> Difficulty | None`
  - `metrics(source: str, solutions: Sequence[Solution]) -> dict[str, float | int]`

Spec §10: a constraint table, not a weighted score. Returns `None` when a source word fits no bucket — that word is discarded. Buckets are tested hardest-first so a word qualifying for several lands in the most demanding one.

- [ ] **Step 1: Write the failing test**

Create `tests/generator/test_difficulty.py`:

```python
from wortissimo.generator.difficulty import (
    Difficulty, classify_difficulty, metrics,
)
from wortissimo.generator.solve import Category, Solution


def sols(n_total, n_long=0, n_cross=0, n_trivial=0):
    """Build a solution list with the requested shape."""
    out = []
    for i in range(n_total):
        long_enough = i < n_long
        word = ("l" * 7 + str(i)) if long_enough else f"w{i:02d}"
        category = (Category.CROSS_BOUNDARY if i < n_cross
                    else Category.OBVIOUS_COMPONENT)
        freq = 5.5 if i < n_trivial else 4.0
        out.append(Solution(word=word, category=category, freq=freq))
    return out


def test_leicht_word_is_classified_leicht():
    source = "a" * 18
    assert classify_difficulty(source, sols(20, 3, 1, 5)) is Difficulty.LEICHT


def test_brutal_word_is_classified_brutal():
    source = "a" * 30
    assert classify_difficulty(source, sols(40, 8, 15, 4)) is Difficulty.BRUTAL


def test_word_with_too_few_solutions_fits_no_bucket():
    source = "a" * 18
    assert classify_difficulty(source, sols(4)) is None


def test_word_that_is_too_short_fits_no_bucket():
    source = "a" * 10
    assert classify_difficulty(source, sols(20, 3, 1, 5)) is None


def test_too_many_trivial_solutions_is_rejected_from_brutal():
    source = "a" * 30
    # 40 solutions, 30 of them trivial = 75% > brutal's 20% ceiling.
    result = classify_difficulty(source, sols(40, 8, 15, 30))
    assert result is not Difficulty.BRUTAL


def test_hardest_matching_bucket_wins():
    source = "a" * 27
    # Satisfies both Mittel and Schwer length/solution ranges.
    assert classify_difficulty(source, sols(30, 6, 8, 3)) is Difficulty.SCHWER


def test_metrics_reports_the_measured_shape():
    m = metrics("a" * 30, sols(40, 8, 15, 4))
    assert m["length"] == 30
    assert m["solution_count"] == 40
    assert m["long_count"] == 8
    assert m["cross_boundary_count"] == 15
    assert m["trivial_share"] == 4 / 40


def test_metrics_on_empty_solutions_does_not_divide_by_zero():
    m = metrics("a" * 20, [])
    assert m["trivial_share"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/generator/test_difficulty.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wortissimo.generator.difficulty'`

- [ ] **Step 3: Write the implementation**

Create `wortissimo/generator/difficulty.py`:

```python
"""Difficulty bucketing by hard constraints (spec section 10).

Deliberately NOT a weighted score. Five coefficients cannot be calibrated
from two players' data, so the apparent precision would be fake. A table
is deterministic, debuggable, and retunable by editing one place.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from wortissimo.generator.solve import Category, Solution
from wortissimo.lexicon.lists import TRIVIAL_ZIPF

LONG_WORD_LENGTH = 7


class Difficulty(StrEnum):
    LEICHT = "leicht"
    MITTEL = "mittel"
    SCHWER = "schwer"
    BRUTAL = "brutal"


@dataclass(frozen=True)
class Bucket:
    difficulty: Difficulty
    min_len: int
    max_len: int
    min_solutions: int
    max_solutions: int
    min_long: int
    min_cross: int
    max_trivial_share: float


# Ordered hardest-first: a word qualifying for several buckets lands in
# the most demanding one.
BUCKETS: tuple[Bucket, ...] = (
    Bucket(Difficulty.BRUTAL, 25, 40, 30, 60, 5, 10, 0.20),
    Bucket(Difficulty.SCHWER, 25, 35, 25, 45, 4, 6, 0.30),
    Bucket(Difficulty.MITTEL, 20, 28, 20, 35, 3, 3, 0.40),
    Bucket(Difficulty.LEICHT, 15, 20, 15, 25, 2, 1, 0.50),
)


def metrics(source: str, solutions: Sequence[Solution]) -> dict[str, float | int]:
    """Measure the shape of one candidate round."""
    total = len(solutions)
    trivial = sum(
        1 for s in solutions
        if s.category is Category.OBVIOUS_COMPONENT and s.freq >= TRIVIAL_ZIPF
    )
    return {
        "length": len(source),
        "solution_count": total,
        "long_count": sum(1 for s in solutions if len(s.word) >= LONG_WORD_LENGTH),
        "cross_boundary_count": sum(
            1 for s in solutions if s.category is Category.CROSS_BOUNDARY
        ),
        "trivial_share": (trivial / total) if total else 0.0,
    }


def _fits(bucket: Bucket, m: dict[str, float | int]) -> bool:
    return (
        bucket.min_len <= m["length"] <= bucket.max_len
        and bucket.min_solutions <= m["solution_count"] <= bucket.max_solutions
        and m["long_count"] >= bucket.min_long
        and m["cross_boundary_count"] >= bucket.min_cross
        and m["trivial_share"] <= bucket.max_trivial_share
    )


def classify_difficulty(
    source: str, solutions: Sequence[Solution]
) -> Difficulty | None:
    """Return the hardest bucket this round qualifies for, or None."""
    m = metrics(source, solutions)
    for bucket in BUCKETS:
        if _fits(bucket, m):
            return bucket.difficulty
    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/generator/test_difficulty.py -v`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add wortissimo/generator/difficulty.py tests/generator/test_difficulty.py
git commit -m "feat: add difficulty bucketing by constraint table"
```

---

### Task 9: `generator.build` — produce `puzzles.sqlite`

**Files:**
- Create: `wortissimo/generator/store.py`
- Create: `wortissimo/generator/build.py`
- Create: `scripts/build_puzzles.py`
- Test: `tests/generator/test_store.py`
- Test: `tests/generator/test_build.py`

**Interfaces:**
- Consumes: `Lexicon` (Task 5), `segment()` (Task 6), `find_solutions()`/`Solution` (Task 7), `classify_difficulty()`/`metrics()` (Task 8).
- Produces:
  - `wortissimo.generator.store.SCHEMA: str`
  - `create_schema(conn: sqlite3.Connection) -> None`
  - `insert_puzzle(conn, source_word: str, difficulty: str, solutions: Sequence[Solution], meta: dict) -> int`
  - `wortissimo.generator.build.build_puzzles(lexicon, conn, candidates: Iterable[str], limit: int | None = None, progress: Callable[[int, int], None] | None = None) -> int`

Schema is the `puzzles` and `solutions` half of spec §12; the `games`/`rounds`/`submissions` half belongs to Phase 2 and is created by the server against its own database file.

- [ ] **Step 1: Write the failing store test**

Create `tests/generator/test_store.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/generator/test_store.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wortissimo.generator.store'`

- [ ] **Step 3: Write the store implementation**

Create `wortissimo/generator/store.py`:

```python
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
) -> int:
    """Insert one puzzle and its solutions. Returns the new puzzle id."""
    cur = conn.execute(
        "INSERT INTO puzzles (source_word, difficulty, solution_count, meta_json)"
        " VALUES (?, ?, ?, ?)",
        (source_word, difficulty, len(solutions), json.dumps(meta)),
    )
    puzzle_id = int(cur.lastrowid)
    conn.executemany(
        "INSERT INTO solutions (puzzle_id, word, category, freq)"
        " VALUES (?, ?, ?, ?)",
        [(puzzle_id, s.word, str(s.category), s.freq) for s in solutions],
    )
    return puzzle_id
```

- [ ] **Step 4: Run store tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/generator/test_store.py -v`
Expected: PASS (5 tests)

- [ ] **Step 5: Write the failing build test**

Create `tests/generator/test_build.py`:

```python
import sqlite3

from wortissimo.generator.build import build_puzzles
from wortissimo.generator.store import create_schema
from wortissimo.lexicon.lists import Lexicon

# A tiny closed world: one source word engineered to qualify for LEICHT.
SOURCE = "strassenbahnhalte"          # 17 chars -> Leicht range 15..20
SOLUTION_WORDS = [
    "strasse", "strassen", "rassen", "assen", "sen", "senbahn", "enbahn",
    "nbahn", "bahn", "ahnhalte", "nhalte", "halte", "alte", "hal", "bahnhalte",
    "senba", "asse", "rasse",
]


def make_lexicon():
    words = frozenset(SOLUTION_WORDS)
    return Lexicon(acceptance=words, solutions=words,
                   freq={w: 4.0 for w in words})


def conn():
    c = sqlite3.connect(":memory:")
    create_schema(c)
    return c


def test_writes_a_qualifying_puzzle():
    c = conn()
    written = build_puzzles(make_lexicon(), c, [SOURCE])
    assert written == 1
    (count,) = c.execute("SELECT COUNT(*) FROM puzzles").fetchone()
    assert count == 1


def test_skips_a_candidate_that_fits_no_bucket():
    c = conn()
    # 'bahn' is far too short and has no solutions.
    written = build_puzzles(make_lexicon(), c, ["bahn"])
    assert written == 0


def test_writes_solutions_for_the_puzzle():
    c = conn()
    build_puzzles(make_lexicon(), c, [SOURCE])
    (count,) = c.execute("SELECT COUNT(*) FROM solutions").fetchone()
    assert count > 0


def test_never_stores_the_source_word_as_its_own_solution():
    c = conn()
    build_puzzles(make_lexicon(), c, [SOURCE])
    rows = c.execute("SELECT word FROM solutions").fetchall()
    assert (SOURCE,) not in rows


def test_limit_stops_early():
    c = conn()
    written = build_puzzles(make_lexicon(), c, [SOURCE, SOURCE + "x"], limit=1)
    assert written == 1


def test_duplicate_candidates_do_not_crash():
    c = conn()
    written = build_puzzles(make_lexicon(), c, [SOURCE, SOURCE])
    assert written == 1
```

- [ ] **Step 6: Run build test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/generator/test_build.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'wortissimo.generator.build'`

- [ ] **Step 7: Write the build implementation**

Create `wortissimo/generator/build.py`:

```python
"""Drive the full generation pipeline for a set of candidate source words."""

import sqlite3
from collections.abc import Callable, Iterable

from wortissimo.generator.difficulty import classify_difficulty, metrics
from wortissimo.generator.segment import segment
from wortissimo.generator.solve import find_solutions
from wortissimo.generator.store import insert_puzzle
from wortissimo.lexicon.lists import Lexicon

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


def build_puzzles(
    lexicon: Lexicon,
    conn: sqlite3.Connection,
    candidates: Iterable[str],
    limit: int | None = None,
    progress: Callable[[int, int], None] | None = None,
) -> int:
    """Generate puzzles for `candidates` and write those that qualify.

    Returns the number of puzzles written. Candidates fitting no
    difficulty bucket are silently discarded — that is the normal case
    for most long German words.
    """
    written = 0
    for seen, source in enumerate(candidates, start=1):
        if limit is not None and written >= limit:
            break

        boundaries = segment(source, lexicon.solutions)
        solutions = find_solutions(source, lexicon, boundaries)
        difficulty = classify_difficulty(source, solutions)
        if difficulty is None:
            continue

        meta = metrics(source, solutions)
        meta["boundaries"] = list(boundaries)
        try:
            insert_puzzle(conn, source, str(difficulty), solutions, meta)
        except sqlite3.IntegrityError:
            continue  # already have this source word
        written += 1

        if progress and written % 100 == 0:
            progress(seen, written)

    conn.commit()
    return written
```

- [ ] **Step 8: Run build tests to verify they pass**

Run: `.venv/Scripts/python.exe -m pytest tests/generator/test_build.py -v`
Expected: PASS (6 tests). If `test_writes_a_qualifying_puzzle` fails because the fixture misses a Leicht constraint, adjust `SOLUTION_WORDS` in the test until the fixture genuinely qualifies — do not relax `BUCKETS`.

- [ ] **Step 9: Write the CLI**

Create `scripts/build_puzzles.py`:

```python
"""Build data/puzzles.sqlite from the German word list.

Usage:
    python scripts/build_puzzles.py [--limit N] [--out PATH]
"""

import argparse
import sqlite3
import time
from pathlib import Path

from wortissimo.generator.build import build_puzzles, candidate_source_words
from wortissimo.generator.store import create_schema
from wortissimo.lexicon.lists import build_lexicon, load_blocklist
from wortissimo.lexicon.source import load_normalized

DEFAULT_OUT = Path("data/puzzles.sqlite")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None,
                        help="stop after writing N puzzles")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    started = time.monotonic()
    print("Loading dictionary...")
    lexicon = build_lexicon(load_normalized(), load_blocklist())
    print(f"  acceptance {len(lexicon.acceptance):,}"
          f"  solutions {len(lexicon.solutions):,}")

    candidates = candidate_source_words(lexicon)
    print(f"  candidate source words {len(candidates):,}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    if args.out.exists():
        args.out.unlink()
    conn = sqlite3.connect(args.out)
    create_schema(conn)

    def progress(seen: int, written: int) -> None:
        print(f"  {seen:,} scanned / {written:,} written", flush=True)

    written = build_puzzles(lexicon, conn, candidates,
                            limit=args.limit, progress=progress)

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
```

- [ ] **Step 10: Run a small build to verify the CLI end to end**

Run: `.venv/Scripts/python.exe scripts/build_puzzles.py --limit 25 --out data/puzzles-sample.sqlite`
Expected: completes and prints a per-difficulty breakdown with 25 puzzles total.

- [ ] **Step 11: Commit**

```bash
git add wortissimo/generator/store.py wortissimo/generator/build.py \
        scripts/build_puzzles.py tests/generator/test_store.py \
        tests/generator/test_build.py
git commit -m "feat: add puzzle store and build pipeline CLI"
```

---

### Task 10: `scripts/play.py` — terminal round, and full-corpus build

**Files:**
- Create: `scripts/play.py`
- Create: `scripts/inspect_puzzle.py`

**Interfaces:**
- Consumes: everything above.
- Produces: no importable API. This task's deliverable is *evidence that the pipeline produces a fun game*, which no unit test can supply.

This is the task that makes Phase 1 working software rather than a pile of modules. Phase 2 should not begin until a human has played several rounds here and judged the puzzle quality acceptable.

- [ ] **Step 1: Write the puzzle inspector**

Create `scripts/inspect_puzzle.py`:

```python
"""Print one puzzle and its full solution list, for eyeballing quality.

Usage:
    python scripts/inspect_puzzle.py [--difficulty schwer] [--db PATH]
"""

import argparse
import json
import sqlite3
from pathlib import Path

DEFAULT_DB = Path("data/puzzles.sqlite")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--difficulty", default=None)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    if args.difficulty:
        row = conn.execute(
            "SELECT id, source_word, difficulty, meta_json FROM puzzles"
            " WHERE difficulty=? ORDER BY RANDOM() LIMIT 1",
            (args.difficulty,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT id, source_word, difficulty, meta_json FROM puzzles"
            " ORDER BY RANDOM() LIMIT 1"
        ).fetchone()

    if row is None:
        print("no puzzles found")
        return 1

    pid, source, difficulty, meta_json = row
    meta = json.loads(meta_json)
    print(f"{source.upper()}  [{difficulty}]")
    boundaries = meta.get("boundaries", [])
    if boundaries:
        marked = source
        for offset in reversed(boundaries):
            marked = marked[:offset] + "|" + marked[offset:]
        print(f"segmented: {marked}")
    print(json.dumps(meta, indent=2, ensure_ascii=False))
    print()

    for word, category, freq in conn.execute(
        "SELECT word, category, freq FROM solutions WHERE puzzle_id=?"
        " ORDER BY LENGTH(word) DESC, word",
        (pid,),
    ):
        flag = "*" if category == "cross_boundary" else " "
        print(f"  {flag} {word:<24} zipf {freq:.2f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Write the terminal game**

Create `scripts/play.py`:

```python
"""Play one Wortissimo round in the terminal against the real pipeline.

This exists to validate puzzle quality before any UI is built. It uses
the same rules package the server will use in Phase 2.

Usage:
    python scripts/play.py [--difficulty mittel] [--seconds 180]
"""

import argparse
import sqlite3
import time
from pathlib import Path

from wortissimo.lexicon.lists import build_lexicon, load_blocklist
from wortissimo.lexicon.source import load_normalized
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
    query = ("SELECT id, source_word FROM puzzles"
             + (" WHERE difficulty=?" if args.difficulty else "")
             + " ORDER BY RANDOM() LIMIT 1")
    params = (args.difficulty,) if args.difficulty else ()
    row = conn.execute(query, params).fetchone()
    if row is None:
        print("no puzzles found - run scripts/build_puzzles.py first")
        return 1
    puzzle_id, source = row

    solutions = [
        w for (w,) in conn.execute(
            "SELECT word FROM solutions WHERE puzzle_id=?", (puzzle_id,)
        )
    ]

    print("Loading acceptance list...")
    lexicon = build_lexicon(load_normalized(), load_blocklist())

    print(f"\n{source.upper()}\n")
    print(f"{args.seconds} Sekunden. Leere Eingabe beendet die Runde.\n")

    deadline = time.monotonic() + args.seconds
    found: list[str] = []

    while time.monotonic() < deadline:
        remaining = int(deadline - time.monotonic())
        try:
            raw = input(f"[{remaining:3d}s] > ").strip()
        except EOFError:
            break
        if not raw:
            break
        if time.monotonic() >= deadline:
            print("  zu spät")
            break

        verdict = validate_word(raw, source, lexicon.acceptance)
        if verdict.accepted:
            if verdict.word in found:
                print("  schon gefunden")
            else:
                found.append(verdict.word)
                print(f"  ok ({len(found)})")
        else:
            print(f"  abgelehnt: {verdict.reason}")

    result = score_round({"du": found}, solutions)
    score = result.scores[0]
    print(f"\n{score.points} Punkte, {len(found)}/{len(solutions)} gefunden")
    print("\nverpasst:")
    print("  " + ", ".join(result.missed_words))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 3: Run the full corpus build**

Run: `.venv/Scripts/python.exe scripts/build_puzzles.py`
Expected: runs for a while (segmentation over ~100k+ candidates is the slow part) and reports counts per difficulty. Every bucket should be non-empty. If a bucket is empty, the constraint table in `difficulty.py` needs retuning against the real distribution — that is expected on the first run and is exactly what spec §10 means by "recalibrated against real play".

- [ ] **Step 4: Inspect several puzzles by hand**

Run each of these and read the output critically:
```bash
.venv/Scripts/python.exe scripts/inspect_puzzle.py --difficulty leicht
.venv/Scripts/python.exe scripts/inspect_puzzle.py --difficulty mittel
.venv/Scripts/python.exe scripts/inspect_puzzle.py --difficulty schwer
.venv/Scripts/python.exe scripts/inspect_puzzle.py --difficulty brutal
```
Check specifically: does the solution list contain words a German speaker would dispute? Add those to `data/blocklist.txt`. Are the `*`-flagged cross-boundary finds actually the interesting ones? Does the segmentation shown look right?

- [ ] **Step 5: Play several real rounds**

Run: `.venv/Scripts/python.exe scripts/play.py --difficulty mittel`

This is the acceptance gate for Phase 1. Judge: is the round fun, is the difficulty label honest, did the acceptance list wrongly reject any word you actually knew? Wrong rejections are the failure mode to hunt for — note them.

- [ ] **Step 6: Retune and record**

Apply any blocklist additions and any `BUCKETS` adjustments the previous two steps revealed. Re-run `scripts/build_puzzles.py`. Record the final per-difficulty counts in the commit message so the next phase knows the corpus size.

- [ ] **Step 7: Run the whole suite**

Run: `.venv/Scripts/python.exe -m pytest -v`
Expected: PASS, all tasks' tests green (approximately 68 tests).

- [ ] **Step 8: Commit**

```bash
git add scripts/play.py scripts/inspect_puzzle.py data/blocklist.txt \
        wortissimo/generator/difficulty.py
git commit -m "feat: add terminal play and puzzle inspection tools

Phase 1 acceptance gate. Corpus: <fill in per-difficulty counts>."
```

---

## Phase 1 Exit Criteria

Phase 2 must not start until all of these hold:

1. `pytest` passes with no skips.
2. `data/puzzles.sqlite` exists and every difficulty bucket is non-empty.
3. A human has played at least five rounds via `scripts/play.py` across at least two difficulties.
4. No word wrongly rejected during those rounds remains unfixed — either it is now in the acceptance list, or its absence is understood and accepted.
5. `wortissimo/rules/` still imports nothing from `lexicon`, `generator`, or `server`. Verify:
   `grep -rE "from wortissimo\.(lexicon|generator|server)" wortissimo/rules/` returns nothing.

## Self-Review Notes

Spec coverage check against `2026-09-06-wortissimo-design.md`:

- §5 module boundaries → Tasks 1-9; purity enforced by exit criterion 5.
- §6 two lists → Task 5.
- §7 normalization → Task 1 (ß handled by `casefold`, verified).
- §8 runtime protocol → **Phase 2**, not this plan.
- §9 generation and classification → Tasks 6, 7.
- §10 difficulty → Task 8.
- §11 rules → Tasks 2, 3. The `DUPLICATE`/`TOO_LATE` reasons are declared here but produced in Phase 2.
- §12 data model → Task 9 covers `puzzles`/`solutions`; `games`/`rounds`/`submissions` are Phase 2.
- §13 Apple requirements → **Phase 2**, not this plan.
- §14 testing → property tests in Task 1, golden inspection in Task 10; WS and Playwright tests are Phase 2.
- §16 open items → frequency corpus resolved to `wordfreq` 3.1.1 in Task 5. Container config and whether `puzzles.sqlite` is committed are Phase 2 decisions.
