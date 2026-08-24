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
    CONF_CONFIG_KEY,
    CONF_KEEPALIVE,
    DEFAULT_CONFIG_KEY_SECRET,
    CONF_LABEL,
    CONF_OPEN_CODE_MODE,
    CONF_OPEN_CODE_VALUE,
    CONF_RECONNECT_MAX,
    CONF_REFRESH_INTERVAL,
    DOMAIN,
    KEEPALIVE_INTERVAL,
    KEEPALIVE_MAX,
    KEEPALIVE_MIN,
    OPEN_CODE_MODE_DIRECT,
    OPEN_CODE_MODE_NONE,
    OPEN_CODE_MODE_OTP,
    OPEN_CODE_MODE_SECRET,
    RECONNECT_DELAY_MAX,
    RECONNECT_MAX_MAX,
    RECONNECT_MAX_MIN,
    REFRESH_INTERVAL_DEFAULT,
    REFRESH_INTERVAL_MAX,
    REFRESH_INTERVAL_MIN,
    SERVICE_UUID,
)
from .otp_store import OtpPool
from .protocol import normalize_config_key, normalize_pin
from .secret import SecretError, async_resolve, async_resolve_mode, is_secret_ref


def _title(address: str, name: str | None) -> str:
    return f"Boks {name}" if name and name != address else f"Boks {address[-8:]}"


