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

One source modification, needed to build on Windows, plus one file rename:

- `components/api_proto/CMakeLists.txt` — the nanopb generator was invoked as
  hard-coded `python3`, which does not exist as an executable on Windows (it
  triggers the Microsoft Store app-execution alias and the build fails with
  *"Python was not found"*). It now uses the ESP-IDF Python interpreter through
  the standard IDF idiom `idf_build_get_property(python PYTHON)`.

  This is a portability fix, not a functional change — behaviour on Linux and
  macOS is unchanged. Submitted upstream as
  [fl4p/nimble-ble-proxy-esphome#1](https://github.com/fl4p/nimble-ble-proxy-esphome/pull/1).

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
