# Hardware

Any ESP32 board with Bluetooth can run this bridge — it only needs to reach the
cabinet over BLE and stay powered. This page documents the board this project
was tested with, so you can reproduce the setup or pick something equivalent.

## Choosing a board

Requirements:

- **ESP32 with BLE** (classic ESP32, ESP32-C3, ESP32-S3, …). The bridge uses an
  active GATT client, which a Shelly or a passive BLE proxy cannot provide.
- **Placed within good BLE range** of the cabinet — an active connection is more
  sensitive than passive advertising reception.
- **A power source near the cabinet** (USB or mains, depending on the board).

On single-core boards such as the ESP32-C3, use the **ESP-IDF** framework for a
stable Wi-Fi/BLE coexistence (the provided config already does this), and keep
Wi-Fi power saving off (also already set).

## Tested example: IoTorero (Athom) Mini Relay RS01C3

The reference build uses an **IoTorero Mini Relay RS01C3** (IoTorero is the newer
brand name of Athom). It is a mains-powered, ESPHome-friendly ESP32-C3 module —
convenient when 230 V is already available near the cabinet.

Athom lists this board as **"Bluetooth Proxy Supported"** and it runs as an
ESPHome Bluetooth Proxy by default. This project instead uses it as an active
BLE client (the cabinet controller), but the vendor confirmation is useful if
you ever want the alternative "Home Assistant drives the BLE via a proxy"
architecture — see the proxy notes in the mirror-cabinet project documentation.

| Property | Value |
|----------|-------|
| SoC | ESP32-C3 (single-core RISC-V, BLE 5) |
| ESPHome board id | `esp32-c3-devkitm-1` |
| Framework | ESP-IDF (required for stable BLE on the C3) |
| Power | 230 V AC (built-in AC/DC supply); there is **no USB power input** |
| Firmware | ships pre-flashed with ESPHome ("Made for ESPHome") → OTA-adoptable |
| USB port | none accessible → **flash over the air (OTA)** |
| Recovery | UART pads (TX/RX/GND/3V3) inside the housing, for a 3.3 V USB-UART adapter, only if OTA ever becomes unreachable |

### GPIO map (for reference)

| GPIO | Function on the RS01C3 |
|------|------------------------|
| GPIO3 | push button |
| GPIO6 | relay |
| GPIO7 | status LED |
| GPIO20 | power-monitoring IC (CSE7766 or HLW8032, depending on hardware revision) |

This project **does not use the relay or the power monitor** — the board only
serves as a continuously powered ESP32 for the BLE link. You therefore do not
need to declare those GPIOs in the configuration.

> ⚠ **Mains wiring:** The RS01C3 is powered from 230 V (L/N). Its switched
> output is unused here; the **S1/S2 inputs are potential-free — do not apply
> voltage to them.** Mains work must be done de-energized by a qualified person.

### Flashing this board the first time

Because there is no USB port, the very first flash is done wirelessly:

1. Power the board from 230 V.
2. If it does not already join your Wi-Fi, it opens a fallback hotspot — connect
   to it and enter your Wi-Fi via the captive portal (the provided config
   enables both the fallback AP and the captive portal).
3. Adopt the node in the ESPHome dashboard (it appears via mDNS) and install
   this configuration wirelessly (`Install → Wirelessly`, or `esphome run`).

Switching the framework from a pre-flashed Arduino build to ESP-IDF works over
OTA: ESPHome writes to a free partition, verifies it, and only then switches
over, rolling back on failure. Keep the board powered and close to the access
point during the flash.

## Alternative

If mains wiring is not desirable, any USB-powered ESP32 placed near the cabinet
works just as well — set `board:` in `esphome/mirror-cabinet.yaml` to match it
and flash it over USB the first time.
