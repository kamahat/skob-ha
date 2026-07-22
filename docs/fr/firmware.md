> 🇬🇧 **[English version](../firmware.md)**

# Compiler et flasher le proxy Bluetooth

Le firmware se trouve dans [`firmware/nimble-ble-proxy/`](../../firmware/nimble-ble-proxy/).
C'est une copie vendorée de [`fl4p/nimble-ble-proxy-esphome`](https://github.com/fl4p/nimble-ble-proxy-esphome)
— voir [`NOTICE.md`](../../firmware/nimble-ble-proxy/NOTICE.md) pour
l'attribution et l'unique correctif de portabilité appliqué.

Il se présente à Home Assistant comme un **proxy Bluetooth ESPHome standard**,
mais utilise la pile **NimBLE** au lieu de Bluedroid — ce qui est précisément ce
qui rend cette boîte exploitable (voir *Pourquoi NimBLE* dans le README).

## Prérequis

- **ESP-IDF v5.5** (5.x devrait convenir) — [guide d'installation](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32s3/get-started/).
- Une carte **ESP32-S3** — voir [matériel](hardware.md).
- Python avec `protobuf` disponible dans l'environnement IDF.

## Compilation

```bash
cd firmware/nimble-ble-proxy
```

### 1. Identifiants WiFi

```bash
cp include/wifi_creds.h.example include/wifi_creds.h
# éditez include/wifi_creds.h : SSID et mot de passe de votre réseau 2,4 GHz
```

Ce fichier est **gitignoré** et volontairement absent du dépôt. Utilisez un
réseau 2,4 GHz — l'ESP32-S3 n'a pas de radio 5 GHz.

### 2. Vendorer nanopb

Les bindings protobuf sont générés à la compilation par nanopb, qui n'est
**pas** embarqué (il a sa propre licence) :

```bash
cd components/api_proto
git clone --depth 1 https://github.com/nanopb/nanopb.git nanopb
cd ../..
```

La compilation de référence utilisait le commit nanopb
`d21fa5084287ab67da2f166f4def045bedcb535e`.

### 3. Dépendance Python

```bash
pip install protobuf
```

Installez-la **dans l'environnement Python d'ESP-IDF** (donc après avoir sourcé
`export.sh` / `export.ps1`).

### 4. Définir la cible — commande isolée

```bash
idf.py set-target esp32s3
grep CONFIG_IDF_TARGET= sdkconfig     # doit afficher esp32s3
```

> ⚠️ **Lancez cette commande seule et vérifiez le résultat.** Enchaînée à une
> compilation qui échoue au stade *configure*, la cible reste silencieusement à
> la valeur par défaut `esp32`. Les compilations suivantes réussissent alors mais
> produisent une image pour la mauvaise puce, et le flash échoue avec
> *« This chip is ESP32-S3, not ESP32 »*. Le cas échéant : `idf.py fullclean`,
> puis redéfinissez la cible.

### 5. Compiler et flasher

```bash
idf.py build
idf.py -p /dev/ttyUSB0 flash        # Linux/macOS
idf.py -p COM12 flash               # Windows
```

Utilisez le port **`COM`/UART** de la carte, pas le port USB natif — voir
[matériel](hardware.md#ports-usb--le-piège-classique).

Observez le démarrage avec `idf.py -p <port> monitor` : vous devez voir
l'adresse WiFi, `NimBLE ready`, et un point de terminaison OTA sur le port 80.

Les mises à jour suivantes passent en WiFi, sans câble :

```bash
curl --data-binary @build/nimble_ble_proxy.bin http://<ip-appareil>/update
```

## Configuration recommandée

Le firmware sait aussi faire routeur WiFi (SoftAP + NAT). **Désactivez-le** :
ici la carte n'est qu'un pont, et un SoftAP vole du temps d'antenne au Bluetooth
sur l'unique radio 2,4 GHz (il biaise en outre l'arbitre de coexistence vers le
WiFi) :

```bash
curl -X POST "http://<ip-appareil>/nat?enabled=0"
```

Le réglage persiste au redémarrage.

> Les points de configuration exigent **`curl -X POST`**. Un `curl` simple est un
> GET : il se contente de relire la valeur courante sans rien appliquer.

## Points de terminaison utiles

| Endpoint | Rôle |
|---|---|
| `GET /` | Tableau de bord web |
| `GET /stats.json` | Santé : mémoire, température, compteurs BLE |
| `GET /devices` | Appareils Bluetooth vus, avec RSSI — pratique pour le placement |
| `GET /log?since=0` | Journal du firmware (débogage à distance) |
| `POST /level?nimble=<0..5>` | Verbosité des logs NimBLE |
| `POST /update` | Mise à jour OTA |
| `POST /reboot` | Redémarrage |

## Déclarer le proxy dans Home Assistant

Le firmware s'annonce en mDNS comme un appareil ESPHome. Home Assistant le
détecte dans **Paramètres → Appareils et services** ; confirmez-le (API en clair,
sans clé de chiffrement). Il s'enregistre alors comme scanner Bluetooth, ce qui
permet à l'intégration Boks d'atteindre la boîte.
