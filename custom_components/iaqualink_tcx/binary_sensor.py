"""Observed equipment states, without any control methods."""

from homeassistant.components.binary_sensor import BinarySensorEntity

from .entity import TcxEntity, setup_readings


async def async_setup_entry(hass, entry, async_add_entities):
    setup_readings(entry, async_add_entities, TcxBinarySensor, binary=True)


class TcxBinarySensor(TcxEntity, BinarySensorEntity):
    @property
    def is_on(self):
        return self.reading_value()
