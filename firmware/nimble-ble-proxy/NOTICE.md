# Third-party code — attribution

This directory contains a **vendored copy** of a third-party firmware. It is
**not** original work of this repository.

| | |
|---|---|
| Upstream project | [`fl4p/nimble-ble-proxy-esphome`](https://github.com/fl4p/nimble-ble-proxy-esphome) |
| Author | fl4p |
| Vendored at commit | `b773dc6f5980e2de48ff3c61951befb357a3ee8b` (2026-06-15) |
| Declared license | **MIT** — stated in the upstream `README.md` ("## License / MIT.") |

## About the license

At the time of vendoring, the upstream repository declares MIT **in its README
only**: it contains no `LICENSE` file, and GitHub reports no detected license
for it. This copy is redistributed in good faith under that stated MIT grant,
with explicit attribution to the original author and a pin to the exact
upstream commit.

If you intend to redistribute this code further, please check the upstream
repository first — a formal `LICENSE` file may have been added since.

The rest of **skob-ha** (the Home Assistant integration and the documentation)
is licensed under **GPL-3.0**, see the repository root `LICENSE`. MIT-licensed
material may be combined into a GPL-3.0 work; the files in this directory
remain under their original MIT terms.

## What was changed relative to upstream

One source modification needed to build on Windows, one build-default change,
one dashboard feature, one file rename, and one connection-power change:

- `components/api_proto/CMakeLists.txt` — the nanopb generator was invoked as
  hard-coded `python3`, which does not exist as an executable on Windows (it
  triggers the Microsoft Store app-execution alias and the build fails with
  *"Python was not found"*). It now uses the ESP-IDF Python interpreter through
  the standard IDF idiom `idf_build_get_property(python PYTHON)`.

  This is a portability fix, not a functional change — behaviour on Linux and
  macOS is unchanged. Submitted upstream as
  [fl4p/nimble-ble-proxy-esphome#1](https://github.com/fl4p/nimble-ble-proxy-esphome/pull/1).

- `sdkconfig.defaults` — `CONFIG_NBP_NAT_ROUTER` switched from `y` to `n`.
  Upstream pins it on ("so the build is testable" during clone development),
  which brings up a WiFi SoftAP. Here the board is a pure WiFi↔BLE bridge and
  never a router: the access point would compete for the single 2.4 GHz radio,
  tip the coexistence arbiter towards WiFi, and cost flash and DRAM on a
  no-PSRAM S3 — while forcing every user through a runtime `POST /nat?enabled=0`.
  Note `n` is what upstream's own Kconfig and README table declare as the
  default, so this restores the documented behaviour rather than departing
  from it. Verified to build clean; it also trims ~14 KB of flash (1 284 496 →
  1 269 824 bytes) plus the router's runtime footprint. Set it back to `y` if
  you want the router.

- `web/index.html` — added a firmware-upload control to the dashboard. The
  footer already printed the OTA curl command but there was no way to perform
  an update from the browser; `POST /update` accepts the raw image as the
  request body, so no firmware-side change was needed. Hidden unless the page
  is reached over HTTP, since the Web Bluetooth transport cannot carry a
  ~1.3 MB image. Offered upstream as
  [`feat/dashboard-firmware-upload`](https://github.com/kamahat/nimble-ble-proxy-esphome/tree/feat/dashboard-firmware-upload).

- `include/proxy_config.h` + `components/ble_backend/connection.cpp` — the
  outgoing central connection now calls `NimBLEClient::setConnectionParams()`
  with an explicit interval/latency/timeout instead of leaving it uncalled.
  Upstream's default (via `BLE_GAP_INITIAL_CONN_ITVL_{MIN,MAX}`) is a 30-50 ms
  interval with zero slave latency: the peripheral must wake and respond on
  every connection event, 20-33 times a second, for as long as the link is
  held — fine for the upstream project's general low-latency use case, costly
  for a battery-powered peripheral held connected long-term. What prompted the
  change: a 58%→28% battery drop over 6 days while a permanent link was held,
  and a mailbox "Bluetooth active" LED that stayed lit continuously (unlike
  the vendor's own dongle's connection). Widened to 200-400 ms / latency 4 /
  6000 ms supervision timeout — a ~10-30× reduction in radio duty cycle,
  comfortably under the ~30 s application-level watchdog a held link still
  needs to satisfy with periodic writes. See `proxy_config.h` for the exact
  values and the BLE-spec unit conversions.

  **Tested after deploying (2026-08-02): this change does not affect the
  LED.** Holding the link at the new, far gentler interval still keeps it lit
  continuously — it tracks link *presence*, not radio traffic. The battery
  benefit (fewer radio wake-ups) stands regardless; the LED difference from
  the vendor dongle remains unexplained. A link-layer pairing/bonding step the
  vendor dongle may perform, and this proxy never initiates, is the leading
  unconfirmed theory — not pursued yet, since testing it means eliciting
  untested behaviour from a live access-control peripheral. See
  [skob-ha README § Holding the link](https://github.com/kamahat/skob-ha#holding-the-link).

- `README.md` → `README-DETAIL.md` — **renamed, contents untouched.** The
  upstream author's document is a technical reference, not a build guide, and
  people landing in this folder needed step-by-step instructions instead. The
  new `README.md` / `README-FR.md` are ours; his text is preserved verbatim
  under the new name.

## What was NOT vendored

Only files tracked by upstream git are included (121 files). Deliberately
excluded:

- `include/wifi_creds.h` — per-user WiFi credentials (gitignored upstream;
  you create it yourself, see the build guide).
- `build/` — build artifacts.
- `managed_components/` — fetched automatically by the ESP-IDF component manager.
- `components/api_proto/nanopb/` — a separate dependency you clone yourself
  (see the build guide); it carries its own license.
- `CLAUDE.md` and `.claude/` — the upstream author's own AI-assistant notes.
  They are development context for *their* setup (including their LAN details)
  and are irrelevant here. They also contain instructions addressed to an AI
  agent, which have no business being carried into a third-party repository.
