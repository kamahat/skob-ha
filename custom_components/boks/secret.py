"""Résolution d'une valeur d'option depuis ``secrets.yaml``.

Home Assistant ne résout ``!secret`` que dans le YAML de configuration : les
entrées de config (config flow) n'y ont pas droit, et une valeur ``!secret x``
saisie dans un formulaire serait stockée telle quelle, littéralement. On
implémente donc la résolution nous-mêmes, avec la syntaxe que les utilisateurs
connaissent déjà, pour que le secret puisse vivre dans le fichier prévu pour
les secrets plutôt que dans ``.storage``.

Deux usages distincts, à ne pas confondre :

- **``async_resolve``** (reniflage par préfixe) reste le chemin **actif** pour
  la Config Key (cf. ``CONF_CONFIG_KEY`` dans ``__init__.py``), qui n'a pas de
  mode explicite comme le code d'ouverture.
- **``is_secret_ref``/``secret_key``** sont réutilisés tels quels par
  ``async_migrate_entry`` (dans ``__init__.py``) pour lire une seule fois
  l'ancien ``open_code`` v1 et le répartir vers le nouveau mode/valeur — mais
  ``async_resolve`` lui-même n'intervient **pas** dans cette migration.
- **``async_resolve_mode``** est le chemin v2 du code d'ouverture, qui n'a
  plus besoin de reniflage : le mode dit directement quoi faire de la valeur.
"""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.util.yaml import load_yaml

from .const import (
    OPEN_CODE_MODE_DIRECT,
    OPEN_CODE_MODE_NONE,
    OPEN_CODE_MODE_SECRET,
    SECRET_PREFIX,
)

_LOGGER = logging.getLogger(__name__)


class SecretError(ValueError):
    """La référence ne peut pas être résolue."""


def is_secret_ref(value: str) -> bool:
    """Vrai si la valeur désigne une entrée de ``secrets.yaml``.

    Utilisé par ``async_migrate_entry`` (migration v1→v2 du code d'ouverture)
    et par la résolution de la Config Key, qui garde ce reniflage par préfixe
    faute de mode explicite dédié.
    """
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
    """Résout une valeur par reniflage de préfixe ``!secret``.

    Chemin **actif** pour la Config Key (cf. module docstring) : accepte
    indifféremment la valeur elle-même ou une référence ``!secret <clé>``.
    Le code d'ouverture, lui, est passé au mode explicite
    (``async_resolve_mode``) et n'a plus besoin de ce reniflage.

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


async def async_resolve_mode(
    hass: HomeAssistant, mode: str, value: str | None
) -> str | None:
    """Résout (mode, value) v2 en code d'ouverture effectif.

    Remplace le reniflage de préfixe pour le code d'ouverture : le mode dit
    directement quoi faire de ``value``, pas besoin de deviner.

    ``OPEN_CODE_MODE_OTP`` n'est **pas** géré ici : un code à usage unique ne
    se résout pas à une valeur unique au démarrage, il vit dans un pool
    consommé au fil des ouvertures (cf. ``otp_store.py``). L'appelant doit
    router ce mode séparément ; ``value`` y est de toute façon vide (v2 ne
    stocke jamais les codes OTP dans les options, voir config_flow.py).
    """
    if mode == OPEN_CODE_MODE_NONE or not value:
        return None
    if mode == OPEN_CODE_MODE_DIRECT:
        return value
    if mode == OPEN_CODE_MODE_SECRET:
        return await hass.async_add_executor_job(
            _load, hass.config.path("secrets.yaml"), value
        )
    return None
