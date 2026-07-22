"""Capteurs Boks : batterie, RSSI, versions."""
from __future__ import annotations

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, EntityCategory, SIGNAL_STRENGTH_DECIBELS_MILLIWATT
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import BoksLink
from .entity import BoksEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Ajoute les capteurs."""
    link: BoksLink = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        [
            BoksBatterySensor(link),
            BoksRssiSensor(link),
            BoksVersionSensor(link, "firmware", "Firmware"),
            BoksVersionSensor(link, "software", "Software"),
        ]
    )


class BoksBatterySensor(BoksEntity, SensorEntity):
    """Niveau de batterie (poussé par la Boks, lu à la connexion)."""

    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, link: BoksLink) -> None:
        super().__init__(link, "battery")
        self._attr_name = "Batterie"

    @property
    def native_value(self) -> int | None:
        return self._link.state.battery


class BoksRssiSensor(BoksEntity, SensorEntity):
    """Puissance du signal reçu, relevée sur les advertisements."""

    _attr_device_class = SensorDeviceClass.SIGNAL_STRENGTH
    _attr_native_unit_of_measurement = SIGNAL_STRENGTH_DECIBELS_MILLIWATT
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, link: BoksLink) -> None:
        super().__init__(link, "rssi")
        self._attr_name = "RSSI"

    @property
    def available(self) -> bool:
        """Le RSSI vient des advertisements : valable même hors connexion."""
        return self._link.state.rssi is not None

    @property
    def native_value(self) -> int | None:
        return self._link.state.rssi


class BoksVersionSensor(BoksEntity, SensorEntity):
    """Version de firmware ou de logiciel (lue à la connexion)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_entity_registry_enabled_default = False

    def __init__(self, link: BoksLink, key: str, name: str) -> None:
        super().__init__(link, key)
        self._key = key
        self._attr_name = name

    @property
    def native_value(self) -> str | None:
        return getattr(self._link.state, self._key)
