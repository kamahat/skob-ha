"""Entité texte : l'UID du badge à révoquer.

N'existe que si une Config Key est configurée. Sert de champ de saisie pour le
bouton « Révoquer le badge » — Home Assistant n'a pas de bouton-avec-paramètre,
on découple donc la saisie (ici) de l'action (le bouton).
"""
from __future__ import annotations

from homeassistant.components.text import TextEntity
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
    """Ajoute le champ UID, si une Config Key est configurée."""
    link: BoksLink = hass.data[DOMAIN][entry.entry_id]
    if link.config_key:
        async_add_entities([BoksUnregisterUidText(link)])


class BoksUnregisterUidText(BoksEntity, TextEntity):
    """UID (hex) du badge à révoquer, consommé par le bouton « Révoquer ».

    Champ de saisie transitoire (pas de persistance nécessaire) : on renseigne
    l'UID juste avant d'appuyer sur « Révoquer ».
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:card-account-details-outline"
    #: UID Mifare : jusqu'à 7 octets → 14 hex, avec séparateurs optionnels.
    _attr_native_min = 0
    _attr_native_max = 23
    _attr_pattern = r"[0-9A-Fa-f: ]*"

    def __init__(self, link: BoksLink) -> None:
        super().__init__(link, "unregister_uid")
        self._attr_name = "UID à révoquer"

    @property
    def available(self) -> bool:
        return True

    @property
    def native_value(self) -> str:
        return self._link.pending_unregister_uid

    async def async_set_value(self, value: str) -> None:
        self._link.pending_unregister_uid = value.strip()
        self.async_write_ha_state()
