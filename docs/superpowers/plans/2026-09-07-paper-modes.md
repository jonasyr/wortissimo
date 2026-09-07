# Paper Modes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add blind scoring to the two-device game, and a separate single-device "on paper" mode where players claim their words after the timer.

**Architecture:** Blind scoring is a flag threaded through the existing game config; the room keeps recording verdicts but returns a neutral ack, and the results screen gains a rejected-word list from rows already in the database. On-paper mode is a fully client-side path served by two stateless endpoints — no WebSocket, no room, no game record — because with one device there is no state to synchronise.

**Tech Stack:** Python 3.13, FastAPI, pydantic v2, pytest; React 19 + TypeScript, Vitest, Playwright.

**Spec:** `docs/superpowers/specs/2026-09-07-paper-modes-design.md`

## Global Constraints

- `wortissimo/rules/` stays pure and is the only definition of scoring. The solo scoring endpoint calls `score_round`; scoring is never reimplemented in TypeScript.
- Blind mode changes **what is reported**, never what is recorded. `submissions` rows keep their real `accepted` flag and `reason`.
- In blind mode, opponent progress reports **entries**, not accepted words. Reporting accepted words leaks validity one increment at a time.
- Solo endpoints are stateless: they never read or write the games database.
- Round length stays 60–1800 seconds in both modes, enforced server-side.
- UI copy is German, matching the existing screens.
- Existing behaviour is unchanged when `blind` is false and solo mode is unused. All 226 existing Python tests must still pass.

---

### Task 1: `blind` flag and the neutral ack

**Files:**
- Modify: `wortissimo/server/protocol.py` (`Ack.accepted`)
- Modify: `wortissimo/server/room.py` (`Room.blind`, `Room.submit`, `Room.progress_count`)
- Modify: `wortissimo/server/app.py` (`NewGame.blind`)
- Test: `tests/server/test_blind.py`

**Interfaces:**
- Produces: `Room.blind -> bool`; `Ack.accepted: bool | None`; `Room.entered_count(player_id) -> int`.
- Consumes: existing `Room.submit`, `db.record_submission`, `db.accepted_words`.

- [ ] **Step 1: Write the failing test**

```python
# tests/server/test_blind.py
def test_blind_ack_hides_the_verdict(blind_room):
    p = blind_room.join("A", None)
    blind_room.start_round(now_ms=0)
    ack = blind_room.submit(p.id, "u1", "quatschwort", 1000)
    assert ack.accepted is None
    assert ack.reason is None
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/Scripts/python.exe -m pytest tests/server/test_blind.py -q`
Expected: FAIL — `accepted` is `False`, not `None`.

- [ ] **Step 3: Make `Ack.accepted` optional**

```python
class Ack(BaseModel):
    type: Literal["ack"] = "ack"
    client_uuid: str
    word: str
    accepted: bool | None   # None in blind mode: verdict withheld
    reason: str | None = None
```

- [ ] **Step 4: Add the flag and the neutral return to the room**

In `Room`:

```python
@property
def blind(self) -> bool:
    return bool(self.config.get("blind", False))
```

At the end of `submit`, after the row is recorded, replace the returned ack:

```python
if self.blind:
    return self._remember(client_uuid, Ack(
        client_uuid=client_uuid, word=verdict.word,
        accepted=None, reason=None))
```

The duplicate branch must also return a neutral ack when blind, and must
still record the row.

- [ ] **Step 5: Add `entered_count` and use it for progress**

```python
def entered_count(self, player_id: str) -> int:
    """Submissions made, regardless of verdict.

    Blind mode reports this instead of accepted words: an accepted count
    would leak, one increment at a time, whether the opponent's last entry
    was valid.
    """
    if self.round is None:
        return 0
    (n,) = self._conn.execute(
        "SELECT COUNT(*) FROM submissions WHERE round_id=? AND player=?",
        (self.round.row_id, player_id),
    ).fetchone()
    return int(n)
```

- [ ] **Step 6: Add `blind` to the game config**

```python
class NewGame(BaseModel):
    difficulty: str = "mittel"
    rounds: int = Field(default=10, ge=1, le=50)
    round_seconds: int = Field(default=180, ge=60, le=1800)
    blind: bool = False
```

- [ ] **Step 7: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/server -q`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add wortissimo/server tests/server/test_blind.py
git commit -m "feat: add blind scoring flag with a neutral ack"
```

---

### Task 2: Rejected words in the round result

