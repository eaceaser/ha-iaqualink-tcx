"""Synthetic cloud fixtures. No real account or controller data."""

import asyncio
import json
from contextlib import asynccontextmanager
from unittest.mock import patch

import pytest
from homeassistant import config_entries, loader
from homeassistant.core import HomeAssistant

import httpx  # noqa: E402

# isort: skip_file
from iaqualink.const import AQUALINK_DEVICES_URL, AQUALINK_LOGIN_URL, AQUALINK_REFRESH_URL
from iaqualink.systems.tcx.system import TcxSystem

from custom_components.iaqualink_tcx.client import TcxClient

SERIAL = "synthetic-tcx-001"
CREDENTIALS = {"username": "synthetic@example.invalid", "password": "fixture-password"}
AUTH = {
    "session_id": "fixture-session",
    "authentication_token": "fixture-auth",
    "id": 123,
    "userPoolOAuth": {"IdToken": "fixture-id-token", "RefreshToken": "fixture-refresh"},
}
CONTROLLERS = [{"serial_number": SERIAL, "name": "Synthetic pool", "device_type": "tcx"}]
STATE = {
    "aws": {"status": "connected"},
    "systemMode": 0,
    "tempSetting": 0,
    "water": {"value": 0, "us": 1},
    "air": {"value": 200, "us": 1},
    "filt0": {"st": 0},
    "TspBdy0": {"heatEnabled": True, "waterTempSet": 280},
    "lvh1": {"en": 1, "app": "HEAT"},
    "ecm0": {
        "cmdSpd": 600,
        "minSpd": 600,
        "maxSpd": 3450,
        "spdList": [{"name": "Low", "speed": 600}],
    },
}


def frame(state, service="Authorization"):
    return {"service": service, "payload": {"main": {"state": {"reported": state}}}}


@pytest.fixture
async def hass(tmp_path):
    hass = HomeAssistant(str(tmp_path))
    hass.config_entries = config_entries.ConfigEntries(hass, {})
    loader.async_setup(hass)
    yield hass
    await hass.async_stop(force=True)


@pytest.fixture
def entry():
    return config_entries.ConfigEntry(
        domain="iaqualink_tcx",
        state=config_entries.ConfigEntryState.SETUP_IN_PROGRESS,
        title="Synthetic pool",
        version=1,
        minor_version=1,
        source="user",
        data={**CREDENTIALS, "serial": SERIAL},
        options={},
        unique_id=SERIAL,
        discovery_keys={},
        subentries_data=[],
    )


class Cloud:
    def __init__(self):
        self.requests = []
        self.sent = []
        self.controllers = list(CONTROLLERS)
        self.state = dict(STATE)
        self.queue = asyncio.Queue()
        self.clients = []
        self.status = 200
        self.sockets = 0

    def request(self, request):
        self.requests.append(request)
        if self.status != 200:
            return httpx.Response(self.status, json={})
        if str(request.url).split("?")[0] in (AQUALINK_LOGIN_URL, AQUALINK_REFRESH_URL):
            assert request.method == "POST"
            return httpx.Response(200, json=AUTH)
        if str(request.url).startswith(AQUALINK_DEVICES_URL):
            assert request.method == "GET"
            return httpx.Response(200, json=self.controllers)
        assert request.method == "GET" and request.url.path.endswith("/shadow")
        return httpx.Response(200, json={"state": {"reported": self.state}})

    def client(self, *args, **kwargs):
        client = TcxClient(*args, **kwargs)
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(self.request))
        self.clients.append(client)
        return client

    @asynccontextmanager
    async def connect(self, *args, **kwargs):
        cloud = self
        cloud.sockets += 1

        class Socket:
            async def send_text(self, raw):
                cloud.sent.append(json.loads(raw))

            async def receive_text(self, **kwargs):
                item = await cloud.queue.get()
                if isinstance(item, Exception):
                    raise item
                return json.dumps(item)

        try:
            yield Socket()
        finally:
            cloud.sockets -= 1

    async def drain(self):
        for _ in range(12):
            await asyncio.sleep(0)


@pytest.fixture
async def cloud():
    cloud = Cloud()
    with (
        patch("iaqualink.client.aconnect_ws", cloud.connect),
        patch("socket.socket.connect", side_effect=AssertionError("Offline test blocked network")),
        patch(
            "socket.socket.connect_ex", side_effect=AssertionError("Offline test blocked network")
        ),
    ):
        yield cloud
    for client in cloud.clients:
        await client.close()
    assert cloud.sockets == 0


@pytest.fixture
async def acquisition(hass, entry, cloud):
    from custom_components.iaqualink_tcx.coordinator import TcxCoordinator

    client = cloud.client(**CREDENTIALS)
    await client.login()
    system = (await client.get_systems())[SERIAL]
    assert isinstance(system, TcxSystem)
    await cloud.queue.put(frame(STATE))
    coordinator = TcxCoordinator(hass, entry, client, system)
    await coordinator.async_refresh()
    yield coordinator
    await coordinator.async_close()
