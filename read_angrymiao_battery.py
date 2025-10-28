#!/usr/bin/env python3
"""
Utility to read Angry Miao mouse battery percentage without launching vendor software.

The tool opens the specified HID interface, sends the feature initialisation packet the
official driver emits (`SET_REPORT` with report 0, payload starting with 0xF7), then
requests feature report 0xF7 and prints the third payload byte which tracks the battery.
"""

import argparse
import sys
import time
from typing import Optional

try:
    import hid  # type: ignore
except ImportError as exc:  # pragma: no cover - dependency check only
    print("This script needs the 'hidapi' package. Install it via 'pip install hidapi'.")
    raise SystemExit(1) from exc


# Path gathered from USBPcap/Wireshark while the vendor driver was running.
DEFAULT_ANGRY_MIAO_PATH = (
    r"\\?\HID#VID_3151&PID_5007&MI_02#8&512c24e&0&0000#{4d1e55b2-f16f-11cf-88cb-001111000030}"
)
DEFAULT_VENDOR_ID = 0x3151
DEFAULT_PRODUCT_ID = 0x5007

# First byte is the report ID (0), the remaining 64 bytes match the payload captured
# from the official software via USBPcap/Wireshark.
ANGRY_MIAO_INIT_FEATURE = bytes([0x00, 0xF7] + [0x00] * 63)
ANGRY_MIAO_REPORT_ID = 0xF7
DEFAULT_BUFFER_LENGTH = 65  # report ID + 64 payload bytes


def _to_int(value: str) -> int:
    """Parse decimal or hexadecimal CLI integers (0x1234 / 1234 / 1234h)."""
    cleaned = value.strip().lower()
    base = 10
    if cleaned.startswith("0x"):
        cleaned = cleaned[2:]
        base = 16
    elif cleaned.endswith("h"):
        cleaned = cleaned[:-1]
        base = 16
    return int(cleaned, base)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read Angry Miao mouse battery percentage via HID feature reports."
    )
    parser.add_argument("--vid", type=_to_int, help="USB vendor ID of the target device.")
    parser.add_argument("--pid", type=_to_int, help="USB product ID of the target device.")
    parser.add_argument(
        "--path",
        default=None,
        help="Raw HID path string (preferred on Windows). Auto-detected when omitted.",
    )
    parser.add_argument(
        "--poll",
        type=float,
        default=0.0,
        help="Polling interval in seconds (0 for a single read).",
    )
    parser.add_argument(
        "--retry",
        type=int,
        default=3,
        help="Number of times to retry reading before giving up.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.05,
        help="Delay in seconds between init packet and read operations.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress detailed errors; only exit code indicates failure.",
    )

    args = parser.parse_args()
    if args.retry < 1:
        parser.error("--retry must be at least 1.")

    if args.path:
        return args

    if (args.vid is None) != (args.pid is None):
        parser.error("Provide either --path or both --vid and --pid.")

    vid = args.vid if args.vid is not None else DEFAULT_VENDOR_ID
    pid = args.pid if args.pid is not None else DEFAULT_PRODUCT_ID

    auto_path = find_device_path(vid, pid)
    if auto_path:
        args.path = auto_path
        args.vid = vid
        args.pid = pid
        return args

    if args.vid is None and args.pid is None:
        args.path = DEFAULT_ANGRY_MIAO_PATH
        args.vid = vid
        args.pid = pid
    return args


def _decode_path(raw_path: object) -> Optional[str]:
    if raw_path is None:
        return None
    if isinstance(raw_path, bytes):
        try:
            return raw_path.decode("utf-8")
        except UnicodeDecodeError:
            return raw_path.decode("latin-1")
    if isinstance(raw_path, str):
        return raw_path
    return None


def find_device_path(vid: int, pid: int) -> Optional[str]:
    """
    Locate a HID path for the given VID/PID combination.
    """
    matches: list[tuple[str, dict]] = []
    for dev_info in hid.enumerate(vid, pid):
        path = _decode_path(dev_info.get("path"))
        if not path:
            continue
        matches.append((path, dev_info))

    if not matches:
        return None

    # Prefer interface #2 (battery endpoint), fall back to the first match.
    for path, dev_info in matches:
        interface_no = dev_info.get("interface_number")
        if interface_no == 2:
            return path

    lower_matches = [(path, dev_info) for path, dev_info in matches if "mi_02" in path.lower()]
    if lower_matches:
        return lower_matches[0][0]

    return matches[0][0]
    return None


def open_device(path: Optional[str], vid: Optional[int], pid: Optional[int]) -> hid.device:
    dev = hid.device()
    if path:
        dev.open_path(path.encode("utf-8"))
    elif vid is not None and pid is not None:
        dev.open(vid, pid)
    else:
        raise ValueError("Need path or VID/PID to open device.")
    return dev


def query_battery(dev: hid.device, delay: float, retry: int, quiet: bool) -> Optional[int]:
    """
    Send the initialisation feature report and read report 0xF7.

    Returns None if the battery byte could not be retrieved.
    """
    for attempt in range(1, retry + 1):
        try:
            dev.send_feature_report(ANGRY_MIAO_INIT_FEATURE)
        except OSError as exc:
            if not quiet:
                print(f"[attempt {attempt}] Failed to send init report: {exc}")
            continue

        if delay > 0:
            time.sleep(delay)

        try:
            data = dev.get_feature_report(ANGRY_MIAO_REPORT_ID, DEFAULT_BUFFER_LENGTH)
        except OSError as exc:
            if not quiet:
                print(f"[attempt {attempt}] Failed to read report 0x{ANGRY_MIAO_REPORT_ID:02X}: {exc}")
            continue

        if len(data) < 4 or data[0] != ANGRY_MIAO_REPORT_ID:
            if not quiet:
                payload_hex = " ".join(f"{b:02X}" for b in data)
                print(f"[attempt {attempt}] Unexpected report format: {payload_hex}")
            continue

        payload = data[1:]
        battery = payload[2]
        return battery

    return None


def main() -> int:
    args = parse_args()
    try:
        dev = open_device(args.path, args.vid, args.pid)
    except Exception as exc:
        if not args.quiet:
            print(f"Unable to open device: {exc}")
        return 1

    try:
        if args.poll > 0:
            try:
                while True:
                    battery = query_battery(dev, args.delay, args.retry, args.quiet)
                    if battery is None:
                        if not args.quiet:
                            print("Battery read failed.")
                        return 1
                    print(f"{battery}")
                    time.sleep(args.poll)
            except KeyboardInterrupt:
                return 0
        else:
            battery = query_battery(dev, args.delay, args.retry, args.quiet)
            if battery is None:
                if not args.quiet:
                    print("Battery read failed.")
                return 1
            print(f"{battery}")
            return 0
    finally:
        try:
            dev.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
