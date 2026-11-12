"""Read-only AquaLink TCX monitoring."""

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME, EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from iaqualink.exception import AqualinkServiceUnauthorizedException

from .client import TcxClient, discover
from .const import CONF_SERIAL
from .coordinator import TcxCoordinator

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR]


async def async_setup_entry(hass, entry):
    client = TcxClient(entry.data[CONF_USERNAME], entry.data[CONF_PASSWORD])
    try:
        systems = await discover(client)
        system = systems.get(entry.data[CONF_SERIAL])
        if system is None:
            raise ConfigEntryNotReady("Selected TCX controller was not found")
        coordinator = TcxCoordinator(hass, entry, client, system)
        await coordinator.async_config_entry_first_refresh()
        entry.runtime_data = coordinator
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException as exc:
        await client.close()
        if isinstance(exc, AqualinkServiceUnauthorizedException):
            raise ConfigEntryAuthFailed("Cloud authentication failed") from None
        if isinstance(exc, (ConfigEntryAuthFailed, ConfigEntryNotReady)):
            raise
        if isinstance(exc, Exception):
            raise ConfigEntryNotReady("Unable to connect to AquaLink cloud") from None
        raise
    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, coordinator.async_close)
    )
    return True


async def async_unload_entry(hass, entry):
    if await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_close()
        return True
    return False
