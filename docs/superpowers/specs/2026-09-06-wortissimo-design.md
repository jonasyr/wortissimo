# Wortissimo — Design Spec

Date: 2026-09-06
Status: Approved (design). Implementation plan pending.

## 1. Purpose

A self-hosted, two-player German word game. Each round shows one long German
source word. Both players race a shared 180-second clock to find as many valid
German words as possible that appear as **contiguous substrings** of that word.
Target devices: iPhone and iPad, two separate devices, played simultaneously.

The application generates its own rounds from a dictionary. There is no
hand-authored card set and no manual round preparation, ever.

## 2. Deployment context (fixed, not a variable)

- Runs on the existing home server.
- Reachable over Tailscale, served via `tailscale serve` on a `*.ts.net` name.
- That name carries a real Let's Encrypt certificate, which supplies the secure
  context iOS requires for service workers and PWA installation. Plain
  `http://192.168.x.x` would not, and is not an option.
- No public internet exposure. No user accounts. No third-party runtime services.

## 3. The constraint that shapes the design

iOS suspends an application shortly after the screen locks or the app
backgrounds. A suspended iOS app may keep only a narrow set of connections
(audio, VoIP); **WebSockets are not among them**. Reports indicate this is more
aggressive in installed-PWA mode than in plain Safari.

Over a 180-second round on a phone this is not an edge case — it is expected
behaviour. Therefore:

- No timer may be derived from accumulated `setInterval` ticks.
- No submitted word may exist only in foreground memory.
- No round outcome may depend on both players being connected at the buzzer.

Section 8 specifies the protocol that satisfies these.

## 4. Architecture: two phases

### 4.1 Build phase (offline batch, Python)

```
germandict (public domain, ~2M forms incl. inflections)
  -> normalize
  -> frequency annotate
  -> ACCEPTANCE list (generous)  +  SOLUTION list (clean)
  -> for each candidate source word: enumerate contiguous substrings
  -> lookup against SOLUTION list
  -> CharSplit segmentation -> classify each solution
  -> hard-constraint filter -> assign difficulty bucket
  -> puzzles.sqlite   <- the only thing runtime ever sees
```

Runs on demand, not per request. Output is a persisted artifact.

Cost analysis: a source word of length n yields n(n+1)/2 substrings; n=40 gives
820. Across ~100k candidate source words that is ~82M set lookups — seconds,
once, in a batch job. The proposal this design replaces treated this as a
scaling concern. It is not one.

### 4.2 Runtime phase

A single FastAPI process serving:

- the built static SPA,
- one WebSocket endpoint,
- SQLite (puzzles read-only; games read-write).

Runtime holds **no dictionary**. Per round it knows exactly one thing: that
puzzle's precomputed solution set.

### 4.3 Rejected alternative

An earlier proposal placed Dictionary, Morphology, and Word Validator as
runtime services. They are build-time concerns. Moving them to build time
deletes three runtime components, removes all dictionary memory pressure from
the server, and reduces validation to an O(1) set membership test.

The Python stack itself is retained, for a reason the original proposal did not
give: the generator unavoidably requires Python (CharSplit, frequency tooling),
so introducing a second Node runtime purely to host a ~200-line WebSocket
server would mean two containers and two dependency trees for zero gain.

## 5. Module boundaries

```
wortissimo/rules/       PURE. normalize(), is_valid_substring(), score_round().
                        No I/O, no state, no config loading.
                        Imported by BOTH generator and server.
wortissimo/lexicon/     Build-time only. Loaders, frequency, filters, blocklist.
wortissimo/generator/   Substring enumeration, classification, difficulty bucketing.
wortissimo/server/      FastAPI app, WS protocol, room state machine, persistence.
web/                    React + Vite + TypeScript PWA.
```

`rules` being pure and shared is the load-bearing decision of this design: it
makes it structurally impossible for the offline generator and the live game to
disagree about what counts as a valid word.

Dependency direction is strictly one-way: `lexicon`, `generator`, and `server`
may import `rules`. `rules` imports nothing from them.

## 6. Lexicon: two lists, not one

A single word list cannot serve both runtime jobs, because the jobs have
opposite requirements.

**Acceptance list** — decides whether a word a player typed scores. Must be
generous. Wrongly rejecting a real German word is the most rage-inducing
failure mode in this genre and is to be avoided even at the cost of accepting
some marginal words.

**Solution list** — what the game reveals as "words you missed", and the basis
for all puzzle-quality and difficulty computation. Must be clean. Revealing
`aer` or `Ilm` as a word the player "missed" destroys trust in the game
immediately.

