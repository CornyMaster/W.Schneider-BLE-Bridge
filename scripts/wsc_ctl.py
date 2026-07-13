#!/usr/bin/env python3
"""Send a single control command to a WSC LC10 cabinet controller.

Connects, writes one command, disconnects. The controller keeps its state
between calls, and a single write needs neither the init handshake nor a
keepalive — which makes this ideal for quick manual tests and shell
scripting.

Commands:
    scan                        list BLE devices advertising as 'WSC*'
    read                        read and decode the current state
    on                          both lamps ON
    off                         both lamps OFF
    outer                       only the OUTER (perimeter) lamp on
    inner                       only the INNER (mirror) lamp on
    brightness <1..100>         set brightness in percent (both lamps)
    colortemp <2000..6500>      set color temperature in Kelvin (both lamps)
    raw <char> <hex ...>        write raw bytes, e.g.: raw c6 01 00 03 00

Note: brightness/colortemp only have a visible effect while at least one
lamp is on; the value is applied to both lamps (the hardware cannot dim
them individually).

Usage:
    python wsc_ctl.py <command> [args] [--mac ADDRESS]
"""
from __future__ import annotations

import argparse
import asyncio
import sys

try:
    from bleak import BleakClient, BleakScanner
except ImportError:
    sys.exit("bleak is not installed -> pip install -r requirements.txt")

import wsc_lc10

#: Characteristics shown by the ``read`` command, in display order.
READ_CHARS = ("c6", "c3", "c2", "c4", "c5")


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Define and parse the command line interface."""
    parser = argparse.ArgumentParser(
        description="Send a single command to a W.Schneider cabinet controller.")
    parser.add_argument(
        "--mac", metavar="ADDRESS", default=None,
        help="BLE address of the controller (macOS: CoreBluetooth UUID). "
             "Omit to scan for a device advertising as 'WSC*'.")
    parser.add_argument(
        "--timeout", type=float, default=wsc_lc10.DEFAULT_SCAN_TIMEOUT_S,
        help="scan timeout in seconds (default: %(default)s)")

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scan", help="list BLE devices advertising as 'WSC*'")
    sub.add_parser("read", help="read and decode the current state")
    sub.add_parser("on", help="both lamps ON")
    sub.add_parser("off", help="both lamps OFF")
    sub.add_parser("outer", help="only the OUTER (perimeter) lamp on")
    sub.add_parser("inner", help="only the INNER (mirror) lamp on")

    p_bri = sub.add_parser("brightness", help="set brightness in percent")
    p_bri.add_argument("percent", type=int, metavar="1..100")

    p_cct = sub.add_parser("colortemp", help="set color temperature in Kelvin")
    p_cct.add_argument("kelvin", type=int, metavar="2000..6500")

    p_raw = sub.add_parser("raw", help="write raw bytes to a characteristic")
    p_raw.add_argument("char", choices=wsc_lc10.KNOWN_SHORT_IDS,
                       help="short characteristic id (e.g. c6)")
    p_raw.add_argument("data", nargs="+",
                       help="payload as hex bytes, e.g. 01 00 03 00")

    return parser.parse_args(argv)


def build_write(args: argparse.Namespace) -> tuple[str, bytes, str]:
    """Translate parsed arguments into (characteristic, payload, description)."""
    if args.command == "on":
        return (wsc_lc10.CHAR_LAMP_MASK,
                wsc_lc10.encode_lamp_mask(outer=True, inner=True),
                "both lamps ON")
    if args.command == "off":
        return (wsc_lc10.CHAR_LAMP_MASK,
                wsc_lc10.encode_lamp_mask(outer=False, inner=False),
                "both lamps OFF")
    if args.command == "outer":
        return (wsc_lc10.CHAR_LAMP_MASK,
                wsc_lc10.encode_lamp_mask(outer=True, inner=False),
                "only OUTER lamp on")
    if args.command == "inner":
        return (wsc_lc10.CHAR_LAMP_MASK,
                wsc_lc10.encode_lamp_mask(outer=False, inner=True),
                "only INNER lamp on")
    if args.command == "brightness":
        return (wsc_lc10.CHAR_BRIGHTNESS,
                wsc_lc10.encode_brightness(args.percent),
                f"brightness {args.percent} %")
    if args.command == "colortemp":
        return (wsc_lc10.CHAR_COLOR_TEMP,
                wsc_lc10.encode_color_temp(args.kelvin),
                f"color temperature {args.kelvin} K")
    if args.command == "raw":
        payload = bytes.fromhex("".join(args.data))
        return (wsc_lc10.char_uuid(args.char), payload,
                f"raw write to {args.char}")
    raise AssertionError(f"unhandled command {args.command}")


async def scan(timeout: float) -> None:
    """List devices advertising with the expected name prefix."""
    print(f"Scanning for '{wsc_lc10.ADVERTISED_NAME_PREFIX}*' devices "
          f"(max {timeout:.0f}s) ...")
    devices = await BleakScanner.discover(timeout=timeout)
    matches = [d for d in devices
               if (d.name or "").startswith(wsc_lc10.ADVERTISED_NAME_PREFIX)]
    if not matches:
        print("No matching device found. All devices seen:")
        for d in devices:
            print(f"  {d.address}  {d.name or '(no name)'}")
        return
    for d in matches:
        print(f"  {d.address}  {d.name}")


async def read_state(mac: str | None, timeout: float) -> None:
    """Read and decode the controller's current state."""
    wsc_lc10.ensure_uuid_configured()
    device = await wsc_lc10.find_device(mac, timeout=timeout)
    async with BleakClient(device) as client:
        print(f"Current state of {device.name or '?'} ({device.address}):")
        for short in READ_CHARS:
            try:
                value = await client.read_gatt_char(wsc_lc10.char_uuid(short))
                summary = wsc_lc10.describe_value(short, value)
                print(f"  {short} = {value.hex(' '):<24} {summary}")
            except Exception as exc:
                print(f"  {short}: read failed ({type(exc).__name__})")


async def write_command(args: argparse.Namespace) -> None:
    """Connect, perform the requested single write, and report it."""
    wsc_lc10.ensure_uuid_configured()
    char, payload, description = build_write(args)
    device = await wsc_lc10.find_device(args.mac, timeout=args.timeout)
    async with BleakClient(device) as client:
        await client.write_gatt_char(char, payload, response=True)
    print(f"SENT: {description}   (payload {payload.hex(' ')})")


def main() -> int:
    """Script entry point; returns the process exit code."""
    args = parse_args(sys.argv[1:])
    try:
        if args.command == "scan":
            asyncio.run(scan(args.timeout))
        elif args.command == "read":
            asyncio.run(read_state(args.mac, args.timeout))
        else:
            asyncio.run(write_command(args))
    except wsc_lc10.DeviceNotFoundError as exc:
        print(exc)
        return 1
    except ValueError as exc:
        print(f"Invalid value: {exc}")
        return 2
    except KeyboardInterrupt:
        print("\nAborted.")
        return 130
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
