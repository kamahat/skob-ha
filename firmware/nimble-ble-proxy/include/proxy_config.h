// Project-wide configuration constants. Edit these to rebrand the device
// or tune the BLE proxy. Nothing here is runtime-configurable in v1.

#pragma once

// IDF v5.5 does not auto-inject sdkconfig.h; pull it in here so every
// translation unit that uses proxy_config.h also sees the CONFIG_NBP_*
// macros from main/Kconfig.projbuild.
#include "sdkconfig.h"

#include <cstddef>
#include <cstdint>

namespace proxy {

inline constexpr const char *VERSION = "0.2.1";

// Compile-time default hostname. Runtime value is exposed via
// `hostname()` below — it may be overridden by an NVS entry loaded at
// boot by `api_server::stats::apply_hostname_from_nvs()`.
inline constexpr const char *DEFAULT_HOSTNAME = "nimble-proxy";

// Mutable hostname buffer, defined in main.cpp. All consumers (mDNS,
// netif, NimBLE GAP name, aioesphomeapi DeviceInfo) should read
// through `hostname()` rather than the compile-time default so a user
// rename via /hostname takes effect after reboot.
//
// Capped at 30 so the value (+ NUL) always fits the smallest consumer:
// proxyapi_HelloResponse.name is 31 bytes. Going higher trips
// -Werror=format-truncation in handshake.cpp.
constexpr size_t HOSTNAME_MAX = 30;
extern char g_hostname[HOSTNAME_MAX + 1];

inline const char *hostname() { return g_hostname; }

inline constexpr const char *FRIENDLY_NAME = "NimBLE Proxy";
inline constexpr const char *MODEL = "esp32-s3-devkitc";
inline constexpr const char *MANUFACTURER = "Custom";

// Reported as DeviceInfoResponse.esphome_version. HA does more than sanity-check
// it: the ESPHome integration raises a **repair issue** ("update <device> to
// ESPHome 2026.5.1 or later") for any Bluetooth-proxy device reporting below
// 2026.5.1, so anything older produces a permanent warning in the UI.
//
// This is a declared version, not an implemented one — this firmware is an
// independent reimplementation of the ESPHome API, not a build of ESPHome. In
// particular it does **not** carry the low-latency event handling that real
// ESPHome 2026.5.1 introduced (BLE event dispatch cut from 0-16 ms to ~12 µs);
// the value here only tells HA's version gate that we are not a stale device.
// If HA ever raises that floor, raise this to match.
inline constexpr const char *FAKE_ESPHOME_VERSION = "2026.5.1";

// aioesphomeapi protocol version we claim to speak. 1.14 is current as of
// ESPHome 2026.x; bumping just adds optional fields, never breaks framing.
inline constexpr uint32_t API_VERSION_MAJOR = 1;
inline constexpr uint32_t API_VERSION_MINOR = 14;

// Plaintext API port — fixed by ESPHome convention.
inline constexpr uint16_t API_PORT = 6053;

// Bluetooth proxy feature flags advertised to HA.
//   bit 0 = PASSIVE_SCAN
//   bit 1 = ACTIVE_CONNECTIONS
//   bit 2 = REMOTE_CACHING  (REQUIRED by modern aioesphomeapi for any
//                            GATT connection through the proxy — we always
//                            do a fresh discovery so we ignore cache hints,
//                            but HA needs to see this bit to proceed)
//   bit 5 = RAW_ADVERTISEMENTS
// See bluetooth_proxy.h:42-50 in esphome for the full enum.
inline constexpr uint32_t BT_PROXY_FEATURE_FLAGS =
    (1u << 0) | (1u << 1) | (1u << 2) | (1u << 5);

// BLE proxy tuning.
// Trimmed 9->4 to relieve internal-DRAM pressure on this no-PSRAM S3 (see
// the rationale in sdkconfig.defaults). This is the BT-proxy slot count
// advertised to HA (bt_handlers.cpp -> BluetoothConnectionsFreeResponse.limit),
// so HA will only ever open up to 4 BLE links. Keep in sync with
// CONFIG_BT_NIMBLE_MAX_CONNECTIONS in sdkconfig.defaults AND
// proxyapi.BluetoothConnectionsFreeResponse.allocated max_count in
// components/api_proto/api_subset.options.
inline constexpr uint8_t MAX_CONNECTIONS = 4;
#ifdef CONFIG_BT_NIMBLE_MAX_CONNECTIONS
// We advertise MAX_CONNECTIONS slots to HA and size connection::g_slots by it,
// so it must never exceed what NimBLE is actually built to handle. (Guarded
// because the macro is undefined when BLE is compiled out via NBP_BLE=n.)
static_assert(MAX_CONNECTIONS <= CONFIG_BT_NIMBLE_MAX_CONNECTIONS,
              "proxy::MAX_CONNECTIONS exceeds CONFIG_BT_NIMBLE_MAX_CONNECTIONS — "
              "raise it in sdkconfig.defaults");
#endif
// 50% duty: listening half the time still catches devices that
// advertise every 100 ms-1 s in well under a second, while halving
// scanner radio-on time vs the previous 100% duty (interval=window=30).
inline constexpr uint16_t SCAN_INTERVAL_MS = 60;
inline constexpr uint16_t SCAN_WINDOW_MS = 30;
inline constexpr uint8_t ADV_BATCH_SIZE = 16;
inline constexpr uint32_t ADV_FLUSH_INTERVAL_MS = 100;

// GATT discovery batching threshold — ESPHome chunks at ~1360 B per
// BluetoothGATTGetServicesResponse to fit comfortably in a typical MTU stream.
inline constexpr size_t GATT_DISCOVERY_CHUNK_BYTES = 1360;

// Per-connection timeouts.
inline constexpr uint32_t CONNECT_TIMEOUT_MS = 8000;
inline constexpr uint32_t DISCONNECT_TIMEOUT_MS = 10000;

// BLE link-layer connection parameters, applied to every outgoing central
// connection via NimBLEClient::setConnectionParams(). Left uncalled, NimBLE
// falls back to BLE_GAP_INITIAL_CONN_ITVL_{MIN,MAX} = 30/50 ms with zero slave
// latency: the peripheral's radio must wake and respond on *every* connection
// event, 20-33 times per second, for as long as the link is held. On a
// battery-powered peripheral (observed: a mailbox lock, 58%→28% battery drop
// in 6 days while a permanent link was held) that duty cycle is the dominant
// cost — far more than the periodic application-level write a persistent
// central still needs to send to satisfy the peripheral's own watchdog.
//
// Units per Bluetooth Core spec: interval in 1.25 ms steps, latency in
// skippable connection events, timeout in 10 ms steps (must exceed
// (1+latency) * maxInterval * 2 = (1+4) * 400ms * 2 = 4000 ms — the 6000 ms
// below gives 2000 ms of margin, and stays well under any peripheral
// application watchdog measured in seconds).
#if CONFIG_SOC_WIFI_SUPPORT_5G
// esp32c5 override: GATT discovery (services -> characteristics ->
// descriptors) is many sequential ATT request/response round trips, each
// bound by roughly one connection interval — the ATT protocol allows only
// one request in flight. At 200-400 ms/interval that's 9-15+ seconds just
// in interval-bound latency for a device with a handful of services, on
// top of WiFi/BLE coexistence overhead already measured to roughly double
// connect time on this chip (see docs/hardware.md). Confirmed against the
// real mailbox: discoverAttributes() never returns — the mailbox's own
// ~30 s idle-disconnect fires mid-discovery and NimBLE doesn't recover
// from that cleanly on this target, it crashes. Latency 0 so every
// connection event is serviced immediately (needed while actively
// exchanging, not just idle-keepalive) and a tight interval close to
// NimBLE's own un-configured default (30-50 ms) so each round trip is
// ~10x faster. Costs more of the mailbox's battery per session than the
// S3's held-link tuning, but this proxy only holds the link for the
// discovery burst, not continuously — unlike the "Holding the link"
// scenario CONN_INTERVAL_MIN/MAX above are tuned for.
inline constexpr uint16_t CONN_INTERVAL_MIN = 24;          // 30 ms
inline constexpr uint16_t CONN_INTERVAL_MAX = 40;          // 50 ms
inline constexpr uint16_t CONN_LATENCY = 0;                // service every event
inline constexpr uint16_t CONN_SUPERVISION_TIMEOUT = 600;  // 6000 ms
#else
inline constexpr uint16_t CONN_INTERVAL_MIN = 160;    // 200 ms
inline constexpr uint16_t CONN_INTERVAL_MAX = 320;    // 400 ms
inline constexpr uint16_t CONN_LATENCY = 4;           // skip up to 4 events when idle
inline constexpr uint16_t CONN_SUPERVISION_TIMEOUT = 600;  // 6000 ms
#endif

// API frame limits — matches ESPHome's MAX_MESSAGE_SIZE for plaintext.
inline constexpr size_t MAX_MESSAGE_SIZE = 2048;

// Concurrent API clients. ESPHome's default is 4; we match that so HA
// can stay connected while a CLI client (esphome / aioesphomeapi) also
// inspects the device. Each slot costs ~4 KiB stack + one socket.
inline constexpr uint8_t MAX_API_CLIENTS = 4;

}  // namespace proxy
