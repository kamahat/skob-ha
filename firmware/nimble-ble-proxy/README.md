> 🇫🇷 **[Version française](README-FR.md)**

# Building and installing the Bluetooth proxy — step by step

This folder holds the firmware that lets Home Assistant talk to the mailbox.
It runs on an **ESP32-S3** and presents itself to Home Assistant as a standard
**ESPHome Bluetooth proxy** — but on the **NimBLE** stack instead of Bluedroid,
which is precisely what makes this mailbox reachable at all.

You need to do this **once**, before installing the Home Assistant integration.
Plan for 30–45 minutes the first time, most of it spent installing ESP-IDF.

| | |
|---|---|
| Origin | [`fl4p/nimble-ble-proxy-esphome`](https://github.com/fl4p/nimble-ble-proxy-esphome), pinned commit — see [`NOTICE.md`](NOTICE.md) |
| Author's own technical documentation | [`README-DETAIL.md`](README-DETAIL.md) — architecture, protocol, design notes |
| Hardware to buy and its pitfalls | [`../../docs/hardware.md`](../../docs/hardware.md) |

> **`README-DETAIL.md` is the upstream author's document**, kept verbatim. It
> explains how the firmware works internally. The guide you are reading is ours
> and only covers getting it built and running.

---

## A. What you have to configure

Surprisingly little — **two values**:

| Parameter | Value | Where |
|---|---|---|
| WiFi SSID | your **2.4 GHz** network name | `include/wifi_creds.h` |
| WiFi password | that network's password | `include/wifi_creds.h` |

Two frequent misunderstandings worth clearing up now:

- **The mailbox's Bluetooth address is _not_ configured here.** The firmware is
  a generic proxy: it relays whatever Bluetooth Home Assistant asks for. The
  mailbox address is chosen later, in Home Assistant, when you add the Boks
  integration (it is even discovered for you).
- **2.4 GHz is mandatory.** The ESP32-S3 has no 5 GHz radio. If your access
  point publishes both bands under one SSID, that is fine — the board will
  associate on 2.4 GHz.

Optional, changeable later without reflashing: the device hostname
(`nimble-proxy` by default), via `POST /hostname?val=...`.

---

## B. Where to put them

The credentials file does not exist yet — the repository ships a template, and
the real file is deliberately ignored by git so your password never lands in a
commit:

```bash
cd firmware/nimble-ble-proxy
cp include/wifi_creds.h.example include/wifi_creds.h
```

Then edit `include/wifi_creds.h`. It should end up looking like this:

```c
#pragma once

#define WIFI_SSID     "my-iot-network"
#define WIFI_PASSWORD "correct-horse-battery-staple"
```

That is the whole configuration. Everything else has a sane default.

---

## C. Building

### C.1 — Install the tools

| Tool | Version | Notes |
|---|---|---|
| **ESP-IDF** | **v5.5** (any 5.x should work) | [official installation guide](https://docs.espressif.com/projects/esp-idf/en/v5.5/esp32s3/get-started/) |
| **git** | any | to fetch one dependency |
| **Python** | comes with ESP-IDF | you only add one package |

ESP-IDF brings its own compiler, its own Python environment and `esptool`, so
there is nothing else to install by hand.

**Every command below must run in an ESP-IDF shell**, i.e. after sourcing the
environment:

```bash
. ~/esp/esp-idf/export.sh          # Linux / macOS
```
```powershell
. $env:USERPROFILE\esp\esp-idf\export.ps1   # Windows PowerShell
```

You know it worked when `idf.py --version` answers.

### C.2 — Fetch nanopb

The protobuf bindings are generated at build time by **nanopb**, which is not
bundled here (it carries its own license). Clone it exactly where the build
expects it:

```bash
cd firmware/nimble-ble-proxy/components/api_proto
git clone --depth 1 https://github.com/nanopb/nanopb.git nanopb
cd ../..
```

Reference build used nanopb commit `d21fa5084287ab67da2f166f4def045bedcb535e`.

Skip this and the build stops early with a message that tells you exactly this:
`nanopb not vendored at …`.

### C.3 — Add the one Python package

```bash
pip install protobuf
```

Run it **inside the ESP-IDF environment** (after `export.sh`/`export.ps1`), so
it lands in IDF's virtualenv rather than your system Python.

### C.4 — Select the chip — as its own command

```bash
idf.py set-target esp32s3
```

Then **check it actually took**:

```bash
grep CONFIG_IDF_TARGET= sdkconfig
# expected: CONFIG_IDF_TARGET="esp32s3"
```

> ⚠️ **Do not chain this with the build.** If `set-target` is combined with a
> build that fails during *configure* (a missing nanopb, for instance), the
> target silently stays at the default `esp32`. Every later build then
> *succeeds* while producing an image for the wrong chip, and you only find out
> at flash time:
>
> ```
> A fatal error occurred: This chip is ESP32-S3, not ESP32. Wrong --chip argument?
> ```
>
> If that happens: `idf.py fullclean`, then set the target again and re-check.

### C.5 — Build

```bash
idf.py build
```

The first build takes several minutes (it compiles ESP-IDF itself and downloads
the NimBLE component). Subsequent builds take seconds. A successful run ends
with something like:

```
Project build complete. To flash, run:
 idf.py flash
nimble_ble_proxy.bin binary size 0x139300 bytes.
Smallest app partition is 0x1e0000 bytes. 0xa6d00 bytes (35%) free.
```

The firmware is now at `build/nimble_ble_proxy.bin` — around **1.28 MB**.

---

## D. Checking the firmware before you flash it

Three quick checks catch the mistakes that are painful to diagnose later.

**1. The right BLE stack** — this is the entire point of this firmware:

```bash
grep -E "CONFIG_BT_(NIMBLE|BLUEDROID)_ENABLED" sdkconfig
```
```
CONFIG_BT_NIMBLE_ENABLED=y
# CONFIG_BT_BLUEDROID_ENABLED is not set     ← Bluedroid must be absent
```

If Bluedroid appears here, the build will misbehave with this mailbox exactly
the way the stock ESPHome proxy does.

**2. The right chip:**

```bash
grep CONFIG_IDF_TARGET= sdkconfig
# CONFIG_IDF_TARGET="esp32s3"
```

**3. The binary exists and is plausible:**

```bash
ls -l build/nimble_ble_proxy.bin       # ~1.3 MB
```

Post-flash verification is in section **E.4**.

---

## E. Installing it on the ESP32-S3

### E.1 — Pick the right USB port

Most ESP32-S3 development boards expose **two USB-C ports**, and this trips up
almost everyone:

| Port | Silkscreen | Use it? |
|---|---|---|
| USB-to-serial bridge (CP210x, CH343…) | often `COM` or `UART` | ✅ **yes** — auto-reset works, flashing just runs |
| The chip's native USB | often `USB` | ⚠️ avoid for the first flash |

Plug into the **`COM`/UART** port and check that a serial device appeared:

```bash
ls /dev/ttyUSB* /dev/ttyACM*          # Linux
ls /dev/cu.*                          # macOS
```
```powershell
Get-CimInstance Win32_SerialPort | Select-Object DeviceID, Description   # Windows
```

You are looking for a line naming a serial bridge, for example
`USB-Enhanced-SERIAL CH343 (COM12)` or `/dev/ttyUSB0`.

*Nothing appears?* Try another USB cable first — charge-only cables with no data
wires are the most common cause by far.

### E.2 — Flash

```bash
idf.py -p /dev/ttyUSB0 flash        # Linux
idf.py -p /dev/cu.usbserial-110 flash   # macOS
idf.py -p COM12 flash               # Windows
```

This writes the bootloader, the partition table and the firmware. Expect
roughly a minute, ending with:

```
Hash of data verified.
Leaving...
Hard resetting via RTS pin...
```

*If it fails with "Failed to connect … No serial data received"*, put the board
into download mode by hand: **hold `BOOT`, tap `RST`, release `BOOT`**, then run
the flash command again.

### E.3 — Watch it boot

```bash
idf.py -p COM12 monitor        # Ctrl-] to quit
```

A healthy first boot prints, in order:

```
nimble-ble-proxy 0.1.0 booting
wifi: connected, IP 192.168.1.42
mdns: _esphomelib._tcp on nimble-proxy:6053 announced
ota: OTA endpoint at http://nimble-proxy.local/update
ble: NimBLE ready (max_conn=4, scan=30ms/60ms)
```

**Write down the IP address** — the next steps use it.

*The board reboots in a loop instead?* Look for `Guru Meditation Error` in the
log; the usual culprit on cheap boards is a PSRAM mismatch, covered in
[hardware.md](../../docs/hardware.md).

### E.4 — Verify it is really running

From any machine on the same network:

```bash
curl http://192.168.1.42/stats.json
```
```json
{"adverts":335,"heap":61660,"temp_c":44.5,"ble":true,"connections":0}
```

`"ble": true` and a rising `adverts` count mean the Bluetooth side is alive.
The web dashboard at `http://192.168.1.42/` shows the same, plus every device
seen with its signal strength — which is the tool you want when choosing where
to put the board.

### E.5 — Turn off the WiFi router mode

The firmware can also act as a WiFi access point and router. **Switch that
off**: here the board is only a bridge, and an access point steals airtime from
Bluetooth on the single 2.4 GHz radio — it also tips the coexistence arbiter in
WiFi's favour.

```bash
curl -X POST "http://192.168.1.42/nat?enabled=0"
```
```json
{"ok":true}
```

The setting survives reboots.

> Configuration endpoints need **`curl -X POST`**. A plain `curl` performs a GET
> and merely reads the value back without changing anything — an easy half-hour
> to lose.

### E.6 — Later updates go over WiFi

Once the firmware is on the board, the cable is no longer needed:

```bash
idf.py build
curl --data-binary @build/nimble_ble_proxy.bin http://192.168.1.42/update
```
```
ok: wrote 1284496 bytes to ota_1, rebooting
```

---

## Adding the proxy to Home Assistant

The firmware announces itself over mDNS as an ESPHome device. Home Assistant
picks it up under **Settings → Devices & services**; confirm it — the API is
plaintext, so there is no encryption key to enter.

Once added, it registers as a Bluetooth scanner, and *that* is what lets the
Boks integration reach the mailbox. Without this step the integration will never
find it, however correctly it is installed.

---

## Useful endpoints

| Endpoint | Purpose |
|---|---|
| `GET /` | Web dashboard |
| `GET /stats.json` | Health: heap, temperature, BLE counters |
| `GET /devices` | Devices seen with RSSI — use this to choose a location |
| `GET /log?since=0` | Firmware log, remotely |
| `POST /level?nimble=<0..5>` | NimBLE log verbosity |
| `POST /nat?enabled=0` | Disable the WiFi router mode |
| `POST /update` | OTA update |
| `POST /reboot` | Reboot |

## Troubleshooting

| Symptom | Cause |
|---|---|
| `nanopb not vendored at …` | Step **C.2** skipped |
| `Python was not found` (Windows) | Not in an ESP-IDF shell — see **C.1** |
| `This chip is ESP32-S3, not ESP32` | Target not set — see the warning in **C.4** |
| `Failed to connect … No serial data received` | Wrong USB port (**E.1**), or use manual download mode (**E.2**) |
| No serial port appears at all | Charge-only USB cable, or missing bridge driver |
| Boot loop with `Guru Meditation` | Usually PSRAM — see [hardware.md](../../docs/hardware.md) |
| Home Assistant never discovers it | mDNS blocked between VLANs; add the device by IP instead |
