"""Base commune aux entités Boks."""
from __future__ import annotations

from homeassistant.helpers.device_registry import CONNECTION_BLUETOOTH, DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN
from .coordinator import BoksLink


class BoksEntity(Entity):
    """Entité rattachée à une Boks, mise à jour par push."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, link: BoksLink, key: str) -> None:
        self._link = link
        self._attr_unique_id = f"{link.address}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, link.address)},
            connections={(CONNECTION_BLUETOOTH, link.address)},
            manufacturer="Boks",
            model="Boîte aux lettres connectée",
            name="Boks",
        )

    async def async_added_to_hass(self) -> None:
        """S'abonne aux mises à jour poussées par la liaison."""
        self.async_on_remove(
            self._link.async_add_listener(self.async_write_ha_state)
        )

    @property
    def available(self) -> bool:
        """Indisponible tant que la Boks n'est pas jointe."""
        return self._link.state.connected
