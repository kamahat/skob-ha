"""Capteurs Zigbee optionnels associés à une Boks : porte et volet à courrier.

Le lien BLE de la Boks est intermittent (voir ``REFRESH_INTERVAL_DEFAULT``) :
son entité « Porte » est donc souvent périmée. Un capteur de contact externe
donne, lui, l'ouverture **en temps réel**. Ce module suit ces capteurs, en tire
les événements courrier (cf. ``mail_logic``) et les publie vers les entités.

Tout est optionnel : sans capteur associé, ``BoksLink.tracker`` reste ``None``
et rien de ce module n'est instancié.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.core import State
from homeassistant.helpers.event import async_call_later, async_track_state_change_event
from homeassistant.util import dt as dt_util

from .coordinator import BoksLink
from .mail_logic import (
    EVENT_COLLECTED,
    EVENT_DEPOSITED,
    EVENT_UNAUTHORIZED,
    MODE_HA_COMMAND,
    MailLogic,
)

_LOGGER = logging.getLogger(__name__)

#: Événement → attribut de ``BoksState`` qui mémorise sa dernière date.
_EVENT_ATTR: dict[str, str] = {
    EVENT_DEPOSITED: "last_mail_deposit",
    EVENT_COLLECTED: "last_mail_collect",
    EVENT_UNAUTHORIZED: "last_unauthorized_opening",
}


def _as_bool(state: State | None) -> bool | None:
    """``on``/``off`` → bool ; tout le reste (unknown, unavailable, absent) → None."""
    if state is None:
        return None
    if state.state == "on":
        return True
    if state.state == "off":
        return False
    return None


class BoksSensorTracker:
    """Suit les capteurs associés et diffuse les événements courrier."""

    def __init__(
        self,
        hass: HomeAssistant,
        link: BoksLink,
        door_entity: str | None,
        flap_entity: str | None,
        mode: str,
        window: float,
    ) -> None:
        self.hass = hass
        self.link = link
        self.door_entity = door_entity
        self.flap_entity = flap_entity
        self.logic = MailLogic(mode, window)
        self._window = window
        self._listeners: list[Callable[[str, datetime], None]] = []
        self._unsubs: list[CALLBACK_TYPE] = []

    # -- état miroir ------------------------------------------------------
    @property
    def door_state(self) -> bool | None:
        return _as_bool(self.hass.states.get(self.door_entity)) if self.door_entity else None

    @property
    def flap_state(self) -> bool | None:
        return _as_bool(self.hass.states.get(self.flap_entity)) if self.flap_entity else None

    # -- cycle de vie -----------------------------------------------------
    @callback
    def async_start(self) -> None:
        """Abonne le suivi. L'état initial est lu sans produire d'événement."""
        now = dt_util.utcnow()
        watched = [e for e in (self.door_entity, self.flap_entity) if e]
        # Premier passage : prev=None, donc jamais un front.
        self.logic.on_door(self.door_state, now)
        self.logic.on_flap(self.flap_state, now)
        if watched:
            self._unsubs.append(
                async_track_state_change_event(self.hass, watched, self._on_change)
            )
        self.link.on_ha_open = self._on_ha_open
        self.link.on_history = self._on_history

    @callback
    def async_stop(self) -> None:
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        self.link.on_ha_open = None
        self.link.on_history = None

    @callback
    def async_add_event_listener(
        self, listener: Callable[[str, datetime], None]
    ) -> CALLBACK_TYPE:
        """Abonne l'entité ``event`` aux événements courrier."""
        self._listeners.append(listener)

        def _remove() -> None:
            if listener in self._listeners:
                self._listeners.remove(listener)

        return _remove

    # -- entrées ------------------------------------------------------------
    @callback
    def _on_change(self, event: Event) -> None:
        now = dt_util.utcnow()
        entity_id = event.data["entity_id"]
        new = _as_bool(event.data.get("new_state"))
        if entity_id == self.door_entity:
            emitted = self.logic.on_door(new, now)
            if self.logic.mode == MODE_HA_COMMAND and emitted:
                # Tranche l'ouverture une fois la fenêtre écoulée.
                self._unsubs.append(
                    async_call_later(self.hass, self._window + 1, self._on_tick)
                )
        else:
            emitted = self.logic.on_flap(new, now)
        self._publish(emitted)
        self.link.async_notify()  # rafraîchit les entités miroir

    @callback
    def _on_tick(self, _now: datetime) -> None:
        self._publish(self.logic.on_tick(dt_util.utcnow()))

    @callback
    def _on_ha_open(self, at: datetime) -> None:
        self._publish(self.logic.on_ha_open(at))

    @callback
    def _on_history(self, openings: list[datetime], now: datetime) -> None:
        self._publish(self.logic.on_journal(openings, now))

    # -- sortie -------------------------------------------------------------
    @callback
    def _publish(self, emitted: list[tuple[str, datetime]]) -> None:
        for kind, at in emitted:
            _LOGGER.debug("événement courrier %s à %s", kind, at)
            attr = _EVENT_ATTR[kind]
            current = getattr(self.link.state, attr)
            if current is None or at > current:
                setattr(self.link.state, attr, at)
            for listener in list(self._listeners):
                listener(kind, at)
        if emitted:
            self.link.async_notify()
