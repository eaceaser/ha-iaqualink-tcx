import json
import time

import pytest
from iaqualink.system import SystemStatus

from custom_components.iaqualink_tcx.binary_sensor import TcxBinarySensor
from custom_components.iaqualink_tcx.diagnostics import async_get_config_entry_diagnostics
from custom_components.iaqualink_tcx.entity import setup_readings
from custom_components.iaqualink_tcx.readings import inventory
from custom_components.iaqualink_tcx.sensor import TcxDiagnostic, TcxSensor
from tests.conftest import frame


def entities(c):
    return {
        r.identity: (TcxBinarySensor if r.kind == "binary" else TcxSensor)(c, r)
        for r in inventory(c.system)
    }


async def push(c, cloud, state, service="StateStreamer"):
    await cloud.queue.put(frame(state, service))
    await cloud.drain()
    await c.async_refresh()


async def test_measurements_zero_and_heat_distinctions(acquisition):
    items = entities(acquisition)
    assert items["water_temperature"].native_value == 0.0
    assert items["water_temperature"].native_unit_of_measurement == "°C"
    assert items["air_temperature"].native_value == 20
    assert items["filt0_state"].is_on is False
    assert items["TspBdy0_enabled"].is_on is True
    assert items["TspBdy0_target"].native_value == 28
    assert items["lvh1_status"].native_value == "standby"
    assert items["lvh1_enable_enabled"].is_on is True
    assert items["ecm0_percentage"].native_value == 0
    assert items["ecm0_preset"].native_value == "Low"
    assert items["ecm0_minSpd_configured"].native_value == 600
    assert items["ecm0_minSpd_configured"].native_unit_of_measurement == "rpm"
    assert items["water_temperature"].unique_id == "synthetic-tcx-001_water_temperature"
    # No inference that 0% means pump off or that heat enable means firing.
    assert "running" not in items


@pytest.mark.parametrize("reading", [None, "", "bad", "NaN", "inf", True])
async def test_invalid_temperatures_are_unknown(acquisition, cloud, reading):
    await push(acquisition, cloud, {"water": {"value": reading}})
    assert entities(acquisition)["water_temperature"].native_value is None


async def test_invalid_status_and_binary_values(acquisition, cloud):
    await push(
        acquisition,
        cloud,
        {
            "water": {"us": 2},
            "filt0": {"st": None},
            "TspBdy0": {"heatEnabled": "false"},
            "lvh1": {"en": -1},
        },
    )
    items = entities(acquisition)
    assert items["water_temperature"].native_value is None
    assert items["filt0_state"].is_on is None
    assert items["TspBdy0_enabled"].is_on is None
    assert items["lvh1_status"].native_value is None


@pytest.mark.parametrize("status", list(SystemStatus))
async def test_controller_availability_policy(acquisition, status):
    acquisition.system.status = status
    expected = status in (SystemStatus.CONNECTED, SystemStatus.ONLINE)
    assert entities(acquisition)["water_temperature"].available is expected
    assert TcxDiagnostic(acquisition, "controller").available
    assert TcxDiagnostic(acquisition, "stream").available


async def test_stale_disconnect_and_unobserved_session_fields(acquisition):
    item = entities(acquisition)["water_temperature"]
    acquisition.client.last_state = time.monotonic() - 121
    assert not item.available
    assert item.native_value is None
    assert TcxDiagnostic(acquisition, "stream").native_value == "stale"
    acquisition.client.last_state = time.monotonic()
    acquisition.client.stream_connected = False
    assert not item.available
    acquisition.client.stream_connected = True
    acquisition.client.observed_fields.clear()
    # Existing library objects must not smuggle previous-session values back.
    assert not item.available


async def test_dynamic_discovery_and_partial_updates(acquisition, entry, cloud):
    entry.runtime_data = acquisition
    added = []
    setup_readings(entry, added.extend, TcxBinarySensor, binary=True)
    original = len(added)
    await push(acquisition, cloud, {"aux2": {"st": 1}})
    assert len(added) == original + 1
    aux = next(x for x in added if x.reading.key == "aux2")
    assert aux.is_on is True
    await push(acquisition, cloud, {"air": {"value": 210}})
    assert len(added) == original + 1
    assert aux.is_on is True
    assert entities(acquisition)["air_temperature"].native_value == 21
    await acquisition.async_refresh()
    assert len({e.unique_id for e in added}) == len(added)


async def test_late_light_and_heating_status(acquisition, cloud):
    await push(
        acquisition,
        cloud,
        {"aux1": {"et": "JL", "st": 1, "currClr": 1, "statClr": 0}, "lvh1": {"en": 6}},
    )
    items = entities(acquisition)
    assert items["aux1_state"].is_on is True
    assert items["aux1_effect"].native_value == "Alpine White"
    assert items["lvh1_status"].native_value == "heating"


async def test_redacted_diagnostics(acquisition, entry, hass):
    entry.runtime_data = acquisition
    data = await async_get_config_entry_diagnostics(hass, entry)
    text = json.dumps(data)
    for secret in ("synthetic", "fixture", "username", "password", "serial", "token", "payload"):
        assert secret not in text
    assert data["equipment_available"]
    assert data["controller_type"] == "tcx"


async def test_no_writable_platforms_or_services(acquisition, cloud):
    from custom_components.iaqualink_tcx import PLATFORMS

    assert {p.value for p in PLATFORMS} == {"sensor", "binary_sensor"}
    for entity in entities(acquisition).values():
        assert not any(
            hasattr(entity, method)
            for method in (
                "async_turn_on",
                "async_turn_off",
                "async_set_temperature",
                "async_set_native_value",
            )
        )
    before = len(cloud.sent)
    for entity in entities(acquisition).values():
        _ = entity.available
        _ = entity.is_on if isinstance(entity, TcxBinarySensor) else entity.native_value
    assert len(cloud.sent) == before
