"""Capteurs binaires Boks : état de la porte et santé du lien."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import BoksLink
from .entity import BoksEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Ajoute les capteurs binaires."""
    link: BoksLink = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BoksDoorSensor(link), BoksLinkSensor(link)])


class BoksDoorSensor(BoksEntity, BinarySensorEntity):
    """Porte de la boîte aux lettres (poussé par la Boks)."""

    _attr_device_class = BinarySensorDeviceClass.DOOR

    def __init__(self, link: BoksLink) -> None:
        super().__init__(link, "door")
        self._attr_name = "Porte"

    @property
    def is_on(self) -> bool | None:
        """True si la porte est ouverte."""
        return self._link.state.door_open


class BoksLinkSensor(BoksEntity, BinarySensorEntity):
    """État de la liaison BLE avec la Boks."""

    _attr_device_class = BinarySensorDeviceClass.CONNECTIVITY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, link: BoksLink) -> None:
        super().__init__(link, "link")
        self._attr_name = "Lien BLE"

    @property
    def available(self) -> bool:
        """Toujours disponible : c'est précisément ce capteur qui dit si ça l'est."""
        return True

    @property
    def is_on(self) -> bool:
        return self._link.state.connected
