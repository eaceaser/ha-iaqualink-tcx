import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers.update_coordinator import UpdateFailed
from iaqualink.const import AQUALINK_LOGIN_URL

from custom_components.iaqualink_tcx import async_setup_entry, async_unload_entry
from custom_components.iaqualink_tcx.client import discover
from custom_components.iaqualink_tcx.config_flow import TcxConfigFlow
from tests.conftest import CREDENTIALS, SERIAL, STATE, frame


async def test_transport_boundary_and_subscription_reuse(acquisition, cloud):
    c = acquisition
    assert c.equipment_available
    for _ in range(3):
        await c.async_refresh()
    assert cloud.sockets == 1
    assert len(cloud.sent) == 1
    assert cloud.sent[0]["action"] == "subscribe"
    assert cloud.sent[0]["service"] == "Authorization"
    assert all(r.method == "GET" or str(r.url) == AQUALINK_LOGIN_URL for r in cloud.requests)
    assert len(cloud.requests) == 2  # Login + metadata, no REST shadow with fresh WS.
    with pytest.raises(RuntimeError, match="disabled"):
        await c.system.set_filter_pump(1)
    with pytest.raises(RuntimeError, match="disabled"):
        await c.client.send_request("https://example.invalid/shadow", method="post", json={})
    await c.async_close()
    await c.async_close()
    assert cloud.sockets == 0
    assert len(cloud.sent) == 1


async def test_discovery_does_not_refresh_other_equipment(cloud):
    cloud.controllers += [
        {"serial_number": "synthetic-other", "name": "Other", "device_type": "iaqua"}
    ]
    client = cloud.client(**CREDENTIALS)
    systems = await discover(client)
    assert list(systems) == [SERIAL]
    assert all(not s.devices for s in systems.values())
    assert len(cloud.requests) == 2
    assert not cloud.sent


async def test_flow_selection_duplicates_and_reauth(hass, entry, cloud):
    flow = TcxConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    cloud.controllers += [
        {"serial_number": "synthetic-tcx-002", "name": "Second", "device_type": "tcx"}
    ]
    with patch("custom_components.iaqualink_tcx.config_flow.TcxClient", cloud.client):
        result = await flow.async_step_user(CREDENTIALS)
    assert result["step_id"] == "controller"
    assert all(c._client is None for c in cloud.clients)
    with (
        patch.object(flow, "async_set_unique_id", AsyncMock()),
        patch.object(flow, "_abort_if_unique_id_configured") as duplicate,
    ):
        result = await flow.async_step_controller({"serial": SERIAL})
    duplicate.assert_called_once()
    assert result["data"]["serial"] == SERIAL
    flow.context = {"source": "reauth", "entry_id": entry.entry_id}
    with (
        patch.object(flow, "_get_reauth_entry", return_value=entry),
        patch.object(
            flow, "async_update_reload_and_abort", return_value={"type": "abort"}
        ) as update,
        patch("custom_components.iaqualink_tcx.config_flow.TcxClient", cloud.client),
    ):
        await flow.async_step_reauth_confirm(CREDENTIALS)
    update.assert_called_once_with(entry, data_updates=CREDENTIALS)


@pytest.mark.parametrize("status,error", [(401, "invalid_auth"), (500, "cannot_connect")])
async def test_flow_errors(hass, cloud, status, error):
    flow = TcxConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    cloud.status = status
    with patch("custom_components.iaqualink_tcx.config_flow.TcxClient", cloud.client):
        result = await flow.async_step_user(CREDENTIALS)
    assert result["errors"]["base"] == error
    assert all(c._client is None for c in cloud.clients)


async def test_no_tcx_and_wrong_account_reauth(hass, entry, cloud):
    flow = TcxConfigFlow()
    flow.hass = hass
    flow.context = {"source": "user"}
    cloud.controllers = []
    with patch("custom_components.iaqualink_tcx.config_flow.TcxClient", cloud.client):
        assert (await flow.async_step_user(CREDENTIALS))["reason"] == "no_tcx"
        with patch.object(flow, "_get_reauth_entry", return_value=entry):
            result = await flow.async_step_reauth_confirm(CREDENTIALS)
    assert result["errors"]["base"] == "controller_missing"


