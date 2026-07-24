> 🇫🇷 **[Version française](docs/fr/TODO.md)**

# Roadmap / open subjects

Subjects still on the table. These are directions, not commitments or dates.
Contributions are welcome — one focused pull request per subject.

Guiding rule: the integration stays **read-only by default**. Any feature that
transmits more than a status request or an opt-in open command must stay behind
explicit user configuration and must never widen the transmit-opcode allowlist
silently.

---

## 1. Mifare NFC badge

**Goal.** Read, register and revoke Mifare NFC tags used to open the mailbox,
from Home Assistant.

**What we know.** The Boks protocol reserves opcodes for exactly this —
`REGISTER_NFC_TAG_SCAN_START` (23), `REGISTER_NFC_TAG` (24),
`UNREGISTER_NFC_TAG` (25) — with matching notifications (`NOTIFY_NFC_TAG_FOUND`,
`NOTIFY_NFC_TAG_REGISTERED`, …). The vendor SDK exposes `scanNFCTags()`,
`registerNfcTag()`, `unregisterNfcTag()`.

**What's needed.** These are administrative operations: they require the
owner's **Config Key** (retrievable from the account API), and they write to the
box. Implementing them means adding those opcodes to the allowlist *only when a
Config Key is configured*, mirroring how remote opening already gates on an open
code.

**Hardware.** NFC is **confirmed working on the reference box** — six Mifare
badges are in active use on it — even though it reports `Model Number = 2.0` and
exposes no Hardware Revision characteristic. So the SDK's "HW ≥ 4.0" note does
not preclude it here, and the feature can be developed and tested against real
hardware. Other hardware generations may still differ, so the feature should
detect capability rather than assume it.

**Status.** Not started. Design document first (credential handling,
mid-operation failure, capability detection), as agreed for any write feature.
Testable end-to-end on the reference box once built.

---

## 2. Vigik badge

**Goal.** Support the **Vigik** access badges used by La Poste (and utilities /
emergency services) to open building common areas and mailboxes.

**What we know.** The SDK defines a configuration type `BoksConfigType.LaPosteNfc`
applied through `SET_CONFIGURATION` (opcode 22). This strongly suggests Vigik /
La Poste postal access is a *configuration* of the box rather than an ordinary
user tag, and is therefore distinct from subject 1 above.

**What's needed.** Confirm, by observation, how a Vigik/La Poste credential is
provisioned over BLE and what `SET_CONFIGURATION` expects.

**Hardware.** Present on the reference box: its **keypad module was upgraded in
2025 to support Vigik badges**, and that same module is what enables the Mifare
NFC of subject 1. So the "HW ≥ 4.0" note is about this keypad/NFC module — here
retrofitted onto an otherwise `Model 2.0` box — and both badge subjects are
testable end-to-end on real hardware.

**Status.** Investigation. The protocol path is inferred from SDK constants and
not yet observed on a device, but a device that supports it is available for
capture. Nothing should be implemented before the frame layout is confirmed.

---

## 3. Bluetooth stack reliability

**Goal.** Fewer failed connections and clearer failure handling across the
`bleak` / `bleak-esphome` / `habluetooth` path.

**Open items.**

- **Weak-signal failures.** Through the mailbox's metal enclosure the link sits
  near −85 dBm; connection attempts occasionally fail and retry. The backoff is
  in place, but the temp-session open path (used when the link is not held) has
  only one real-world validation so far and deserves more.
- **`error=-2` root cause upstream.** The integration works around the ESPHome
  proxy advertising `REMOTE_CACHING` without honouring it (see
  [the troubleshooting section](README.md#gatt-cache-and-the-error-2-failure-mode))
  by clearing the GATT cache each session. The real fix belongs in the proxy
  firmware; a patch is prepared for upstream.
- **Connection-interval negotiation.** The firmware does not call
  `updateConnParams`. Negotiating a longer interval is the main lever left on
  battery drain while the link is held — more effective than tuning the
  keepalive.
- **Dependency pinning.** Track `bleak-esphome` / `aioesphomeapi` versions that
  are known-good against this box, so a Home Assistant update cannot silently
  regress the link.

**Status.** Ongoing, incremental.

---

## 4. Code hardening

**Goal.** Make the integration robust and maintainable enough for wider use.

**Open items.**

- **No test suite yet.** At minimum: frame build/parse round-trips, the
  opcode allowlist (it must keep refusing 16–19 / 22 / 32–33), PIN validation,
  door-state decoding, and the battery sag/plateau logic.
- **Value persistence across restart.** After a Home Assistant restart the
  sensors read `unavailable` until the first connection, because state lives in
  memory only. `RestoreEntity` on the sensors would keep the last known values,
  as already documented for the switches.
- **Config-flow / options-flow edge cases.** Cover a broken `!secret`
  reference, a removed secret key, and re-validation on reload.
- **HA quality-scale items.** Diagnostics download, reauth/reconfigure paths,
  strict typing, and CI running `hassfest` + `ruff`.

**Status.** Ongoing.

---

*If you plan to work on any of these, opening an issue first avoids duplicate
effort — especially for subjects 1 and 2, whose protocol details still need to
be confirmed on real hardware.*
