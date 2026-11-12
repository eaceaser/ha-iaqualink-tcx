# AquaLink TCX for Home Assistant

Read-only cloud monitoring for **Jandy AquaLink TCX** controllers. Continue using
**the iAquaLink app for every equipment write**, including schedules and settings.
This integration exposes only sensors and binary sensors. It provides no equipment
command services or switch, light, climate, fan, number, select, or button entities.

**Status: 0.1.0 release candidate, validated offline; not tested against the owner's
live controller. No GitHub release has been published.**

## Compatibility

- Supported and tested Home Assistant version: **2026.11.0**, Python **3.14.10**.
  Other HA versions have not been validated; HACS declares that version as its minimum.
- Works with the **stock HA container**; no custom image is required.
- TCX only. Other controller types on the account are ignored and their equipment
  is never enumerated or refreshed.
- Requires an iAquaLink account and cloud access; this is not local monitoring.
- **Do not configure the built-in iAquaLink integration in the same HA instance.**
  It pins `iaqualink==0.7.0`, while this integration requires a newer Git revision.
  Both share one Python environment. Removing an integration entry alone does not
  restore its Python package. If changing between integrations, restart HA and
  verify the required dependency was reinstalled; use a separate HA instance for
  simultaneous operation. Using the iAquaLink mobile app alongside TCX monitoring
  does not create this Python dependency conflict.

