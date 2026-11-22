# Gemmy Orchestra of Lights — Home Assistant Integration & CLI

[![CI](https://github.com/johnstonjay/orchestra-of-lights-ha/actions/workflows/ci.yml/badge.svg)](https://github.com/johnstonjay/orchestra-of-lights-ha/actions/workflows/ci.yml)
[![Hassfest](https://github.com/johnstonjay/orchestra-of-lights-ha/actions/workflows/hassfest.yml/badge.svg)](https://github.com/johnstonjay/orchestra-of-lights-ha/actions/workflows/hassfest.yml)
[![HACS](https://github.com/johnstonjay/orchestra-of-lights-ha/actions/workflows/hacs.yml/badge.svg)](https://github.com/johnstonjay/orchestra-of-lights-ha/actions/workflows/hacs.yml)
[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=johnstonjay&repository=orchestra-of-lights-ha&category=integration)

Unofficial, zero-dependency Home Assistant custom integration and CLI for the **Gemmy Orchestra of Lights** Wi-Fi Hub (Gen 1 & Gen 2 / Model `881995`, FCC ID `GPO883047` / `GPO883047B`).

Ditch the mobile app and control your Orchestra of Lights hub natively in Home Assistant with full support for lights, custom RGB, all 44 preset themes/lightshows, all 5 animation effects, synchronized 12-song musical lightshows, volume, Bluetooth speaker mode, built-in timer, and hub diagnostics.

---

## Features

* **Zero external Python dependencies (`requirements: []`)**: Pure Python standard library `asyncio` implementation — works out-of-the-box on HAOS, Docker, and Core.
* **Hybrid Transport (`auto` / `local` / `cloud`)**:
  * **Local LAN TCP (`port 8087`)**: Direct binary protocol + UDP `8087` discovery.
  * **AWS IoT Core MQTT over WebSocket**: Uses the hub's native unauthenticated Cognito Identity Pool (`us-east-1`) and `$aws/things/<hub_id>/...` topics — **no account login required**, works across VLANs, and provides instant push state updates.
* **14 Entities across 7 Platforms**:
  * `light`: Power ON/OFF, custom RGB color, brightness (`0–100%`), and all 44 built-in themes/lightshows as effects.
  * `media_player`: Full musical lightshow controller (Play/Pause/Resume/Next/Prev, Volume, Shuffle/Loop, all 12 songs).
  * `select` (×3): Theme (44 presets), Effect (`Steady`, `Glimmer`, `Sparkle`, `Starry Night`, `Lightshow`), and Song (12 songs).
  * `number`: Speaker Volume slider (`0–100%`).
  * `switch` (×2): Bluetooth Speaker streaming mode & Hub Built-in Timer toggle.
  * `button` (×3): Random Show, Next Song, and Refresh Status.
  * `sensor` (×3): Wi-Fi Signal (dBm), Paired 2.4 GHz Products (count + full product list in attributes), and Connection Transport (`local`/`cloud`).
* **5 Custom Home Assistant Services**:
  * `orchestra_of_lights.set_theme` — Atomic theme + effect selection.
  * `orchestra_of_lights.play_song` — Play any song by name or index (`0–11`) with optional volume.
  * `orchestra_of_lights.set_playlist` — Configure the hub's 12-song playlist order.
  * `orchestra_of_lights.set_timer` — Enable, disable, or reconfigure the hub's built-in daily timer.
  * `orchestra_of_lights.refresh` — Force an immediate refresh of state, RSSI, and paired devices.

---

## Installation

### Option 1: HACS (Custom Repository)
1. Open **HACS → Integrations → ⋮ → Custom repositories**.
2. Add `https://github.com/johnstonjay/orchestra-of-lights-ha` as category **Integration**.
3. Install **Gemmy Orchestra of Lights** and restart Home Assistant.

### Option 2: Manual Install
1. Copy `custom_components/orchestra_of_lights` into your Home Assistant `/config/custom_components/orchestra_of_lights` directory.
2. Restart Home Assistant.

### Configuration
1. Go to **Settings → Devices & Services → Add Integration → Gemmy Orchestra of Lights**.
2. Enter your **Hub ID / MAC Address** (12 hex characters—shown in your router as `espressif`, or in the official app under Hub Info).
3. *(Optional)* Enter the Hub's **Local IP Address** and leave Connection Mode on `auto`.
4. *(Recommended)* Turn **OFF** the **Hub Built-in Timer** switch if you want Home Assistant automations to manage your schedule without the hub's single daily timer conflicting.

---

## Standalone CLI Usage

Works on macOS/Linux with Python 3.11+ and zero `pip install` needed:

```bash
export OOL_HUB_ID=aabbccddeeff
export OOL_HOST=192.168.1.50   # optional

python3 ool_cli.py status
python3 ool_cli.py list
python3 ool_cli.py power on
python3 ool_cli.py theme "Christmas LightShow"
python3 ool_cli.py theme "Red & Green" --effect Sparkle
python3 ool_cli.py rgb 255 40 0 --brightness 80
python3 ool_cli.py play 7
python3 ool_cli.py volume 45
python3 ool_cli.py pause
python3 ool_cli.py timer off
```

---

## Examples

* [`examples/dashboard.yaml`](examples/dashboard.yaml) — Built-in Lovelace "Christmas Command Center" dashboard view (no custom frontend cards required).
* [`examples/christmas_show_package.yaml`](examples/christmas_show_package.yaml) — Home Assistant package with relay-safe Wave Reveal ON/OFF, Showtime Mode, Nightly Theme Rotation, and 9:30 PM Cozy Wind-Down.

---

## Protocol Overview

### Local LAN (UDP & TCP Port `8087`)
* **UDP Discovery:** Broadcast `03 00 B0 00 01` to port `8087`; hub replies with `cmd=0xB1`, MAC at `[5:11]`, group name at `[19:31]`.
* **TCP Handshake:** Time Sync `0B 00 AA 00 00 E1 <H> <M> <S> <tz_sign> <tz_abs> 00 00` → Auth Check `03 00 A0 00 01` → Version `02 00 A6 02` → State `02 00 A6 01`.
* **Keepalive:** `04 00 AF 00 00 00` every 20 seconds.
* **Commands:** Power `03 00 A6 09 <0|1>`, Theme/Effect `0B 00 AA 00 00 02 <theme> <effect> 00 00 00 00 00`, Custom RGB `0B 00 AA 00 00 03 <R> <G> <B> 00 00 00 <bri>`, Play `0B 00 AA 00 00 01 01 <idx> ...`, Pause `... 01 02 ...`, Resume `... 01 03 ...`, Volume `... 01 04 <vol> <vol> ...`, Bluetooth `03 00 A6 0D <0|1>`, Timer `0B 00 AA 00 00 E0 <en> <sh> <sm> <eh> <em> 00 00`.

### AWS IoT Core MQTT-over-WebSocket
* Authenticates via the app's unauthenticated Cognito Identity Pool (`us-east-1`) and connects via SigV4-presigned MQTT-over-WebSocket (`wss://.../mqtt`).
* **Subscribe:** `$aws/things/<hub_id>/{cmd/hub,pw,rssi,name,state,heartbeat,devicelist}`
* **Publish:** `$aws/things/<hub_id>/{request,cmd/app,name,pw,devicelist}` with compact JSON and a 4-char little-endian hex byte-length in `"length"`.

## Running Tests

```bash
python3 -m unittest discover -s tests -v
```
