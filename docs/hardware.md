> 🇫🇷 **[Version française](fr/hardware.md)**

# Hardware specification

You need one board acting as a Bluetooth proxy between the mailbox and your
WiFi network. The reference build and the shipped firmware target the
**ESP32-S3**; any ESP32-S3 module will do, and the notes below come from a real
build and will save you time. Two newer RISC-V chips are also worth
considering — see [Alternative boards](#alternative-boards-esp32-c6--c5).

## Required

| Item | Requirement | Why |
|---|---|---|
| MCU | **ESP32-S3** | The firmware targets `esp32s3`. Its dual radio and NimBLE stack handle this mailbox reliably. |
| Flash | 4 MB minimum | The firmware image is ~1.3 MB and the layout is dual-OTA (two 1.875 MB slots). |
| PSRAM | **not required** | The firmware is designed to run without it. |
| Antenna | **external, strongly recommended** | The mailbox is a metal enclosure, so its signal is weak. See [radio budget](#radio-budget). |
| Power | Any 5 V USB supply | A power bank is fine for testing; use a fixed supply for permanent installs. |

## Alternative boards (ESP32-C6 / C5)

The **ESP32-S3** is the reference and is validated end-to-end against this
mailbox. Two newer RISC-V chips are attractive alternatives — both need the
firmware retargeted and rebuilt (`idf.py set-target esp32c6` / `esp32c5`), and
neither has yet been validated against the mailbox here.

| Chip | Suggested boards | Radio | Cores | Maturity for this use | Watch out |
|---|---|---|---|---|---|
| **ESP32-S3** *(reference)* | generic DevKitC-1 (N16R8) | 2.4 GHz Wi-Fi + BLE 5 | 2× Xtensa (true dual-core) | **Validated** end-to-end | mislabelled PSRAM on clones — see [reference board](#board-used-for-reference) |
| **ESP32-C6** | Seeed XIAO ESP32-C6, M5Stack NanoC6 | 2.4 GHz Wi-Fi 6 + BLE 5 | 1× HP RISC-V + 1× LP core | Mature silicon, well supported in ESP-IDF | **poor-quality clones circulate** — buy from a reputable seller |
| **ESP32-C5** | M5Stack Stamp-C5, Seeed XIAO ESP32-C5 | **dual-band 2.4 + 5 GHz** Wi-Fi 6 + BLE 5 | 1× HP RISC-V + 1× LP core | Recent and promising; ESP-IDF support still maturing | bleeding edge — expect rough tooling and firmware churn |

> **Why the C5 is interesting for this project specifically.** On single-band
> chips (S3, C6), Wi-Fi and BLE share the one 2.4 GHz radio and must time-slice
> it — the coexistence contention that made an earlier proxy attempt
> unreliable. The C5 is **dual-band**: put Wi-Fi on 5 GHz and the 2.4 GHz radio
> is left entirely to Bluetooth. Given how thin the
> [radio budget](#radio-budget) already is through the mailbox's metal
> enclosure, not sharing 2.4 GHz airtime is a real advantage.
>
> The C6, by contrast, is single-band like the S3 — no coexistence gain — but
> it is mature and cheap. Its "cores" are not comparable to the S3's: one
> high-performance RISC-V core plus a low-power core, not two application cores.

### C5 bring-up notes (2026-08-24, XIAO ESP32-C5)

First real bring-up against the mailbox — see
[PR #4](https://github.com/kamahat/skob-ha/pull/4) for the firmware branch
(`idf.py --preview set-target esp32c5`; the target is still preview in
IDF v5.5).

- **WiFi does not pick 5 GHz by default.** The stock scan/connect path
  associated on a 2.4 GHz channel even with a dual-band SSID in range —
  forcing `esp_wifi_set_band_mode(WIFI_BAND_MODE_5G_ONLY)` on connect
  is required to actually exercise the dual-band scenario this target
  exists for.
- **That band lock persists across a WiFi driver reinit**, since
  `esp_wifi_set_band_mode()` writes through to flash under the default
  `WIFI_STORAGE_FLASH`. If the 5 GHz connect ever fails, the SoftAP
  provisioning fallback (which needs 2.4 GHz, channel 1) inherits the
  stale 5G-only lock and the device aborts instead of recovering. Fixed
  with `esp_wifi_set_storage(WIFI_STORAGE_RAM)` — see the PR for detail.
- **Connects successfully on 5 GHz** (confirmed at the desk: channel 64,
  SNR 36 dB) and NimBLE starts alongside it.
- **Against the actual mailbox, the BLE connect is slow — around 10
  seconds** to complete (firmware-side `onConnect`), against a couple of
  seconds on the S3 reference. Home Assistant's own connect-attempt
  budget (`bleak-retry-connector`) is shorter than that and gives up
  first, so the integration never sees the connection succeed even
  though the firmware eventually gets there. Not yet root-caused —
  leading suspect is WiFi/BLE coexistence overhead while 5 GHz is
  actively associated, since this is new territory: nobody had profiled
  BLE central-role connect latency on this chip under active WiFi load
  before.
- **External antenna: connector mismatch, not a band/RF problem.**
  Tried a Bingfu 2.4/5.8 GHz dual-band antenna (confirmed genuinely
  dual-band, RP-SMA + U.FL pigtail) in place of the stock antenna —
  WiFi stopped working entirely. Not an antenna-band issue: physical
  check showed **the two U.FL connectors are different sizes/standards**
  (XIAO boards commonly use a smaller MHF4-class micro-connector, not
  the full-size U.FL/IPEX-1 that generic pigtails like the Bingfu ship
  with) — the connector visibly clips but doesn't make real RF contact.
  No firmware-side antenna-select switch was found for this board
  (unlike the sibling XIAO ESP32-C6, which has one) — it's a single
  U.FL port, whatever's properly mated to it is the antenna. Stuck on
  the stock antenna until a matching micro-connector pigtail is
  sourced.

**Follow-up the same day, chasing the ~10s GATT connect (see PR #4 for full detail):**

- **WiFi/BLE coexistence confirmed as a real cost, not just a hunch.**
  Espressif's own docs confirm the C5 has a **single RF chain** shared
  between WiFi and BLE, time-division arbitrated even though the two
  never collide in spectrum (5 GHz WiFi vs 2.4 GHz BLE). Biasing the
  arbiter with `esp_coex_preference_set(ESP_COEX_PREFER_BT)` cut the
  mailbox connect time from ~10s to ~5.4s.
- **Connection interval mattered even more.** The 200-400 ms interval
  tuned for *holding* a link (S3, battery-saving) is a poor fit for a
  *fast one-shot discovery* — GATT discovery is dozens of sequential
  ATT round trips, each bound by roughly one interval. Switching to a
  tight 30-50 ms/latency-0 interval for the C5 specifically dropped
  connect-to-discovery-start further to **~1.4s**.
- **The real blocker: `discoverAttributes()` itself crashes** against
  the actual mailbox, on every interval/timing variant tried — including
  the fast one, where it now fails almost immediately rather than near
  any timeout boundary. Ruled out the "mailbox's 30s idle-disconnect
  fires mid-discovery" theory this pointed to initially: too fast now
  for that to be it. A NimBLE debug-logging attempt to see more detail
  backfired — the logging overhead itself exhausted BLE controller
  memory (`NimBLEScan: Error starting scan; rc=519`, HCI Memory
  Capacity Exceeded) before anything useful could be observed.
  **Unresolved** — needs a core dump or serial gdb session to actually
  see the fault; out of reach without a NimBLE-level debugging pass.

Net for this session: mailbox connect time went from failing outright
(NO_AP_FOUND / never reaching 5 GHz) to a reliable ~1.4s connect — real
progress — but GATT service discovery, the actual point of connecting,
still doesn't survive on this target. Firmware PR #4 stays in draft.

### C5 field test (2026-08-25, stock antenna, ~11 m + 1 wall)

Same physical position used earlier the same night for a Pi4/noble comparison
(that position measured **−97 dBm**, connect eventually succeeded there with
noble/BlueZ). With the C5 running this firmware, **stock antenna**, at the
identical position:

- **Passive advertisement scan, 60 s, clean run (no connection errors): the
  mailbox was never once seen.** `0/60s`, vs. the Pi4 which — imperfectly, but
  genuinely — detected it at the same spot the same night.
- This is a **passive scan result**, unrelated to the `discoverAttributes()`
  crash above (no GATT connect attempted). It suggests the C5's stock-antenna
  BLE receive sensitivity may be materially worse than the Pi4's, on top of
  the already-documented WiFi/BLE coexistence cost.
- Also observed: one connection attempt to the C5's own ESPHome API (WiFi,
  not BLE) timed out outright (`TimeoutAPIError`) right after a prior
  scan+disconnect sequence, while ping/TCP to the board stayed reachable —
  general link fragility under combined load, consistent with the
  coexistence findings above; a retry succeeded cleanly.

**Blocked on hardware**: no antenna change was tested (the previously-tried
Bingfu pigtail's connector doesn't mate — see above). **Paused, awaiting a
correctly-matched MHF4 pigtail + antenna before the next attempt.**

## USB ports — a common pitfall

Most ESP32-S3 devkits expose **two USB-C ports**, and they do not behave alike:

- **`COM` / `UART` port** (CP210x, CH343… bridge): use **this one**. Auto-reset
  works, so flashing and serial logs need no button presses.
- **native `USB` port** (the S3's own USB peripheral): flashing usually requires
  entering download mode manually — hold **BOOT**, tap **RST**, release **BOOT**.
  The serial console may also stay silent depending on the firmware's console
  configuration.

Recommendation: **flash and debug through the `COM`/UART port.** Once the
firmware is running, updates can go over WiFi (OTA) and no cable is needed.

## Radio budget

The mailbox's BLE radio sits inside a **metal enclosure**, which acts as a
Faraday cage. Expect a weak and channel-dependent signal — around **−83 dBm on
the best advertising channel and −92 dBm on the others** in a typical install a
few metres away through a wall.

This still works: connection and GATT discovery succeed at −83 dBm, and a native
BlueZ host has been observed working at −93 dBm. But margin is thin, so
connection attempts occasionally fail and simply retry.

To improve it — in order of effectiveness:

1. **Aim for the plastic front or the letter slot**, not the metal body.
2. **Get closer.** Halving the distance gains roughly 6 dB.
3. **Keep the antenna vertical**, parallel to the mailbox's own antenna.
4. **Move the antenna away** from the board's ground plane, the power bank and
   any metal — a pigtail lets you place the antenna alone at the best spot.

Target **better than −80 dBm** for a consistently reliable link.

> Increasing the proxy's BLE transmit power does **not** improve the measured
> RSSI: that figure is what *you receive* from the mailbox. Higher TX power only
> helps the return path. The firmware caps BLE TX at 9 dBm anyway.

## Board used for reference

The reference build used a generic **ESP32-S3 DevKitC-1 clone** ("N16R8",
16 MB flash, external u.FL antenna connector).

⚠️ **Beware of mislabelled PSRAM on cheap clones.** The board advertised
"N16R8" (8 MB PSRAM) but its PSRAM is unusable: configuring `octal` mode causes
an `IllegalInstruction` panic and a boot loop, and `quad` mode reports *"PSRAM
chip is not connected"*. The module was marked `X01-S3E`, a third-party clone
rather than a genuine Espressif module. This costs nothing here — the firmware
needs no PSRAM and leaves it disabled — but do not count on the PSRAM of such a
board for anything else.

If you buy a board with an external antenna connector, check that the antenna is
actually wired to it: some designs need a 0 Ω resistor moved to switch from the
onboard PCB antenna to the u.FL connector.
