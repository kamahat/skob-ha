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
            # La boîte n'expose aucun identifiant lisible : son Serial Number
            # GATT renvoie sa propre MAC. Sans l'identifiant saisi par
            # l'utilisateur, deux boîtes s'appelleraient toutes deux « Boks »
            # et leurs entités seraient indiscernables.
            name=f"Boks {link.label}" if link.label else "Boks",
        )

    async def async_added_to_hass(self) -> None:
        """S'abonne aux mises à jour poussées par la liaison."""
        self.async_on_remove(
            self._link.async_add_listener(self.async_write_ha_state)
        )

    @property
    def available(self) -> bool:
        """Disponible dès qu'une valeur a été relevée au moins une fois.

        Volontairement plus permissif que « le lien est up » : la connexion
        n'est maintenue que si l'utilisateur le demande (switch « connexion
        maintenue »), et sur un appareil à piles elle sera coupée la plupart du
        temps. Faire disparaître les entités à chaque déconnexion viderait le
        tableau de bord de toute information. On conserve donc la dernière
        valeur connue, et le capteur *Dernière connexion* dit de quand elle
        date.
        """
        return self._link.state.connected or self._link.state.last_connected is not None
