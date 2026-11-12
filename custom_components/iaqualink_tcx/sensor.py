"""Read-only TCX measurements, settings and connection diagnostics."""

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfTemperature

from .entity import TcxEntity, setup_readings


async def async_setup_entry(hass, entry, async_add_entities):
    setup_readings(entry, async_add_entities, TcxSensor, binary=False)
    async_add_entities(
        [TcxDiagnostic(entry.runtime_data, kind) for kind in ("stream", "controller")]
    )


class TcxSensor(TcxEntity, SensorEntity):
    def __init__(self, coordinator, reading):
        super().__init__(coordinator, reading)
        if reading.kind == "temperature":
            self._attr_device_class = SensorDeviceClass.TEMPERATURE
            if reading.key in ("water", "air", "solar"):
                self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def native_unit_of_measurement(self):
        if self.reading.kind == "temperature":
            return (
                UnitOfTemperature.CELSIUS
                if self.coordinator.system.temp_unit == "C"
                else UnitOfTemperature.FAHRENHEIT
            )
        return self.reading.unit

    @property
    def native_value(self):
        return self.reading_value()


class TcxDiagnostic(TcxEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, kind):
        super().__init__(coordinator)
        self.kind = kind
        self._attr_unique_id = f"{coordinator.system.serial}_{kind}"
        self._attr_name = "State stream" if kind == "stream" else "Last reported controller status"

    @property
    def available(self):
        return True

    @property
    def native_value(self):
        if self.kind == "controller":
            return self.coordinator.system.status.name.lower()
        client = self.coordinator.client
        if not client.stream_connected:
            return "disconnected"
        if client.last_state is None:
            return "waiting"
        return "fresh" if client.stream_fresh else "stale"
