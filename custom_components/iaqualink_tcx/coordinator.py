"""Single polling owner per selected TCX controller."""

import asyncio
import logging
from datetime import timedelta

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from iaqualink.exception import AqualinkServiceUnauthorizedException
from iaqualink.system import SystemStatus

from .client import ShadowSuperseded
from .const import DOMAIN, QUIET_SECONDS, UPDATE_SECONDS

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
            not self.closed
            and self.refresh_ok
            and self.last_update_success
            and self.client.stream_active
            and "status" in self.client.observed_fields.get("aws", set())
            and "systemMode" in self.client.observed_fields
            and self.system.status in (SystemStatus.CONNECTED, SystemStatus.ONLINE)
        )

    async def _async_update_data(self):
        async with self._io_lock:
            if self.closed:
                return None
            return await self._refresh()

    async def _refresh(self):
        try:
            # TCX sends changes, not periodic state samples. Once THIS session
            # has state, retain it while upstream's WS ping/pong watchdog keeps
            # the socket alive. Otherwise an idle connection's REST fallback
            # can replace live session data with an older cloud shadow.
            # This is the upstream engine's public freshness-policy setting;
            # leave its bootstrap/reconnect fallback in place without state.
            self.system.WS_STATE_FRESH_SECS = (
                float("inf") if self.client.stream_active else QUIET_SECONDS
            )
            try:
                await self.system.refresh()
            except ShadowSuperseded:
                # The response was discarded before upstream parsed it. One
                # bounded retry re-derives status from the live WS cache; the
                # active-session gate skips REST and reuses the subscription.
                self.system.WS_STATE_FRESH_SECS = (
                    float("inf") if self.client.stream_active else QUIET_SECONDS
                )
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
