# Paper Modes — Design Spec

Date: 2026-09-07
Status: Approved (design).

Two additions that make Wortissimo feel closer to playing on paper.

## 1. Blind scoring (a flag on the existing two-device mode)

### Problem

Live validation tells you instantly whether a word counts. On paper you
write everything down and find out at the end. The instant verdict also
changes how people play: you stop guessing, because guessing is punished
with a red flash.

### Design

A per-game boolean `blind`, chosen in the lobby, stored in the game's
config alongside `difficulty`, `rounds` and `round_seconds`.

When `blind` is on:

- `Room.submit()` validates and records exactly as it does now. The
  `submissions` table already stores rejected rows with their reason, so
  no schema change is needed.
- The returned `Ack` carries `accepted: null` and no reason. The client
  renders every entry as a neutral chip.
- Duplicate words are accepted silently rather than rejected. Any live
  "schon gefunden" would break the illusion; duplicates are collapsed at
  scoring, which is what already happens.
- **Opponent progress reports words *entered*, not words correct.**
  Reporting correct words would leak, one increment at a time, whether
  the opponent's last entry was valid — which defeats the entire point of
  the mode.

At round end the results screen shows three groups instead of two:

| group | source |
|---|---|
| richtig | accepted submissions, as today |
| falsch | rejected submissions, previously discarded |
| verpasst | revealed solutions nobody found, as today |

### Not in scope

Blind mode does not change scoring, the timer, or reconnect behaviour. A
word rejected in blind mode is rejected for the same reasons and shows the
same explanation — just later.

## 2. On-paper mode (single device)

### Problem

Two people, one iPad, sitting at the same table. The two-device mode is
the wrong shape for that: it wants a room, two connections, a synchronised
clock and rejoin tokens, none of which exist when there is one device and
one clock that everybody can see.

### Design decision: a separate path, not the engine with one player

On-paper mode is **fully client-side**. It uses no WebSocket, creates no
game record, and never enters `Room`.

The reasoning: with one device there is no state to synchronise. Building
this on the room machinery would drag in reconnect handling, an outbox, a
rejoin token and a clock-offset protocol to solve problems this mode does
not have. The only thing it genuinely needs from the server is a puzzle,
and a definition of scoring.

### Server surface

Two stateless endpoints. Neither touches the games database.

```
GET  /api/solo/puzzle?difficulty=<bucket>
     -> { source_word, solutions: [...], solution_count }

POST /api/solo/score
     { solutions: [...], claims: { "<name>": ["wort", ...] } }
     -> { scores: [ { player, points, words, unique_words } ],
          shared_words, missed_words }
```

`/api/solo/puzzle` ships the solution list to the client. That is
acceptable here and only here: there is one device, the players are in the
same room, and the list is revealed a few minutes later regardless.

`/api/solo/score` exists so that `rules.score_round` stays the single
definition of scoring. Reimplementing "one point, two if nobody else found
it" in TypeScript is about fifteen lines — and the first time the two
drifted, the disagreement would surface as an argument between two people
at a table with no way to settle it.

### Client flow

```
SoloSetup   player count (2-6) and names
    |
SoloRound   source word + countdown, no input at all
    |
SoloClaim   one player at a time taps the words they wrote down,
            then hands the device on
    |
Results     per-player points, shared and unique words, missed words
    |
            next round, or the existing Stats screen
```

Claiming is **player by player**: the full solution list is shown, the
active player taps everything they found, confirms, and passes the device.
This mirrors reading your own sheet and ticking things off, keeps one
active player on screen at a time, and extends to three or more players
without changing any screen.

### Timer

Configurable exactly as in two-device mode (1–30 minutes). The countdown
is local: with one device there is no clock to synchronise and no
suspension problem to survive, because nobody is going to lock the screen
mid-round while both players are looking at it.

### State

Held in React state for the duration of the game. Nothing is persisted.
Closing the tab ends the game — acceptable for a mode played in one
sitting at one table, and the alternative (a game record, a resume path)
buys nothing for the way the mode is actually used.

## 3. Reuse

Unchanged and reused: `wortissimo/rules/` for scoring, `PuzzleRepo` for
puzzle selection, the puzzle corpus, the Stats screen, and all styling.

Added: the `blind` config flag, a neutral `Ack`, the rejected-word list in
round results, two REST endpoints, and four client screens.

## 4. Testing

- `blind`: room-level tests that a rejected word still records its reason
  while the ack stays neutral, that progress counts entries rather than
  accepted words, and that scoring is unchanged by the flag.
- `/api/solo/puzzle`: returns a puzzle of the requested difficulty, 404s
  for an unknown bucket, and includes the solutions.
- `/api/solo/score`: agrees with `score_round` for the same input,
  including the unique-word bonus and the missed list.
- Client: the claim screen's selection logic, and a Playwright pass
  through setup → round → claim → result at iPad size.

## 5. Risks

| Risk | Mitigation |
|---|---|
| Solutions visible in devtools in solo mode | Accepted by design: one device, one room, revealed minutes later anyway |
| Two scoring implementations drift | There is only one — the client calls the server to score |
| Blind mode leaking validity via progress count | Progress counts entries, not accepted words; covered by a test |
| Solo mode state lost on tab close | Accepted: one sitting, one table |
