# AquaLink TCX for Home Assistant

A planned HACS custom integration for Jandy AquaLink TCX controllers using the
iAquaLink cloud and the upstream [`iaqualink-py`](https://github.com/flz/iaqualink-py)
library.

**Status:** project kickoff. No installable integration is available yet.

The first release will be **read-only**. Continue using the iAquaLink app for
equipment control, schedules, and configuration.

## Initial target

- Account setup and TCX controller selection.
- Read-only equipment state and telemetry, including temperatures, pump state
  and available speed readings, heater state and setpoints, and light/auxiliary
  state where exposed by the library and installed hardware.
- Connection status, unavailable/unknown handling, reconnect behavior, and
  redacted diagnostics.
- HACS installation from this repository, using the stock Home Assistant image.
- A pinned upstream library revision containing TCX support.

No switches, climate controls, writable numbers, or equipment command services
will be exposed in the first release. Cloud authentication, subscriptions, and
read requests are still required. This is a cloud integration, not local control.

## Future targets

Pump speed/preset control, pump power, heater control and temperature setpoints,
and light/auxiliary controls. These will be implemented and validated separately
after read-only monitoring works reliably.

## Approach

Use a dedicated `iaqualink_tcx` integration domain. Reuse appropriate Home
Assistant integration patterns while implementing adapters against the current
TCX library interfaces. Leave authentication, protocol parsing, and WebSocket
transport in the upstream library.

Reference implementation:
[Home Assistant's built-in iAquaLink integration](https://github.com/home-assistant/core/tree/dev/homeassistant/components/iaqualink).

Upstream tracking:

- [TCX feature request #38](https://github.com/flz/iaqualink-py/issues/38)
- [TCX implementation PR #248](https://github.com/flz/iaqualink-py/pull/248)
- [TCX announcements and testing discussion #266](https://github.com/flz/iaqualink-py/discussions/266)

## License

Apache-2.0. Retain applicable attribution and license notices when adapting
upstream code. The upstream library retains its own license.
