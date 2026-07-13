#!/usr/bin/env python3
"""List all GATT services and characteristics of a cabinet controller.

This is a diagnostics tool: it connects to the controller (no pairing
needed), enumerates every service/characteristic with its properties and
handle, and reads each readable characteristic once. Use it to

* verify that your computer can reach the cabinet at all,
* capture a protocol snapshot when adding support for a NEW model
  (see docs/adding-a-new-model.md).

Discovery reveals structure (UUIDs, properties), not meaning: what a
characteristic does has to be determined by observing the device while the
vendor app operates it, or by careful test writes.

Usage:
    python discover_gatt.py                 # scan for a 'WSC*' device
    python discover_gatt.py --mac AA:BB:..  # connect to a known address
"""
from __future__ import annotations

import argparse
import asyncio
import sys

try:
    from bleak import BleakClient
except ImportError:
    sys.exit("bleak is not installed -> pip install -r requirements.txt")

import wsc_lc10


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Define and parse the command line interface."""
    parser = argparse.ArgumentParser(
        description="Dump the GATT database of a W.Schneider cabinet controller.")
    parser.add_argument(
        "--mac", metavar="ADDRESS", default=None,
        help="BLE address of the controller (macOS: CoreBluetooth UUID). "
             "Omit to scan for a device advertising as 'WSC*'.")
    parser.add_argument(
        "--timeout", type=float, default=wsc_lc10.DEFAULT_SCAN_TIMEOUT_S,
        help="scan timeout in seconds (default: %(default)s)")
    return parser.parse_args(argv)


async def dump_gatt(mac: str | None, timeout: float) -> None:
    """Connect to the controller and print its full GATT database."""
    print(f"Scanning for the cabinet controller (max {timeout:.0f}s) ...")
    device = await wsc_lc10.find_device(mac, timeout=timeout)
    print(f"Found: {device.name or '?'} ({device.address}) — connecting ...\n")

    async with BleakClient(device) as client:
        for service in client.services:
            print(f"Service {service.uuid}")
            for char in service.characteristics:
                props = ",".join(char.properties)
                value = ""
                # Read every readable characteristic once; the raw values help
                # with guessing what a characteristic means on unknown models.
                if "read" in char.properties:
                    try:
                        raw = await client.read_gatt_char(char)
                        value = "  = " + (raw.hex(" ") or "(empty)")
                    except Exception as exc:
                        value = f"  (read error: {type(exc).__name__})"
                print(f"  {char.uuid}  handle=0x{char.handle:04x}  [{props}]{value}")
                for descriptor in char.descriptors:
                    print(f"      descriptor {descriptor.uuid} "
                          f"(handle 0x{descriptor.handle:04x})")
        print("\nDone.")
        print("\nNext: identify the vendor light service — the one holding "
              "~10 writable\ncharacteristics (not the standard 0x1800/0x1801 "
              "services) — and paste its\nUUID into the configuration (see the "
              "README, 'Fill in your cabinet's identifiers').")


def main() -> int:
    """Script entry point; returns the process exit code."""
    args = parse_args(sys.argv[1:])
    try:
        asyncio.run(dump_gatt(args.mac, args.timeout))
    except wsc_lc10.DeviceNotFoundError as exc:
        print(exc)
        return 1
    except KeyboardInterrupt:
        print("\nAborted.")
        return 130
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
