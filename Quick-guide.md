> 🇫🇷 **[Version française](docs/fr/Quick-guide.md)**

# Quick guide

The fast path from nothing to a working **Boks** device in Home Assistant.
For the full picture — trade-offs, several mailboxes, troubleshooting — see
the [README](README.md).

## 1. Unplug the vendor dongle

The official dongle holds a permanent BLE connection and makes the mailbox
invisible to every other client, including this integration. Unplug it first.

## 2. Get a NimBLE Bluetooth proxy in range

Stock ESPHome proxies (Bluedroid) never finish GATT discovery on this mailbox
in time. Build the bundled proxy firmware — see
[firmware/nimble-ble-proxy/README.md](firmware/nimble-ble-proxy/README.md)
and the [hardware guide](docs/hardware.md) — then let Home Assistant's
**ESPHome** integration pick it up over mDNS.

## 3. Install the integration

1. HACS → ⋮ → **Custom repositories** → add this repository, category
   **Integration**.
2. Install **Boks**, restart Home Assistant.
3. **Settings → Devices & services**: the mailbox is discovered
   automatically. Otherwise, *Add integration → Boks*.

You now have door state, battery, BLE link and diagnostics — read-only, no
configuration required.

## 4. (Optional) Name the mailbox

Only needed with more than one Boks. **Configure** → *Mailbox identifier* →
the reference printed on the mailbox (e.g. `F540`). Details:
[Several mailboxes](README.md#several-mailboxes).

## 5. (Optional) Enable remote opening

Adds an **Open** button — and only that. **Configure** → *Open code* → a
permanent 6-character code (`0-9`, `A`, `B`), ideally as
`!secret boks_code1`. Anyone with access to your Home Assistant can then open
the mailbox. Details: [Opening the door](README.md#opening-the-door).

## Defaults worth knowing

- **Hold connection**: off. Recommended — keeps the mailbox's Bluetooth LED
  dark and saves battery. See [Holding the link](README.md#holding-the-link).
- **Refresh interval**: `0` (disabled). Set it (in minutes) for periodic
  state refreshes, or to enable the opening-history sensors — but read
  [Opening history](README.md#opening-history) first: reading the log drains
  it.
- **Battery gauge**: meaningless with regulated lithium cells. Flip
  **Rechargeable batteries** on and use the **Battery low** sensor, not the
  percentage. See [Battery](README.md#battery-alkaline-vs-regulated-cells).

## Something not working?

See [Troubleshooting](README.md#troubleshooting) in the README, or enable
debug logs:

```yaml
logger:
  logs:
    custom_components.boks: debug
```
