> 🇫🇷 **[Version française](docs/fr/README.md)**

# Boks for Home Assistant

A **read-only** Home Assistant integration for the **Boks** connected mailbox,
installable through [HACS](https://hacs.xyz/).

The mailbox is reached over Bluetooth LE. Home Assistant is notified **the
moment the door state changes** — there is no polling.

| Entity | Type | Notes |
|---|---|---|
| Door | `binary_sensor` (`door`) | pushed by the mailbox on every change |
| Battery | `sensor` (%) | pushed on change, read on connect |
| BLE link | `binary_sensor` (`connectivity`) | diagnostic |
| RSSI | `sensor` (dBm) | diagnostic, disabled by default |
| Firmware / Software | `sensor` | diagnostic, disabled by default |

## Scope — read only

This integration **only reads**. The sole frames it ever transmits are
**status requests**, which double as the keepalive described below. The frame
builder *refuses* any other opcode by construction, so the integration cannot
open the door, manage PIN codes, or change the mailbox configuration — not even
by accident. No owner credentials are required or used.

## Requirements

1. **A Bluetooth proxy or adapter in range of the mailbox**, declared in Home
   Assistant. A proxy running the **NimBLE** stack is strongly recommended —
   see [Why NimBLE](#why-nimble). This repository ships a
   [ready-to-build firmware](firmware/nimble-ble-proxy/) and its
   [build guide](firmware/nimble-ble-proxy/README.md).
2. **The official vendor dongle must be unplugged.** It holds a permanent BLE
   connection to the mailbox, which makes the mailbox invisible to every other
   client, including this integration.

## Installation

### 1. Firmware (once)

Build and flash the Bluetooth proxy — see **[firmware/nimble-ble-proxy/README.md](firmware/nimble-ble-proxy/README.md)**
and the **[hardware specification](docs/hardware.md)**.

Then add the proxy to Home Assistant: it announces itself over mDNS and is
picked up by the **ESPHome** integration (plaintext API, no encryption key).
This is what allows Home Assistant to route Bluetooth to the mailbox.

### 2. Integration (via HACS)

1. HACS → ⋮ → **Custom repositories** → add this repository, category
   **Integration**.
2. Install **Boks**, then restart Home Assistant.
3. **Settings → Devices & services**: the mailbox is discovered automatically
   (its service UUID is declared in the manifest). Otherwise, *Add integration
   → Boks*.

## Why NimBLE

The mailbox closes any connection after roughly **30 seconds** unless the
client keeps exchanging with it. Two consequences:

- **The BLE stack matters.** With **Bluedroid** — the stack used by stock
  ESPHome Bluetooth proxies — GATT service discovery never completes within
  that window on this device, so the connection is dropped before anything can
  be read. With **NimBLE**, discovery completes in about 6 seconds. A native
  Linux BlueZ host also works. This is why the firmware in this repository uses
  NimBLE.
- **A keepalive is mandatory.** The integration sends a periodic status request
  to keep the link alive; without it the mailbox disconnects. This is normal and
  expected behaviour, not a workaround for a bug.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| Mailbox never discovered | Official dongle still plugged in, or no connectable proxy in range |
| Connects then drops after ~30 s | Keepalive not running — check the integration logs |
| Frequent connection failures | Weak signal. The mailbox is a metal enclosure: aim for line of sight to its plastic front, and see [hardware](docs/hardware.md) |
| Entities show *unavailable* | The BLE link is down; the *BLE link* sensor stays available and tells you so |
| One failed connection right after a restart, then fine | Expected: the GATT cache is purged on the first attempt (see below) |

Enable debug logging:

```yaml
logger:
  logs:
    custom_components.boks: debug
```

### GATT cache and the `error=-2` failure mode

ESPHome Bluetooth proxies only resolve characteristics after an explicit
*GetServices* request. Home Assistant skips that request whenever it has cached
services **and** the proxy advertises the `REMOTE_CACHING` feature — and it does
so regardless of what a client asks for (`REMOTE_CACHING or
dangerous_use_bleak_cache` in `bleak_esphome`).

Proxies that advertise `REMOTE_CACHING` without implementing it therefore end up
with no characteristic objects for the connection, and every handle-based
operation fails with `error=-2`.

This integration works around it by **purging the GATT cache at the end of each
session**, which forces a fresh discovery on the next attach. In practice you may
see a single failed connection right after a Home Assistant restart; it recovers
on the following attempt and then stays connected.

## Interoperability statement

This project exists so that owners of a Boks mailbox can use **their own
device** with **their own** home automation system, locally. It reads status
information the device exposes over standard, unauthenticated Bluetooth
characteristics. It circumvents no security measure, extracts no secret, and
does not interact with the vendor's servers.

## Credits & licenses

- Home Assistant integration and documentation: **GPL-3.0** (see `LICENSE`).
- Bundled firmware: third-party work by **fl4p**, declared MIT — see
  [`firmware/nimble-ble-proxy/NOTICE.md`](firmware/nimble-ble-proxy/NOTICE.md)
  for attribution, the pinned upstream commit, and the single portability
  change applied.
