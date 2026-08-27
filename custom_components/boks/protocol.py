"""Encodage/décodage des trames applicatives Boks.

Format (docs/02-protocole-ble.md) :
    [opcode (1o)][longueur payload (1o)][payload (N o)][checksum (1o)]
Le checksum est la somme des octets de la trame hors checksum, masquée sur 8 bits.
"""
from __future__ import annotations

import logging
import re

from .const import (
    ALLOWED_TX_OPCODES,
    CONFIG_KEY_LENGTH,
    NFC_TAGTYPE_MIFARE,
    NFC_TAGTYPE_VIGIK,
    OPCODE_ASK_DOOR_STATUS,
    OPCODE_GET_LOGS_COUNT,
    OPCODE_LOG_CODE_KEY_VALID,
    OPCODE_LOG_NFC_OPENING,
    OPCODE_OPEN_DOOR,
    OPCODE_REBOOT,
    OPCODE_REGISTER_NFC_TAG,
    OPCODE_REGISTER_NFC_TAG_SCAN_START,
    OPCODE_REQUEST_LOGS,
    OPCODE_SET_CONFIGURATION,
    OPCODE_UNREGISTER_NFC_TAG,
    PIN_ALPHABET,
    PIN_LENGTH,
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

#: Redémarre la carte. Sans payload, sans réponse applicative attendue —
#: la boîte coupe simplement le lien en redémarrant (cf. const.OPCODE_REBOOT).
REBOOT_FRAME: bytes = build_frame(OPCODE_REBOOT)

#: Lecture de l'historique (lecture seule, sans authentification).
GET_LOGS_COUNT_FRAME: bytes = build_frame(OPCODE_GET_LOGS_COUNT)
REQUEST_LOGS_FRAME: bytes = build_frame(OPCODE_REQUEST_LOGS)


#: Catégories d'ouverture suivies, dans l'ordre de préférence d'affichage.
OPENING_KINDS: tuple[str, ...] = ("vigik", "mifare", "code")


def history_opening(opcode: int, payload: bytes) -> tuple[str, int] | None:
    """``(kind, age_secondes)`` d'un événement d'ouverture suivi, sinon ``None``.

    ``kind`` ∈ :data:`OPENING_KINDS`. Chaque événement commence par
    ``[age : 3 octets big-endian, secondes]`` — la boîte n'ayant pas d'horloge,
    la date se dérive par ``maintenant − age``.

    Formats (cf. docs/02) :
    - ``161`` NFC : ``[age:3][tagType:1][uidLen:1][uid]`` — ``tagType`` distingue
      ``vigik`` (``0x01``) de ``mifare`` (``0x03``) ; tout autre type est ignoré.
    - ``135`` code clavier : ``[age:3][code…]`` → ``code``.
    """
    if len(payload) < 3:
        return None
    age = int.from_bytes(payload[:3], "big")
    if opcode == OPCODE_LOG_NFC_OPENING:
        if len(payload) < 4:
            return None
        tagtype = payload[3]
        if tagtype == NFC_TAGTYPE_VIGIK:
            return "vigik", age
        if tagtype == NFC_TAGTYPE_MIFARE:
            return "mifare", age
        return None
    if opcode == OPCODE_LOG_CODE_KEY_VALID:
        return "code", age
    return None


def normalize_pin(pin: str) -> str:
    """Valide et normalise un code d'ouverture.

    Les PIN Boks font 6 caractères sur l'alphabet ``0123456789AB`` — douze
    symboles, pas seize : ``C`` à ``F`` n'en font pas partie. On vérifie ici
    plutôt qu'à l'usage, car un code mal saisi produirait une trame que la
    boîte peut **ignorer sans répondre**, ce qui se diagnostique très mal.
    """
    candidate = pin.strip().upper()
    if len(candidate) != PIN_LENGTH:
        raise ValueError(
            f"un code d'ouverture fait {PIN_LENGTH} caractères, celui-ci en a "
            f"{len(candidate)}"
        )
    invalid = sorted({c for c in candidate if c not in PIN_ALPHABET})
    if invalid:
        raise ValueError(
            f"caractères invalides {invalid} — alphabet autorisé : {PIN_ALPHABET}"
        )
    return candidate


def build_open_door_frame(pin: str) -> bytes:
    """Construit la commande d'ouverture pour un code donné."""
    return build_frame(OPCODE_OPEN_DOOR, normalize_pin(pin).encode("ascii"))


def normalize_config_key(key: str) -> str:
    """Valide et normalise une Config Key : exactement 8 caractères hexadécimaux.

    Vérifiée ici plutôt qu'à l'usage : une clé mal formée produirait une trame
    que la boîte refuse en ``225 UNAUTHORIZED``, sans indice clair.
    """
    candidate = key.strip().upper()
    if not re.fullmatch(rf"[0-9A-F]{{{CONFIG_KEY_LENGTH}}}", candidate):
        raise ValueError(
            f"une Config Key fait {CONFIG_KEY_LENGTH} caractères hexadécimaux"
        )
    return candidate


# --- Trames d'administration NFC / VIGIK -----------------------------------
# Formats reversés de l'app officielle (cf. docs/02). La Config Key part **en
# ASCII** dans le payload. Points non évidents, à ne PAS « corriger » :
#   - SCAN_START n'a NI préfixe 0x00 NI checksum (le 0x00 du SDK communautaire
#     décalait la clé et causait le 225) ;
#   - register/unregister terminent par l'octet d'opcode (pas une somme) ;
#   - set_configuration termine par (opcode + type + flag) & 0xFF.
# Ces builders sont dédiés (hors `build_frame`) et gatés par le coordinateur sur
# la présence d'une Config Key.


def build_scan_start_frame(config_key: str) -> bytes:
    """``REGISTER_NFC_TAG_SCAN_START`` (23) : ``[23, 8, …ASCII(clé)]``."""
    key = normalize_config_key(config_key).encode("ascii")
    return bytes([OPCODE_REGISTER_NFC_TAG_SCAN_START, len(key)]) + key


def build_register_nfc_frame(config_key: str, uid: bytes) -> bytes:
    """``REGISTER_NFC_TAG`` (24) : ``[24, 9+U, …ASCII(clé), U, …uid, 24]``."""
    key = normalize_config_key(config_key).encode("ascii")
    op = OPCODE_REGISTER_NFC_TAG
    return (
        bytes([op, len(key) + 1 + len(uid)]) + key + bytes([len(uid)]) + uid + bytes([op])
    )


def build_unregister_nfc_frame(config_key: str, uid: bytes) -> bytes:
    """``UNREGISTER_NFC_TAG`` (25) : même structure que register, opcode 25."""
    key = normalize_config_key(config_key).encode("ascii")
    op = OPCODE_UNREGISTER_NFC_TAG
    return (
        bytes([op, len(key) + 1 + len(uid)]) + key + bytes([len(uid)]) + uid + bytes([op])
    )


def build_set_configuration_frame(
    config_key: str, config_type: int, enabled: bool
) -> bytes:
    """``SET_CONFIGURATION`` (22) : ``[22, 10, …ASCII(clé), type, flag, cksum]``.

    ``cksum = (22 + type + flag) & 0xFF`` (ni la clé ni la longueur ne comptent —
    c'est le calcul exact de l'app).
    """
    key = normalize_config_key(config_key).encode("ascii")
    op = OPCODE_SET_CONFIGURATION
    flag = 1 if enabled else 0
    body = bytes([op, len(key) + 2]) + key + bytes([config_type, flag])
    return body + bytes([(op + config_type + flag) & 0xFF])


def parse_uid(uid_hex: str) -> bytes:
    """Convertit un UID hexadécimal (``04A1B2C3`` ou ``04:A1:B2:C3``) en octets."""
    cleaned = re.sub(r"[\s:]", "", uid_hex).upper()
    if not re.fullmatch(r"(?:[0-9A-F]{2})+", cleaned):
        raise ValueError("UID invalide : attendu des octets hexadécimaux")
    return bytes.fromhex(cleaned)


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
