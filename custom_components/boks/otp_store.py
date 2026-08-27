"""Pool de codes d'ouverture à usage unique (OTP).

Un code OTP ne peut être utilisé qu'une fois — contrairement au code
permanent (``OPEN_CODE_MODE_DIRECT``/``OPEN_CODE_MODE_SECRET``), il n'est
donc pas résolu une bonne fois pour toutes au démarrage : il vit dans un
pool consommé au fil des ouvertures, persisté indépendamment de
``config_entry.options`` (qui reste la configuration *voulue* par
l'utilisateur, pas l'état d'exécution).

Règle de retrait, tranchée dans TODO.md #5 : un code n'est retiré du pool
qu'**après confirmation d'usage** par la boîte (``VALID_OPEN_CODE``), jamais
à l'envoi. Un code refusé (``INVALID_OPEN_CODE``) reste dans le pool tel
quel — cette intégration n'essaie pas de deviner pourquoi il a été refusé.
Risque résiduel assumé : si la confirmation est perdue après une acceptation
réelle (coupure de lien), le prochain appui rejouera le même code ; la boîte
répondra alors ``INVALID_OPEN_CODE`` — un échec bruyant et attribuable, pas
un dysfonctionnement silencieux.
"""
from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers.storage import Store

from .protocol import normalize_pin

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
#: Un fichier par entrée de configuration — chaque boîte a son propre pool.
STORAGE_KEY_PREFIX = "boks_otp"


class OtpPool:
    """Pool de codes OTP pour une Boks donnée.

    Charger (``async_load``) avant tout usage — le constructeur ne fait
    aucune E/S. Un même ``entry_id`` réutilise toujours le même fichier de
    stockage : recharger l'intégration ne perd donc pas le pool en cours.
    """

    def __init__(self, hass: HomeAssistant, entry_id: str) -> None:
        self._store: Store[dict] = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY_PREFIX}_{entry_id}"
        )
        self._codes: list[str] = []

    async def async_load(self) -> None:
        """Charge le pool depuis le disque. Idempotent."""
        data = await self._store.async_load()
        self._codes = list(data.get("codes", [])) if data else []

    async def async_add(self, raw_codes: str) -> int:
        """Ajoute des codes au pool, un par ligne de ``raw_codes``.

        **Ajoute**, ne remplace jamais : une soumission du formulaire
        Options en mode ``otp`` ne doit pas effacer un pool partiellement
        consommé au prétexte qu'on en profite pour changer le keepalive.
        Les doublons (même code déjà présent) sont silencieusement ignorés.

        Lève ``ValueError`` (via ``normalize_pin``) sur la première ligne mal
        formée — un code invalide produirait une trame que la boîte peut
        ignorer sans réponse, ce qui se diagnostique très mal une fois dans
        le pool plutôt qu'à la saisie. Rien n'est persisté si l'ajout échoue
        en cours de route : soit tout, soit rien.

        Retourne le nombre de codes effectivement ajoutés.
        """
        new_codes = list(self._codes)
        added = 0
        for line in raw_codes.splitlines():
            line = line.strip()
            if not line:
                continue
            code = normalize_pin(line)  # ValueError si invalide — propagée
            if code not in new_codes:
                new_codes.append(code)
                added += 1
        if added:
            self._codes = new_codes
            await self._store.async_save({"codes": self._codes})
        return added

    def peek(self) -> str | None:
        """Le prochain code à essayer, **sans** le retirer du pool."""
        return self._codes[0] if self._codes else None

    async def async_commit_use(self, code: str) -> None:
        """Retire définitivement un code confirmé utilisé par la boîte.

        Idempotent et tolérant : si ``code`` n'est plus en tête (pool modifié
        entre-temps par un ajout concurrent) ou déjà absent, on le retire là
        où il se trouve plutôt que de lever une erreur — la confirmation de
        la boîte est la seule source de vérité sur ce qui a été consommé, pas
        la position dans la liste.
        """
        try:
            self._codes.remove(code)
        except ValueError:
            _LOGGER.debug("code OTP déjà absent du pool (retrait ignoré)")
            return
        await self._store.async_save({"codes": self._codes})

    @property
    def remaining(self) -> int:
        """Nombre de codes encore disponibles."""
        return len(self._codes)
