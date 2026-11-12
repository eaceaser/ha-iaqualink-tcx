# Architecture

`TcxClient` owns upstream HTTP and WS transports. `discover()` performs authentication
and account controller metadata discovery, then filters by `TcxSystem`. It never
calls `get_devices()` or refreshes unrelated systems. Config flows close their
short-lived client in `finally` before presenting controller selection. Reauth
requires the original serial. Only HA config entries persist runtime credentials.

`TcxCoordinator` owns the selected system and a 30-second `refresh()` cycle. The
upstream engine owns subscription reuse, parsing, REST fallback and token refresh.
An I/O lock makes shutdown wait for active refresh, then closes the client and its
registered subscriptions. Later refreshes skip I/O. Platform listeners are registered
with entry unload callbacks, and known reading identities prevent duplicate entities.
HA's shutdown event additionally closes the owned transports.

The library lacks a public consumer freshness API. Instead of monkeypatching WS
internals, the client overrides public `ws_connect()` to observe connection lifetime
and uses public `ws_capture_hook` to observe state arrival and field presence. It
recognizes the two reported-state envelopes accepted by the pinned library but
retains **no payload values**. Values and status parsing remain upstream. Freshness
is session-local, measured with a monotonic clock, and rejects disconnected cached
REST shadows. Controller status and a valid service-mode flag must also be observed in the current
session, so a reconnect delta cannot promote an old cached status. Reading fields
must appear in this session; partial updates preserve
previous presence. Temperature additionally requires a valid observed unit flag.
This small metadata adapter is isolated in `client.py`; it is not a second protocol
client. A public upstream health/presence API could eventually replace it.

`readings.py` provides an explicit inventory of safe public getters and source-field
dependencies. Entities never call network operations or setters. Sensor/binary
sensor platforms listen to the coordinator and add late readings dynamically. Raw
shadow parsing is not scattered through entities. Small public device views avoid
two upstream in-place-upsert limitations: late light type metadata and null values
on synthetic pump-number devices. Those constructors only assign system/data;
getters remain the library's implementation. Unknown device types are omitted.

Guardrails reject `send_ws_frame()` entirely and REST verbs except GET or auth POST
to the exact upstream login/refresh URLs. These guards supplement reachable-call-path
review and mocked-transport traffic assertions. Subscription frames sent by the
upstream receive engine remain allowed. There is no speculative write infrastructure.

Diagnostics use an allowlist. Upstream logs are reduced to a generic message;
`ContextVar`-scoped transport suppression handles HTTPX/HTTPCore, including HA's
`httpx2`/`httpcore2` aliases and inherited WS task contexts, without suppressing
unrelated HA traffic. Filters are idempotent and contain no credentials or client
references. Integration exceptions contain only fixed safe text. Cancellation is
not converted into setup or communication failure.
