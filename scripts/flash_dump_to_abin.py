#!/usr/bin/env python3
"""
Inspect STM32 flight-log flash dump and optionally export .abin / .csv.

Examples:
  python3 scripts/flash_dump_to_abin.py data/mcu/flash_dump.bin
  python3 scripts/flash_dump_to_abin.py dump.bin --csv log.csv --out log.abin
  python3 scripts/flash_dump_to_abin.py full_chip.bin --offset 0x40000
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "core"))

from mcu_flight_log import (  # noqa: E402
    CSV_FIELDS,
    FLIGHT_LOG_FLASH_OFFSET_FROM_CHIP,
    format_flash_dump_report,
    inspect_flash_dump,
    records_to_csv_rows,
    report_first_brake_open,
    write_abin,
)


def _default_csv_path(dump: Path) -> Path:
    return dump.with_suffix(".csv")


def _default_abin_path(dump: Path) -> Path:
    return dump.with_suffix(".abin")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Inspect MCU flash dump (ABIN log) and optionally export files."
    )
    parser.add_argument("dump", help="Raw binary read from flash log region or full chip")
    parser.add_argument(
        "--offset",
        type=lambda x: int(x, 0),
        default=None,
        help="Byte offset where log region starts "
        f"(auto-detect ABIN, else 0; use {FLIGHT_LOG_FLASH_OFFSET_FROM_CHIP:#x} for full-chip dump)",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write .abin when samples are present (default: <dump>.abin)",
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=None,
        help="CSV output path (default: <dump>.csv)",
    )
    parser.add_argument(
        "--no-csv",
        action="store_true",
        help="Do not write CSV (still writes .abin unless --no-export)",
    )
    parser.add_argument(
        "--no-export",
        action="store_true",
        help="Only print inspection report, do not write files",
    )
    args = parser.parse_args()

    dump_path = Path(args.dump)
    if not dump_path.is_file():
        print(f"Error: not a file: {dump_path}", file=sys.stderr)
        return 2

    report = inspect_flash_dump(dump_path, base_offset=args.offset)
    print(format_flash_dump_report(report))

    if not report.has_abin or not report.records:
        return 0 if report.erased or report.has_abin else 1

    report_first_brake_open(list(report.records))

    if args.no_export:
        return 0

    records = list(report.records)
    if not args.no_csv:
        csv_path = _default_csv_path(dump_path) if args.csv is None else args.csv
        with csv_path.open("w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(CSV_FIELDS)
            writer.writerows(records_to_csv_rows(records))
        print(f"CSV: {report.record_count} records -> {csv_path}")

    abin_path = _default_abin_path(dump_path) if args.out is None else args.out
    write_abin(abin_path, records)
    print(f"ABIN: {report.record_count} records -> {abin_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
