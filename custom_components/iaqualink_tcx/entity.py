"""Shared read-only entity lifecycle and dynamic inventory."""

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .readings import inventory


def setup_readings(entry, async_add_entities, entity_type, binary):
    coordinator = entry.runtime_data
    known = set()

    def discover():
        entities = []
        for reading in inventory(coordinator.system):
            if (reading.kind == "binary") != binary or reading.identity in known:
                continue
            known.add(reading.identity)
            entities.append(entity_type(coordinator, reading))
        if entities:
            async_add_entities(entities)

    entry.async_on_unload(coordinator.async_add_listener(discover))
    discover()


class TcxEntity(CoordinatorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, reading=None):
        super().__init__(coordinator)
        self.reading = reading
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.system.serial)},
            name="AquaLink TCX",
            manufacturer="Jandy",
            model="AquaLink TCX",
        )
        if reading is not None:
            self._attr_unique_id = f"{coordinator.system.serial}_{reading.identity}"
            self._attr_name = reading.name

    @property
    def available(self):
        return self.coordinator.equipment_available and self.reading.observed(
            self.coordinator.client
        )

    def reading_value(self):
        return self.reading.value(self.coordinator.system) if self.available else None
