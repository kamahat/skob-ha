> 🇫🇷 **[Version française](docs/fr/README.md)**

# Boks for Home Assistant

A Home Assistant integration for the **Boks** connected mailbox, installable
through [HACS](https://hacs.xyz/). **Read-only unless you opt in** to remote
opening by entering a code — see [Scope](#scope).

The mailbox is reached over Bluetooth LE. Home Assistant is notified **the
moment the door state changes** — there is no polling.

| Entity | Type | Notes |
|---|---|---|
| Door | `binary_sensor` (`door`) | pushed by the mailbox on every change |
| Open | `button` | **only if an open code is configured** — see [Opening the door](#opening-the-door) |
| Battery | `sensor` (%) | pushed on change, read on connect |
| Battery low | `binary_sensor` (`battery`) | diagnostic — **use this, not the percentage** ([why](#battery-alkaline-vs-regulated-cells)) |
| Hold connection | `switch` | config — see [Holding the link](#holding-the-link) |
| Rechargeable batteries | `switch` | config — declares the cell type in place |
| BLE link | `binary_sensor` (`connectivity`) | diagnostic |
| Last connected | `sensor` (timestamp) | diagnostic — how fresh the values above are |
| BLE address | `sensor` | diagnostic |
| RSSI | `sensor` (dBm) | diagnostic, disabled by default |
| Firmware / Software | `sensor` | diagnostic, disabled by default |

![The Boks device page in Home Assistant](docs/img/ha-device-page.png)

> Home Assistant splits the device page by entity category: *Sensors* first,
> then *Configuration* (the two switches), then *Diagnostic*. The two switches
> are **not** in the Controls block — that block only holds uncategorised
> entities.

## Scope

**Read-only by default.** Out of the box the only frames transmitted are
**status requests**, which double as the keepalive described below. No owner
credentials are required or used, and no `button` entity is created.

**Opening is opt-in.** If — and only if — you enter an open code in the
options, an **Open** button appears and the integration may additionally send
`OPEN_DOOR`. Nothing else ever becomes possible: the frame builder *refuses*
every other opcode by construction, so code management (16–19), configuration
changes (22) and provisioning (32–33) remain unreachable, not merely unused.

> Entering a code means **anyone with access to your Home Assistant can open
> your mailbox**. The code is stored in the config entry, in clear text like
> every other Home Assistant credential. Leave the field empty to keep the
> integration strictly read-only.

See [Opening the door](#opening-the-door).

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

## Holding the link

The **Hold connection** switch is the central trade-off of this integration,
and it is yours to make:

- **On** — the GATT link is held permanently. State changes are pushed the
  instant they happen, but the mailbox keeps its radio awake: on a
  battery-powered device, that costs. Measured on ours: **58 % → 28 % in six
  days**, batteries found flat afterwards. The mailbox's Bluetooth LED stays
  lit the whole time, which is a handy way to check.
- **Off** (default) — no connection at all. Already-known values stay on
  display, and *Last connected* tells you how old they are. Presence keeps
  being tracked through advertisements, which cost the mailbox nothing.

Two settings are exposed through **Configure** on the integration entry, and
applied without restarting Home Assistant:

| Setting | Range | What it does |
|---|---|---|
| Keepalive interval | 5–28 s | Main power lever while the link is held |
| Reconnect ceiling | 30–900 s | Backoff cap when the mailbox is out of range |

The keepalive is capped at 28 s on purpose: the mailbox drops the connection
after about **30 s** of silence. Past that, the link falls between two
keepalives and reconnects in a loop — which costs *more* than holding it.

> Reloading the config entry does **not** reload the integration's Python code;
> it stays cached in the Home Assistant process. After updating the component
> files, a full restart is still required.

## Opening the door

Opening requires a secret, but **not** a cryptographic session: there is no
encrypted handshake on the Boks link. The command simply carries a 6-character
PIN that the mailbox validates itself, answering `VALID_OPEN_CODE` (129) or
`INVALID_OPEN_CODE` (130). The secret is the code, not the channel.

Enter one in **Configure** → *Open code*. It must be 6 characters over the
alphabet `0123456789AB` — twelve symbols, so `C` to `F` are **not** valid. The
format is checked when you save rather than when you press: a malformed frame
can be **ignored by the mailbox without any reply**, which is close to
undiagnosable once in service.

Use a **permanent** code — a master or fixed code from your account. The
one-time codes the mobile app relays would work exactly once.

The button works **whether or not the link is held**: if it isn't, a temporary
session is opened for the command and released afterwards. A button that only
worked while holding the link would be useless in practice, since not holding
it is both the default and the battery-friendly setting.

The press only reports success once the mailbox answers `VALID_OPEN_CODE`. A
GATT write on its own proves nothing — a refused code and an unheard command
would look identical.

## Battery: alkaline vs regulated cells

The mailbox does not expose a voltage. It publishes the standard `0x2A19`
characteristic — a percentage **it derives itself** from the pack voltage, on
an alkaline curve (~1.6 V full → ~0.9 V empty). That number therefore only
means something with non-regulated cells.

Rechargeable 1.5 V lithium cells contain a converter that holds 1.5 V flat
until their protection cuts out. The gauge sits at the top of the scale for
nearly the whole service life, then collapses at once — no warning slope. In a
series pack, the first cell to reach its cutoff takes the whole pack down, so
the failure is abrupt.

**No recalculation can fix this**: a regulated pack's voltage no longer carries
the state of charge, and inventing a curve would produce a credible, wrong
gauge. So the **Rechargeable batteries** switch changes the *interpretation*,
not the value:

| | Alkaline (off) | Regulated lithium (on) |
|---|---|---|
| The percentage | tracks remaining charge | pinned near the top |
| Low-battery alert | threshold at 20 % | **drop** of 3 points below the observed plateau |

Toggling the switch counts as declaring a fresh pack: the reference plateau is
reset. In automations, use **Battery low** rather than the percentage — a fixed
threshold on the percentage would never fire with regulated cells.

Isolated voltage sags are filtered out: opening the door drives the motor and
the mailbox has been seen publishing 0 % during the manoeuvre. A sharp drop is
only retained once a second reading confirms it.

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
