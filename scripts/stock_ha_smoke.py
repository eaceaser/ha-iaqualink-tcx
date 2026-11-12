"""Offline entry/platform lifecycle smoke test; run inside stock HA 2026.11.0.

All vendor HTTP and WS traffic is replaced at the transport boundary. Credentials,
serials and telemetry are synthetic. Never takes account arguments.
"""

import asyncio
import logging
import shutil
import tempfile
from pathlib import Path
from unittest.mock import patch

from homeassistant import bootstrap, config_entries, loader
from homeassistant.core import HomeAssistant

from tests.conftest import CREDENTIALS, STATE, Cloud, frame

SOURCE = Path(__file__).resolve().parents[1]


async def main():
    with tempfile.TemporaryDirectory(prefix="tcx-offline-") as directory:
        shutil.copytree(
            SOURCE / "custom_components",
            Path(directory) / "custom_components",
            ignore=shutil.ignore_patterns("__pycache__"),
        )
        hass = HomeAssistant(directory)
        loader.async_setup(hass)
        loader.async_mount_config_dir(hass)
        hass.config_entries = config_entries.ConfigEntries(hass, {})
        assert await bootstrap.async_load_base_functionality(hass)
        cloud = Cloud()
        # Import only after HA has installed transport aliases and mounted custom code.
        with (
            patch("iaqualink.client.aconnect_ws", cloud.connect),
            patch("custom_components.iaqualink_tcx.TcxClient", cloud.client),
            patch("custom_components.iaqualink_tcx.config_flow.TcxClient", cloud.client),
            patch(
                "socket.socket.connect", side_effect=AssertionError("Offline test blocked network")
            ),
            patch(
                "socket.socket.connect_ex",
                side_effect=AssertionError("Offline test blocked network"),
            ),
        ):
            try:
                await cloud.queue.put(frame(STATE))
                flow = await hass.config_entries.flow.async_init(
                    "iaqualink_tcx", context={"source": "user"}
                )
                assert flow["step_id"] == "user"
                result = await hass.config_entries.flow.async_configure(
                    flow["flow_id"], CREDENTIALS
                )
                assert result["type"] == "create_entry", result
                entry = result["result"]
                await hass.async_block_till_done()
                assert entry.state is config_entries.ConfigEntryState.LOADED, entry.state
                states = hass.states.async_all()
                assert states and all(s.domain in ("sensor", "binary_sensor") for s in states)
                water = next(s for s in states if s.entity_id.endswith("water_temperature"))
                assert water.state == "0.0", water
                count = len(states)
                duplicate = await hass.config_entries.flow.async_init(
                    "iaqualink_tcx", context={"source": "user"}
                )
                result = await hass.config_entries.flow.async_configure(
                    duplicate["flow_id"], CREDENTIALS
                )
                assert result["reason"] == "already_configured", result
                reauth = await hass.config_entries.flow.async_init(
                    "iaqualink_tcx",
                    context={"source": "reauth", "entry_id": entry.entry_id},
                    data=dict(entry.data),
                )
                assert reauth["step_id"] == "reauth_confirm", reauth
                await cloud.queue.put(frame(STATE))
                result = await hass.config_entries.flow.async_configure(
                    reauth["flow_id"], CREDENTIALS
                )
                assert result["reason"] == "reauth_successful", result
                await hass.async_block_till_done()
                assert cloud.sockets == 1
                await cloud.queue.put(frame({"aux2": {"st": 1}}, "StateStreamer"))
                await cloud.drain()
                await entry.runtime_data.async_refresh()
                await hass.async_block_till_done()
                assert len(hass.states.async_all()) == count + 1
                assert not hass.services.async_services().get("iaqualink_tcx")
                await hass.config_entries.async_unload(entry.entry_id)
                await hass.async_block_till_done()
                assert cloud.sockets == 0
                assert all(c._client is None for c in cloud.clients)
                await cloud.queue.put(frame(STATE))
                assert await hass.config_entries.async_setup(entry.entry_id)
                await hass.async_block_till_done()
                assert (
                    len(hass.states.async_all()) == count + 1
                )  # Registry retains late aux, unavailable.
                assert cloud.sockets == 1
                await hass.async_stop(force=True)
                assert cloud.sockets == 0
                assert all(c._client is None for c in cloud.clients)
                print(
                    f"PASS: stock HA setup, {count} initial entities, "
                    "late discovery, unload, reload, shutdown"
                )
            finally:
                await hass.async_stop(force=True)
                for client in cloud.clients:
                    await client.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    asyncio.run(main())
