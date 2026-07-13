"""Protocol library for the W.Schneider "WSC LC10" BLE light controller.

The WSC LC10 is the Bluetooth Low Energy light controller built into
W.Schneider mirror cabinets. It exposes an unencrypted, proprietary GATT
service (no pairing/bonding, no device-side access control). This module
contains everything the tooling in this repository needs to talk to it:

* GATT UUIDs of the vendor service and its characteristics,
* encoders/decoders for the payload formats,
* device discovery (by MAC address or by advertised name),
* a keepalive loop that prevents the controller from dropping the link.

The full protocol description lives in ``docs/protocol.md``. The command set
was validated against a real WSC LC10 in July 2026 (all commands confirmed
working on the physical device).

Requires ``bleak`` (``pip install -r requirements.txt``).
"""
from __future__ import annotations

import asyncio
from datetime import datetime

from bleak import BleakClient, BleakScanner
from bleak.backends.device import BLEDevice

# --------------------------------------------------------------------------
# GATT identifiers
# --------------------------------------------------------------------------

#: Name prefix the controller uses in its BLE advertisements ("WSC LC10").
ADVERTISED_NAME_PREFIX = "WSC"

#: Placeholder value that marks :data:`SERVICE_UUID` as not-yet-configured.
_UUID_PLACEHOLDER = "00000000-0000-0000-0000-000000000000"

#: Vendor GATT service UUID of the light controller — YOU MUST FILL THIS IN.
#:
#: This 128-bit UUID is baked into the cabinet firmware and is not shipped with
#: this project, so read it once from your own cabinet and paste it here:
#:
#:     python discover_gatt.py
#:
#: In the output, find the service that holds ~10 characteristics whose UUIDs
#: end in ...c1 through ...d1 and copy that service UUID below (lowercase). On
#: the WSC LC10 every characteristic shares this UUID except for the 4th byte
#: (characters 7-8), which selects the characteristic; :func:`char_uuid` swaps
#: it in. See the README section "Fill in your cabinet's identifiers".
SERVICE_UUID = _UUID_PLACEHOLDER


def char_uuid(short: str) -> str:
    """Derive a characteristic UUID from :data:`SERVICE_UUID`.

    ``short`` is the characteristic selector as two hex characters (e.g.
    ``"c6"``). All WSC LC10 characteristics share the service UUID except for
    the 4th byte (characters 7-8), which this function replaces.
    """
    return SERVICE_UUID[:6] + short + SERVICE_UUID[8:]


def uuid_configured() -> bool:
    """Return ``True`` once :data:`SERVICE_UUID` has been filled in."""
    return SERVICE_UUID != _UUID_PLACEHOLDER


def ensure_uuid_configured() -> None:
    """Abort with a helpful message if the service UUID is still a placeholder.

    Discovery tools (``discover_gatt.py`` and the ``scan`` command) do not need
    the UUID — that is how you obtain it — so they never call this. Every
    command that reads or writes a specific characteristic does.
    """
    if not uuid_configured():
        raise SystemExit(
            "The vendor service UUID is not configured yet.\n"
            "Read it from your cabinet with:  python discover_gatt.py\n"
            "then paste it into SERVICE_UUID at the top of wsc_lc10.py.\n"
            "See the README section 'Fill in your cabinet's identifiers'.")


CHAR_STATUS = char_uuid("c1")        # read-only status/info blob
CHAR_COLOR_TEMP = char_uuid("c2")    # color temperature in Kelvin
CHAR_BRIGHTNESS = char_uuid("c3")    # brightness, 0..10000 == 0..100 %
CHAR_RTC_DATE = char_uuid("c4")      # controller real-time clock: date
CHAR_RTC_TIME = char_uuid("c5")      # controller real-time clock: time
CHAR_LAMP_MASK = char_uuid("c6")     # on/off bit mask for both lamps
CHAR_KEEPALIVE = char_uuid("ce")     # keepalive endpoint
CHAR_DEVICE_NAME = char_uuid("cf")   # device name ("WSC LC10", writable)

#: Short ids accepted by the ``raw`` command of ``wsc_ctl.py``.
KNOWN_SHORT_IDS = ("c1", "c2", "c3", "c4", "c5", "c6", "c8", "c9",
                   "ca", "cb", "cc", "ce", "cf", "d0", "d1")

# --------------------------------------------------------------------------
# Protocol constants
# --------------------------------------------------------------------------

