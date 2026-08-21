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

# --- Historique (lecture seule) --------------------------------------------
# La boîte tient un journal d'événements, lisible SANS authentification :
# REQUEST_LOGS/GET_LOGS_COUNT ont un payload vide (pas de Config Key). Elle
# streame ses événements du plus ancien au plus récent, clos par LOG_END_HISTORY.
# Chaque événement porte un `age` = uint24 big-endian en secondes (pas de RTC) ;
# on en dérive une date ≈ maintenant − age. Cf. docs/02-protocole-ble.md.
OPCODE_GET_LOGS_COUNT: Final = 7
OPCODE_REQUEST_LOGS: Final = 3
OPCODE_NOTIFY_LOGS_COUNT: Final = 121
OPCODE_LOG_CODE_KEY_VALID: Final = 135  # ouverture par code au clavier
OPCODE_LOG_DOOR_CLOSE: Final = 144
OPCODE_LOG_DOOR_OPEN: Final = 145
OPCODE_LOG_END_HISTORY: Final = 146
OPCODE_LOG_NFC_OPENING: Final = 161     # ouverture par badge NFC (VIGIK ou Mifare)
#: Ensemble des opcodes émis par la boîte pendant un flux d'historique.
HISTORY_EVENT_OPCODES: Final = frozenset(range(134, 163)) | {OPCODE_NOTIFY_LOGS_COUNT}
#: `tagType` d'un événement NFC : 0x01 = LaPosteNfc (VIGIK), 0x03 = Mifare associé.
NFC_TAGTYPE_VIGIK: Final = 0x01
NFC_TAGTYPE_MIFARE: Final = 0x03

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

# Périmètre volontairement restreint. L'intégration lit l'état de la boîte,
# lit son historique (opérations de LECTURE), et — si l'utilisateur a configuré
# un code — sait ouvrir la porte. Rien d'autre : aucune gestion de codes
# (16-19), aucune modification de configuration (22), aucun provisioning
# (32-33). Ces opérations exigent la Config Key / Master Key du propriétaire et
# sont, pour certaines, irréversibles — le constructeur de trames refuse leurs
# opcodes par construction, pas par convention.
ALLOWED_TX_OPCODES: Final = frozenset(
    {
        OPCODE_ASK_DOOR_STATUS,
        OPCODE_TEST_BATTERY,
        OPCODE_OPEN_DOOR,
        OPCODE_GET_LOGS_COUNT,
        OPCODE_REQUEST_LOGS,
    }
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
#: Intervalle (minutes) de relecture de l'historique (VIGIK / code) — dans les
#: deux régimes : en connexion tenue, une re-demande périodique dans la même
#: session (sinon l'historique n'est lu qu'une fois, à la connexion) ; lien
#: non tenu, une connexion brève dédiée. Objectif : reproduire ce que fait le
#: BoksLINK officiel — surveillance continue — mais en poussant vers Home
#: Assistant plutôt que vers le cloud Boks. 0 = désactivé.
#:
#: ⚠️ Défaut **0** volontairement : lire l'historique **draine** le journal de
#: la boîte (curseur persistant), et ce journal sert de **backlog au BoksLINK
#: officiel** quand il est hors ligne. Un drain périodique local risquerait de
#: lui **voler des événements** → ouvertures manquantes dans l'historique cloud
#: officiel. Sans incidence tant que le BoksLINK reste débranché/hors ligne —
#: mais reste un choix explicite de l'utilisateur, pas un défaut.
CONF_REFRESH_INTERVAL: Final = "refresh_interval"
REFRESH_INTERVAL_DEFAULT: Final = 0
REFRESH_INTERVAL_MIN: Final = 0
REFRESH_INTERVAL_MAX: Final = 1440

#: Le watchdog applicatif de la Boks ferme la connexion vers 30 s de silence.
#: On garde une marge : au-delà, le lien tombe entre deux keepalives et se
#: reconnecte en boucle — ce qui consomme bien plus que de le tenir.
KEEPALIVE_MIN: Final = 5.0
KEEPALIVE_MAX: Final = 28.0
RECONNECT_MAX_MIN: Final = 30.0
RECONNECT_MAX_MAX: Final = 900.0
