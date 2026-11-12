"""Single polling owner per selected TCX controller."""

import asyncio
import logging
from datetime import timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from iaqualink.exception import AqualinkServiceUnauthorizedException
from iaqualink.system import SystemStatus

from .const import DOMAIN, UPDATE_SECONDS

LOGGER = logging.getLogger(__name__)


class TcxCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, client, system):
        super().__init__(
            hass,
            LOGGER,
            name=DOMAIN,
            config_entry=entry,
            update_interval=timedelta(seconds=UPDATE_SECONDS),
        )
        self.client = client
        self.system = system
        self._io_lock = asyncio.Lock()
        self.closed = False
        self.refresh_ok = False

    @property
    def equipment_available(self):
        return (
            self.refresh_ok
            and self.last_update_success
            and self.client.stream_fresh
            and self.system.status in (SystemStatus.CONNECTED, SystemStatus.ONLINE)
        )

    async def _async_update_data(self):
        async with self._io_lock:
            if self.closed:
                return None
            return await self._refresh()

    async def _refresh(self):
        try:
            await self.system.refresh()
        except AqualinkServiceUnauthorizedException:
            self.refresh_ok = False
            raise ConfigEntryAuthFailed("Cloud authentication failed") from None
        except Exception:
            # Do not forward upstream exceptions: messages/tracebacks may
            # contain URLs, serials or raw response bodies.
            self.refresh_ok = False
            raise UpdateFailed("Cloud update failed") from None
        self.refresh_ok = True
        return None  # Devices are upserted in place; always publish each tick.

    async def async_close(self, event=None):
        if not self.closed:
            self.closed = True
            await self.async_shutdown()
            async with self._io_lock:
                await self.client.close()
