"""Intégration Boks — boîte aux lettres connectée, en lecture seule.

Le lien BLE est maintenu en permanence à travers la stack Bluetooth de Home
Assistant (donc, en pratique, via un proxy Bluetooth ESPHome). La Boks pousse
ses changements d'état ; l'intégration ne fait aucun polling.
"""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_ADDRESS, DOMAIN
from .coordinator import BoksLink

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Met en place une Boks."""
    address: str = entry.data[CONF_ADDRESS]

    link = BoksLink(hass, address)
    try:
        await link.async_start()
    except Exception as err:  # noqa: BLE001
        raise ConfigEntryNotReady(f"démarrage du lien Boks impossible: {err}") from err

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = link
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Décharge l'intégration."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        link: BoksLink = hass.data[DOMAIN].pop(entry.entry_id)
        await link.async_stop()
        if not hass.data[DOMAIN]:
            hass.data.pop(DOMAIN)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
