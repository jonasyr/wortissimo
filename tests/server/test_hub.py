"""Delivery guarantees for the hub.

The round summary is produced once, by a server-side timer, and must reach
BOTH players — including one who is mid-reconnect with two live sockets,
and regardless of which of them started the round.
"""

import asyncio
import sqlite3

import pytest

from wortissimo.server.db import create_schema
from wortissimo.server.hub import Hub
from wortissimo.server.protocol import RoundEnded


class FakeSocket:
    """Records what was sent; can be made to fail like a dead connection."""

    def __init__(self, broken: bool = False) -> None:
        self.sent: list[str] = []
        self.broken = broken

    async def send_text(self, payload: str) -> None:
        if self.broken:
            raise ConnectionError("socket is gone")
        self.sent.append(payload)


@pytest.fixture
def hub(tmp_path):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    create_schema(conn)
    # No puzzle corpus needed: these tests only exercise delivery.
    (tmp_path / "empty.sqlite").touch()
    h = Hub.__new__(Hub)
    h._conn = conn
    h._repo = None
    h._rooms = {}
    h._sockets = {}
    h._timers = {}
    return h


def ended() -> RoundEnded:
    return RoundEnded(idx=0, result={"source_word": "strassenbahn"})


def test_round_summary_reaches_both_players(hub):
    a, b = FakeSocket(), FakeSocket()
    hub.connect("ABCD", "jw", a)
    hub.connect("ABCD", "gf", b)

    asyncio.run(hub.broadcast("ABCD", ended()))

    assert len(a.sent) == 1
    assert len(b.sent) == 1
    assert "round_ended" in a.sent[0]
    assert "round_ended" in b.sent[0]


def test_summary_reaches_every_socket_a_player_holds(hub):
    # iOS reconnects eagerly, so a player can briefly hold two sockets.
    first, second = FakeSocket(), FakeSocket()
    hub.connect("ABCD", "jw", first)
    hub.connect("ABCD", "jw", second)

    asyncio.run(hub.broadcast("ABCD", ended()))

    assert len(first.sent) == 1
    assert len(second.sent) == 1


def test_a_dead_socket_does_not_stop_the_other_player_being_told(hub):
    dead, alive = FakeSocket(broken=True), FakeSocket()
    hub.connect("ABCD", "jw", dead)
    hub.connect("ABCD", "gf", alive)

    asyncio.run(hub.broadcast("ABCD", ended()))

    assert len(alive.sent) == 1
    # The dead socket is dropped so it is not retried forever.
    assert dead not in hub._sockets["ABCD"]["jw"]


def test_broadcast_excludes_only_when_asked(hub):
    a, b = FakeSocket(), FakeSocket()
    hub.connect("ABCD", "jw", a)
    hub.connect("ABCD", "gf", b)

    asyncio.run(hub.broadcast("ABCD", ended(), exclude="jw"))

    assert a.sent == []
    assert len(b.sent) == 1


def test_summary_is_not_excluded_for_anyone_by_default(hub):
    """Guards the actual bug risk: end_round must broadcast to all.

    Progress updates deliberately exclude the sender; the round summary
    must not, or whoever's submission ended the round would never see it.
    """
    a, b = FakeSocket(), FakeSocket()
    hub.connect("ABCD", "jw", a)
    hub.connect("ABCD", "gf", b)

    asyncio.run(hub.broadcast("ABCD", ended(), exclude=None))

    assert len(a.sent) == 1 and len(b.sent) == 1