class BoksConfigFlow(ConfigFlow, domain=DOMAIN):
    """Ajout d'une Boks."""

    VERSION = 2

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

    Deux étapes : ``init`` couvre les réglages généraux plus le *choix* du
    mode de code d'ouverture ; ``open_code`` ne s'affiche que si ce mode
    n'est pas ``none``, et ne montre qu'un seul champ dont le type et le
    libellé suivent le mode choisi. Séparer les deux évite un champ qui ne
    veut rien dire tant qu'aucun mode n'est sélectionné.

    Valider ce formulaire déclenche le rechargement de l'entrée (via
    ``add_update_listener``) : la liaison est reconstruite avec les nouvelles
    valeurs, sans toucher au reste de l'installation.

    À noter : recharger une entrée ne recharge **pas** le code Python de
    l'intégration, qui reste en cache dans le processus. Après une mise à jour
    des fichiers du composant, un redémarrage de Home Assistant reste
    nécessaire.
    """

    def __init__(self) -> None:
        super().__init__()
        #: Données validées à l'étape ``init``, complétées par ``open_code``
        #: avant la création finale de l'entrée.
        self._pending: dict[str, Any] = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Réglages généraux, Config Key, et choix du mode de code d'ouverture."""
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_LABEL] = (user_input.get(CONF_LABEL) or "").strip()
            # Config Key : secrets.yaml ou valeur directe. Absente = pas de
            # capacité d'admin NFC/VIGIK exposée. Inchangé par le passage du
            # code d'ouverture en mode/valeur explicite (TODO.md #5) — les
            # deux champs sont indépendants.
            ckey = (user_input.get(CONF_CONFIG_KEY) or "").strip()
            if not ckey:
                user_input[CONF_CONFIG_KEY] = ""
            elif is_secret_ref(ckey):
                try:
                    normalize_config_key(await async_resolve(self.hass, ckey))
                except SecretError:
                    errors[CONF_CONFIG_KEY] = "unknown_secret"
                except ValueError:
                    errors[CONF_CONFIG_KEY] = "invalid_config_key"
                else:
                    user_input[CONF_CONFIG_KEY] = ckey
            else:
                try:
                    user_input[CONF_CONFIG_KEY] = normalize_config_key(ckey)
                except ValueError:
                    errors[CONF_CONFIG_KEY] = "invalid_config_key"

            if not errors:
                self._pending = user_input
                if user_input[CONF_OPEN_CODE_MODE] == OPEN_CODE_MODE_NONE:
                    self._pending[CONF_OPEN_CODE_VALUE] = ""
                    return self.async_create_entry(data=self._pending)
                return await self.async_step_open_code()

        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_LABEL,
                        default=options.get(CONF_LABEL, ""),
                    ): selector.TextSelector(),
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
                    vol.Required(
                        CONF_OPEN_CODE_MODE,
                        default=options.get(CONF_OPEN_CODE_MODE, OPEN_CODE_MODE_NONE),
                    ): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=[
                                OPEN_CODE_MODE_NONE,
                                OPEN_CODE_MODE_DIRECT,
                                OPEN_CODE_MODE_SECRET,
                                OPEN_CODE_MODE_OTP,
                            ],
                            translation_key="open_code_mode",
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    ),
                    vol.Optional(
                        CONF_CONFIG_KEY,
                        # Par défaut, on propose la référence secrets.yaml
                        # recommandée plutôt qu'un champ vide : la Config Key doit
                        # rester dans secrets.yaml. Un utilisateur sans ce secret
                        # est guidé par l'erreur « unknown_secret » à la validation.
                        default=options.get(
                            CONF_CONFIG_KEY, DEFAULT_CONFIG_KEY_SECRET
                        ),
                    ): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=selector.TextSelectorType.PASSWORD
                        )
                    ),
                    vol.Required(
                        CONF_REFRESH_INTERVAL,
                        default=options.get(
                            CONF_REFRESH_INTERVAL, REFRESH_INTERVAL_DEFAULT
                        ),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=REFRESH_INTERVAL_MIN,
                            max=REFRESH_INTERVAL_MAX,
                            step=5,
                            unit_of_measurement="min",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    ),
                }
            ),
            errors=errors,
        )

    async def async_step_open_code(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Second écran : un seul champ, dont le sens dépend du mode choisi.

        ``direct``/``secret`` se comportent comme le champ unique v1 : validés
        et stockés tels quels dans les options (masqués, comme avant).

        ``otp`` est différent par construction : le champ ne porte que les
        codes à *ajouter*, jamais le pool lui-même — il est analysé, validé,
        puis ajouté directement au ``OtpPool`` ici même. Ce qui finit dans
        les options pour ce mode est toujours une valeur vide : le pool vit
        dans son propre stockage (cf. otp_store.py), pas dans
        ``config_entry.options``, qui représente la config voulue, pas
        l'état d'exécution.
        """
        errors: dict[str, str] = {}
        mode = self._pending[CONF_OPEN_CODE_MODE]

        if user_input is not None:
            raw = (user_input.get(CONF_OPEN_CODE_VALUE) or "").strip()

            if mode == OPEN_CODE_MODE_SECRET:
                # Vérifié dès maintenant que la clé existe et contient un code
                # valide, sinon l'erreur ne se révélerait qu'au premier appui
                # sur le bouton. La valeur n'est jamais réaffichée — seule la
                # référence (le nom de clé) l'est.
                try:
                    normalize_pin(
                        await async_resolve_mode(self.hass, OPEN_CODE_MODE_SECRET, raw)
                    )
                except SecretError:
                    errors[CONF_OPEN_CODE_VALUE] = "unknown_secret"
                except ValueError:
                    errors[CONF_OPEN_CODE_VALUE] = "invalid_open_code"

            elif mode == OPEN_CODE_MODE_DIRECT:
                try:
                    raw = normalize_pin(raw)
                except ValueError:
                    errors[CONF_OPEN_CODE_VALUE] = "invalid_open_code"

            elif mode == OPEN_CODE_MODE_OTP:
                if not raw:
                    errors[CONF_OPEN_CODE_VALUE] = "no_codes_entered"
                else:
                    pool = OtpPool(self.hass, self.config_entry.entry_id)
                    await pool.async_load()
                    try:
                        added = await pool.async_add(raw)
                    except ValueError:
                        errors[CONF_OPEN_CODE_VALUE] = "invalid_open_code"
                    else:
                        if added == 0:
                            # Tous doublons d'un pool déjà chargé : pas une
                            # erreur bloquante, juste rien de neuf à ajouter.
                            pass
                        raw = ""  # jamais stocké dans les options, voir docstring

            if not errors:
                self._pending[CONF_OPEN_CODE_VALUE] = raw
                return self.async_create_entry(data=self._pending)

        is_secret_field = mode in (OPEN_CODE_MODE_DIRECT, OPEN_CODE_MODE_SECRET)
        return self.async_show_form(
            step_id="open_code",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_OPEN_CODE_VALUE, default=""): selector.TextSelector(
                        selector.TextSelectorConfig(
                            type=(
                                selector.TextSelectorType.PASSWORD
                                if is_secret_field
                                else selector.TextSelectorType.TEXT
                            ),
                            multiline=(mode == OPEN_CODE_MODE_OTP),
                        )
                    ),
                }
            ),
            description_placeholders={"mode": mode},
            errors=errors,
        )
