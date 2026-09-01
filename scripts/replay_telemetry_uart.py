#!/usr/bin/env python3
"""
Replay ASTRA CSV data as stub_telemetry_frame_t over UART (no CRC).

Frame layout (little-endian, packed, 21 bytes):
    uint8  state
    uint32 timeMs
    float  posZ
    float  velZ
    float  gpsSpeed
    float  gpsCourse
"""

from __future__ import annotations

import argparse
import csv
import math
import struct
import time
from pathlib import Path

import serial


FRAME_STRUCT = struct.Struct("<BIffff")
FRAME_SIZE = FRAME_STRUCT.size  # 21 bytes
STATE_STANDING = 0
STATE_ARMED = 1
STATE_ACCELERATING = 2
STATE_FREE_FLIGHT = 3
STATE_FREE_FALL = 4
STATE_LANDED = 5


def _to_float(row: dict[str, str], key: str, default: float = 0.0) -> float:
    raw = row.get(key, "")
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _build_rows(csv_path: Path, state_override: int | None) -> list[tuple[int, int, float, float, float, float]]:
    out: list[tuple[int, int, float, float, float, float]] = []
    with csv_path.open("r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    if not rows:
        return out

    vel_profile = [_to_float(row, "velocity_z", 0.0) for row in rows]
    peak_idx = max(range(len(vel_profile)), key=lambda i: vel_profile[i])

    for i, row in enumerate(rows):
        t_s = _to_float(row, "time", i * 0.01)
        time_ms = int(round(t_s * 1000.0))

        pos_z = _to_float(row, "position_z", 0.0)
        vel_z = _to_float(row, "velocity_z", 0.0)

        if "velocity_lateral" in row and row["velocity_lateral"] != "":
            v_lat = _to_float(row, "velocity_lateral", 0.0)
        else:
            vx = _to_float(row, "velocity_x", 0.0)
            vy = _to_float(row, "velocity_y", 0.0)
            v_lat = math.sqrt(vx * vx + vy * vy)

        if "gpsCourse" in row and row["gpsCourse"] != "":
            gps_course = _to_float(row, "gpsCourse", 0.0)
        else:
            gps_course = 0.0

        if state_override is not None:
            state = int(state_override)
        else:
            # State inference for replay (matches FC telemetry_state_t):
            # - ACCELERATING until max velocity_z (burnout),
            # - FREE_FLIGHT from burnout to apogee (velocity_z > 0),
            # - FREE_FALL after apogee (velocity_z <= 0).
            if i < peak_idx:
                state = STATE_ACCELERATING
            elif vel_z > 0.0:
                state = STATE_FREE_FLIGHT
            else:
                state = STATE_FREE_FALL

        out.append((state, time_ms, pos_z, vel_z, v_lat, gps_course))

    return out


def replay(port: str, baud: int, frames: list[tuple[int, int, float, float, float, float]], speed: float, loop: bool) -> None:
    if not frames:
        raise ValueError("No frames to replay.")
    if not hasattr(serial, "Serial"):
        raise RuntimeError(
            "Detected wrong 'serial' package. Install pyserial instead:\n"
            "  pip uninstall -y serial\n"
            "  pip install pyserial"
        )

    with serial.Serial(port=port, baudrate=baud, timeout=0.2) as ser:
        print(f"UART open: {port} @ {baud}, frame_size={FRAME_SIZE} bytes")
        print(f"Frames: {len(frames)}, replay speed: x{speed}")

        while True:
            wall_start = time.monotonic()
            t0_ms = frames[0][1]

            for idx, (state, t_ms, pos_z, vel_z, gps_speed, gps_course) in enumerate(frames):
                elapsed_ms = t_ms - t0_ms
                target_s = (elapsed_ms / 1000.0) / speed

                now_s = time.monotonic() - wall_start
                if target_s > now_s:
                    time.sleep(target_s - now_s)

                packet = FRAME_STRUCT.pack(state, t_ms, pos_z, vel_z, gps_speed, gps_course)
                ser.write(packet)

                if idx % 100 == 0:
                    print(
                        f"[{idx:6d}] state={state} t={t_ms:7d}ms "
                        f"z={pos_z:8.2f} vz={vel_z:7.2f} vlat={gps_speed:7.2f}"
                    )

            print("Replay finished.")
            if not loop:
                break
            print("Looping...")


def preview_frames(
    frames: list[tuple[int, int, float, float, float, float]],
    limit: int,
) -> None:
    print(f"Frame size: {FRAME_SIZE} bytes")
    print(f"Total frames: {len(frames)}")
    print("idx,state,timeMs,posZ,velZ,gpsSpeed,gpsCourse,hex")
    shown = min(limit, len(frames))
    for idx, (state, t_ms, pos_z, vel_z, gps_speed, gps_course) in enumerate(frames[:shown]):
        packet = FRAME_STRUCT.pack(state, t_ms, pos_z, vel_z, gps_speed, gps_course)
        print(
            f"{idx},{state},{t_ms},{pos_z:.3f},{vel_z:.3f},"
            f"{gps_speed:.3f},{gps_course:.3f},{packet.hex()}"
        )
    if shown < len(frames):
        print(f"... truncated, shown {shown}/{len(frames)} frames")


def main() -> None:
    p = argparse.ArgumentParser(description="Replay ASTRA CSV as telemetry UART frames (no CRC).")
    p.add_argument("--csv", required=True, help="Path to CSV (e.g. data/converted/or_3d.csv)")
    p.add_argument("--port", help="Serial port (e.g. /dev/ttyUSB0, COM5)")
    p.add_argument("--baud", type=int, default=115200, help="UART baudrate (default: 115200)")
    p.add_argument("--speed", type=float, default=1.0, help="Replay speed multiplier (e.g. 1.0, 2.0)")
    p.add_argument(
        "--state",
        type=int,
        default=None,
        help="Force telemetry state for all frames (e.g. 3 for free_flight). "
             "If not set, state is inferred: accelerating->free_flight->free_fall from velocity_z.",
    )
    p.add_argument("--dry-run", action="store_true", help="Print packed UART frames, do not open serial port.")
    p.add_argument("--limit", type=int, default=20, help="How many frames to print in --dry-run (default: 20).")
    p.add_argument("--loop", action="store_true", help="Loop replay forever.")
    args = p.parse_args()

    csv_path = Path(args.csv)
    frames = _build_rows(csv_path, args.state)
    if args.dry_run:
        preview_frames(frames, max(1, args.limit))
        return

    if not args.port:
        raise SystemExit("error: --port is required unless --dry-run is used")
    replay(args.port, args.baud, frames, args.speed, args.loop)


if __name__ == "__main__":
    main()
