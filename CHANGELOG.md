# Changelog

All notable changes to this integration are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and the project
follows [Semantic Versioning](https://semver.org/).

## [0.2.0] — 2026-07-24

### Added
- **Remote open button**, opt-in: it appears only when an open code is
  configured. Without a code the integration stays strictly read-only. The
  press reports success only once the mailbox answers `VALID_OPEN_CODE`.
- **Open code from `secrets.yaml`**: the code field accepts `!secret <key>`;
  only the reference is stored, the code stays in the secrets file.
- **Mailbox identifier (label)**: names the device `Boks <id>` and adds an
  *Identifier* diagnostic sensor. Needed to tell several mailboxes apart —
  the box exposes no readable identifier of its own (its GATT serial is the MAC).
- **Battery type switch** (alkaline vs regulated lithium) with adapted
  end-of-life detection, plus a **Battery low** binary sensor to use in
  automations instead of the raw percentage.
- **Options flow**: keepalive interval and reconnect ceiling, applied without
  restarting Home Assistant.

### Fixed
- **Battery could stick at its last value during a real decline.** The
  transient-sag filter required two *identical* readings to confirm a drop; a
  genuine discharge (especially the sudden collapse of regulated lithium cells,
  e.g. 100 → 40 → 10) never matched and left the sensor pinned high. It now
  confirms "still low", not "same number".
- **GATT `error=-2`** with ESPHome proxies that advertise `REMOTE_CACHING`
  without honouring it: the GATT cache is cleared each session.
- **"Last connected" not refreshed** after opening through a temporary session.
- **Broken manifest links**: `documentation` and `issue_tracker` pointed to a
  non-existent repository (404); they now point to `skob-ha`.

### Removed
- Dead code: an unused import and an unused state field.

## [0.1.1]
- Early read-only release: door, battery, BLE link and version sensors over a
  maintained BLE connection, with Bluetooth discovery.

[0.2.0]: https://github.com/kamahat/skob-ha/releases/tag/v0.2.0
[0.1.1]: https://github.com/kamahat/skob-ha/releases/tag/v0.1.1