**Files:**
- Modify: `wortissimo/server/db.py` (`rejected_words`)
- Modify: `wortissimo/server/room.py` (`end_round` payload)
- Test: `tests/server/test_blind.py`

**Interfaces:**
- Produces: `db.rejected_words(conn, round_id) -> dict[str, list[str]]`; `RoundEnded.result["rejected"] -> dict[player_id, list[str]]`.

- [ ] **Step 1: Write the failing test**

```python
def test_round_result_lists_words_that_were_wrong(blind_room):
    p = blind_room.join("A", None)
    blind_room.start_round(now_ms=0)
    blind_room.submit(p.id, "u1", "bahn", 1000)
    blind_room.submit(p.id, "u2", "quatschwort", 1100)
    ended = blind_room.end_round(now_ms=200_000)
    assert ended.result["rejected"][p.id] == ["quatschwort"]
```

- [ ] **Step 2: Run it and watch it fail**

Run: `.venv/Scripts/python.exe -m pytest tests/server/test_blind.py -q`
Expected: FAIL — `KeyError: 'rejected'`.

- [ ] **Step 3: Add the query**

```python
def rejected_words(conn: sqlite3.Connection, round_id: int) -> dict[str, list[str]]:
    """Words that did not count, per player, in submission order.

    These rows were always recorded; blind mode is the first thing that
    reads them back.
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
```

- [ ] **Step 4: Include it in the payload**

In `Room.end_round`, before building `payload`:

```python
rejected = db.rejected_words(self._conn, self.round.row_id)
for player_id in self.players:
    rejected.setdefault(player_id, [])
```

and add `"rejected": rejected` to the payload dict.

- [ ] **Step 5: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/server -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add wortissimo/server tests/server/test_blind.py
git commit -m "feat: report rejected words in the round result"
```

---

### Task 3: Solo endpoints

**Files:**
- Modify: `wortissimo/server/app.py`
- Test: `tests/server/test_solo.py`

**Interfaces:**
- Produces:
  - `GET /api/solo/puzzle?difficulty=<bucket>` → `{source_word, solutions, solution_count}`
  - `POST /api/solo/score` with `{solutions: list[str], claims: dict[str, list[str]]}` → `{scores: [{player, points, words, unique_words}], shared_words, missed_words}`

- [ ] **Step 1: Write the failing tests**

```python
# tests/server/test_solo.py
def test_solo_puzzle_returns_a_playable_round(client):
    body = client.get("/api/solo/puzzle?difficulty=mittel").json()
    assert body["source_word"]
    assert body["solution_count"] == len(body["solutions"])
    assert body["solution_count"] > 0


def test_solo_puzzle_rejects_an_unknown_difficulty(client):
    assert client.get("/api/solo/puzzle?difficulty=unmoeglich").status_code == 404


def test_solo_score_awards_the_unique_bonus(client):
    body = client.post("/api/solo/score", json={
        "solutions": ["bahn", "halte", "strasse"],
        "claims": {"Jonas": ["bahn"], "Freundin": ["halte"]},
    }).json()
    points = {s["player"]: s["points"] for s in body["scores"]}
    assert points == {"Jonas": 2, "Freundin": 2}


def test_solo_score_halves_the_bonus_for_a_shared_word(client):
    body = client.post("/api/solo/score", json={
        "solutions": ["bahn", "halte"],
        "claims": {"Jonas": ["bahn"], "Freundin": ["bahn"]},
    }).json()
    assert {s["points"] for s in body["scores"]} == {1}
    assert body["shared_words"] == ["bahn"]
    assert body["missed_words"] == ["halte"]
```

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/Scripts/python.exe -m pytest tests/server/test_solo.py -q`
Expected: FAIL — 404 on both routes.

- [ ] **Step 3: Add the endpoints**

```python
class SoloScoreRequest(BaseModel):
    solutions: list[str] = Field(default_factory=list, max_length=500)
    claims: dict[str, list[str]] = Field(default_factory=dict)


@app.get("/api/solo/puzzle")
def solo_puzzle(difficulty: str = "mittel") -> dict:
    """One puzzle for single-device play, solutions included.

    Shipping the solutions is acceptable here and only here: one device,
    players in the same room, and the list is revealed minutes later.
    """
    puzzle = hub.repo.pick(difficulty, exclude=set())
    if puzzle is None:
        raise HTTPException(status_code=404,
                            detail=f"no puzzles for difficulty {difficulty}")
    return {
        "source_word": puzzle.source_word,
        "solutions": sorted(puzzle.revealed),
        "solution_count": puzzle.solution_count,
    }


@app.post("/api/solo/score")
def solo_score(body: SoloScoreRequest) -> dict:
    """Score claimed words with the same function the live game uses."""
    result = score_round(body.claims, body.solutions)
    return {
        "scores": [
            {"player": s.player, "points": s.points,
             "words": list(s.words), "unique_words": list(s.unique_words)}
            for s in result.scores
        ],
        "shared_words": list(result.shared_words),
        "missed_words": list(result.missed_words),
    }
```

