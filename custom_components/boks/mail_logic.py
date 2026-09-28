"""Logique pure « courrier » : dépôt, relève, ouverture non attendue.

Volontairement **sans dépendance à Home Assistant** : la machine d'états ne
manipule que des dates et des booléens, ce qui la rend testable seule
(cf. tests/test_mail_logic.py). Le branchement sur les entités HA est fait
par ``sensors_link.BoksSensorTracker``.

Trois événements possibles :

- ``mail_deposited``      : le volet s'est ouvert puis refermé (dépôt de courrier) ;
- ``mail_collected``      : la porte de la boîte s'est ouverte (relève) ;
- ``unauthorized_opening``: la porte s'est ouverte sans ouverture légitime
  correspondante, selon le mode de corrélation choisi (voir ci-dessous).

Trois modes de corrélation pour ``unauthorized_opening`` :

- ``off`` (défaut) : aucune corrélation, jamais d'alerte ;
- ``ha_command``   : légitime = une ouverture commandée depuis Home Assistant
  (bouton Ouvrir) dans la fenêtre. **Sans lecture du journal**, donc sans
  drain — mais une ouverture au clavier ou au badge est vue comme « non
  commandée par HA » : cette alerte ne distingue pas un voisin d'un intrus ;
- ``journal``      : légitime = une ouverture par code ou badge inscrite au
  journal de la boîte (ou une commande HA) dans la fenêtre. Distingue un
  accès autorisé d'une ouverture à la clé/forcée, mais exige la lecture
  périodique du journal, qui le **draine** — et l'alerte n'arrive qu'à la
  lecture suivante.

**Anti-rebond.** Constaté le 26/09 sur un vrai capteur : le contact reed peut
faire plusieurs allers-retours en moins d'une seconde (jusqu'à ~2,8 s d'écart
observé entre deux fronts) au moment d'une manœuvre — pas deux ouvertures
distinctes, un seul mouvement mécanique bruité. Sans filtrage, chaque rebond
produisait son propre ``mail_collected``/``mail_deposited`` (et donc sa
propre entrée dans ``_pending``, doublant aussi les alertes
``unauthorized_opening``). ``debounce`` (5 s par défaut) n'accepte qu'un
événement de chaque nature par fenêtre glissante : le premier front part
immédiatement, les suivants dans la fenêtre sont ignorés. Contrepartie
assumée : une seconde ouverture *réelle* dans les 5 s qui suivent la première
ne compte pas non plus — comme le fait déjà, au même seuil, l'automatisation
Telegram côté Home Assistant.
"""
from __future__ import annotations

from datetime import datetime, timedelta

MODE_OFF = "off"
MODE_HA_COMMAND = "ha_command"
MODE_JOURNAL = "journal"
MODES = (MODE_OFF, MODE_HA_COMMAND, MODE_JOURNAL)

EVENT_DEPOSITED = "mail_deposited"
EVENT_COLLECTED = "mail_collected"
EVENT_UNAUTHORIZED = "unauthorized_opening"

#: Ouvertures de porte en attente d'un verdict — plafond de sécurité.
MAX_PENDING = 50

#: Anti-rebond par défaut (secondes) — cf. section « Anti-rebond » ci-dessus.
DEBOUNCE_DEFAULT = 5.0

Emitted = list[tuple[str, datetime]]


def _transition(prev: bool | None, new: bool | None) -> bool | None:
    """Vrai/faux si le passage ``prev → new`` est un front réel, sinon ``None``.

    Un passage depuis/vers un état inconnu (``unavailable``, ``unknown``,
    redémarrage) n'est **pas** un événement : on ne sait pas ce qui s'est
    passé entre-temps, donc on n'invente rien.
    """
    if prev is None or new is None or prev == new:
        return None
    return new


