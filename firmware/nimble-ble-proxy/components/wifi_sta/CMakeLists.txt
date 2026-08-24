# esp_http_server is only used by the AP-fallback captive page (POSTs
# creds back to NVS, then reboots) — see wifi_sta.cpp's own
# `#if CONFIG_NBP_AP_FALLBACK` guard around the include and the code that
# uses it. It used to be gated here too via `if(CONFIG_NBP_AP_FALLBACK)`,
# but that guard doesn't see the Kconfig value at the point
# idf_component_register() expands PRIV_REQUIRES, so a build with
# NBP_AP_FALLBACK=y (never exercised before — the option defaults to n)
# failed with a missing esp_http_server.h. Unconditional PRIV_REQUIRES
# costs nothing: esp_http_server is already pulled into every build of
# this project by api_server/ble_httpd.
idf_component_register(
    SRCS "wifi_sta.cpp"
    INCLUDE_DIRS "." "../../include"
    REQUIRES esp_wifi esp_event esp_netif nvs_flash
    PRIV_REQUIRES log esp_http_server esp_coex
)
