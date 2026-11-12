"""Explicit read-only presentation of the pinned library's public device APIs."""

import math
import re
from dataclasses import dataclass
from typing import Callable

from iaqualink.systems.tcx.device import (
    TcxAuxLight,
    TcxAuxSwitch,
    TcxClimate,
    TcxFilterPump,
    TcxHeaterEnableSwitch,
    TcxHeaterStatusSensor,
    TcxVariableSpeedPump,
)


@dataclass(frozen=True)
class Reading:
    key: str
    suffix: str
    name: str
    getter: Callable
    fields: tuple[str, ...]
    source: str | None = None
    kind: str = "text"
    unit: str | None = None

    @property
    def identity(self):
        return f"{self.key}_{self.suffix}"

    def value(self, system):
        try:
            device = system.devices[self.key]
            source_device = system.devices.get(self.source, device)
            numeric_fields = {
                "value",
                "waterTempSet",
                "cmdSpd",
                "minSpd",
                "maxSpd",
                "prmSpd",
                "frzSpd",
                "prmDur",
            }
            if self.kind in ("temperature", "number") and any(
                isinstance(source_device.data.get(field), bool)
                for field in self.fields
                if field in numeric_fields
            ):
                return None
            value = self.getter(device)
            if self.kind in ("temperature", "number"):
                if value is None or value == "" or isinstance(value, bool):
                    return None
                number = float(value)
                return number if math.isfinite(number) else None
            return value if not isinstance(value, str) or len(value) <= 255 else None
        except (KeyError, ValueError, TypeError, OverflowError, AttributeError, IndexError):
            return None

    def observed(self, client, system):
        required = self.fields
        if self.suffix == "effect":
            color = "lockClr" if system.devices[self.key].data.get("statClr") == 6 else "currClr"
            required = (*required, color)
        fields = client.observed_fields.get(self.source or self.key, set())
        return all(field in fields for field in required) and (
            self.kind != "temperature" or "tempSetting" in client.observed_fields
        )


def _state(device):
    # Upstream is_on maps missing and arbitrary values to False. Only explicit
    # binary source values are valid observations; missing means unknown.
    raw = device.data.get("st")
    return device.is_on if type(raw) in (bool, int) and raw in (0, 1) else None


def _heat_enabled(device):
    raw = device.data.get("heatEnabled")
    return device.is_on if type(raw) in (bool, int) and raw in (0, 1) else None


def _heater_enabled(device):
    return device.is_on if device.data.get("app") in ("HEAT", "OFF") else None


def _heater_status(device):
    raw = device.data.get("en")
    return device.value if type(raw) is int and raw >= 0 else None


def _percentage(device):
    raw = [device.data.get(k) for k in ("cmdSpd", "minSpd", "maxSpd")]
    if any(isinstance(v, bool) or v is None for v in raw):
        return None
    cmd, low, high = map(float, raw)
    if not all(math.isfinite(v) for v in (cmd, low, high)) or cmd < 0 or low < 0 or high <= low:
        return None
    return device.percentage


def inventory(system):
    """Discover explicit known readings; no generic fallback or controls."""
    for key, device in list(system.devices.items()):
        if key in ("water", "air", "solar"):
            yield Reading(
                key,
                "temperature",
                f"{key.title()} temperature",
                lambda d: d.value,
                ("value",) if key == "air" else ("value", "us"),
                kind="temperature",
            )
        elif isinstance(device, (TcxFilterPump, TcxAuxSwitch, TcxAuxLight)):
            yield Reading(key, "state", f"{key.upper()} state", _state, ("st",), kind="binary")
            if isinstance(device, TcxAuxLight) or device.data.get("et") in (
                "JL",
                "IB",
                "PSS",
                "HU",
            ):
                yield Reading(
                    key,
                    "effect",
                    f"{key.upper()} effect",
                    lambda d: TcxAuxLight(d.system, d.data).effect,
                    ("et", "statClr"),
                )
        elif isinstance(device, TcxClimate):
            yield Reading(
                key, "enabled", "Heat enabled", _heat_enabled, ("heatEnabled",), kind="binary"
            )
            yield Reading(
                key,
                "target",
                "Water target temperature",
                lambda d: d.target_temperature,
                ("waterTempSet",),
                kind="temperature",
            )
        elif isinstance(device, TcxHeaterStatusSensor):
            yield Reading(key, "status", "Heater reported status", _heater_status, ("en",))
        elif isinstance(device, TcxHeaterEnableSwitch):
            yield Reading(
                key,
                "enabled",
                "Heater enabled",
                _heater_enabled,
                ("app",),
                source="lvh1",
                kind="binary",
            )
        elif isinstance(device, TcxVariableSpeedPump):
            yield Reading(
                key,
                "percentage",
                "Pump commanded speed",
                _percentage,
                ("cmdSpd", "minSpd", "maxSpd"),
                kind="number",
                unit="%",
            )
            yield Reading(
                key,
                "preset",
                "Pump commanded preset",
                lambda d: d.preset_mode,
                ("cmdSpd", "spdList"),
            )
        # Expose installed, public numeric settings as sensors. These are
        # configured values, never measured RPM or inferred power.
        elif re.fullmatch(r"ecm0_(minSpd|maxSpd|prmSpd|frzSpd|prmDur)", key):
            labels = {
                "minSpd": "minimum speed",
                "maxSpd": "maximum speed",
                "prmSpd": "priming speed",
                "frzSpd": "freeze protection speed",
                "prmDur": "priming duration",
            }
            field = key.split("_", 1)[1]
            yield Reading(
                key,
                "configured",
                f"Pump configured {labels[field]}",
                lambda d: type(d)(d.system, d.system.devices["ecm0"].data).current_value,
                (field,),
                source="ecm0",
                kind="number",
                unit=device.unit_of_measurement,
            )
