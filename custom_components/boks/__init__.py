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

from .const import (
    CONF_ADDRESS,
    CONF_KEEPALIVE,
    CONF_LABEL,
    CONF_CONFIG_KEY,
    CONF_OPEN_CODE,
    CONF_OPEN_CODE_MODE,
    CONF_OPEN_CODE_VALUE,
    CONF_RECONNECT_MAX,
    CONF_REFRESH_INTERVAL,
    DOMAIN,
    KEEPALIVE_INTERVAL,
    OPEN_CODE_MODE_DIRECT,
    OPEN_CODE_MODE_NONE,
    OPEN_CODE_MODE_OTP,
    OPEN_CODE_MODE_SECRET,
    RECONNECT_DELAY_MAX,
    REFRESH_INTERVAL_DEFAULT,
)
from .coordinator import BoksLink
from .otp_store import OtpPool
from .secret import SecretError, async_resolve, async_resolve_mode, is_secret_ref, secret_key

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SENSOR,
    Platform.SWITCH,
    Platform.TEXT,
]


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migre une entrée v1 (``open_code`` unique) vers v2 (``mode``/``value``).

    v1 encodait trois états dans une seule chaîne, reniflée par préfixe :
    vide, code brut, ou ``!secret <clé>``. v2 les rend explicites. Chaque
    chaîne v1 retombe sans ambiguïté sur exactement l'un des trois modes
    statiques (jamais ``otp``, qui n'existait pas en v1) — cette migration ne
    peut donc pas échouer : aucune branche d'erreur, aucun risque de
    désactiver silencieusement le bouton Ouvrir d'une installation existante.

    Ne touche jamais aux autres options (keepalive, label, etc.).
    """
    if entry.version == 1:
        old = (entry.options.get(CONF_OPEN_CODE) or "").strip()
        options = {k: v for k, v in entry.options.items() if k != CONF_OPEN_CODE}
        if not old:
            options[CONF_OPEN_CODE_MODE] = OPEN_CODE_MODE_NONE
            options[CONF_OPEN_CODE_VALUE] = ""
        elif is_secret_ref(old):
            options[CONF_OPEN_CODE_MODE] = OPEN_CODE_MODE_SECRET
            options[CONF_OPEN_CODE_VALUE] = secret_key(old)
        else:
            options[CONF_OPEN_CODE_MODE] = OPEN_CODE_MODE_DIRECT
            options[CONF_OPEN_CODE_VALUE] = old
        hass.config_entries.async_update_entry(entry, options=options, version=2)
        _LOGGER.debug(
            "entrée %s migrée v1→v2 (mode=%s)",
            entry.entry_id,
            options[CONF_OPEN_CODE_MODE],
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Met en place une Boks."""
    address: str = entry.data[CONF_ADDRESS]

    mode = entry.options.get(CONF_OPEN_CODE_MODE, OPEN_CODE_MODE_NONE)
    value = entry.options.get(CONF_OPEN_CODE_VALUE, "")

    open_code: str | None = None
    otp_pool: OtpPool | None = None

    if mode == OPEN_CODE_MODE_OTP:
        # Pas de résolution à une valeur unique ici : un code OTP se consomme
        # à l'usage, pas au démarrage. Voir BoksLink.async_open_door.
        otp_pool = OtpPool(hass, entry.entry_id)
        await otp_pool.async_load()
    else:
        # Le code peut référencer secrets.yaml. Une référence cassée ne doit
        # pas empêcher l'intégration de démarrer : les capteurs de lecture
        # n'ont rien à voir avec l'ouverture. On journalise clairement et on
        # continue sans bouton — mieux vaut une capacité absente qu'une
        # intégration entière indisponible.
        try:
            open_code = await async_resolve_mode(hass, mode, value)
        except SecretError as err:
            _LOGGER.error(
                "code d'ouverture introuvable (%s) — le bouton d'ouverture ne sera "
                "pas créé ; le reste de l'intégration fonctionne normalement",
                err,
            )
            open_code = None

    # Config Key : même traitement tolérant que le code d'ouverture. Absente ou
    # cassée = pas de capacité d'admin NFC/VIGIK, le reste fonctionne.
    try:
        config_key = await async_resolve(hass, entry.options.get(CONF_CONFIG_KEY))
    except SecretError as err:
        _LOGGER.error(
            "Config Key introuvable (%s) — les fonctions d'administration "
            "NFC/VIGIK ne seront pas exposées ; le reste fonctionne normalement",
            err,
        )
        config_key = None

    link = BoksLink(
        hass,
        address,
        keepalive=float(entry.options.get(CONF_KEEPALIVE, KEEPALIVE_INTERVAL)),
        reconnect_max=float(entry.options.get(CONF_RECONNECT_MAX, RECONNECT_DELAY_MAX)),
        open_code=open_code,
        otp_pool=otp_pool,
        label=(entry.options.get(CONF_LABEL) or "").strip() or None,
        refresh_interval=int(
            entry.options.get(CONF_REFRESH_INTERVAL, REFRESH_INTERVAL_DEFAULT)
        ),
        config_key=config_key,
    )
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
