"""Exercise actual HTTPX-WS ping/pong handling without opening a network socket."""

import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import patch

import wsproto
from httpx_ws import AsyncWebSocketSession
from wsproto.events import Ping, TextMessage

from custom_components.iaqualink_tcx.coordinator import TcxCoordinator
from tests.conftest import CREDENTIALS, SERIAL, STATE, frame


class HeartbeatStream:
    """In-memory server: one bootstrap, then only protocol pong responses."""

    def __init__(self):
        self.connection = wsproto.connection.Connection(wsproto.ConnectionType.SERVER)
        self.incoming = asyncio.Queue()
        self.sent = []
        self.answer_pings = True
        self.ping_count = 0
        self.three_pings = asyncio.Event()
        self.closed = False

    async def read(self, max_bytes):
        return await self.incoming.get()

    async def write(self, data):
        self.connection.receive_data(data)
        for event in self.connection.events():
            if isinstance(event, Ping):
                self.ping_count += 1
                if self.answer_pings:
                    await self.incoming.put(self.connection.send(event.response()))
                if self.ping_count >= 3:
                    self.three_pings.set()
            elif isinstance(event, TextMessage):
                self.sent.append(json.loads(event.data))
                await self.incoming.put(
                    self.connection.send(TextMessage(data=json.dumps(frame(STATE))))
                )

    async def aclose(self):
        self.closed = True


async def test_real_ping_watchdog_keeps_quiet_session_and_detects_missing_pong(hass, entry, cloud):
    streams = []
    disconnected = asyncio.Event()

    @asynccontextmanager
    async def connect(*args, **kwargs):
        assert kwargs["keepalive_ping_interval_seconds"] == 30
        stream = HeartbeatStream()
        streams.append(stream)
        # Accelerate only the transport's clock intervals for the offline test.
        try:
            async with AsyncWebSocketSession(
                stream, keepalive_ping_interval_seconds=0.01, keepalive_ping_timeout_seconds=0.01
            ) as socket:
                yield socket
        finally:
            disconnected.set()

    client = cloud.client(**CREDENTIALS)
    await client.login()
    system = (await client.get_systems())[SERIAL]
    coordinator = TcxCoordinator(hass, entry, client, system)
    with patch("iaqualink.client.aconnect_ws", connect):
        try:
            await coordinator.async_refresh()
            assert coordinator.equipment_available
            last_state = client.last_state
            await asyncio.wait_for(streams[0].three_pings.wait(), timeout=1)
            assert client.stream_active
            assert client.last_state == last_state  # Pongs are not equipment samples.
            streams[0].answer_pings = False
            await asyncio.wait_for(disconnected.wait(), timeout=1)
            assert streams[0].closed
            assert not coordinator.equipment_available
            assert len(streams[0].sent) == 1
            # Public refresh restarts the subscription and bootstraps a new session.
            await coordinator.async_refresh()
            assert coordinator.equipment_available
            assert len(streams) == 2
            assert all(s.sent[0]["action"] == "subscribe" for s in streams)
        finally:
            await coordinator.async_close()
    assert all(s.closed for s in streams)