class MailLogic:
    """Machine d'états des capteurs volet / porte."""

    def __init__(
        self,
        mode: str = MODE_OFF,
        window: float = 30.0,
        debounce: float = DEBOUNCE_DEFAULT,
    ) -> None:
        self.mode = mode if mode in MODES else MODE_OFF
        self.window = timedelta(seconds=window)
        self.debounce = timedelta(seconds=debounce)
        self._door: bool | None = None
        self._flap: bool | None = None
        self._flap_opened_at: datetime | None = None
        self._pending: list[datetime] = []
        self._ha_opens: list[datetime] = []
        #: Horodatage du dernier événement ACCEPTÉ de chaque nature (anti-rebond).
        self._last_collected: datetime | None = None
        self._last_deposited: datetime | None = None

    # -- utilitaires ------------------------------------------------------
    def _near(self, moment: datetime, candidates: list[datetime]) -> bool:
        return any(abs(moment - c) <= self.window for c in candidates)

    def _accept(self, now: datetime, last_attr: str) -> bool:
        """Anti-rebond : faux si un événement de même nature est trop récent.

        Le tout premier événement est toujours accepté (``last`` vaut
        ``None``). Un événement accepté devient la nouvelle référence — les
        rebonds suivants se mesurent donc depuis le dernier front réellement
        retenu, pas depuis le tout premier d'une rafale.
        """
        last = getattr(self, last_attr)
        if last is not None and now - last < self.debounce:
            return False
        setattr(self, last_attr, now)
        return True

    # -- entrées ------------------------------------------------------------
    def on_flap(self, is_open: bool | None, now: datetime) -> Emitted:
        """Nouvel état du volet (``None`` = indisponible)."""
        edge = _transition(self._flap, is_open)
        self._flap = is_open
        if edge is True:
            # Toujours mis à jour, même si un rebond avait déjà ouvert : c'est
            # le point de départ du cycle en cours, pas un événement en soi.
            self._flap_opened_at = now
        elif edge is False and self._flap_opened_at is not None:
            self._flap_opened_at = None
            if self._accept(now, "_last_deposited"):
                return [(EVENT_DEPOSITED, now)]
        elif is_open is None:
            self._flap_opened_at = None
        return []

    def on_door(self, is_open: bool | None, now: datetime) -> Emitted:
        """Nouvel état de la porte (``None`` = indisponible)."""
        edge = _transition(self._door, is_open)
        self._door = is_open
        if edge is not True:
            return []
        if not self._accept(now, "_last_collected"):
            return []  # rebond du capteur : pas une seconde ouverture réelle
        out: Emitted = [(EVENT_COLLECTED, now)]
        if self.mode != MODE_OFF:
            self._pending.append(now)
            del self._pending[:-MAX_PENDING]
        return out

    def on_ha_open(self, now: datetime) -> Emitted:
        """Une ouverture commandée depuis Home Assistant vient d'être acceptée."""
        self._ha_opens.append(now)
        del self._ha_opens[:-MAX_PENDING]
        # Verdict positif : on solde les ouvertures déjà en attente à proximité.
        self._pending = [p for p in self._pending if abs(p - now) > self.window]
        return []

    def on_journal(self, openings: list[datetime], now: datetime) -> Emitted:
        """Une lecture du journal vient de se terminer (mode ``journal``).

        ``openings`` = dates approximatives des ouvertures par code/badge vues
        dans ce drain. La lecture couvre tout jusqu'à ``now`` : toute porte
        encore en attente et sans correspondance est donc définitivement
        non autorisée.
        """
        if self.mode != MODE_JOURNAL:
            return []
        legit = openings + self._ha_opens
        out = [
            (EVENT_UNAUTHORIZED, at)
            for at in self._pending
            if not self._near(at, legit)
        ]
        self._pending = []
        return out

    def on_tick(self, now: datetime) -> Emitted:
        """Échéance de fenêtre (mode ``ha_command``) : tranche les portes en attente."""
        if self.mode != MODE_HA_COMMAND:
            return []
        out: Emitted = []
        keep: list[datetime] = []
        for at in self._pending:
            if now - at < self.window:
                keep.append(at)  # fenêtre pas encore écoulée
            elif not self._near(at, self._ha_opens):
                out.append((EVENT_UNAUTHORIZED, at))
        self._pending = keep
        return out
