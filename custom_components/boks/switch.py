"""Interrupteur de maintien du lien BLE."""
from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import DOMAIN
from .coordinator import BoksLink
from .entity import BoksEntity


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Ajoute l'interrupteur de connexion."""
    link: BoksLink = hass.data[DOMAIN][entry.entry_id]
    async_add_entities([BoksHoldConnectionSwitch(link), BoksRechargeableSwitch(link)])


class BoksHoldConnectionSwitch(BoksEntity, SwitchEntity, RestoreEntity):
    """Maintient (ou non) le lien BLE avec la boîte aux lettres.

    C'est l'arbitrage central de cette intégration, et il appartient à
    l'utilisateur :

    - **Allumé** — le lien est tenu en permanence. Les changements d'état sont
      poussés à l'instant où ils se produisent, mais la radio de la boîte reste
      éveillée : sur un appareil à piles, cela se paie.
    - **Éteint** — aucune connexion. Les valeurs déjà connues restent affichées
      (leur fraîcheur se lit sur *Dernière connexion*) et la présence continue
      d'être suivie par les advertisements, qui ne coûtent rien à la boîte.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:bluetooth-connect"

    def __init__(self, link: BoksLink) -> None:
        super().__init__(link, "hold_connection")
        self._attr_name = "Connexion maintenue"

    @property
    def available(self) -> bool:
        """Toujours disponible : c'est ce réglage qui décide du reste."""
        return True

    @property
    def is_on(self) -> bool:
        return self._link.hold

    async def async_added_to_hass(self) -> None:
        """Restaure l'état choisi avant le redémarrage.

        Sans cela, un redémarrage de Home Assistant rétablirait silencieusement
        le lien alors que l'utilisateur l'avait coupé — précisément ce qu'on
        cherche à éviter sur un appareil à piles.
        """
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state == "on":
            await self._link.async_set_hold(True)

    async def async_turn_on(self, **kwargs: Any) -> None:
        await self._link.async_set_hold(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        await self._link.async_set_hold(False)
        self.async_write_ha_state()


class BoksRechargeableSwitch(BoksEntity, SwitchEntity, RestoreEntity):
    """Type de piles en place — change la lecture du niveau de batterie.

    La Boks n'expose pas de tension : elle publie un pourcentage qu'elle a
    dérivé elle-même, sur une courbe d'alcaline. Ce chiffre ne veut donc pas
    dire la même chose selon ce qu'on a mis dedans :

    - **Éteint (alcalines)** — la tension décroît régulièrement, le pourcentage
      suit la charge restante et se lit normalement.
    - **Allumé (lithium 1,5 V rechargeables)** — un convertisseur maintient la
      tension plate jusqu'à la coupure de la protection. La jauge reste collée
      en haut d'échelle puis s'effondre : elle ne mesure plus la charge, tout
      juste le décrochage. L'alerte *Piles à remplacer* bascule alors sur ce
      décrochage plutôt que sur un seuil.

    Rien n'est recalculé : la tension d'un pack régulé ne contient plus
    l'information de charge, aucune formule ne peut la restituer. Ce réglage
    change l'interprétation, pas la valeur affichée.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_icon = "mdi:battery-sync"

    def __init__(self, link: BoksLink) -> None:
        super().__init__(link, "rechargeable")
        self._attr_name = "Piles rechargeables"

    @property
    def available(self) -> bool:
        """Toujours disponible : c'est un réglage, pas une mesure."""
        return True

    @property
    def is_on(self) -> bool:
        return self._link.rechargeable

    async def async_added_to_hass(self) -> None:
        """Restaure le type déclaré avant le redémarrage."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state == "on":
            self._link.async_set_rechargeable(True)

    async def async_turn_on(self, **kwargs: Any) -> None:
        self._link.async_set_rechargeable(True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        self._link.async_set_rechargeable(False)
        self.async_write_ha_state()