#: Payload the official app writes to CHAR_KEEPALIVE roughly every 2.5 s.
KEEPALIVE_PAYLOAD = bytes([0xAF, 0x01])

#: Interval used by :func:`run_keepalive`. The controller drops an idle
#: connection after roughly 18 seconds, so anything well below that is fine.
KEEPALIVE_INTERVAL_S = 2.0

#: Lamp bit assignments in the CHAR_LAMP_MASK payload (verified on device).
LAMP_OUTER = 0x01  # bit 0: outer / perimeter lamp
LAMP_INNER = 0x02  # bit 1: inner / mirror lamp

#: Brightness is written as percent * 100 (so 100 % == 10000 raw).
BRIGHTNESS_RAW_PER_PERCENT = 100
BRIGHTNESS_MIN_PERCENT = 1    # the vendor app never goes below 10 %
BRIGHTNESS_MAX_PERCENT = 100

#: Color temperature range supported by the device (vendor app: 100 K steps).
COLOR_TEMP_MIN_K = 2000
COLOR_TEMP_MAX_K = 6500

#: Default BLE scan timeout in seconds.
DEFAULT_SCAN_TIMEOUT_S = 15.0


class DeviceNotFoundError(Exception):
    """Raised when no matching cabinet controller could be discovered."""


# --------------------------------------------------------------------------
# Payload encoders
# --------------------------------------------------------------------------

def encode_u16_pair(value: int) -> bytes:
    """Encode ``value`` as two identical big-endian uint16 values.

    Brightness (c3) and color temperature (c2) writes carry the value twice:
    once per lamp (inner + outer). The device only accepts identical values,
    so this helper always duplicates the input.
    """
    if not 0 <= value <= 0xFFFF:
        raise ValueError(f"value {value} does not fit into uint16")
    high, low = (value >> 8) & 0xFF, value & 0xFF
    return bytes([high, low, high, low])


def encode_brightness(percent: int) -> bytes:
    """Encode a brightness percentage (1..100) for CHAR_BRIGHTNESS.

    The raw scale is 0..10000. Note that 0 is intentionally rejected here:
    switching the lamps off is done via the lamp mask (CHAR_LAMP_MASK), not
    via brightness 0 — the vendor app never writes brightness 0 either.
    """
    if not BRIGHTNESS_MIN_PERCENT <= percent <= BRIGHTNESS_MAX_PERCENT:
        raise ValueError(
            f"brightness must be {BRIGHTNESS_MIN_PERCENT}.."
            f"{BRIGHTNESS_MAX_PERCENT} %, got {percent}")
    return encode_u16_pair(percent * BRIGHTNESS_RAW_PER_PERCENT)


def encode_color_temp(kelvin: int) -> bytes:
    """Encode a color temperature in Kelvin (2000..6500) for CHAR_COLOR_TEMP."""
    if not COLOR_TEMP_MIN_K <= kelvin <= COLOR_TEMP_MAX_K:
        raise ValueError(
            f"color temperature must be {COLOR_TEMP_MIN_K}.."
            f"{COLOR_TEMP_MAX_K} K, got {kelvin}")
    return encode_u16_pair(kelvin)


def encode_lamp_mask(*, outer: bool, inner: bool) -> bytes:
    """Encode the absolute on/off state of BOTH lamps for CHAR_LAMP_MASK.

    Payload layout is ``MM 00 ZZ 00`` where ``ZZ`` is the lamp bit mask
    (bit 0 = outer, bit 1 = inner) and ``MM`` is 0x01 if any lamp is on,
    otherwise 0x00. There is no "toggle one lamp" command: every write sets
    the state of both lamps, so callers must pass the desired absolute state.
    """
    mask = (LAMP_OUTER if outer else 0) | (LAMP_INNER if inner else 0)
    return bytes([0x01 if mask else 0x00, 0x00, mask, 0x00])


def encode_rtc_date(now: datetime) -> bytes:
    """Encode the date part of the RTC sync handshake (``YY MM DD``)."""
    return bytes([now.year % 100, now.month, now.day])


def encode_rtc_time(now: datetime) -> bytes:
    """Encode the time part of the RTC sync handshake (``HH MM SS``)."""
    return bytes([now.hour, now.minute, now.second])


# --------------------------------------------------------------------------
# Payload decoders (for reads / diagnostics)
# --------------------------------------------------------------------------

