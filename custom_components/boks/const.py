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

# --- Ouverture à distance --------------------------------------------------
# Contrairement au reste, ouvrir exige un secret. Il n'y a cependant AUCUN
# handshake chiffré sur le lien Boks : la commande transporte simplement un
# code PIN de 6 caractères que la boîte valide elle-même, et répond 129 ou 130.
# Le secret est donc le code, pas une session.
OPCODE_OPEN_DOOR: Final = 1
OPCODE_VALID_OPEN_CODE: Final = 129
OPCODE_INVALID_OPEN_CODE: Final = 130

#: Identifiant lisible de la boîte (ex. « F540 »). La Boks ne l'expose pas :
#: son Serial Number GATT (0x2A25) renvoie sa propre adresse MAC, et aucune
#: characteristic ne porte cette référence — elle vient de l'étiquette ou du
#: compte. Elle doit donc être saisie, et sert à distinguer plusieurs boîtes.
CONF_LABEL: Final = "label"

CONF_OPEN_CODE: Final = "open_code"
#: Le champ accepte aussi une référence vers ``secrets.yaml``, avec la syntaxe
#: que les utilisateurs connaissent déjà. Home Assistant ne résout pas
#: ``!secret`` dans les entrées de configuration : on le fait nous-mêmes
#: (cf. secret.py), pour que le code n'ait pas à être recopié dans .storage.
SECRET_PREFIX: Final = "!secret "
#: Les PIN Boks s'écrivent sur douze symboles seulement — pas de C à F.
PIN_ALPHABET: Final = "0123456789AB"
PIN_LENGTH: Final = 6
#: Attente de la réponse 129/130. Généreux : lien coupé, il faut d'abord
#: établir la connexion.
OPEN_TIMEOUT: Final = 30.0

# Périmètre volontairement restreint. L'intégration lit l'état de la boîte
# et, si — et seulement si — l'utilisateur a configuré un code, sait ouvrir la
# porte. Rien d'autre : aucune gestion de codes (16-19), aucune modification
# de configuration (22), aucun provisioning (32-33). Ces opérations exigent la
# Config Key / Master Key du propriétaire et sont, pour certaines,
# irréversibles — le constructeur de trames refuse leurs opcodes par
# construction, pas par convention.
ALLOWED_TX_OPCODES: Final = frozenset(
    {OPCODE_ASK_DOOR_STATUS, OPCODE_TEST_BATTERY, OPCODE_OPEN_DOOR}
)

# --- Liaison ---------------------------------------------------------------
# La Boks applique un watchdog applicatif : elle ferme la connexion au bout
# d'environ 30 s si le central n'échange rien. Un ASK_DOOR_STATUS périodique
# réarme ce watchdog ET renvoie l'état de la porte.
KEEPALIVE_INTERVAL: Final = 20.0
RECONNECT_DELAY_MIN: Final = 5.0
RECONNECT_DELAY_MAX: Final = 120.0

CONF_ADDRESS: Final = "address"

# --- Batterie --------------------------------------------------------------
# La Boks ne publie pas de tension : elle expose la caractéristique standard
# 0x2A19, c'est-à-dire un pourcentage qu'elle a elle-même dérivé de la tension
# du pack sur une courbe d'alcaline (~1,6 V pleine → ~0,9 V vide).
#
# Ce chiffre n'a donc de sens QUE pour des piles non régulées. Les lithium
# rechargeables 1,5 V embarquent un convertisseur qui maintient 1,5 V plat
# jusqu'à la coupure de leur protection : la tension ne porte plus aucune
# information d'état de charge, et la jauge reste collée en haut d'échelle
# avant de s'effondrer d'un coup. Aucun calcul ne peut restituer ce que la
# mesure ne contient pas — on change donc l'interprétation, pas la valeur.
BATTERY_LOW_ALKALINE: Final = 20
#: En mode régulé, on ne peut plus lire un niveau : on ne peut que détecter le
#: décrochage. Toute baisse durable sous le plateau observé signale une fin de
#: vie imminente, pas « il en reste les trois quarts ».
BATTERY_SAG_REGULATED: Final = 3
#: L'ouverture de la porte sollicite le moteur et fait plonger la tension le
#: temps de la manœuvre : la Boks a déjà publié 0 % dans ces conditions. Une
#: chute d'au moins cette amplitude doit être confirmée par une seconde lecture
#: avant d'être retenue.
BATTERY_TRANSIENT_DROP: Final = 10

# --- Options (réglables depuis l'interface, sans redémarrage) ---------------
CONF_KEEPALIVE: Final = "keepalive"
CONF_RECONNECT_MAX: Final = "reconnect_max"

#: Le watchdog applicatif de la Boks ferme la connexion vers 30 s de silence.
#: On garde une marge : au-delà, le lien tombe entre deux keepalives et se
#: reconnecte en boucle — ce qui consomme bien plus que de le tenir.
KEEPALIVE_MIN: Final = 5.0
KEEPALIVE_MAX: Final = 28.0
RECONNECT_MAX_MIN: Final = 30.0
RECONNECT_MAX_MAX: Final = 900.0
