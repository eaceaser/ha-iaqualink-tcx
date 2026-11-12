"""Strict allowlist: no entry data, identifiers, labels or cloud payloads."""

from collections import Counter

from .const import QUIET_SECONDS, UPDATE_SECONDS


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    return {
        "controller_type": "tcx",
        "reported_status": coordinator.system.status.name.lower(),
        "stream_connected": coordinator.client.stream_connected,
        "stream_fresh": coordinator.client.stream_fresh,
        "stream_active": coordinator.client.stream_active,
        "refresh_success": coordinator.refresh_ok,
        "equipment_available": coordinator.equipment_available,
        "update_interval_seconds": UPDATE_SECONDS,
        "stream_quiet_after_seconds": QUIET_SECONDS,
        "stream_keepalive_interval_seconds": coordinator.system.WS_KEEPALIVE_SECS,
        "equipment_types": dict(
            Counter(type(d).__name__ for d in coordinator.system.devices.values())
        ),
    }
