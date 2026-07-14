# W.Schneider mirror cabinet — BLE bridge for Home Assistant

Turn an ESP32 into a dedicated Bluetooth Low Energy bridge that brings the
light of a **W.Schneider mirror cabinet** into Home Assistant as a proper
device — with on/off, brightness and color-temperature entities.

W.Schneider cabinets ship with a proprietary BLE light controller ("WSC LC10")
that is normally only reachable through the vendor's *Schneider Ambient
Lighting* app. This project runs an [ESPHome](https://esphome.io) BLE client on
an ESP32 that connects to that controller and exposes it to Home Assistant over
the native ESPHome API. The protocol was reverse-engineered and validated
against a real cabinet; see [docs/protocol.md](docs/protocol.md).

> **Status:** One model has been tested end-to-end (see
> [Supported models](#supported-models)). The design is meant to cover
> W.Schneider cabinets in general; other models can be added — see
> [docs/adding-a-new-model.md](docs/adding-a-new-model.md).

## Features

- A combined **Cabinet** light with on/off (both lamps), brightness (1–100 %)
  and color temperature (2000–6500 K).
- The two lamps (inner/mirror and outer/perimeter) also as separate on/off
  switches for per-lamp control.
- A connectivity sensor and a manual "pair / send init" button.
- A built-in local web interface (every entity, a live log and an OTA
  firmware-upload form) served directly by the ESP32.
- Runs autonomously on the ESP32; Home Assistant talks to it directly, no cloud
  and no vendor app involved.

## How it works

A Shelly or a passive BLE proxy is **not** enough: controlling the cabinet
requires an *active* GATT client connection, which needs an ESP32 running
ESPHome's `ble_client`. The ESP32 connects to the cabinet by MAC address (no
pairing/bonding — the controller has no device-side access control), mirrors
the Home Assistant entity state onto the device, and sends a periodic keepalive
so the controller does not drop the link. Details: [docs/protocol.md](docs/protocol.md).

## Hardware

- **An ESP32 board with Bluetooth** placed within good BLE range of the cabinet.
  Any ESP32 works — set `board:` in `esphome/mirror-cabinet.yaml` accordingly.
- A way to power it near the cabinet. If you use a mains-powered board without a
  USB port, flash it over-the-air (OTA); see the flashing step below.

The reference build uses an **IoTorero (Athom) Mini Relay RS01C3** — a
mains-powered, ESPHome-pre-flashed ESP32-C3 module. Full details, GPIO map and
first-flash notes: [docs/hardware.md](docs/hardware.md).

> ⚠ **Mains voltage:** if your board is powered from 230 V, treat wiring as
> live-mains work. Only a qualified person should do this, and only with the
> circuit de-energized.

## Repository layout

```
esphome/
  mirror-cabinet.yaml        Device config — EDIT THIS (identifiers, board)
  packages/wsc-lc10.yaml     WSC LC10 protocol implementation (generic)
  secrets.yaml.example       Template for Wi-Fi / API / OTA secrets
  docker-compose.yaml        Optional: run the ESPHome dashboard locally
scripts/
  wsc_lc10.py                Shared protocol library (UUIDs, encoders, keepalive)
  discover_gatt.py           Dump a cabinet's GATT database (find the service UUID)
  validate_protocol.py       Interactive end-to-end command test from a computer
  wsc_ctl.py                 Send a single command / read state (scripting & tests)
  requirements.txt           Python dependency (bleak)
docs/
  protocol.md                BLE protocol reference
  hardware.md                ESP32 board notes (tested: IoTorero RS01C3)
  home-assistant.md          Entities and optional light template
  adding-a-new-model.md      How to support another cabinet model
models/
  wsc-lc10.md                Notes on the tested model
```

## Setup — step by step

### 1. Prerequisites

- A computer with Bluetooth and Python 3.10+ (used to discover and validate the
  cabinet before you flash anything).
- The ESPHome tooling for building/flashing the firmware — either the
  [ESPHome dashboard](https://esphome.io/guides/installing_esphome) (a
  `docker-compose.yaml` is provided) or the `esphome` CLI.
- Your cabinet powered on and in BLE range.

Install the Python dependency:

```bash
cd scripts
python -m venv .venv && . .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. Fill in your cabinet's identifiers

Two values are specific to *your* cabinet and are intentionally **not** shipped
with this repository: its **BLE MAC address** and its **vendor service UUID**.
Read them from your own device:

```bash
# a) Find the MAC address (look for a device named "WSC ...")
python wsc_ctl.py scan

# b) Dump the GATT database and find the vendor light service UUID
python discover_gatt.py            # or: python discover_gatt.py --mac <MAC>
```

In the `discover_gatt.py` output, locate the vendor service — the one holding
~10 writable characteristics (not the standard `0x1800`/`0x1801` services). Its
UUID looks like `XXXXXXc0-XXXX-XXXX-XXXX-XXXXXXXXXXXX`; the characteristics
share it and differ only in the 4th byte (`...c2`, `...c3`, `...c6`, …).

Now enter these values in two places:

- **`scripts/wsc_lc10.py`** — set `SERVICE_UUID` to the full service UUID.
- **`esphome/mirror-cabinet.yaml`** — set `cabinet_mac`, and split the service
  UUID into `uuid_prefix` (everything before the 4th byte) and `uuid_suffix`
  (everything after it). Also set `board:` to your ESP32 board.

### 3. Validate the protocol from your computer (recommended)

Before flashing, confirm the command set works on your unit. This connects from
your computer and walks through every command, asking you to confirm the effect:

```bash
python validate_protocol.py        # or: --mac <MAC>
```

Paste the printed summary into an issue/PR if you are reporting a new model. You
can also drive single commands directly:

```bash
python wsc_ctl.py on
python wsc_ctl.py brightness 40
python wsc_ctl.py colortemp 3000
python wsc_ctl.py read
python wsc_ctl.py off
```

### 4. Prepare the ESPHome secrets

```bash
cd esphome
cp secrets.yaml.example secrets.yaml
```

Edit `secrets.yaml` and set your Wi-Fi credentials, an API encryption key
(`openssl rand -base64 32`), an OTA password and a fallback-hotspot password.
`secrets.yaml` is gitignored — never commit it.

### 5. Flash the ESP32

Using the ESPHome dashboard (`docker compose up -d` in `esphome/`, then open
`http://localhost:6052`) or the CLI:

```bash
esphome run mirror-cabinet.yaml
```

For the very first flash of a board **without a USB port**, adopt it over its
factory firmware / fallback hotspot and install wirelessly (OTA). Subsequent
updates are always OTA.

### 6. Add to Home Assistant

Home Assistant discovers the node via mDNS: **Settings → Devices & Services →
ESPHome → Add**, then enter the API encryption key from `secrets.yaml`. Assign
the entities to the cabinet's area.

**First connection = the definitive pairing test:** if the light reacts without
any button press on the cabinet, there is no device-side access control (as
observed on the tested unit). If it does not, press any button on the cabinet
while the ESP connects — the "pair / send init" button helps with the timing.

### 7. Verify

- The **Cabinet connected** sensor is on and the ESPHome log shows a stable BLE
  link (no reconnect loop).
- The **Cabinet** light switches both lamps and its brightness / color
  temperature visibly affect the lit lamp(s); **Outer lamp** / **Inner lamp**
  switch the respective lamp.
- After a Home Assistant restart the entities return; after an ESP reconnect the
  state is re-applied automatically.

## Entities

| Entity | Type | Notes |
|--------|------|-------|
| Cabinet | `light` | on/off (both lamps) + brightness + color temperature |
| Outer lamp | `switch` | perimeter lamp, per-lamp on/off |
| Inner lamp | `switch` | mirror lamp, per-lamp on/off |
| Cabinet connected | `binary_sensor` | BLE link state |
| Pair / send init | `button` | re-sends the init handshake |

The **Cabinet** light is the main control; its on/off drives both lamps, and its
brightness and color temperature apply to **both** lamps together (a hardware
limitation). The two lamp switches remain for per-lamp on/off. See
[docs/home-assistant.md](docs/home-assistant.md) for behaviour details.

## Supported models

| Model | Status | Notes |
|-------|--------|-------|
| WSC LC10 | ✅ tested end-to-end | [models/wsc-lc10.md](models/wsc-lc10.md) |

Other W.Schneider cabinets are expected to be similar but are unverified. To add
one, follow [docs/adding-a-new-model.md](docs/adding-a-new-model.md).

## Limitations

- **No reliable state feedback.** The controller does not report a trustworthy
  state, so Home Assistant works *optimistically*. Changes made through the
  vendor app are not reflected in Home Assistant.
- **Shared brightness/color.** The hardware cannot set brightness or color
  temperature per lamp.
- **Night-light schedules and scenes** are out of scope.
- **Range matters.** An active connection is more sensitive than passive
  advertising reception — place the ESP32 close to the cabinet.

## License

See [LICENSE](LICENSE).
