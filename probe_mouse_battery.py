#!/usr/bin/env python3
"""
Quick-and-dirty HID feature report dumper aimed at finding mouse battery data.

Usage examples:
  # List all HID devices so you can find VID/PID or the raw path
  python probe_mouse_battery.py

  # Probe a specific dongle by VID/PID (hex accepted) and try common report IDs
  python probe_mouse_battery.py --vid 0x1234 --pid 0x5678

  # Probe a HID path directly (copy from the listing output)
  python probe_mouse_battery.py --path '\\\\?\\hid#vid_1234&pid_5678#7&1a2b3c4d&0&0000#{...}'

  # Blind-scan feature report IDs 0x00–0x1F, requesting 32 payload bytes each time
  python probe_mouse_battery.py --vid 0x1234 --pid 0x5678 --scan 0x1F --feature-length 32

Requires the `hidapi` bindings (`pip install hidapi`). On Linux you may need udev
rules or sudo; on Windows you might have to run inside an admin shell.
"""

import argparse
import sys
import time
from dataclasses import dataclass
from typing import Iterable, List, Optional, Sequence

try:
    import hid  # type: ignore
except ImportError as exc:  # pragma: no cover - only triggered when dependency missing
    print("This script needs the 'hidapi' package. Install it via 'pip install hidapi'.")
    raise SystemExit(1) from exc


DEFAULT_REPORT_IDS: Sequence[int] = (
    0x00,
    0x01,
    0x02,
    0x03,
    0x04,
    0x05,
    0x06,
    0x10,
    0x11,
    0x20,
    0x21,
    0x30,
    0x31,
    0x40,
    0x41,
    0x81,
    0x90,
    0x91,
)


def _to_int(value: str) -> int:
    """Parse integer values from CLI, accepting decimal or hex (with/without 0x)."""
    base = 10
    cleaned = value.strip().lower()
    if cleaned.startswith("0x"):
        base = 16
        cleaned = cleaned[2:]
    elif cleaned.endswith("h"):
        base = 16
        cleaned = cleaned[:-1]
    return int(cleaned, base)


def list_hid_devices() -> None:
    """Enumerate HID devices and print a quick summary."""
    devices = list(hid.enumerate())
    if not devices:
        print("No HID devices found.")
        return

    print(f"Found {len(devices)} HID device(s):")
    for idx, dev in enumerate(devices, start=1):
        path_bytes = dev.get("path") or b""
        try:
            # Windows paths are ASCII, Linux often UTF-8; fall back to repr on failure.
            path_str = path_bytes.decode("utf-8")
        except UnicodeDecodeError:
            path_str = repr(path_bytes)

        vid = dev.get("vendor_id")
        pid = dev.get("product_id")
        man = dev.get("manufacturer_string") or ""
        prod = dev.get("product_string") or ""
        usage_page = dev.get("usage_page")
        usage = dev.get("usage")

        print(f"[{idx:02d}] VID:PID=0x{vid:04X}:0x{pid:04X}  path={path_str}")
        if man or prod:
            print(f"     {man} {prod}".rstrip())
        if usage_page is not None and usage is not None:
            print(f"     usage_page=0x{usage_page:04X} usage=0x{usage:04X}")


def decode_battery_candidates(payload: Sequence[int]) -> List[str]:
    """
    Try to spot bytes that could represent battery level.

    Heuristics:
      - values 1..100 → likely direct percentage
      - values 1..254 → interpret as 0..255 scalar
    """
    hints: List[str] = []
    seen = set()
    for idx, val in enumerate(payload):
        if val <= 0:
            continue

        label_direct = f"byte{idx}={val}%"
        if val <= 100 and label_direct not in seen:
            hints.append(f"{label_direct} (0-100 scale)")
            seen.add(label_direct)
            continue

        label_scaled = f"byte{idx}=0x{val:02X}"
        if label_scaled in seen:
            continue
        pct = val * 100.0 / 255.0
        hints.append(f"{label_scaled} (~{pct:.1f}% on 0-255 scale)")
        seen.add(label_scaled)

    return hints


def format_bytes(buf: Sequence[int]) -> str:
    return " ".join(f"{b:02X}" for b in buf)


@dataclass
class ProbeConfig:
    vid: Optional[int]
    pid: Optional[int]
    path: Optional[str]
    report_ids: Sequence[int]
    feature_length: int
    tries: int
    poll: float
    quiet_errors: bool
    send: Sequence[bytes]


def open_device(cfg: ProbeConfig) -> hid.device:
    dev = hid.device()
    if cfg.path:
        dev.open_path(cfg.path.encode("utf-8"))
    elif cfg.vid is not None and cfg.pid is not None:
        dev.open(cfg.vid, cfg.pid)
    else:
        raise ValueError("Need either --path or both --vid and --pid.")
    return dev