The manifest pins [`iaqualink-py` commit
`565b93d019077007a88bca57f5b2a253332be929`](https://github.com/flz/iaqualink-py/tree/565b93d019077007a88bca57f5b2a253332be929),
which installs as `0.8.0a1.dev8+g565b93d01`. PyPI `0.7.0` predates TCX support.
HACS installs integration files; **Home Assistant installs manifest requirements**.
The stock image successfully built this immutable Git dependency using its existing
Git/build tools and HA constraints. This integration owns the library's HTTP/WS
clients; it does not inject HA's shared client. HA's `httpx2` compatibility alias
is exercised by the test suite and stock-image smoke test.

## Install and configure

Once these changes are available on the repository's default branch:

1. In HACS, open **Custom repositories**, add
   `https://github.com/eaceaser/ha-iaqualink-tcx`, and choose **Integration**.
2. Download **AquaLink TCX** and restart Home Assistant.
3. Open **Settings → Devices & services → Add integration → AquaLink TCX**.
4. Enter iAquaLink credentials. If the account has several TCX controllers, select
   one. Repeat to monitor another controller. A controller cannot be added twice.

For a local/manual installation, copy `custom_components/iaqualink_tcx` into
`<HA config>/custom_components/iaqualink_tcx` and restart. Use all files from the
same revision. HACS default-catalog registration is not required.

Credentials remain in HA config-entry storage, which is sensitive. No credentials,
tokens, or real cloud payloads belong in source control or bug reports. When HA
prompts for reauthentication, supply an account containing the same controller.

## Supported readings

Entities appear only when corresponding equipment is discovered. Missing or invalid
values are unknown; zero is retained. Synthetic keys below are library device keys,
not claims that the corresponding hardware is installed.

| Source | Read-only entity | Meaning / unit |
| --- | --- | --- |
| `water`, `air`, configured `solar` | Temperature sensor | °C or °F from the controller's unit flag; invalid sensor status is unknown |
| `filt0` | Filter pump state binary sensor | Observed on/off; independent of commanded speed |
| `ecm0` | Pump commanded speed sensor | Percentage normalized between configured minimum and maximum RPM; **not measured RPM** and 0% does not mean off |
| `ecm0` | Pump commanded preset sensor | Named preset matching commanded speed, or unknown when unmatched |
| `ecm0_minSpd`, `ecm0_maxSpd` | Configured minimum/maximum speed sensors | Settings in RPM, **not actual pump speed** |
| `ecm0_prmSpd`, `ecm0_frzSpd` | Configured priming/freeze protection speed sensors | Settings in RPM |
| `ecm0_prmDur` | Configured priming duration sensor | Seconds |
| `TspBdy0` | Heat enabled binary sensor; water target temperature sensor | Enabled is **not active heating**; target is °C/°F |
| `lvh1_enable` | Heater enabled binary sensor | Reported application mode `HEAT` versus `OFF` |
| `lvh1` | Heater reported status sensor | Library mapping: off, standby, heating. Reported tile status, not independently measured firing |
| `auxN` | Auxiliary state binary sensor | Observed relay on/off; stable key used instead of personal equipment label |
| Color-capable `auxN` | Current effect sensor | Library's named current/locked color mapping; unknown for invalid/unobserved color |
| Controller | State stream diagnostic sensor | disconnected, waiting, fresh, stale |
| Controller | Last reported controller status diagnostic sensor | Library status; explicitly a reported value, not proof of live controller reachability |

This release does **not** expose salinity, chlorinator output/boost, measured pump
RPM/power, solar target, freeze setpoint, feature circuits, ZigBee devices, or valves.
No generic device fallback invents telemetry for unknown equipment.

## Updates and availability

The coordinator publishes every **30 seconds**. The library reuses one WebSocket
subscription per selected controller. Recent WS state suppresses REST shadow polls;
a missing/stale stream permits REST fallback. Startup can wait up to **5 seconds**
for the first WS state, and REST operations have a **10-second** timeout. Authentication
may replay a read once. This is honestly classified as **cloud polling**, not an
immediate push integration.

Equipment requires a successful refresh, controller status `CONNECTED` or `ONLINE`,
a connected state stream with a state frame less than **120 seconds** old, and all
required fields observed in the current socket session, including controller status
and a valid service-mode flag. Disconnect, stale stream,
offline/unknown/service/firmware-update status, or refresh failure makes equipment
unavailable. A successful REST shadow fetch alone never makes it live again.
Recovery normally appears on the next 30-second tick. The upstream library retries
a failed subscription on refresh and has no automatic exponential WS backoff.
A stale connected stream may incur the 5-second initial-state wait before REST.
The library can briefly reuse its previous freshness timestamp after reconnect;
the integration's separate session gate still rejects previous-session readings.

Partial stream updates preserve prior fields in the same session; newly appearing
equipment is added without a reload. A fresh frame proves recent cloud traffic,
**not that every field was physically sampled recently**: the library exposes no
per-field measurement timestamp. The conservative gate may hide usable readings
when the cloud sends no state frames for two minutes. Diagnostics remain available.

## Upgrade, remove, and troubleshoot

For upgrades, back up HA, update through HACS (or replace the entire integration
folder), then restart. Stable entity IDs use controller serial plus equipment key
and reading suffix; edits to app labels do not rename identities. Review compatibility
notes before upgrading HA or this pinned library.

To remove, delete each AquaLink TCX entry in Devices & services, remove the HACS
repository/integration (or integration folder), then restart HA. Unload closes
subscriptions and owned clients. Removal changes no controller settings.

Invalid login prompts for reauthentication. Cloud/setup failures retry through HA.
No TCX on the account produces a clear setup message. For unavailable readings,
check the two connection diagnostics and cloud/app connectivity. Service mode is
intentionally unavailable. Do not enable the built-in integration to troubleshoot.

Download diagnostics from the integration entry. Diagnostics are an allowlist of
status flags, timing constants, and class counts; no credentials, serials, labels,
account data, or raw shadows are included. Library protocol log messages are
suppressed because upstream redaction is incomplete. Transport messages are
suppressed only during this integration's owned I/O; unrelated transport logs
remain visible. HA still stores the controller identifier and credentials locally.
Do not post HA's full config-entry storage or unreviewed global logs.

## Development and validation

Use Python 3.14 and an isolated environment:

```sh
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -r requirements-dev.txt
.venv/bin/ruff check custom_components tests scripts
.venv/bin/ruff format --check custom_components tests scripts
.venv/bin/python -m pytest -q
```

Tests use synthetic data and mocked HTTP/WS transports; no live account is needed.
See [validation instructions and results](docs/validation.md) for stock-image
installation/load checks, validator limitations, and milestone review records.
See [architecture](docs/architecture.md) for the acquisition/presentation boundary.

Future controls require a separate implementation and review milestone: verify
upstream payloads, permissions, asynchronous failures and live readback, then design
explicitly authorized power/speed, heat, and light controls. None is implemented here.

## License

Apache-2.0. This integration is a dedicated implementation using public HA patterns,
not a compatibility fork or copied core integration. The external
[`iaqualink-py`](https://github.com/flz/iaqualink-py) library retains its BSD-3-Clause
license. Brand art is original repository artwork, not an official Jandy mark.
