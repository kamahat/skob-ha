"""Résolution d'un code d'ouverture depuis ``secrets.yaml``.

Home Assistant ne résout ``!secret`` que dans le YAML de configuration : les
entrées de config (config flow) n'y ont pas droit, et une valeur ``!secret x``
saisie dans un formulaire serait stockée telle quelle, littéralement. On
implémente donc la résolution nous-mêmes, avec la syntaxe que les utilisateurs
connaissent déjà, pour que le code d'ouverture puisse vivre dans le fichier
prévu pour les secrets plutôt que dans ``.storage``.
"""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.util.yaml import load_yaml

from .const import SECRET_PREFIX

_LOGGER = logging.getLogger(__name__)


class SecretError(ValueError):
    """La référence ne peut pas être résolue."""


def is_secret_ref(value: str) -> bool:
    """Vrai si la valeur désigne une entrée de ``secrets.yaml``."""
    return value.strip().startswith(SECRET_PREFIX)


def secret_key(value: str) -> str:
    """Extrait le nom de clé d'une référence ``!secret <clé>``."""
    return value.strip()[len(SECRET_PREFIX) :].strip()


def _load(path: str, key: str) -> str:
    """Lit une clé dans ``secrets.yaml`` (appel bloquant, à déporter)."""
    try:
        secrets = load_yaml(path)
    except Exception as err:  # noqa: BLE001 - fichier absent, illisible, invalide
        raise SecretError(f"secrets.yaml illisible: {err}") from err
    if not isinstance(secrets, dict) or key not in secrets:
        raise SecretError(f"clé « {key} » absente de secrets.yaml")
    value = secrets[key]
    if not isinstance(value, str) or not value.strip():
        raise SecretError(f"la clé « {key} » ne contient pas de texte exploitable")
    return value.strip()


async def async_resolve(hass: HomeAssistant, value: str | None) -> str | None:
    """Résout une valeur d'option en code d'ouverture.

    Accepte indifféremment le code lui-même ou une référence ``!secret <clé>``.
    La lecture du fichier est déportée dans un thread : la boucle d'événements
    de Home Assistant ne doit jamais faire d'entrée-sortie disque.

    Les messages d'erreur nomment la **clé**, jamais la valeur — un secret ne
    doit pas finir dans le journal.
    """
    if not value:
        return None
    if not is_secret_ref(value):
        return value
    key = secret_key(value)
    if not key:
        raise SecretError("référence !secret sans nom de clé")
    return await hass.async_add_executor_job(
        _load, hass.config.path("secrets.yaml"), key
    )
