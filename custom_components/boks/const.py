"""Constantes de l'intégration Boks.

Protocole établi par rétro-ingénierie (cf. docs/02-protocole-ble.md) et validé
sur appareil réel le 2026-07-22.
"""
from __future__ import annotations

from typing import Final

DOMAIN: Final = "boks"

# --- GATT ------------------------------------------------------------------
SERVICE_UUID: Final = "a7630001-f491-4f21-95ea-846ba586e361"
WRITE_UUID: Final = "a7630002-f491-4f21-95ea-846ba586e361"
NOTIFY_UUID: Final = "a7630003-f491-4f21-95ea-846ba586e361"

BATTERY_UUID: Final = "00002a19-0000-1000-8000-00805f9b34fb"
FIRMWARE_UUID: Final = "00002a26-0000-1000-8000-00805f9b34fb"
SOFTWARE_UUID: Final = "00002a28-0000-1000-8000-00805f9b34fb"

# --- Trames applicatives ---------------------------------------------------
# [opcode][longueur payload][payload][checksum], checksum = somme & 0xFF.
OPCODE_ASK_DOOR_STATUS: Final = 2
OPCODE_TEST_BATTERY: Final = 8
OPCODE_NOTIFY_DOOR_STATUS: Final = 132
OPCODE_ANSWER_DOOR_STATUS: Final = 133

# Périmètre volontairement restreint : cette intégration est en LECTURE.
# Les seules trames émises sont des requêtes de statut. Aucune commande
# d'ouverture (OPEN_DOOR=1), aucune gestion de codes (16-19), aucune
# modification de configuration (22) — ces opérations exigeraient la
# Config Key / Master Key du propriétaire et sortent du périmètre.
ALLOWED_TX_OPCODES: Final = frozenset({OPCODE_ASK_DOOR_STATUS, OPCODE_TEST_BATTERY})

# --- Liaison ---------------------------------------------------------------
# La Boks applique un watchdog applicatif : elle ferme la connexion au bout
# d'environ 30 s si le central n'échange rien. Un ASK_DOOR_STATUS périodique
# réarme ce watchdog ET renvoie l'état de la porte.
KEEPALIVE_INTERVAL: Final = 20.0
RECONNECT_DELAY_MIN: Final = 5.0
RECONNECT_DELAY_MAX: Final = 120.0

CONF_ADDRESS: Final = "address"
