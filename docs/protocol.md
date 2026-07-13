# WSC LC10 BLE protocol reference

This document describes the proprietary Bluetooth Low Energy protocol of the
**W.Schneider "WSC LC10"** light controller, reverse-engineered from HCI snoop
logs of the *Schneider Ambient Lighting* app and confirmed by live test writes
to a physical cabinet.

> **Scope / status:** Confirmed on one cabinet (model tracked in
> [`models/`](../models/)). The service and characteristic UUIDs are expected to
> be identical across all WSC LC10 controllers — only the MAC address differs
> per unit. Other controller generations may differ; see
> [adding-a-new-model.md](adding-a-new-model.md).

## Link-layer facts

- **No pairing and no bonding.** No BLE Security Manager (SMP) traffic appears
  in any capture.
- **No device-side access control.** A client that knows the MAC address may
  read and write immediately after connecting. The "press any button on the
  cabinet to pair" step required by the vendor app is **app-side only** — it
  selects the device in the app, it does not gate BLE access.
- **Idle timeout.** The controller drops a connection after roughly 18 seconds
  without traffic. A periodic keepalive keeps the link open (see below).
- **Chip.** The controller is a Nordic nRF part; it also exposes the Nordic
  Secure DFU service (`0000fe59`), which this project does not use.

## Vendor service

All light-control characteristics live under a single vendor GATT service.
The service's 128-bit UUID is baked into the controller firmware; it is **not
published by the vendor and is not shipped with this project** — read it once
from your own cabinet with [`discover_gatt.py`](../scripts/discover_gatt.py)
and fill it into your configuration (see the README).

Every characteristic shares the service UUID except for the **4th byte**, which
selects the characteristic. Writing the placeholders `<prefix>` (the first
three bytes) and `<suffix>` (everything after the 4th byte) for the parts you
copy from your device:

```
Service:  <prefix>c0<suffix>
          <prefix>NN<suffix>     NN = selector byte from the table below
```

| Selector (NN) | Function                       | Access              |
|---------------|--------------------------------|---------------------|
| c1            | status / info blob             | read                |
| c2            | color temperature (Kelvin)     | read, write         |
| c3            | brightness (0..10000)          | read, write         |
| c4            | RTC date (`YY MM DD`)          | read, write         |
| c5            | RTC time (`HH MM SS`)          | read, write, notify |
| c6            | lamp on/off mask               | read, write         |
| ce            | keepalive                      | read, write         |
| cf            | device name ("WSC LC10")       | read, write         |
| c8/c9/ca      | scenes / presets               | read, write         |
| d0/d1         | night-light schedules          | read, write         |

Values are **big-endian**. c8–d1 are out of scope for this project.

## Commands

### Brightness — c3

Two identical big-endian uint16 values (one per lamp; the device only accepts
identical values). Raw scale `0..10000` maps to `0..100 %`.

```
100 %  ->  27 10 27 10
 50 %  ->  13 88 13 88
 10 %  ->  03 e8 03 e8   (vendor app minimum)
```

A **read** returns four uint16 values: actual + target per lamp.

### Color temperature — c2

Same encoding as brightness, value is Kelvin. Range `2000..6500 K`, the vendor
app uses 100 K steps.

```
6500 K ->  19 64 19 64
4000 K ->  0f a0 0f a0
2000 K ->  07 d0 07 d0
```

### Lamp on/off mask — c6

Payload `MM 00 ZZ 00`:

- `ZZ` is the lamp bit mask — **bit 0 = outer/perimeter lamp, bit 1 = inner/
  mirror lamp** (verified on device).
- `MM` is `0x01` if any lamp is on, otherwise `0x00`.

```
00 00 00 00   both lamps OFF        <- the real "off" command
01 00 01 00   only OUTER lamp on
01 00 02 00   only INNER lamp on
01 00 03 00   both lamps ON
```

There is **no separate off command via brightness**: the mask is the absolute
on/off state of both lamps, and brightness is preserved while off. Every write
sets the state of *both* lamps at once — to change one lamp, flip its bit and
keep the other bit unchanged.

Brightness and color temperature apply to **both lamps together**; the hardware
cannot set them per lamp.

### RTC sync handshake — c4 / c5

The controller keeps a real-time clock that only its night-light scheduler
uses; it is **not required** for on/off, brightness, or color temperature.

```
c4 (date):  YY MM DD    e.g. 1a 07 0b = 2026-07-11
c5 (time):  HH MM SS
```

The vendor app writes the hour at roughly UTC-1; this project sends the real
local time from Home Assistant instead.

### Keepalive — ce

```
af 01
```

The vendor app writes this roughly every 2.5 seconds for the whole session.
This project writes it every 3 seconds while connected, comfortably below the
~18 s idle timeout.

## Sources

- HCI snoop captures of the *Schneider Ambient Lighting* app (three sessions:
  control traffic, time-stamped action protocol, and a fresh pairing session).
- Live validation with [`scripts/validate_protocol.py`](../scripts/validate_protocol.py):
  all commands confirmed on a physical WSC LC10 in July 2026.
- Full GATT dump via [`scripts/discover_gatt.py`](../scripts/discover_gatt.py).