Add the imports `from fastapi import HTTPException` and
`from wortissimo.rules.scoring import score_round`, and expose the repo on
the hub as a public `repo` attribute.

- [ ] **Step 4: Run the tests**

Run: `.venv/Scripts/python.exe -m pytest tests/server -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add wortissimo/server tests/server/test_solo.py
git commit -m "feat: add stateless solo puzzle and scoring endpoints"
```

---

### Task 4: Solo client — setup, round, claim

**Files:**
- Create: `web/src/screens/SoloSetup.tsx`
- Create: `web/src/screens/SoloRound.tsx`
- Create: `web/src/screens/SoloClaim.tsx`
- Create: `web/src/lib/solo.ts`
- Test: `web/src/lib/solo.test.ts`

**Interfaces:**
- Produces:
  - `solo.ts`: `fetchPuzzle(difficulty): Promise<SoloPuzzle>`, `scoreClaims(solutions, claims): Promise<SoloResult>`, `type SoloPuzzle = {source_word, solutions, solution_count}`, `type SoloPlayer = {name}`.
  - Screens taking explicit props; no connection object anywhere in this mode.

- [ ] **Step 1: Write the failing test**

```ts
// web/src/lib/solo.test.ts
import { describe, expect, it } from "vitest";
import { nextClaimant, togglePick } from "./solo";

describe("claim rotation", () => {
  it("advances to the next player", () => {
    expect(nextClaimant(0, 2)).toBe(1);
  });
  it("returns null once everyone has claimed", () => {
    expect(nextClaimant(1, 2)).toBeNull();
  });
});

describe("togglePick", () => {
  it("adds a word that was not picked", () => {
    expect(togglePick(["bahn"], "halte")).toEqual(["bahn", "halte"]);
  });
  it("removes a word that was picked", () => {
    expect(togglePick(["bahn", "halte"], "bahn")).toEqual(["halte"]);
  });
  it("does not mutate its input", () => {
    const before = ["bahn"];
    togglePick(before, "halte");
    expect(before).toEqual(["bahn"]);
  });
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd web && npx vitest run --environment jsdom`
Expected: FAIL — cannot resolve `./solo`.

- [ ] **Step 3: Write `solo.ts`**

```ts
export interface SoloPuzzle {
  source_word: string;
  solutions: string[];
  solution_count: number;
}

export interface SoloScore {
  player: string;
  points: number;
  words: string[];
  unique_words: string[];
}

export interface SoloResult {
  scores: SoloScore[];
  shared_words: string[];
  missed_words: string[];
}

export async function fetchPuzzle(difficulty: string): Promise<SoloPuzzle> {
  const res = await fetch(`/api/solo/puzzle?difficulty=${difficulty}`);
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

export async function scoreClaims(
  solutions: string[],
  claims: Record<string, string[]>,
): Promise<SoloResult> {
  const res = await fetch("/api/solo/score", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ solutions, claims }),
  });
  if (!res.ok) throw new Error(String(res.status));
  return res.json();
}

/** Index of the next player to claim, or null when everyone has. */
export function nextClaimant(current: number, total: number): number | null {
  return current + 1 < total ? current + 1 : null;
}

/** Immutably toggle a word in a player's picks. */
export function togglePick(picks: string[], word: string): string[] {
  return picks.includes(word)
    ? picks.filter((w) => w !== word)
    : [...picks, word];
}
```

- [ ] **Step 4: Run the test**

Run: `cd web && npx vitest run --environment jsdom`
Expected: PASS.

- [ ] **Step 5: Write the three screens**

`SoloSetup.tsx` collects 2–6 names (a count stepper plus one text field per
player), difficulty, round count and round minutes reusing the lobby's
controls, and calls `onStart({names, difficulty, roundSeconds, rounds})`.
A name left blank becomes `Spieler 1`, `Spieler 2`, … so two blank fields
never collide.

`SoloRound.tsx` shows the source word and a local countdown from
`Date.now() + roundSeconds * 1000`, plus a "Fertig" button to end early.
No text input at all — the paper is the input.

