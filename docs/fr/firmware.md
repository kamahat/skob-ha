> 🇬🇧 **[English version](../firmware/README.md)**

# Compiler et installer le proxy Bluetooth — pas à pas

Cette boîte aux lettres ferme toute connexion BLE après environ 30 secondes
sauf si le client continue d'échanger avec elle, et sa découverte de services
GATT ne se termine jamais dans cette fenêtre sous Bluedroid — la pile
utilisée par les proxys Bluetooth ESPHome standard. Sous **NimBLE**, la
découverte se termine en environ 6 secondes. Voir
[Pourquoi NimBLE](../README.md#why-nimble) dans le README principal pour
l'histoire complète.

**Depuis 2026-09, ce dépôt ne vendorise plus de firmware autonome.** Le proxy
est désormais un appareil **[ESPHome](https://esphome.io)** standard
utilisant [`kamahat/NimbleBLE-Esphome`](https://github.com/kamahat/NimbleBLE-Esphome),
un `external_component` clean-room qui remplace la pile Bluedroid native
d'ESPHome par NimBLE tout en gardant les mêmes classes/schéma de
configuration — donc il se compile et se flashe exactement comme n'importe
quel appareil ESPHome, avec les outils d'ESPHome lui-même (dashboard, CLI, ou
l'add-on ESPHome de Home Assistant), pas un projet ESP-IDF fait main. Pas
d'`idf.py`, pas de vendoring manuel de nanopb, pas de dashboard web maison à
vérifier via un endpoint `/stats.json` — le dashboard et les logs d'ESPHome
lui-même couvrent ce besoin.

À faire **une seule fois**, avant d'installer l'intégration Home Assistant.
Comptez 10 à 15 minutes.

| | |
|---|---|
| Bibliothèque NimBLE utilisée | [`kamahat/NimbleBLE-Esphome`](https://github.com/kamahat/NimbleBLE-Esphome) `v0.1.0` |
| Pourquoi une réécriture clean-room plutôt qu'un fork | [Son README](https://github.com/kamahat/NimbleBLE-Esphome#pourquoi) — même cause racine que la section "Why NimBLE" ci-dessus |
| Matériel à acheter et ses pièges | [`../docs/hardware.md`](../docs/hardware.md) |

---

## A. Installer ESPHome

Choisissez ce que vous utilisez déjà pour vos autres appareils :

- **Add-on Home Assistant** (le plus simple si HA tourne déjà avec le
  Supervisor) : Paramètres → Modules complémentaires → Boutique → cherchez
  **ESPHome**, installez, ouvrez l'interface web créée.
- **Autonome** : `pip install esphome` (nécessite Python ≥ 3.11), ou les
  [méthodes d'installation officielles](https://esphome.io/guides/installing_esphome).

Dans les deux cas vous obtenez le même dashboard/CLI ; la suite du guide
fonctionne à l'identique.

## B. Le fichier de configuration

Créez `nimble-boks-proxy.yaml` (via **New device** du dashboard — passez son
assistant et collez ceci à la place, ou directement dans un éditeur de texte
si vous utilisez la CLI) :

```yaml
esphome:
  name: nimble-boks-proxy

esp32:
  board: esp32-s3-devkitc-1
  framework:
    type: esp-idf

external_components:
  - source: github://kamahat/NimbleBLE-Esphome@v0.1.0
    components: [esp32_ble, nimble_ble, ble_device_base, esp32_ble_tracker,
                 bluetooth_connection, bluetooth_proxy]

esp32_ble_tracker:

bluetooth_proxy:
  active: true

wifi:
  ssid: !secret wifi_ssid
  password: !secret wifi_password

api:
  encryption:
    key: !secret nimble_boks_proxy_api_key

ota:
  platform: esphome
  password: !secret nimble_boks_proxy_ota_password

logger:
```

Deux points qui diffèrent de l'ancien firmware :

- **L'adresse Bluetooth de la boîte aux lettres ne se configure toujours pas
  ici** — comme avant, c'est un proxy générique qui relaie ce que Home
  Assistant lui demande. L'adresse de la boîte se choisit plus tard, à
  l'ajout de l'intégration Boks.
- **La connexion API est chiffrée Noise par défaut** (`api: encryption:`),
  pas en clair comme l'ancien firmware. Générez une clé avec
  `esphome secrets` ou n'importe quelle valeur base64 de 32 octets ;
  stockez-la (ainsi que le mot de passe OTA) en `!secret` comme n'importe
  quel autre identifiant Home Assistant. Si vous préférez rester en clair
  pour retrouver le comportement d'avant, retirez simplement le bloc
  `encryption:` — les deux fonctionnent avec l'intégration ESPHome de Home
  Assistant.

`board: esp32-s3-devkitc-1` et `framework: type: esp-idf` sont obligatoires —
ça ne compile que contre ESP-IDF, et seulement pour des cibles ESP32
supportant NimBLE (S3 recommandé ; voir [hardware.md](../docs/hardware.md)).

## C. Premier flash (par USB)

Depuis le dashboard : **Install** → **Plug into this computer** — ça compile
et flashe par USB, comme n'importe quel appareil ESPHome.

Depuis la CLI :

```bash
esphome run nimble-boks-proxy.yaml
```

La **première** compilation télécharge la toolchain ESP-IDF et prend
plusieurs minutes ; ESPHome la met en cache, donc les compilations
suivantes sont rapides.

La plupart des cartes ESP32-S3 exposent deux ports USB-C — utilisez celui du
**pont USB-série** (souvent sérigraphié `COM`/`UART`), pas le port USB natif
de la puce, pour ce premier flash. Si rien n'apparaît comme port série,
essayez d'abord un autre câble USB (les câbles charge-seule sont la cause la
plus fréquente).

## D. Les mises à jour suivantes passent par le WiFi (OTA)

Une fois l'appareil sur le réseau, plus besoin de câble :

```bash
esphome run nimble-boks-proxy.yaml
```

(ESPHome le retrouve automatiquement via mDNS, ou bascule sur les
identifiants OTA du fichier.) Depuis le dashboard, le bouton **Install** du
même appareil propose désormais **Wirelessly** au lieu de **Plug into this
computer**.

## Ajouter le proxy à Home Assistant

Comme avant : l'appareil s'annonce en mDNS comme un appareil ESPHome. Home
Assistant le détecte sous **Paramètres → Appareils et services** ; confirmez
(entrez la clé `api: encryption:` ci-dessus si vous en avez défini une).

Une fois ajouté, il s'enregistre comme scanner Bluetooth, et c'est **ça** qui
permet à l'intégration Boks d'atteindre la boîte aux lettres. Sans cette
étape l'intégration ne la trouvera jamais, aussi correctement installée
soit-elle par ailleurs.

## Dépannage

| Symptôme | Cause |
|---|---|
| `Component not found: esp32_ble_tracker` (ou similaire) | Un composant listé sous `external_components: components:` n'existe pas exactement sous ce nom — cette surcharge remplace tout son répertoire, un composant absent retombe silencieusement sur ESPHome standard (Bluedroid), qui ne découvrira **pas** les services de cette boîte à temps |
| Échec de compilation en téléchargeant la toolchain ESP-IDF | La première compilation a besoin d'un accès internet pour la récupérer ; réessayez, ou voir la [FAQ d'ESPHome](https://esphome.io/guides/faq) |
| `Failed to connect … No serial data received` | Mauvais port USB (voir partie **C**), ou mettez la carte en mode téléchargement à la main : maintenez `BOOT`, appuyez sur `RST`, relâchez `BOOT`, puis réessayez |
| Home Assistant ne le découvre jamais | mDNS bloqué entre VLAN ; ajoutez l'appareil par IP à la place |
| Boucle de redémarrage / `Guru Meditation Error` | Généralement un problème de PSRAM sur les cartes bon marché — voir [hardware.md](../docs/hardware.md) |

Pour tout ce qui concerne spécifiquement la pile NimBLE elle-même (pas
l'intégration de cette boîte), voir le `docs/` propre de
[`kamahat/NimbleBLE-Esphome`](https://github.com/kamahat/NimbleBLE-Esphome) —
en particulier `OVERRIDE_CAVEATS.md` (ce qui n'est volontairement pas repris
des composants ESPHome standard) et `HARDWARE_VALIDATION.md` (les vrais
tests d'acceptation faits contre cette boîte aux lettres précise).
