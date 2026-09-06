"""Game state machine. Does no networking, so it is directly unit-testable.

The server is authoritative on round end (spec section 8.4): submissions
whose server-receipt time is past round_ends_at are rejected, and scoring
never waits for a disconnected player.

Two word tiers are in play, and confusing them is the bug this module is
most likely to grow. Input is validated against `puzzle.accepted` (the
generous superset). Only `puzzle.revealed` is ever shown or counted.
"""

import secrets
import sqlite3
from dataclasses import dataclass, field

from wortissimo.rules.scoring import score_round
from wortissimo.rules.validate import Rejection, validate_word
from wortissimo.server import db
from wortissimo.server.protocol import (
    Ack, PlayerInfo, RoundEnded, RoundSnapshot, RoundStarted, StateSync,
)
from wortissimo.server.puzzles import Puzzle, PuzzleRepo

ROUND_SECONDS = 180
TOTAL_ROUNDS = 10

STATE_LOBBY = "lobby"
STATE_PLAYING = "playing"
STATE_BETWEEN = "between"
STATE_FINISHED = "finished"


@dataclass
class Player:
    id: str
    name: str
    token: str


@dataclass
class ActiveRound:
    idx: int
    row_id: int
    puzzle: Puzzle
    ends_at: int
    seen_uuids: dict[str, Ack] = field(default_factory=dict)