def decode_u16_values(data: bytes) -> list[int]:
    """Split a payload into big-endian uint16 values.

    Reading c2/c3 returns FOUR uint16 values (actual + target value per
    lamp), while writes only carry two. This helper handles any length.
    """
    return [int.from_bytes(data[i:i + 2], "big")
            for i in range(0, len(data) - 1, 2)]


def describe_lamp_mask(data: bytes) -> str:
    """Return a human-readable description of a CHAR_LAMP_MASK payload."""
    if len(data) < 3:
        return "(payload too short)"
    mask = data[2]
    return {
        0x00: "both lamps OFF",
        LAMP_OUTER: "only OUTER lamp on",
        LAMP_INNER: "only INNER lamp on",
        LAMP_OUTER | LAMP_INNER: "both lamps ON",
    }.get(mask, f"unknown mask 0x{mask:02x}")


def describe_value(short: str, data: bytes) -> str:
    """Best-effort human-readable summary of a read payload for ``short``."""
    if short == "c3" and len(data) >= 2:
        values = decode_u16_values(data)
        return "brightness " + " / ".join(f"{v / 100:.0f}%" for v in values)
    if short == "c2" and len(data) >= 2:
        values = decode_u16_values(data)
        return "color temperature " + " / ".join(f"{v} K" for v in values)
    if short == "c6":
        return describe_lamp_mask(data)
    if short == "c4" and len(data) >= 3:
        return f"RTC date 20{data[0]:02d}-{data[1]:02d}-{data[2]:02d}"
    if short == "c5" and len(data) >= 3:
        return f"RTC time {data[0]:02d}:{data[1]:02d}:{data[2]:02d}"
    return ""


# --------------------------------------------------------------------------
# Device discovery
# --------------------------------------------------------------------------

async def find_device(mac: str | None = None,
                      timeout: float = DEFAULT_SCAN_TIMEOUT_S) -> BLEDevice:
    """Locate the cabinet controller and return its :class:`BLEDevice`.

    With ``mac`` given, scans for exactly that address (on macOS pass the
    CoreBluetooth UUID instead of a MAC). Without ``mac``, scans for any
    device whose advertised name starts with ``WSC`` — handy on macOS and
    when the address is not known yet.

    Raises :class:`DeviceNotFoundError` with a helpful message (including
    everything that WAS found) when no controller shows up.
    """
    if mac:
        device = await BleakScanner.find_device_by_address(mac, timeout=timeout)
        if device is None:
            raise DeviceNotFoundError(
                f"No BLE device with address {mac} found within {timeout:.0f}s. "
                "Is the cabinet powered and in range?")
        return device

    devices = await BleakScanner.discover(timeout=timeout)
    matches = [d for d in devices
               if (d.name or "").startswith(ADVERTISED_NAME_PREFIX)]
    if matches:
        if len(matches) > 1:
            print(f"Multiple '{ADVERTISED_NAME_PREFIX}*' devices found, "
                  f"using the first one:")
            for d in matches:
                print(f"  {d.address}  {d.name}")
        return matches[0]

    seen = "\n".join(f"  {d.address}  {d.name or '(no name)'}"
                     for d in devices) or "  (nothing)"
    raise DeviceNotFoundError(
        f"No device advertising as '{ADVERTISED_NAME_PREFIX}*' found within "
        f"{timeout:.0f}s.\nDevices seen during the scan:\n{seen}\n"
        "Tip: pass the controller address explicitly with --mac.")


# --------------------------------------------------------------------------
# Keepalive
# --------------------------------------------------------------------------

async def run_keepalive(client: BleakClient,
                        stop: asyncio.Event,
                        lock: asyncio.Lock) -> None:
    """Write the keepalive payload every few seconds until ``stop`` is set.

    The controller drops a connection after ~18 s without traffic, so any
    long-lived session (e.g. the interactive validation script, which waits
    for user input between steps) must run this loop as a background task.
    ``lock`` serializes GATT writes so keepalives never interleave with
    control commands issued by the caller.
    """
    while not stop.is_set():
        async with lock:
            try:
                await client.write_gatt_char(
                    CHAR_KEEPALIVE, KEEPALIVE_PAYLOAD, response=True)
            except Exception:
                # A failed keepalive usually means the link just dropped;
                # the main task will notice on its next write.
                pass
        await asyncio.sleep(KEEPALIVE_INTERVAL_S)
