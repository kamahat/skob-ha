"""Bouton d'ouverture à distance.

Cette plateforme n'expose une entité **que si** un code d'ouverture a été
renseigné dans les options. Sans code, l'intégration reste strictement en
lecture et aucun bouton n'apparaît — l'absence de secret vaut absence de
capacité, plutôt qu'un bouton présent qui échouerait à l'usage.
"""
from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import BoksAdminError, BoksLink
from .entity import BoksEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Ajoute le bouton d'ouverture (si code) et l'admin NFC (si Config Key)."""
    link: BoksLink = hass.data[DOMAIN][entry.entry_id]
    entities: list[ButtonEntity] = []
    if link.open_code:
        entities.append(BoksOpenDoorButton(link))
    if link.config_key:
        entities.append(BoksRegisterNfcButton(link))
        entities.append(BoksUnregisterNfcButton(link))
    async_add_entities(entities)


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


class BoksRegisterNfcButton(BoksEntity, ButtonEntity):
    """Enrôle un badge Mifare (n'existe que si une Config Key est configurée).

    L'appui lance le scan d'enrôlement : présentez alors un badge au clavier
    (appui touche puis badge). Le résultat — ou l'erreur (badge non présenté à
    temps, clé refusée…) — est remonté à l'utilisateur.
    """

    _attr_icon = "mdi:nfc-tap"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, link: BoksLink) -> None:
        super().__init__(link, "register_nfc")
        self._attr_name = "Enrôler un badge"

    @property
    def available(self) -> bool:
        return True

    async def async_press(self) -> None:
        result = await self._link.async_register_nfc_tag()
        _LOGGER.info(
            "badge %s : %s", result.get("uid"), result.get("status")
        )


class BoksUnregisterNfcButton(BoksEntity, ButtonEntity):
    """Révoque le badge dont l'UID est saisi dans l'entité « UID à révoquer »."""

    _attr_icon = "mdi:nfc-variant-off"
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, link: BoksLink) -> None:
        super().__init__(link, "unregister_nfc")
        self._attr_name = "Révoquer le badge"

    @property
    def available(self) -> bool:
        return True

    async def async_press(self) -> None:
        uid = (self._link.pending_unregister_uid or "").strip()
        if not uid:
            raise BoksAdminError(
                "renseignez d'abord l'UID du badge dans « UID à révoquer »"
            )
        await self._link.async_unregister_nfc_tag(uid)