class Room:
    def __init__(
        self,
        conn: sqlite3.Connection,
        repo: PuzzleRepo,
        game_id: int,
        code: str,
        config: dict,
    ) -> None:
        self._conn = conn
        self._repo = repo
        self.game_id = game_id
        self.code = code
        self.config = config
        self.players: dict[str, Player] = {}
        self._by_token: dict[str, str] = {}
        self.state = STATE_LOBBY
        self.current_round_idx = 0
        self.round: ActiveRound | None = None
        self.totals: dict[str, int] = {}

    # ----- players -----

    def join(self, name: str, token: str | None) -> Player:
        """Join, or rejoin as an existing player when the token matches.

        The id is opaque and unrelated to the name. Using the name as the
        identity collapsed two players into one whenever they typed the
        same thing — and the lobby's default is "Spieler" for everyone, so
        two people who never filled in the name box shared a word list, a
        score, and each other's progress.
        """
        if token and token in self._by_token:
            return self.players[self._by_token[token]]
        player = Player(
            id=secrets.token_urlsafe(9),
            name=name,
            token=secrets.token_urlsafe(16),
        )
        self.players[player.id] = player
        self._by_token[player.token] = player.id
        self.totals.setdefault(player.id, 0)
        return player

    def display_name(self, player_id: str) -> str:
        player = self.players.get(player_id)
        return player.name if player else player_id

    def roster(self) -> list[PlayerInfo]:
        """Everyone in the room, in join order."""
        return [PlayerInfo(id=p.id, name=p.name) for p in self.players.values()]

    # ----- config -----

    @property
    def difficulty(self) -> str:
        return self.config.get("difficulty", "mittel")

    @property
    def total_rounds(self) -> int:
        return int(self.config.get("rounds", TOTAL_ROUNDS))

    @property
    def round_seconds(self) -> int:
        return int(self.config.get("round_seconds", ROUND_SECONDS))

    @property
    def is_finished(self) -> bool:
        return self.state == STATE_FINISHED

    # ----- rounds -----

    def start_round(self, now_ms: int) -> RoundStarted | None:
        """Begin the next round. None if one is running, or nothing is left.

        Both players see a "next round" control, so two taps can race.
        Starting a second round on top of a live one would discard the
        first round's result before anyone saw it.
        """
        if self.round is not None:
            return None
        if self.current_round_idx >= self.total_rounds:
            self.state = STATE_FINISHED
            db.set_game_state(self._conn, self.game_id, self.state)
            return None

        used = db.used_puzzle_ids(self._conn, self.game_id)
        puzzle = self._repo.pick(self.difficulty, exclude=used)
        if puzzle is None:
            self.state = STATE_FINISHED
            db.set_game_state(self._conn, self.game_id, self.state)
            return None

        ends_at = now_ms + self.round_seconds * 1000
        row_id = db.create_round(
            self._conn, self.game_id, self.current_round_idx, puzzle.id, ends_at
        )
        self.round = ActiveRound(
            idx=self.current_round_idx, row_id=row_id, puzzle=puzzle, ends_at=ends_at
        )
        self.state = STATE_PLAYING
        db.set_game_state(self._conn, self.game_id, self.state)

        return RoundStarted(
            idx=self.round.idx,
            source_word=puzzle.source_word,
            round_ends_at=ends_at,
            solution_count=puzzle.solution_count,
        )

    def submit(self, player_id: str, client_uuid: str, word: str, now_ms: int) -> Ack:
        """Validate and record one submission. Idempotent on client_uuid."""
        if self.round is None or self.state != STATE_PLAYING:
            return Ack(client_uuid=client_uuid, word=word, accepted=False,
                       reason=Rejection.TOO_LATE)

        # Replay after reconnect returns the original verdict unchanged.
        if client_uuid in self.round.seen_uuids:
            return self.round.seen_uuids[client_uuid]

        if now_ms > self.round.ends_at:
            return self._remember(client_uuid, Ack(
                client_uuid=client_uuid, word=word, accepted=False,
                reason=Rejection.TOO_LATE))

        # Validated against the GENEROUS tier, never the revealed one.
        verdict = validate_word(
            word, self.round.puzzle.source_word, self.round.puzzle.accepted
        )

        if verdict.accepted:
            already = db.accepted_words(self._conn, self.round.row_id)
            if verdict.word in already.get(player_id, []):
                db.record_submission(
                    self._conn, self.round.row_id, player_id, verdict.word,
                    client_uuid, False, str(Rejection.DUPLICATE), now_ms)
                return self._remember(client_uuid, Ack(
                    client_uuid=client_uuid, word=verdict.word,
                    accepted=False, reason=Rejection.DUPLICATE))

        reason = str(verdict.reason) if verdict.reason else None
        db.record_submission(
            self._conn, self.round.row_id, player_id, verdict.word, client_uuid,
            verdict.accepted, reason, now_ms,
        )
        return self._remember(client_uuid, Ack(
            client_uuid=client_uuid, word=verdict.word,
            accepted=verdict.accepted, reason=reason))

    def _remember(self, client_uuid: str, ack: Ack) -> Ack:
        assert self.round is not None
        self.round.seen_uuids[client_uuid] = ack
        return ack

    def progress_count(self, player_id: str) -> int:
        if self.round is None:
            return 0
        return len(
            db.accepted_words(self._conn, self.round.row_id).get(player_id, [])
        )

    def end_round(self, now_ms: int) -> RoundEnded:
        """Score the round. Does not wait for disconnected players."""
        assert self.round is not None, "no active round"
        accepted = db.accepted_words(self._conn, self.round.row_id)
        for player_id in self.players:
            accepted.setdefault(player_id, [])

        # Scored against the revealed tier: accepted-only words still earn
        # points when found, but never appear in the missed list.
        result = score_round(accepted, self.round.puzzle.revealed)
        for score in result.scores:
            self.totals[score.player] = self.totals.get(score.player, 0) + score.points

        payload = {
            "source_word": self.round.puzzle.source_word,
            "solution_count": self.round.puzzle.solution_count,
            "scores": [
                {"player": s.player,
                 "name": self.display_name(s.player),
                 "points": s.points,
                 "words": list(s.words), "unique_words": list(s.unique_words)}
                for s in result.scores
            ],
            "shared_words": list(result.shared_words),
            "missed_words": list(result.missed_words),
            "totals": dict(self.totals),
        }

        idx = self.round.idx
        self.round = None
        self.current_round_idx += 1
        self.state = (STATE_FINISHED
                      if self.current_round_idx >= self.total_rounds
                      else STATE_BETWEEN)
        db.set_game_state(self._conn, self.game_id, self.state)
        return RoundEnded(idx=idx, result=payload)

    def game_stats(self) -> dict:
        """Per-round history for the end-of-game summary.

        Recomputed from the append-only submissions table rather than
        accumulated in memory, so it is correct even after a reconnect.
        """
        rounds: list[dict] = []
        totals: dict[str, int] = {p: 0 for p in self.players}

        for row in self._conn.execute(
            "SELECT id, idx, puzzle_id FROM rounds WHERE game_id=? ORDER BY idx",
            (self.game_id,),
        ):
            puzzle = self._repo.get(row["puzzle_id"])
            accepted = db.accepted_words(self._conn, row["id"])
            for player_id in self.players:
                accepted.setdefault(player_id, [])
            result = score_round(accepted, puzzle.revealed)

            per_player: dict[str, dict] = {}
            for score in result.scores:
                longest = max(score.words, key=len) if score.words else None
                per_player[score.player] = {
                    "points": score.points,
                    "words": len(score.words),
                    "unique": len(score.unique_words),
                    "longest": longest,
                }
                totals[score.player] = totals.get(score.player, 0) + score.points

            rounds.append({
                "idx": row["idx"],
                "source_word": puzzle.source_word,
                "solution_count": puzzle.solution_count,
                "found": len({w for s in result.scores for w in s.words}),
                "per_player": per_player,
            })

        return {
            "players": [p.model_dump() for p in self.roster()],
            "rounds": rounds,
            "totals": totals,
        }

    # ----- resync -----

    def snapshot(self, player_id: str) -> StateSync:
        """Full state for one player after (re)connecting.

        Carries the player's OWN accepted words only. The opponent's words
        and both solution tiers are never included (spec section 8.5).
        """
        round_snapshot = None
        my_words: list[str] = []
        if self.round is not None:
            round_snapshot = RoundSnapshot(
                idx=self.round.idx,
                source_word=self.round.puzzle.source_word,
                round_ends_at=self.round.ends_at,
                solution_count=self.round.puzzle.solution_count,
            )
            my_words = db.accepted_words(
                self._conn, self.round.row_id
            ).get(player_id, [])

        return StateSync(state=self.state, round=round_snapshot,
                         my_words=my_words, scores=dict(self.totals),
                         players=self.roster(),
                         round_seconds=self.round_seconds,
                         total_rounds=self.total_rounds)
