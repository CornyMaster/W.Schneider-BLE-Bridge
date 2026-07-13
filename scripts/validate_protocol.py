#!/usr/bin/env python3
"""Interactive end-to-end validation of the WSC LC10 command set.

The script sends every control command to the cabinet, one at a time, and
asks you after each step whether the expected effect was visible on the
device. It finishes with a summary you can paste into an issue or pull
request (useful when reporting results for a new cabinet model).

While the script waits for your input, a background task keeps writing the
keepalive payload — without it the controller drops the connection after
roughly 18 seconds and the remaining steps would fail.

Usage:
    python validate_protocol.py                 # scan for a 'WSC*' device
    python validate_protocol.py --mac AA:BB:..  # connect to a known address

Answer per step:  y = worked · n = did not work · any text = note ·
                  Enter = unclear
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

# Validation sequence: (title, characteristic UUID, payload, question).
# This is the exact sequence that passed on a real WSC LC10 in July 2026.
# It starts by switching both lamps on so every later effect is visible,
# and ends in the "both on" state.
STEPS: list[tuple[str, str, bytes, str]] = [
    ("Both lamps ON", wsc_lc10.CHAR_LAMP_MASK,
     wsc_lc10.encode_lamp_mask(outer=True, inner=True),
     "Are BOTH lamps on?"),
    ("Brightness 100 %", wsc_lc10.CHAR_BRIGHTNESS,
     wsc_lc10.encode_brightness(100),
     "Full brightness?"),
    ("Brightness 10 % (app minimum)", wsc_lc10.CHAR_BRIGHTNESS,
     wsc_lc10.encode_brightness(10),
     "Clearly dimmer now (~10 %)?"),
    ("Brightness 50 %", wsc_lc10.CHAR_BRIGHTNESS,
     wsc_lc10.encode_brightness(50),
     "Medium brightness (~50 %)?"),
    ("Brightness 100 %", wsc_lc10.CHAR_BRIGHTNESS,
     wsc_lc10.encode_brightness(100),
     "Back to full brightness?"),
    ("Color temperature 6500 K (cold)", wsc_lc10.CHAR_COLOR_TEMP,
     wsc_lc10.encode_color_temp(6500),
     "Cold white (bluish)?"),
    ("Color temperature 2000 K (warm)", wsc_lc10.CHAR_COLOR_TEMP,
     wsc_lc10.encode_color_temp(2000),
     "Warm white (yellowish)?"),
    ("Color temperature 4000 K (neutral)", wsc_lc10.CHAR_COLOR_TEMP,
     wsc_lc10.encode_color_temp(4000),
     "Neutral white?"),
    # Per-lamp control. The mask always sets the ABSOLUTE state of both
    # lamps; "switching one lamp" means changing its bit and keeping the
    # other bit as it is.
    ("Outer lamp OFF (inner stays on)", wsc_lc10.CHAR_LAMP_MASK,
     wsc_lc10.encode_lamp_mask(outer=False, inner=True),
     "OUTER lamp off, INNER lamp still on?"),
    ("Outer lamp ON (both on)", wsc_lc10.CHAR_LAMP_MASK,
     wsc_lc10.encode_lamp_mask(outer=True, inner=True),
     "Outer lamp back on -> both on?"),
    ("Inner lamp OFF (outer stays on)", wsc_lc10.CHAR_LAMP_MASK,
     wsc_lc10.encode_lamp_mask(outer=True, inner=False),
     "INNER lamp off, OUTER lamp still on?"),
    ("Inner lamp ON (both on)", wsc_lc10.CHAR_LAMP_MASK,
     wsc_lc10.encode_lamp_mask(outer=True, inner=True),
     "Inner lamp back on -> both on?"),
    ("Both lamps OFF", wsc_lc10.CHAR_LAMP_MASK,
     wsc_lc10.encode_lamp_mask(outer=False, inner=False),
     "Both lamps off?"),
    ("Both lamps ON", wsc_lc10.CHAR_LAMP_MASK,
     wsc_lc10.encode_lamp_mask(outer=True, inner=True),
     "Both lamps on again?"),
]


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Define and parse the command line interface."""
    parser = argparse.ArgumentParser(
        description="Interactively validate the WSC LC10 BLE command set.")
    parser.add_argument(
        "--mac", metavar="ADDRESS", default=None,
        help="BLE address of the controller (macOS: CoreBluetooth UUID). "
             "Omit to scan for a device advertising as 'WSC*'.")
    parser.add_argument(
        "--timeout", type=float, default=wsc_lc10.DEFAULT_SCAN_TIMEOUT_S,
        help="scan timeout in seconds (default: %(default)s)")
    return parser.parse_args(argv)


async def ask(prompt: str) -> str:
    """Read a line of user input without blocking the asyncio event loop.

    ``input()`` is blocking, which would also stall the keepalive task; the
    executor thread keeps the loop (and therefore the keepalive) running.
    """
    loop = asyncio.get_running_loop()
    return (await loop.run_in_executor(None, input, prompt)).strip()


async def run_validation(mac: str | None, timeout: float) -> None:
    """Connect, run all validation steps, and print the summary."""
    wsc_lc10.ensure_uuid_configured()
    print(f"Scanning for the cabinet controller (max {timeout:.0f}s) ...")
    device = await wsc_lc10.find_device(mac, timeout=timeout)
    print(f"Connecting to {device.name or '?'} ({device.address}) ...")

    async with BleakClient(device) as client:
        print("Connected.\n")
        print("Answers: y = worked · n = did not work · text = note · "
              "Enter = unclear")
        print("=" * 64)

        # Start the background keepalive; the lock serializes GATT writes so
        # keepalives never interleave with the test commands below.
        stop = asyncio.Event()
        lock = asyncio.Lock()
        keepalive_task = asyncio.create_task(
            wsc_lc10.run_keepalive(client, stop, lock))

        results: list[tuple[int, str, str, bool, str]] = []
        try:
            for index, (title, char, payload, question) in enumerate(STEPS, 1):
                async with lock:
                    try:
                        await client.write_gatt_char(char, payload,
                                                     response=True)
                        write_ok, error = True, ""
                    except Exception as exc:
                        write_ok = False
                        error = f"{type(exc).__name__}: {exc}"
                status = "sent OK" if write_ok else "WRITE FAILED"
                print(f"\n[{index}/{len(STEPS)}] {title}   "
                      f"(payload {payload.hex(' ')})  -> {status}")
                if not write_ok:
                    print(f"    ! {error}")
                answer = await ask(f"    {question}  [y/n/note]: ")
                results.append((index, title, payload.hex(" "),
                                write_ok, answer or "?"))
        finally:
            stop.set()
            await keepalive_task

        # Summary block, formatted for easy copy & paste into a report.
        confirmed = sum(1 for *_, ok, ans in results
                        if ok and ans.lower() == "y")
        print("\n" + "=" * 64)
        print("SUMMARY — please include this block when reporting results:")
        print("=" * 64)
        for index, title, payload_hex, write_ok, answer in results:
            write = "OK " if write_ok else "ERR"
            print(f"{index:>2}. {title:<34} payload={payload_hex:<12} "
                  f"write={write} answer={answer}")
        print("-" * 64)
        print(f"Confirmed working: {confirmed}/{len(STEPS)}")


def main() -> int:
    """Script entry point; returns the process exit code."""
    args = parse_args(sys.argv[1:])
    try:
        asyncio.run(run_validation(args.mac, args.timeout))
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
