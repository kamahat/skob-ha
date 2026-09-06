> 🇫🇷 **[Version française](../docs/fr/firmware.md)**

# Building and installing the Bluetooth proxy — step by step

This mailbox closes any BLE connection after roughly 30 seconds unless the
client keeps exchanging with it, and its GATT service discovery never
completes within that window on Bluedroid — the stack stock ESPHome
Bluetooth proxies use. On **NimBLE**, discovery completes in about 6 seconds.
See [Why NimBLE](../README.md#why-nimble) in the main README for the full
story.

**As of 2026-09, this repository no longer vendors a standalone firmware.**
The proxy is now a standard **[ESPHome](https://esphome.io) device** using
[`kamahat/NimbleBLE-Esphome`](https://github.com/kamahat/NimbleBLE-Esphome),
a clean-room `external_component` that swaps ESPHome's own Bluedroid stack for
NimBLE while keeping the same classes/config schema — so it is built and
flashed exactly like any other ESPHome device, with ESPHome's own tools
(dashboard, CLI, or the Home Assistant ESPHome add-on), not a hand-rolled
ESP-IDF project. No `idf.py`, no vendoring nanopb by hand, no custom web
dashboard to check a `/stats.json` endpoint — ESPHome's own dashboard and
logs cover that ground.

You need to do this **once**, before installing the Home Assistant
integration. Plan for 10–15 minutes.

| | |
|---|---|
| The NimBLE library used | [`kamahat/NimbleBLE-Esphome`](https://github.com/kamahat/NimbleBLE-Esphome) `v0.1.0` |
| Why a clean-room rewrite instead of a fork | [Its README](https://github.com/kamahat/NimbleBLE-Esphome#pourquoi) — same root cause as the "Why NimBLE" section above |
| Hardware to buy and its pitfalls | [`../docs/hardware.md`](../docs/hardware.md) |

---

## A. Install ESPHome

Pick whichever you already use for other devices:

- **Home Assistant add-on** (simplest if HA already runs the Supervisor):
  Settings → Add-ons → Add-on Store → search **ESPHome**, install, open the
  web UI it creates.
- **Standalone**: `pip install esphome` (needs Python ≥ 3.11), or the
  [official install methods](https://esphome.io/guides/installing_esphome).

Either way you get the same dashboard/CLI; the rest of this guide works
identically.

## B. The configuration file

Create `nimble-boks-proxy.yaml` (via the dashboard's **New device** → skip its
wizard and paste this instead, or straight in a text editor if you're using
the CLI):

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

Two things worth noting, both different from the old firmware:

- **The mailbox's Bluetooth address is still not configured here** — same as
  before, this is a generic proxy that relays whatever Bluetooth Home
  Assistant asks for. The mailbox address is chosen later, when you add the
  Boks integration.
- **The API connection is Noise-encrypted by default** (`api: encryption:`),
  not plaintext like the old firmware. Generate a key with
  `esphome secrets` or any base64 32-byte value; store it (and the OTA
  password) as `!secret` like any other Home Assistant credential. If you'd
  rather keep it plaintext for parity with before, just drop the
  `encryption:` block — either way works with Home Assistant's ESPHome
  integration.

`board: esp32-s3-devkitc-1` and `framework: type: esp-idf` are required —
this only builds against ESP-IDF, and only for ESP32 targets with NimBLE
support (S3 recommended; see [hardware.md](../docs/hardware.md)).

## C. First flash (over USB)

From the dashboard: **Install** → **Plug into this computer** — it compiles
and flashes over USB, same as any ESPHome device.

From the CLI:

```bash
esphome run nimble-boks-proxy.yaml
```

The **first** compile downloads the ESP-IDF toolchain and takes several
minutes; ESPHome caches it, so later builds are fast.

Most ESP32-S3 boards expose two USB-C ports — use the **USB-to-serial
bridge** one (often silkscreened `COM`/`UART`), not the chip's native USB
port, for this first flash. If nothing shows up as a serial port, try another
USB cable first (charge-only cables are the most common culprit).

## D. Later updates go over WiFi (OTA)

Once the device is on the network, no cable needed:

```bash
esphome run nimble-boks-proxy.yaml
```

(ESPHome finds it automatically via mDNS, or falls back to OTA using the
credentials in the file.) From the dashboard, the same device's **Install**
button now offers **Wirelessly** instead of **Plug into this computer**.

## Adding the proxy to Home Assistant

Same as before: the device announces itself over mDNS as an ESPHome device.
Home Assistant picks it up under **Settings → Devices & services**; confirm
it (enter the `api: encryption:` key above if you set one).

Once added, it registers as a Bluetooth scanner, and *that* is what lets the
Boks integration reach the mailbox. Without this step the integration will
never find it, however correctly it is installed.

## Troubleshooting

| Symptom | Cause |
|---|---|
| `Component not found: esp32_ble_tracker` (or similar) | A component listed under `external_components: components:` doesn't exist in that exact spelling — this override replaces its whole directory, an absent one silently falls back to stock ESPHome (Bluedroid), which will *not* discover this mailbox's services in time |
| Build fails downloading the ESP-IDF toolchain | First build needs internet access to fetch it; retry, or see [ESPHome's own toolchain docs](https://esphome.io/guides/faq) |
| `Failed to connect … No serial data received` | Wrong USB port (see part **C**), or put the board in download mode by hand: hold `BOOT`, tap `RST`, release `BOOT`, then retry |
| Home Assistant never discovers it | mDNS blocked between VLANs; add the device by IP instead |
| Boot loop / `Guru Meditation Error` | Usually PSRAM mismatch on cheap boards — see [hardware.md](../docs/hardware.md) |

For anything specific to the NimBLE stack itself (not this mailbox's
integration), see
[`kamahat/NimbleBLE-Esphome`](https://github.com/kamahat/NimbleBLE-Esphome)'s
own `docs/` — particularly `OVERRIDE_CAVEATS.md` (what's intentionally not
carried over from stock ESPHome components) and `HARDWARE_VALIDATION.md`
(the real acceptance testing done against this exact mailbox).
