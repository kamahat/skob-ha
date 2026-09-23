"""Événements courrier Boks : dépôt, relève, ouverture non attendue."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import BoksLink
from .entity import BoksEntity
from .mail_logic import EVENT_COLLECTED, EVENT_DEPOSITED, EVENT_UNAUTHORIZED
from .sensors_link import BoksSensorTracker


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Ajoute l'entité d'événements si au moins un capteur est associé."""
    link: BoksLink = hass.data[DOMAIN][entry.entry_id]
    if link.tracker is not None:
        async_add_entities([BoksMailEvent(link, link.tracker)])


class BoksMailEvent(BoksEntity, EventEntity):
    """Activité courrier déduite des capteurs Zigbee associés."""

    _attr_icon = "mdi:mailbox"
    _attr_event_types = [EVENT_DEPOSITED, EVENT_COLLECTED, EVENT_UNAUTHORIZED]

    def __init__(self, link: BoksLink, tracker: BoksSensorTracker) -> None:
        super().__init__(link, "mail_activity")
        self._attr_name = "Activité courrier"
        self._tracker = tracker

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(self._tracker.async_add_event_listener(self._handle))

    @callback
    def _handle(self, kind: str, at: datetime) -> None:
        self._trigger_event(kind, {"at": at.isoformat()})
        self.async_write_ha_state()
