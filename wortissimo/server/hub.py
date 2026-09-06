"""Live connection registry. One Room per game code, N sockets per player.

A player may hold several sockets at once: iOS reconnects eagerly on
visibilitychange, and the replaced socket is not always closed yet.
Sending to a player therefore fans out, and dead sockets are dropped on
the first failed write.
"""

import asyncio
import json
import sqlite3
from collections.abc import Awaitable, Callable
from pathlib import Path

from fastapi import WebSocket
from pydantic import BaseModel

from wortissimo.server import db
from wortissimo.server.puzzles import PuzzleRepo
from wortissimo.server.room import Room


class Hub:
    def __init__(self, conn: sqlite3.Connection, puzzles_path: Path) -> None:
        self._conn = conn
        self._repo = PuzzleRepo(puzzles_path)
        self._rooms: dict[str, Room] = {}
        self._sockets: dict[str, dict[str, set[WebSocket]]] = {}
        self._timers: dict[str, asyncio.Task] = {}

    def get_room(self, code: str) -> Room | None:
        """Return the live room for `code`, rehydrating it from the db once."""
        if code in self._rooms:
            return self._rooms[code]
        row = db.get_game_by_code(self._conn, code)
        if row is None:
            return None
        room = Room(self._conn, self._repo, row["id"], code,
                    json.loads(row["config_json"]))
        self._rooms[code] = room
        return room

    # ----- sockets -----

    def connect(self, code: str, player_id: str, ws: WebSocket) -> None:
        self._sockets.setdefault(code, {}).setdefault(player_id, set()).add(ws)

    def disconnect(self, code: str, player_id: str, ws: WebSocket) -> None:
        self._sockets.get(code, {}).get(player_id, set()).discard(ws)

    async def send(self, code: str, player_id: str, message: BaseModel) -> None:
        payload = message.model_dump_json()
        for ws in list(self._sockets.get(code, {}).get(player_id, ())):
            try:
                await ws.send_text(payload)
            except Exception:
                self.disconnect(code, player_id, ws)

    async def broadcast(
        self, code: str, message: BaseModel, exclude: str | None = None
    ) -> None:
        for player_id in list(self._sockets.get(code, {})):
            if player_id == exclude:
                continue
            await self.send(code, player_id, message)

    # ----- round timer -----

    def schedule_round_end(
        self, code: str, ends_at: int, on_end: Callable[[], Awaitable[None]]
    ) -> None:
        """Server-side round timer.

        Runs here rather than on either client, so a phone that locks or
        loses its connection cannot stall or extend the round.
        """
        self.cancel_round_end(code)

        async def runner() -> None:
            delay = max(0.0, (ends_at - db.now_ms()) / 1000)
            try:
                await asyncio.sleep(delay)
                await on_end()
            except asyncio.CancelledError:
                pass

        self._timers[code] = asyncio.create_task(runner())

    def cancel_round_end(self, code: str) -> None:
        task = self._timers.pop(code, None)
        if task and not task.done():
            task.cancel()
