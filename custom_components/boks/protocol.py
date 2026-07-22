"""Encodage/décodage des trames applicatives Boks.

Format (docs/02-protocole-ble.md) :
    [opcode (1o)][longueur payload (1o)][payload (N o)][checksum (1o)]
Le checksum est la somme des octets de la trame hors checksum, masquée sur 8 bits.
"""
from __future__ import annotations

import logging

from .const import (
    ALLOWED_TX_OPCODES,
    OPCODE_ASK_DOOR_STATUS,
)

_LOGGER = logging.getLogger(__name__)


def build_frame(opcode: int, payload: bytes = b"") -> bytes:
    """Construit une trame. Refuse tout opcode hors du périmètre lecture."""
    if opcode not in ALLOWED_TX_OPCODES:
        raise ValueError(
            f"opcode {opcode} hors du périmètre autorisé {sorted(ALLOWED_TX_OPCODES)}"
        )
    body = bytes([opcode, len(payload)]) + payload
    return body + bytes([sum(body) & 0xFF])


#: Requête d'état de la porte — sert aussi de keepalive (cf. const.KEEPALIVE_INTERVAL).
ASK_DOOR_STATUS_FRAME: bytes = build_frame(OPCODE_ASK_DOOR_STATUS)


def parse_frame(data: bytes) -> tuple[int, bytes] | None:
    """Décode une trame reçue. Renvoie ``(opcode, payload)`` ou ``None``."""
    if len(data) < 3:
        return None
    opcode, length = data[0], data[1]
    if len(data) < length + 3:
        _LOGGER.debug("trame tronquée: %s", data.hex())
        return None
    payload = data[2 : 2 + length]
    expected = sum(data[: length + 2]) & 0xFF
    if data[length + 2] != expected:
        _LOGGER.warning(
            "checksum invalide (attendu %02x): %s", expected, data.hex()
        )
        return None
    return opcode, payload


def door_is_open(payload: bytes) -> bool | None:
    """Interprète le payload d'un (NOTIFY|ANSWER)_DOOR_STATUS.

    Le payload fait 2 octets ``[inverted, raw]`` et le SDK définit
    ``isOpen = (raw is True and inverted is False)``.

    Validé sur appareil réel le 2026-07-22 : ``01 00`` = fermée,
    ``00 01`` = ouverte (relevé en ouvrant physiquement le volet).
    """
    if len(payload) < 2:
        return None
    inverted, raw = payload[0], payload[1]
    return raw == 1 and inverted == 0
