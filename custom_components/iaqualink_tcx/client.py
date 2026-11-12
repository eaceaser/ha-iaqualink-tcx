"""Owned upstream transport; observe connection health without replacing its engine.

Only protocol metadata (field presence and arrival time) is retained by the capture
hook. Upstream remains responsible for authentication, framing and value parsing.
"""

import logging
import time
from contextlib import asynccontextmanager
from contextvars import ContextVar

from iaqualink.client import AqualinkClient
from iaqualink.systems.tcx.system import TcxSystem

from .const import STALE_SECONDS

_VENDOR_IO = ContextVar("tcx_vendor_io", default=False)


class _PrivacyFilter(logging.Filter):
    def filter(self, record):
        if not record.name.startswith("iaqualink") and not _VENDOR_IO.get():
            return True
        # Upstream redaction is partial: labels, raw bodies and exception URLs
        # can escape. Never forward its text, even with debug logging enabled.
        record.msg = "AquaLink protocol log suppressed for privacy"
        record.args = ()
        record.exc_info = None
        record.exc_text = None
        record.stack_info = None
        return True


def protect_library_logs():
    """Apply once to upstream loggers (all are imported by AqualinkClient)."""
    for name in list(logging.Logger.manager.loggerDict):
        if name.split(".")[0] in (
            "iaqualink",
            "httpx",
            "httpx2",
            "httpcore",
            "httpcore2",
            "httpx_ws",
        ):
            logger = logging.getLogger(name)
            if not any(isinstance(f, _PrivacyFilter) for f in logger.filters):
                logger.addFilter(_PrivacyFilter())


class TcxClient(AqualinkClient):
    """Own REST/WS clients and retain only stream-health metadata."""

    def __init__(self, username, password):
        protect_library_logs()
        super().__init__(username, password, ws_capture_hook=self._observe)
        self.stream_connected = False
        self.last_state = None
        self.observed_fields: dict[str, set[str]] = {}

    @property
    def stream_fresh(self):
        return (
            self.stream_connected
            and self.last_state is not None
            and time.monotonic() - self.last_state < STALE_SECONDS
        )

    @asynccontextmanager
    async def ws_connect(self, url, **kwargs):
        token = _VENDOR_IO.set(True)
        self.last_state = None
        self.observed_fields.clear()
        try:
            async with super().ws_connect(url, **kwargs) as ws:
                self.stream_connected = True
                yield ws
        finally:
            self.stream_connected = False
            _VENDOR_IO.reset(token)

    async def _observe(self, direction, url, frame):
        if direction != "receive" or not isinstance(frame, dict):
            return
        if frame.get("service") not in (
            "Authorization",
            "StateStreamer",
            "DataStreamer",
            "EventStreamer",
        ):
            return
        payload = frame.get("payload")
        if not isinstance(payload, dict):
            return
        # Inspect presence only. Accept precisely the two envelopes supported
        # by the pinned TCX library. Never store raw cloud data here.
        reported = (payload.get("state") or {}).get("reported")
        trees = (
            [reported]
            if isinstance(reported, dict) and reported
            else [
                (v.get("state") or {}).get("reported")
                for v in payload.values()
                if isinstance(v, dict)
            ]
        )
        changed = False
        for tree in trees:
            if not isinstance(tree, dict) or not tree:
                continue
            changed = True
            for key, value in tree.items():
                if key == "systemMode" and (type(value) is not int or value < 0):
                    self.observed_fields.pop(key, None)
                    continue
                if key == "tempSetting" and (type(value) is not int or value not in (0, 1)):
                    self.observed_fields.pop(key, None)
                    continue
                self.observed_fields.setdefault(key, set()).update(
                    value if isinstance(value, dict) else {"__scalar"}
                )
        if changed:
            self.last_state = time.monotonic()

    async def send_ws_frame(self, *args, **kwargs):
        """Fail closed if an accidental equipment command reaches transport."""
        raise RuntimeError("Equipment commands are disabled")

    async def send_request(self, url, method="get", **kwargs):
        # Auth POSTs and discovery/shadow GETs are the only REST operations
        # reachable in phase one. No desired-state POST/PUT/PATCH is allowed.
        from iaqualink.const import AQUALINK_LOGIN_URL, AQUALINK_REFRESH_URL

        if method.lower() != "get" and not (
            method.lower() == "post" and url in (AQUALINK_LOGIN_URL, AQUALINK_REFRESH_URL)
        ):
            raise RuntimeError("Equipment requests are disabled")
        token = _VENDOR_IO.set(True)
        try:
            return await super().send_request(url, method, **kwargs)
        finally:
            _VENDOR_IO.reset(token)


async def discover(client):
    """Discover controller metadata only; never fetch unrelated equipment."""
    await client.login()
    return {
        serial: system
        for serial, system in (await client.get_systems()).items()
        if isinstance(system, TcxSystem)
    }
