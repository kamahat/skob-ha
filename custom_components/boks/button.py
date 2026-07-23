"""Bouton d'ouverture à distance.

Cette plateforme n'expose une entité **que si** un code d'ouverture a été
renseigné dans les options. Sans code, l'intégration reste strictement en
lecture et aucun bouton n'apparaît — l'absence de secret vaut absence de
capacité, plutôt qu'un bouton présent qui échouerait à l'usage.
"""
from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import BoksLink
from .entity import BoksEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Ajoute le bouton d'ouverture, si un code est configuré."""
    link: BoksLink = hass.data[DOMAIN][entry.entry_id]
    if link.open_code:
        async_add_entities([BoksOpenDoorButton(link)])


class BoksOpenDoorButton(BoksEntity, ButtonEntity):
    """Ouvre la boîte aux lettres.

    L'appui établit une connexion si nécessaire, envoie la commande, et attend
    la réponse de la boîte. Une erreur est remontée à l'utilisateur si le code
    est refusé ou si la boîte ne répond pas : l'écriture GATT seule ne prouve
    pas que la porte s'est ouverte.
    """

    _attr_icon = "mdi:door-open"

    def __init__(self, link: BoksLink) -> None:
        super().__init__(link, "open_door")
        self._attr_name = "Ouvrir"

    @property
    def available(self) -> bool:
        """Toujours disponible : l'ouverture n'exige pas un lien déjà établi."""
        return True

    async def async_press(self) -> None:
        """Envoie la commande d'ouverture.

        Les exceptions ``BoksOpenError`` remontent telles quelles : ce sont des
        ``HomeAssistantError``, donc Home Assistant les affiche à l'utilisateur
        au lieu de les enterrer dans le journal.
        """
        await self._link.async_open_door()