def parse_send_packets(hex_values: Optional[Sequence[str]]) -> Sequence[bytes]:
    if not hex_values:
        return []
    packets = []
    for raw in hex_values:
        cleaned = raw.replace(" ", "").replace("_", "")
        if len(cleaned) < 2:
            raise ValueError(f"Send packet '{raw}' is too short (need at least report ID).")
        try:
            packets.append(bytes.fromhex(cleaned))
        except ValueError as exc:
            raise ValueError(f"Cannot parse hex string '{raw}': {exc}") from exc
    return packets


def probe_once(dev: hid.device, cfg: ProbeConfig) -> None:
    for rid in cfg.report_ids:
        for attempt in range(cfg.tries):
            try:
                data = dev.get_feature_report(rid, cfg.feature_length + 1)
            except OSError as exc:
                if not cfg.quiet_errors:
                    err_info = f"{exc}"
                    if getattr(exc, "errno", None):
                        err_info = f"[errno={exc.errno}] {err_info or 'OS error'}"
                    print(f"[Report 0x{rid:02X}] attempt {attempt + 1}: read error {err_info}".rstrip())
                continue

            if not data:
                print(f"[Report 0x{rid:02X}] attempt {attempt + 1}: empty response")
                continue

            report_id = data[0]
            payload = data[1:]
            print(f"[Report 0x{rid:02X}] attempt {attempt + 1}: id=0x{report_id:02X} "
                  f"payload({len(payload)}B)={format_bytes(payload)}")
            hints = decode_battery_candidates(payload)
            if hints:
                print("    heuristics: " + "; ".join(hints))


def run_probe(cfg: ProbeConfig) -> None:
    dev: Optional[hid.device] = None
    try:
        dev = open_device(cfg)
        if cfg.send:
            for packet in cfg.send:
                try:
                    written = dev.send_feature_report(packet)
                    print(f"Sent {written} bytes: {format_bytes(packet)}")
                except OSError as exc:
                    print(f"Failed to send {format_bytes(packet)}: {exc}")

        if cfg.poll > 0:
            print(f"Polling every {cfg.poll} second(s); press Ctrl+C to stop.")
            try:
                while True:
                    probe_once(dev, cfg)
                    time.sleep(cfg.poll)
            except KeyboardInterrupt:
                print("\nStopped by user.")
        else:
            probe_once(dev, cfg)
    except Exception as exc:
        print(f"Probe aborted: {exc}")
    finally:
        if dev is not None:
            try:
                dev.close()
            except Exception:
                pass


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect HID feature reports to hunt for mouse battery data."
    )
    parser.add_argument("--vid", type=_to_int, help="USB vendor ID (decimal or hex, e.g. 0x1234).")
    parser.add_argument("--pid", type=_to_int, help="USB product ID (decimal or hex).")
    parser.add_argument("--path", help="Raw HID path string (overrides VID/PID).")
    parser.add_argument(
        "--report-id",
        dest="report_ids",
        action="append",
        type=_to_int,
        help="Feature report ID to read (can be repeated). Defaults to a curated list.",
    )
    parser.add_argument(
        "--scan",
        type=_to_int,
        help="Scan all report IDs from 0 up to the given value (inclusive).",
    )
    parser.add_argument(
        "--feature-length",
        type=int,
        default=32,
        help="Number of payload bytes to request (excluding the report ID).",
    )
    parser.add_argument(
        "--tries",
        type=int,
        default=1,
        help="Number of times to request each report ID.",
    )
    parser.add_argument(
        "--poll",
        type=float,
        default=0.0,
        help="Interval in seconds for continuous polling (0 = single shot).",
    )
    parser.add_argument(
        "--quiet-errors",
        action="store_true",
        help="Suppress repeated OSError messages when a report ID is unsupported.",
    )
    parser.add_argument(
        "--send",
        action="append",
        metavar="HEX",
        help="Optional feature report(s) to send before reading, e.g. '05 01 00'.",
    )

    args = parser.parse_args(argv)

    if args.scan is not None and args.report_ids:
        parser.error("--scan cannot be combined with explicit --report-id.")

    return args


def build_config(args: argparse.Namespace) -> ProbeConfig:
    if args.scan is not None:
        report_ids = list(range(args.scan + 1))
    elif args.report_ids:
        report_ids = args.report_ids
    else:
        report_ids = DEFAULT_REPORT_IDS

    send_packets = parse_send_packets(args.send)

    return ProbeConfig(
        vid=args.vid,
        pid=args.pid,
        path=args.path,
        report_ids=report_ids,
        feature_length=args.feature_length,
        tries=max(args.tries, 1),
        poll=args.poll,
        quiet_errors=args.quiet_errors,
        send=send_packets,
    )


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv)
    cfg = build_config(args)

    if cfg.path is None and (cfg.vid is None or cfg.pid is None):
        list_hid_devices()
        print("\nProvide --vid/--pid or --path to probe a specific device.")
        return 0

    run_probe(cfg)
    return 0


if __name__ == "__main__":
    sys.exit(main())
