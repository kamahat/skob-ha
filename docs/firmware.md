> 🇫🇷 **[Version française](fr/firmware.md)**

# Building and flashing the Bluetooth proxy

The firmware lives in [`firmware/nimble-ble-proxy/`](../firmware/nimble-ble-proxy/).
It is a vendored copy of [`fl4p/nimble-ble-proxy-esphome`](https://github.com/fl4p/nimble-ble-proxy-esphome)
— see [`NOTICE.md`](../firmware/nimble-ble-proxy/NOTICE.md) for attribution and
the one portability change applied.

It presents itself to Home Assistant as a **standard ESPHome Bluetooth proxy**,
but uses the **NimBLE** stack instead of Bluedroid, which is what makes this
mailbox usable (see *Why NimBLE* in the main README).

## Prerequisites

- **ESP-IDF v5.5** (5.x should work) — [installation guide](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32s3/get-started/).
- An **ESP32-S3** board — see [hardware](hardware.md).
- Python with `protobuf` available in the IDF environment.

## Build

```bash
cd firmware/nimble-ble-proxy
```

### 1. WiFi credentials

```bash
cp include/wifi_creds.h.example include/wifi_creds.h
# edit include/wifi_creds.h and fill in your 2.4 GHz SSID and password
```

This file is **gitignored** and is deliberately not shipped. Use a 2.4 GHz
network — the ESP32-S3 has no 5 GHz radio.

### 2. Vendor nanopb

The protobuf bindings are generated at build time by nanopb, which is **not**
bundled (it carries its own license):

```bash
cd components/api_proto
git clone --depth 1 https://github.com/nanopb/nanopb.git nanopb
cd ../..
```

Reference build used nanopb commit `d21fa5084287ab67da2f166f4def045bedcb535e`.

### 3. Python dependency

```bash
pip install protobuf
```

Install it **in the ESP-IDF Python environment** (run this after sourcing
`export.sh` / `export.ps1`).

### 4. Set the target — on its own

```bash
idf.py set-target esp32s3
grep CONFIG_IDF_TARGET= sdkconfig     # must print esp32s3
```

> ⚠️ **Run this as a separate command and check the result.** If you chain it
> with a build that fails during *configure*, the target silently stays at the
> default `esp32`. Later builds then succeed but produce an image for the wrong
> chip, and flashing fails with *"This chip is ESP32-S3, not ESP32"*. If that
> happens: `idf.py fullclean`, then set the target again.

### 5. Build and flash

```bash
idf.py build
idf.py -p /dev/ttyUSB0 flash        # Linux/macOS
idf.py -p COM12 flash               # Windows
```

Use the **`COM`/UART port** of the board, not the native USB port — see
[hardware](hardware.md#usb-ports--a-common-pitfall).

Watch the boot log with `idf.py -p <port> monitor`. You should see the WiFi
address, `NimBLE ready`, and an OTA endpoint on port 80.

Subsequent updates can go over WiFi, no cable needed:

```bash
curl --data-binary @build/nimble_ble_proxy.bin http://<device-ip>/update
```

## Recommended configuration

The firmware can also act as a WiFi router (SoftAP + NAT). **Turn that off** —
here the board is only a bridge, and a SoftAP steals airtime from Bluetooth on
the single 2.4 GHz radio (it also biases the coexistence arbiter towards WiFi):

```bash
curl -X POST "http://<device-ip>/nat?enabled=0"
```

The setting persists across reboots.

> Configuration endpoints require **`curl -X POST`**. A plain `curl` is a GET
> and only reads the current value back without applying anything.

## Useful endpoints

| Endpoint | Purpose |
|---|---|
| `GET /` | Web dashboard |
| `GET /stats.json` | Health: heap, temperature, BLE counters |
| `GET /devices` | Bluetooth devices seen, with RSSI — handy for placement |
| `GET /log?since=0` | Firmware log (remote debugging) |
| `POST /level?nimble=<0..5>` | NimBLE log verbosity |
| `POST /update` | OTA update |
| `POST /reboot` | Reboot |

## Adding the proxy to Home Assistant

The firmware announces itself over mDNS as an ESPHome device. Home Assistant
discovers it under **Settings → Devices & services**; confirm it (plaintext
API, no encryption key). It then registers as a Bluetooth scanner, which is what
lets the Boks integration reach the mailbox.
