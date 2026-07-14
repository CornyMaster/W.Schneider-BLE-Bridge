# Model notes: WSC LC10

The reference model this project was built and tested against.

## Identification

- **Controller:** "WSC LC10", the BLE light controller built into the cabinet.
- **Advertised name:** begins with `WSC` (the scripts scan for this prefix).
- **Chip:** Nordic nRF (also exposes the Nordic Secure DFU service `0000fe59`,
  which this project does not use).
- **MAC address / service UUID:** unit-specific / firmware-specific and read at
  setup time — see the README. They are intentionally not stored in this repo.

## Lamps

Two lamps, individually switchable:

- **Outer** — perimeter lamp (lamp mask bit 0).
- **Inner** — mirror lamp (lamp mask bit 1).

Bit assignment verified on the physical device. Brightness and color
temperature apply to **both** lamps together (hardware limitation).

In Home Assistant this is presented as two lamp switches (per-lamp on/off) plus
shared **Brightness** and **Color temperature** sliders, with the real state
read back from the cabinet — see [../docs/home-assistant.md](../docs/home-assistant.md).

## Ranges

- **Brightness:** 1–100 % (the vendor app's own minimum is 10 %).
- **Color temperature:** 2000–6500 K, in 100 K steps.

## Protocol

Speaks the protocol documented in [../docs/protocol.md](../docs/protocol.md):
unencrypted GATT, no pairing/bonding, no device-side access control, big-endian
16-bit values, lamp on/off via a bit mask (not via brightness 0), periodic
keepalive required to keep the link open.

## Validation status

✅ **All commands confirmed on the physical device (July 2026)** via
`scripts/validate_protocol.py`: brightness 100/50/10 %, color temperature
cold/warm/neutral, both-on/both-off, and per-lamp switching (outer-only,
inner-only). The controller accepted connections and commands from a
previously-unknown client (a laptop) **without** any button press on the
cabinet, confirming there is no device-side access control.
