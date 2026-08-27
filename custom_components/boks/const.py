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
#: Redémarre la carte de la Boks. Sans payload — trame [6, 0, 6]. Aucune
#: réponse applicative attendue (contrairement à OPEN_DOOR) : la boîte coupe
#: simplement le lien en redémarrant.
OPCODE_REBOOT: Final = 6
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

# --- Administration NFC / VIGIK (authentifié par Config Key) ----------------
# Enregistrer/révoquer un badge Mifare et activer le VIGIK. Ces opérations
# s'authentifient par la **Config Key** (8 hex), transmise **en ASCII** dans le
# payload — format reversé de l'app officielle (cf. docs/02). Pas de session
# chiffrée : le lien reste en clair, seul le format compte. Un `0x00` parasite
# (présent dans le SDK communautaire) décalait la clé → 225 UNAUTHORIZED ; le
# format correct n'a ni ce préfixe ni checksum pour SCAN_START.
OPCODE_SET_CONFIGURATION: Final = 22
OPCODE_REGISTER_NFC_TAG_SCAN_START: Final = 23
OPCODE_REGISTER_NFC_TAG: Final = 24
OPCODE_UNREGISTER_NFC_TAG: Final = 25
#: Réponses de la boîte aux opérations NFC.
OPCODE_NOTIFY_NFC_TAG_FOUND: Final = 197
OPCODE_ERROR_NFC_TAG_ALREADY_EXISTS_SCAN: Final = 198
OPCODE_ERROR_NFC_SCAN_TIMEOUT: Final = 199
OPCODE_NOTIFY_NFC_TAG_REGISTERED: Final = 200
OPCODE_NOTIFY_NFC_TAG_REGISTERED_ERROR_ALREADY_EXISTS: Final = 201
OPCODE_NOTIFY_NFC_TAG_UNREGISTERED: Final = 202
OPCODE_ERROR_UNAUTHORIZED: Final = 225
#: Réponses aux opérations NFC/admin — routées vers la Future en attente.
NFC_RESPONSE_OPCODES: Final = frozenset(
    {
        OPCODE_NOTIFY_NFC_TAG_FOUND,
        OPCODE_ERROR_NFC_TAG_ALREADY_EXISTS_SCAN,
        OPCODE_ERROR_NFC_SCAN_TIMEOUT,
        OPCODE_NOTIFY_NFC_TAG_REGISTERED,
        OPCODE_NOTIFY_NFC_TAG_REGISTERED_ERROR_ALREADY_EXISTS,
        OPCODE_NOTIFY_NFC_TAG_UNREGISTERED,
        OPCODE_ERROR_UNAUTHORIZED,
    }
)
#: Type de configuration `SET_CONFIGURATION` pour le VIGIK (LaPosteNfc).
NFC_CONFIG_TYPE_LAPOSTE: Final = 0x01
#: Attente d'un badge présenté au clavier pendant l'enrôlement. La boîte a sa
#: propre fenêtre de scan (~30 s) ; on attend un peu plus.
NFC_SCAN_TIMEOUT: Final = 40.0
#: Attente de l'accusé d'une écriture admin (register/unregister/config).
ADMIN_ACK_TIMEOUT: Final = 30.0

CONF_CONFIG_KEY: Final = "config_key"
#: Longueur de la Config Key : exactement 8 caractères hexadécimaux.
CONFIG_KEY_LENGTH: Final = 8
#: Valeur proposée par défaut dans le formulaire : la Config Key doit rester
#: dans secrets.yaml, on pré-remplit donc la référence recommandée.
DEFAULT_CONFIG_KEY_SECRET: Final = "!secret boks_config_key"

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

# Périmètre du constructeur de trames **générique** (`build_frame`) : lecture +
# ouverture. Il refuse tout autre opcode par construction. Les opérations d'admin
# NFC/VIGIK (22-25) NE passent PAS par lui : elles ont des constructeurs dédiés
# (`build_scan_start_frame`…), appelés uniquement par le coordinateur **quand une
# Config Key est configurée**. Gestion de codes (16-19) et provisioning (32-33)
# restent, eux, hors d'atteinte.
ALLOWED_TX_OPCODES: Final = frozenset(
    {
        OPCODE_ASK_DOOR_STATUS,
        OPCODE_TEST_BATTERY,
        OPCODE_OPEN_DOOR,
        OPCODE_GET_LOGS_COUNT,
        OPCODE_REQUEST_LOGS,
        OPCODE_REBOOT,
    }
)

# --- Liaison ---------------------------------------------------------------
# La Boks applique un watchdog applicatif : elle ferme la connexion au bout
# d'environ 30 s si le central n'échange rien. Un ASK_DOOR_STATUS périodique
# réarme ce watchdog ET renvoie l'état de la porte.
KEEPALIVE_INTERVAL: Final = 20.0
RECONNECT_DELAY_MIN: Final = 5.0
RECONNECT_DELAY_MAX: Final = 120.0

#: Anti-rebond du bouton reboot. Le redémarrage matériel de la carte prend au
#: moins ~40 s ; un second appui avant ce délai n'aurait pratiquement aucune
#: chance d'aboutir (boîte déjà en train de couper/recharger son firmware) et
#: ne ferait qu'ajouter du bruit sur un lien de toute façon en train de tomber.
REBOOT_DEBOUNCE: Final = 60.0

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