`SoloClaim.tsx` shows one player's name as a heading and the full solution
list as toggle chips, with a "Weiter" button that hands over to the next
player and a running count of the current player's picks.

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/solo.ts web/src/lib/solo.test.ts web/src/screens/Solo*.tsx
git commit -m "feat: add solo mode screens and client helpers"
```

---

### Task 5: Wire both modes into the app

**Files:**
- Modify: `web/src/App.tsx`
- Modify: `web/src/screens/Lobby.tsx` (mode switch, blind toggle)
- Modify: `web/src/screens/Round.tsx` (neutral chips when blind)
- Modify: `web/src/screens/Results.tsx` (rejected list)
- Test: `web/e2e/solo.spec.ts`

**Interfaces:**
- Consumes: everything from Tasks 1–4.

- [ ] **Step 1: Write the failing Playwright test**

```ts
// web/e2e/solo.spec.ts
import { expect, test } from "@playwright/test";

test("a solo game runs from setup to a result", async ({ page }) => {
  await page.setViewportSize({ width: 834, height: 1194 });
  await page.goto("/");
  await page.getByRole("button", { name: "Auf Papier" }).click();

  await page.getByLabel("Name Spieler 1").fill("Jonas");
  await page.getByLabel("Name Spieler 2").fill("Freundin");
  await page.getByRole("button", { name: /Runde starten/ }).click();

  await expect(page.locator(".source-word")).toBeVisible();
  await page.getByRole("button", { name: "Fertig" }).click();

  // Jonas claims the first word, then hands over.
  await expect(page.getByRole("heading", { name: /Jonas/ })).toBeVisible();
  await page.locator(".chip").first().click();
  await page.getByRole("button", { name: "Weiter" }).click();

  await expect(page.getByRole("heading", { name: /Freundin/ })).toBeVisible();
  await page.getByRole("button", { name: "Weiter" }).click();

  await expect(page.getByText(/Punkte/).first()).toBeVisible();
});
```

- [ ] **Step 2: Run it and watch it fail**

Run: `cd web && npx playwright test solo.spec.ts`
Expected: FAIL — no "Auf Papier" button.

- [ ] **Step 3: Add the mode switch to the lobby**

Two buttons at the top: "Zu zweit" (the existing networked mode) and
"Auf Papier" (solo). The blind toggle appears only under "Zu zweit", as a
pressed/unpressed ghost button labelled `Blind — Auswertung erst am Ende`,
and is sent as `blind` in the create-game body.

- [ ] **Step 4: Neutral chips while blind**

`Round.tsx` receives a `blind` prop. When true, an ack with
`accepted === null` appends the word as a plain chip and no flash is shown.

- [ ] **Step 5: Rejected list on the results screen**

`Results.tsx` renders a third group per player, `Falsch`, from
`result.rejected[playerId]`, using `.chip.bad`, shown only when non-empty.

- [ ] **Step 6: Route the solo flow in `App.tsx`**

Add view kinds `solo_setup`, `solo_round`, `solo_claim`, and reuse the
existing `Results` and `Stats` screens for solo results by mapping
`SoloResult` into the same shape.

- [ ] **Step 7: Run everything**

```bash
.venv/Scripts/python.exe -m pytest -q
cd web && npx vitest run --environment jsdom && npm run build && npx playwright test
```
Expected: all green.

- [ ] **Step 8: Commit**

```bash
git add web
git commit -m "feat: wire blind mode and on-paper mode into the app"
```

---

## Exit Criteria

1. All Python tests pass, including the 226 that existed before.
2. Vitest and Playwright pass.
3. A networked game with `blind: false` behaves exactly as before.
4. In a blind game, no ack carries a verdict and progress counts entries.
5. A solo game runs setup → round → claim → result with two players and
   scores identically to the networked game for the same words.

## Self-Review Notes

Spec coverage:
- §1 blind flag, neutral ack, silent duplicates → Task 1.
- §1 entered-not-accepted progress → Task 1 Step 5.
- §1 richtig/falsch/verpasst → Task 2 (server), Task 5 Step 5 (client).
- §2 stateless endpoints → Task 3.
- §2 client flow and player-by-player claiming → Tasks 4 and 5.
- §2 timer → Task 4 (`SoloRound`), bounds enforced server-side already.
- §3 reuse → Task 3 calls `score_round`; Task 5 reuses `Results`/`Stats`.
- §4 testing → Tasks 1–5 each carry their tests.
- §5 risks → progress-leak covered in Task 1; single scoring definition in Task 3.
