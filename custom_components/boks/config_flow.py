"""Config flow de l'intégration Boks.

Deux chemins : découverte Bluetooth automatique (la Boks annonce le service
``a7630001-…``, déclaré dans le manifest) ou saisie manuelle de l'adresse.
"""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.bluetooth import (
    BluetoothServiceInfoBleak,
    async_discovered_service_info,
)
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_ADDRESS,
    CONF_KEEPALIVE,
    CONF_OPEN_CODE,
    CONF_RECONNECT_MAX,
    DOMAIN,
    KEEPALIVE_INTERVAL,
    KEEPALIVE_MAX,
    KEEPALIVE_MIN,
    RECONNECT_DELAY_MAX,
    RECONNECT_MAX_MAX,
    RECONNECT_MAX_MIN,
    SERVICE_UUID,
)
from .protocol import normalize_pin


def _title(address: str, name: str | None) -> str:
    return f"Boks {name}" if name and name != address else f"Boks {address[-8:]}"


class BoksConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ajout d'une Boks."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> BoksOptionsFlow:
        """Expose les options — c'est ce qui rend l'entrée rechargeable à chaud."""
        return BoksOptionsFlow()

    def __init__(self) -> None:
        self._discovered: dict[str, str] = {}
        self._address: str | None = None
        self._name: str | None = None

    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        """Boks détectée automatiquement par la stack Bluetooth."""
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._address = discovery_info.address
        self._name = discovery_info.name
        self.context["title_placeholders"] = {
            "name": _title(discovery_info.address, discovery_info.name)
        }
        return await self.async_step_confirm()

    async def async_step_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirmation d'une Boks découverte."""
        assert self._address is not None
        if user_input is not None:
            return self.async_create_entry(
                title=_title(self._address, self._name),
                data={CONF_ADDRESS: self._address},
            )
        self._set_confirm_only()
        return self.async_show_form(
            step_id="confirm",
            description_placeholders={"name": _title(self._address, self._name)},
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ajout manuel : choix parmi les Boks visibles."""
        if user_input is not None:
            address = user_input[CONF_ADDRESS]
            await self.async_set_unique_id(address, raise_on_progress=False)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=_title(address, self._discovered.get(address)),
                data={CONF_ADDRESS: address},
            )

        current = self._async_current_ids()
        for info in async_discovered_service_info(self.hass, connectable=True):
            if info.address in current:
                continue
            if SERVICE_UUID in (uuid.lower() for uuid in info.service_uuids):
                self._discovered[info.address] = info.name or info.address

        if not self._discovered:
            return self.async_abort(reason="no_devices_found")

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_ADDRESS): vol.In(
                        {
                            address: f"{name} ({address})"
                            for address, name in self._discovered.items()
                        }
                    )
                }
            ),
        )


class BoksOptionsFlow(OptionsFlow):
    """Réglages de la liaison, modifiables sans redémarrer Home Assistant.

    Valider ce formulaire déclenche le rechargement de l'entrée (via
    ``add_update_listener``) : la liaison est reconstruite avec les nouvelles
    valeurs, sans toucher au reste de l'installation.

    À noter : recharger une entrée ne recharge **pas** le code Python de
    l'intégration, qui reste en cache dans le processus. Après une mise à jour
    des fichiers du composant, un redémarrage de Home Assistant reste
    nécessaire.
    """

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Formulaire unique."""
        errors: dict[str, str] = {}
        if user_input is not None:
            code = (user_input.get(CONF_OPEN_CODE) or "").strip()
            if code:
                # Valider ici plutôt qu'à l'appui : un code au mauvais format
                # produit une trame que la boîte peut ignorer *sans répondre*,
                # ce qui se diagnostique très mal une fois en service.
                try:
                    user_input[CONF_OPEN_CODE] = normalize_pin(code)
                except ValueError:
                    errors[CONF_OPEN_CODE] = "invalid_open_code"
            else:
                user_input[CONF_OPEN_CODE] = ""
            if not errors:
                return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_KEEPALIVE,
                        default=options.get(CONF_KEEPALIVE, KEEPALIVE_INTERVAL),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=KEEPALIVE_MIN,
                            max=KEEPALIVE_MAX,
                            step=1,
                            unit_of_measurement="s",
                            mode=selector.NumberSelectorMode.SLIDER,
                        )
                    ),
                    vol.Required(
                        CONF_RECONNECT_MAX,
                        default=options.get(CONF_RECONNECT_MAX, RECONNECT_DELAY_MAX),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=RECONNECT_MAX_MIN,
                            max=RECONNECT_MAX_MAX,
                            step=10,
                            unit_of_measurement="s",
                            mode=selector.NumberSelectorMode.SLIDER,
                        )
                    ),
                    vol.Optional(
                        CONF_OPEN_CODE,
                        default=options.get(CONF_OPEN_CODE, ""),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                }
            ),
            errors=errors,
        )
