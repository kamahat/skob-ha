"""Capteurs binaires Boks : état de la porte et santé du lien."""
from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from collections.abc import Callable

from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import BoksLink
from .entity import BoksEntity, RestoreIntoState


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Ajoute les capteurs binaires."""
    link: BoksLink = hass.data[DOMAIN][entry.entry_id]
    entities: list[BinarySensorEntity] = [
        BoksDoorSensor(link),
        BoksLinkSensor(link),
        BoksBatteryLowSensor(link),
    ]
    tracker = link.tracker
    if tracker is not None and tracker.door_entity:
        entities.append(
            BoksMirrorSensor(
                link, "door_live", "Porte (capteur Zigbee)",
                BinarySensorDeviceClass.DOOR, lambda: tracker.door_state,
            )
        )
    if tracker is not None and tracker.flap_entity:
        entities.append(
            BoksMirrorSensor(
                link, "mail_flap", "Volet à courrier",
                BinarySensorDeviceClass.OPENING, lambda: tracker.flap_state,
            )
        )
    async_add_entities(entities)


class BoksDoorSensor(BoksEntity, BinarySensorEntity, RestoreIntoState):
    """Porte de la boîte aux lettres (poussé par la Boks).

    Restaure son dernier état connu au redémarrage de Home Assistant : sans
    cela elle repartait en « unknown » entre deux rafraîchissements — visible
    depuis le passage au modèle de connexion périodique, où l'entité vit la
    plupart du temps sans lien actif.
    """

    _attr_device_class = BinarySensorDeviceClass.DOOR
    _restore_attr = "door_open"

    def _restore_parse(self, raw: str) -> bool:
        if raw not in ("on", "off"):
            raise ValueError(f"état de porte inattendu: {raw!r}")
        return raw == "on"

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


class BoksBatteryLowSensor(BoksEntity, BinarySensorEntity):
    """Alerte de fin de vie des piles.

    C'est ce capteur, et non le pourcentage, qu'il faut utiliser en
    automatisation : sa logique s'adapte au type de piles déclaré (voir le
    switch « piles rechargeables »), là où un seuil fixe sur le pourcentage
    ne préviendrait jamais avec un pack à tension régulée.
    """

    _attr_device_class = BinarySensorDeviceClass.BATTERY
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, link: BoksLink) -> None:
        super().__init__(link, "battery_low")
        self._attr_name = "Piles à remplacer"

    @property
    def is_on(self) -> bool | None:
        return self._link.battery_low


class BoksMirrorSensor(BoksEntity, BinarySensorEntity):
    """Reflet d'un capteur Zigbee associé (porte ou volet), en temps réel.

    Contrairement à « Porte » — poussé par le lien BLE, souvent coupé —, celui-ci
    suit le capteur externe dès qu'il change. Indisponible si le capteur source
    l'est : on n'invente pas un état.
    """

    def __init__(
        self,
        link: BoksLink,
        key: str,
        name: str,
        device_class: BinarySensorDeviceClass,
        getter: Callable[[], bool | None],
    ) -> None:
        super().__init__(link, key)
        self._attr_name = name
        self._attr_device_class = device_class
        self._getter = getter

    @property
    def available(self) -> bool:
        return self._getter() is not None

    @property
    def is_on(self) -> bool | None:
        return self._getter()
