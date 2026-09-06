"""FastAPI application: static SPA, health, game creation, WebSocket."""

import os
import secrets
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from wortissimo.server import db
from wortissimo.server.hub import Hub
from wortissimo.server.protocol import (
    Error, Join, Joined, OpponentProgress, Ping, Pong, StartRound, Submit,
    parse_client_message,
)

# I and O are omitted: unreadable next to 1 and 0 on a phone screen.
CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ"
CODE_LENGTH = 4
FLAGGED_PATH = Path(os.environ.get("WORTISSIMO_FLAGGED", "data/flagged.txt"))


class NewGame(BaseModel):
    difficulty: str = "mittel"
    rounds: int = Field(default=10, ge=1, le=50)
    round_seconds: int = Field(default=180, ge=30, le=900)


class FlagRound(BaseModel):
    source_word: str = Field(min_length=1, max_length=64)


def create_app(
    puzzles_path: Path, games_path: Path, static_dir: Path | None
) -> FastAPI:
    app = FastAPI(title="Wortissimo")
    conn = db.connect(games_path)
    hub = Hub(conn, puzzles_path)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/api/games")
    def create_game(body: NewGame) -> dict:
        for _ in range(20):
            code = "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))
            if db.get_game_by_code(conn, code) is None:
                db.create_game(conn, code, body.model_dump())
                return {"code": code}
        raise RuntimeError("could not allocate a game code")

    @app.post("/api/flag")
    def flag_round(body: FlagRound) -> dict:
        """Append a flagged round for manual blocklist review (spec §11)."""
        FLAGGED_PATH.parent.mkdir(parents=True, exist_ok=True)
        with FLAGGED_PATH.open("a", encoding="utf-8") as fh:
            fh.write(f"{body.source_word}\n")
        return {"ok": True}

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        code: str | None = None
        player_id: str | None = None

        async def fail(message: str) -> None:
            await ws.send_text(Error(message=message[:200]).model_dump_json())

        try:
            while True:
                raw = await ws.receive_text()
                try:
                    msg = parse_client_message(raw)
                except (ValidationError, ValueError) as exc:
                    await fail(str(exc))
                    continue

                if isinstance(msg, Ping):
                    await ws.send_text(
                        Pong(t0=msg.t0, server_time=db.now_ms()).model_dump_json()
                    )
                    continue

                if isinstance(msg, Join):
                    room = hub.get_room(msg.code)
                    if room is None:
                        await fail(f"unknown game code {msg.code}")
                        continue
                    player = room.join(msg.player, msg.rejoin_token)
                    code, player_id = msg.code, player.id
                    hub.connect(code, player_id, ws)
                    await ws.send_text(Joined(
                        player_id=player.id, rejoin_token=player.token,
                        code=code, state=room.state,
                    ).model_dump_json())
                    # Resync immediately: this is what lets a phone that
                    # locked mid-round pick up exactly where it left off.
                    await ws.send_text(room.snapshot(player.id).model_dump_json())
                    continue

                if code is None or player_id is None:
                    await fail("join first")
                    continue

                room = hub.get_room(code)
                assert room is not None

                if isinstance(msg, StartRound):
                    started = room.start_round(db.now_ms())
                    if started is None:
                        await hub.broadcast(code, Error(message="no rounds left"))
                        continue

                    async def end_now(code: str = code, room=room) -> None:
                        ended = room.end_round(db.now_ms())
                        await hub.broadcast(code, ended)

                    hub.schedule_round_end(code, started.round_ends_at, end_now)
                    await hub.broadcast(code, started)
                    continue

                if isinstance(msg, Submit):
                    ack = room.submit(player_id, msg.client_uuid, msg.word,
                                      db.now_ms())
                    await ws.send_text(ack.model_dump_json())
                    if ack.accepted:
                        await hub.broadcast(
                            code,
                            OpponentProgress(player=player_id,
                                             count=room.progress_count(player_id)),
                            exclude=player_id,
                        )
                    continue

        except WebSocketDisconnect:
            pass
        finally:
            if code and player_id:
                hub.disconnect(code, player_id, ws)

    if static_dir is not None and static_dir.exists():
        assets = static_dir / "assets"
        if assets.exists():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/{path:path}")
        def spa(path: str) -> FileResponse:
            candidate = static_dir / path
            if path and candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(static_dir / "index.html")

    return app


app = create_app(
    puzzles_path=Path(os.environ.get("WORTISSIMO_PUZZLES", "data/puzzles.sqlite")),
    games_path=Path(os.environ.get("WORTISSIMO_GAMES", "data/games.sqlite")),
    static_dir=(Path(os.environ["WORTISSIMO_STATIC"])
                if os.environ.get("WORTISSIMO_STATIC") else None),
)
