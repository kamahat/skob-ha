> 🇫🇷 **[Version française](fr/hardware.md)**

# Hardware specification

You need one **ESP32-S3** board acting as a Bluetooth proxy between the mailbox
and your WiFi network. Any ESP32-S3 module will do; the notes below come from a
real build and will save you time.

## Required

| Item | Requirement | Why |
|---|---|---|
| MCU | **ESP32-S3** | The firmware targets `esp32s3`. Its dual radio and NimBLE stack handle this mailbox reliably. |
| Flash | 4 MB minimum | The firmware image is ~1.3 MB and the layout is dual-OTA (two 1.875 MB slots). |
| PSRAM | **not required** | The firmware is designed to run without it. |
| Antenna | **external, strongly recommended** | The mailbox is a metal enclosure, so its signal is weak. See [radio budget](#radio-budget). |
| Power | Any 5 V USB supply | A power bank is fine for testing; use a fixed supply for permanent installs. |

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
