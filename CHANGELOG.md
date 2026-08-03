# Changelog

All notable changes to this integration are documented here. The format is
based on [Keep a Changelog](https://keepachangelog.com/), and the project
follows [Semantic Versioning](https://semver.org/).

## [0.3.0] — 2026-08-02

### Added
- **Opening history sensors**: *Last VIGIK opening* and *Last code opening*,
  read from the mailbox's own event log (no authentication needed — the log
  request carries an empty payload). Dates are approximate: the mailbox has no
  clock, events carry an age in seconds relative to now.
- **Refresh interval** option (0–1440 min, default **0** = off): a short
  periodic connection that re-reads door state, battery and history without
  holding the link. This is what keeps state usable now that holding the link
  is no longer recommended.
- **Firmware v0.2.0** for the bundled NimBLE proxy: the central now negotiates
  a **200–400 ms connection interval with slave latency**, instead of NimBLE's
  30–50 ms / zero-latency default — a measured ~10–30× cut in the mailbox's
  radio duty cycle whenever a link is open.

### Fixed
- **Door state no longer resets to `unknown` across restarts.** The mailbox
  only notifies door state on *change*, so after a Home Assistant restart the
  entity could stay empty for hours even with successful connections in
  between. It now restores its last known value, like battery and timestamps.
- **History was only read once per session.** With the link held, openings
  occurring later in the same session were never picked up; the log is now
  re-read periodically within a held session too.

### Changed
- **Holding the link is no longer the recommended mode.** The periodic-refresh
  model is, and the docs now say so. Rationale: the mailbox's Bluetooth LED
  stays lit for as long as *any* central holds a link — and the v0.2.0
  connection-interval change, while a real power win, was **tested and does not
  change that** (the LED tracks link presence, not radio traffic). Not holding
  the link keeps the LED dark except for the few seconds each refresh takes.

### Documented
- New **Opening history** section, and a rewritten **Holding the link** section
  covering the LED trade-off and all three link settings — `refresh_interval`
  had never been documented despite existing in code.

> **Note on history reads.** The mailbox's event log is a single shared
> consumable history: reading it *drains* it, and it doubles as the backlog the
> vendor's own bridge dongle catches up on. That is why the refresh interval
> defaults to `0`. See the README before enabling it.

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

[0.3.0]: https://github.com/kamahat/skob-ha/releases/tag/v0.3.0
[0.2.0]: https://github.com/kamahat/skob-ha/releases/tag/v0.2.0
[0.1.1]: https://github.com/kamahat/skob-ha/releases/tag/v0.1.1