Solution list = acceptance list filtered by corpus frequency floor, minimum
length, and proper-noun heuristics, minus a manual blocklist.

The manual blocklist is a first-class artifact, not a hack. It grows from an
in-game "bad round" button (Section 11).

## 7. Normalization

Because positional scoring was cut from scope (Section 11), only *containment*
matters, never character offsets. Both sides may therefore be canonicalised
freely.

Canonical form:

1. `str.casefold()` — never `.lower()`; casefold handles ß correctly.
2. ß -> ss, applied to both the source word and player input.
3. Umlauts are preserved as umlauts. **No ae/oe/ue aliasing in v1.** The iOS
   German keyboard produces ä/ö/ü natively, and aliasing would manufacture
   false substrings.
4. Trim surrounding whitespace. Reject input containing non-letter characters.

This function lives in `rules` and is the single definition used by both phases.

## 8. Runtime protocol

### 8.1 Clock

The server sends `round_ends_at` as an absolute UTC millisecond timestamp. The
client measures its clock offset against the server via a ping/pong exchange at
join and renders:

```
remaining = round_ends_at - (Date.now() + offset)
```

Recomputed on every `visibilitychange` and `pageshow`. Ticks are never
accumulated. This is what makes the timer survive iOS freezing the tab.

### 8.2 Submission outbox

Every submitted word receives a client-generated UUID and is written to
`sessionStorage` before being sent. It is removed from the outbox only on
server acknowledgement. On reconnect the client replays the entire outbox; the
server deduplicates by UUID.

Consequence: locking the phone mid-round loses nothing.

### 8.3 Reconnection

- Exponential backoff, plus an immediate reconnect attempt on
  `visibilitychange -> visible`.
- A rejoin token in `localStorage` allows rejoining after a full app kill.
- On rejoin the server sends a full state resync: current round, `ends_at`, and
  the player's own accepted words — never the opponent's.

### 8.4 Authority

The server is authoritative on round end. Submissions whose server-receipt time
is after `round_ends_at` are rejected with an explicit reason. A player being
disconnected at the buzzer does not block or delay scoring.

### 8.5 Anti-cheat

Validation is server-side. The client never receives the solution set until the
round has ended. On Tailscale the added latency is not measurable in gameplay
terms, so this removes the cheating question entirely rather than mitigating it.

## 9. Puzzle generation

For each candidate source word:

1. Enumerate all contiguous substrings of length >= 3.
2. Look each up in the solution list.
3. Run CharSplit on the source word to obtain morpheme boundaries.
4. Classify each solution by its span:
   - `OBVIOUS_COMPONENT` — span aligns with a morpheme boundary.
   - `CROSS_BOUNDARY` — span straddles a boundary. These are the finds that
     feel clever, and they are the primary difficulty signal.
5. Apply the difficulty constraint table (Section 10). Discard any source word
   matching no bucket.

**CharSplit output is used only for difficulty bucketing. It never accepts or
rejects a player's word.** Its ~5% error rate is therefore cosmetic and cannot
affect correctness. This containment is deliberate.

The `HIDDEN`, `RARE`, and `VERY_RARE` categories from the earlier proposal are
dropped: they are frequency bands, not distinct concepts, and are already
expressed by the frequency annotation.

## 10. Difficulty

Replaces the earlier proposal's weighted score `aN + bU + cL + dD - eB`. Five
coefficients cannot be calibrated from two players' data; the apparent
precision is not real. A constraint table is deterministic, debuggable, and
tunable by editing one table.

| Bucket  | Source length | Solutions | >=7 letters | Cross-boundary | Max trivial share |
|---------|---------------|-----------|-------------|----------------|-------------------|
| Leicht  | 15-20         | 15-25     | >= 2        | >= 1           | 50%               |
| Mittel  | 20-28         | 20-35     | >= 3        | >= 3           | 40%               |
| Schwer  | 25-35         | 25-45     | >= 4        | >= 6           | 30%               |
| Brutal  | 25-40         | 30-60     | >= 5        | >= 10          | 20%               |

"Trivial share" = fraction of solutions that are both `OBVIOUS_COMPONENT` and
high-frequency.

These thresholds are a starting point, to be recalibrated against real play.

## 11. Game rules (v1 scope)

In scope:

- Minimum word length: 3 letters.
- Word must appear as a contiguous substring of the source word, in order, with
  no letters skipped and none added.
