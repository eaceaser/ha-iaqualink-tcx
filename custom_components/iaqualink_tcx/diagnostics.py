"""Strict allowlist: no entry data, identifiers, labels or cloud payloads."""

from collections import Counter

from .const import STALE_SECONDS, UPDATE_SECONDS


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {
        "controller_type": "tcx",
        "reported_status": coordinator.system.status.name.lower(),
        "stream_connected": coordinator.client.stream_connected,
        "stream_fresh": coordinator.client.stream_fresh,
        "refresh_success": coordinator.refresh_ok,
        "equipment_available": coordinator.equipment_available,
        "update_interval_seconds": UPDATE_SECONDS,
        "stream_stale_after_seconds": STALE_SECONDS,
        "equipment_types": dict(
            Counter(type(d).__name__ for d in coordinator.system.devices.values())
        ),
    }