@pytest.mark.parametrize(
    "status,exception", [(401, ConfigEntryAuthFailed), (500, ConfigEntryNotReady)]
)
async def test_setup_error_cleanup(hass, entry, cloud, status, exception):
    cloud.status = status
    with patch("custom_components.iaqualink_tcx.TcxClient", cloud.client), pytest.raises(exception):
        await async_setup_entry(hass, entry)
    assert all(c._client is None for c in cloud.clients)
    assert not cloud.sent


async def test_setup_unload(hass, entry, cloud):
    await cloud.queue.put(frame(STATE))
    with (
        patch("custom_components.iaqualink_tcx.TcxClient", cloud.client),
        patch.object(hass.config_entries, "async_forward_entry_setups", AsyncMock()),
        patch.object(hass.config_entries, "async_unload_platforms", AsyncMock(return_value=True)),
    ):
        assert await async_setup_entry(hass, entry)
        assert cloud.sockets == 1
        assert await async_unload_entry(hass, entry)
        assert entry.runtime_data.closed
        assert cloud.sockets == 0


async def test_disconnect_rest_shadow_is_not_live_and_reconnect(acquisition, cloud):
    c = acquisition
    await cloud.queue.put(ConnectionError("synthetic-drop"))
    await cloud.drain()
    assert not c.equipment_available
    assert not c._shutdown_requested
    c.system.WS_INITIAL_ACK_TIMEOUT_SECS = 0.001
    await c.async_refresh()
    assert not c.equipment_available  # REST succeeds but only has a cached shadow.
    # The pinned engine can reuse its old timestamp across reconnect. Our
    # session-local freshness guard still keeps equipment unavailable.
    c.system._ws_last_update -= 121
    await c.async_refresh()
    assert any(r.url.path.endswith("/shadow") for r in cloud.requests)
    await cloud.queue.put(frame(STATE))
    await cloud.drain()
    await c.async_refresh()
    assert c.equipment_available
    assert cloud.sockets == 1
    assert len(cloud.sent) == 2


async def test_coordinator_safe_errors(acquisition):
    c = acquisition
    with patch.object(c.system, "refresh", side_effect=ValueError("secret-token")):
        with pytest.raises(UpdateFailed, match="Cloud update failed") as exc:
            await c._async_update_data()
    assert "secret" not in str(exc.value)
    assert not c.equipment_available


async def test_shutdown_waits_for_initial_refresh(hass, entry, cloud):
    from custom_components.iaqualink_tcx.coordinator import TcxCoordinator

    client = cloud.client(**CREDENTIALS)
    systems = await discover(client)
    c = TcxCoordinator(hass, entry, client, systems[SERIAL])
    refresh = asyncio.create_task(c.async_refresh())
    await cloud.drain()
    close = asyncio.create_task(c.async_close())
    await cloud.drain()
    assert not close.done()
    await cloud.queue.put(frame(STATE))
    await refresh
    await close
    assert cloud.sockets == 0
    assert client._client is None
    request_count = len(cloud.requests)
    await c.async_refresh()
    assert len(cloud.requests) == request_count
    assert client._client is None


async def test_protocol_logs_are_private_without_hiding_unrelated_traffic(cloud, caplog):
    client = cloud.client(**CREDENTIALS)
    caplog.set_level(logging.DEBUG)
    await discover(client)
    # Cold REST request contains a serial and a signature in its URL.
    await client.send_request(
        "https://prod.zodiac-io.com/devices/v2/PRIVATE-SERIAL/shadow",
        params={"signature": "PRIVATE-SIGNATURE"},
    )
    logging.getLogger("httpx2").info("Unrelated request remains visible")
    for secret in (
        "PRIVATE-SERIAL",
        "PRIVATE-SIGNATURE",
        SERIAL,
        CREDENTIALS["username"],
        CREDENTIALS["password"],
        "fixture-id-token",
        "fixture-auth",
    ):
        assert secret not in caplog.text
    assert "Unrelated request remains visible" in caplog.text