- Word must be in the acceptance list.
- Word may not equal the entire source word.
- Case-insensitive.
- Proper nouns excluded (heuristic; imperfect by acknowledgement).
- Each distinct word scores at most once per player per round, regardless of
  how many positions it occupies.
- Round length: 180 seconds, configurable.
- Scoring: 1 point per valid word; 2 points if no other player submitted that
  word in the same round.
- Game length: 10 rounds, configurable. Highest total wins; ties are shared.
- Difficulty selectable per game: Leicht / Mittel / Schwer / Brutal.
- A source word is never repeated within a game.
- Post-round screen shows: source word, per-player score, each player's words,
  shared words, unique words, missed valid solutions, total solution count.
- A "bad round" button on the results screen flags the round; flagged words feed
  the manual blocklist review.

Explicitly deferred (not built in v1):

- Positional scoring (same word counted per distinct position). Doubles scoring,
  results-screen, and duplicate-handling complexity; in practice rewards
  noticing that "er" occurs four times.
- Reverse reading.
- Joker letter. The earlier proposal admitted this rule was not yet specified.
- Two-letter-word variant.
- More than two players. The data model does not preclude it; the UI assumes two.

## 12. Data model (SQLite)

```
puzzles(id, source_word, difficulty, solution_count, meta_json)
solutions(puzzle_id, word, category, freq)
games(id, code, config_json, state, created_at)
rounds(game_id, idx, puzzle_id, ends_at)
submissions(round_id, player, word, client_uuid, accepted, reason, at)
```

`submissions` is append-only. Rows are never updated or deleted; scoring is a
projection over them. This matches the project's immutability requirement and
makes replay-after-reconnect naturally idempotent (unique index on
`client_uuid`).

## 13. Apple mobile requirements

All verified during design research.

- `viewport-fit=cover` plus `env(safe-area-inset-bottom)` on the fixed input bar.
- Input `font-size` >= 16px. Below this, iOS force-zooms the page on focus.
- `touch-action: manipulation` on buttons only. Applying it to `html` breaks
  keyboard appearance for inputs in standalone mode.
- Position the input bar from `visualViewport`, **not** `100dvh`. A known
  standalone-PWA bug leaves dvh permanently reduced after the keyboard
  dismisses, producing a dead band at the bottom of the screen.
- `autocorrect="off" autocapitalize="off" spellcheck="false"` on the word input.
  Non-negotiable: iOS autocorrect silently rewrites German words mid-typing and
  the player will attribute the resulting rejection to the game.
- `enterkeyhint="send"`; the keyboard stays open between submissions.
- `overscroll-behavior: none` to suppress rubber-band scrolling.
- Service worker caches the app shell only. Game state is never cached.
- No push notifications are required anywhere in this design, so iOS PWA
  notification limitations are out of scope.
- Tap targets sized for one-handed play; the input sits at the bottom of the
  screen within thumb reach.

## 14. Testing strategy

- `rules`: property-based tests (hypothesis) over normalization invariants —
  idempotence, casefold/ß correctness, substring symmetry.
- `generator`: golden-file tests against a small fixture dictionary, so
  classification and bucketing changes are visible as diffs.
- `server`: pytest-asyncio WebSocket tests, **including a simulated mid-round
  disconnect followed by outbox replay**, and a late-submission rejection test.
- One Playwright run at iPhone viewport covering the reconnect flow.
- Coverage target 80% on `rules`, `generator`, and `server`.

## 15. Risks

| Risk | Mitigation |
|---|---|
| germandict contains junk entries | frequency floor + proper-noun heuristics + manual blocklist fed by the in-game reject button |
| CharSplit misclassifies boundaries | contained to difficulty bucketing; cannot affect accept/reject correctness |
| iOS suspends app mid-round | Section 8: absolute-timestamp clock, submission outbox, resync on rejoin; explicitly covered by tests |
| A real German word is rejected | two-tier lists; acceptance side deliberately generous |
| Proper nouns leak into solutions | heuristic only; acknowledged as imperfect. The blocklist is the correction path. |
| Difficulty thresholds feel wrong | single table, recalibrated from real play data |

## 16. Open items for the implementation plan

- Choice of frequency corpus for the annotation step (candidates: Leipzig
  Wortschatz, wordfreq). Licensing must be checked before selection; the
  acceptance list itself is public domain and unaffected.
- Container and `tailscale serve` configuration details.
- Whether `puzzles.sqlite` is committed to the repository or generated during
  the container build.
