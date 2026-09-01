"""MCU binary flight log parsing and conversion to SimulationResult."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.simulation_engine import SimulationResult

FLIGHT_LOG_BIN_MAGIC = 0x4142494E  # 'ABIN'
FLIGHT_LOG_BIN_VERSION = 1
FLIGHT_LOG_RECORD_SIZE = 32
FLIGHT_LOG_FLASH_HEADER_SIZE = 32
FLIGHT_LOG_FLASH_OFFSET_FROM_CHIP = 0x40000  # 0x08040000 - 0x08000000

FILE_HEADER_STRUCT = struct.Struct("<I H H I")
RECORD_STRUCT = struct.Struct("<I B B H 6f")

CSV_FIELDS = (
    "time_s",
    "time_ms",
    "fc_state",
    "active",
    "servo_angle_deg",
    "position_z",
    "velocity_z",
    "velocity_lateral",
    "predicted_apogee",
    "time_to_apogee",
    "control_u",
)


@dataclass(frozen=True)
class McuFlightLogRecord:
    time_ms: int
    fc_state: int
    active: int
    servo_angle_deg: float
    position_z: float
    velocity_z: float
    velocity_lateral: float
    predicted_apogee: float
    time_to_apogee: float
    control_u: float

    @property
    def time_s(self) -> float:
        return self.time_ms * 0.001


@dataclass(frozen=True)
class FlashDumpReport:
    """Result of inspecting a raw flash dump (log region or full chip read)."""

    path: str
    base_offset: int
    region_size: int
    erased: bool
    non_ff_bytes: int
    has_abin: bool
    magic: int
    version: int | None
    record_size: int | None
    header_record_count: int | None
    records: tuple[McuFlightLogRecord, ...]

    @property
    def record_count(self) -> int:
        return len(self.records)


def parse_record(raw: bytes) -> McuFlightLogRecord:
    if len(raw) != FLIGHT_LOG_RECORD_SIZE:
        raise ValueError(f"Record must be {FLIGHT_LOG_RECORD_SIZE} bytes, got {len(raw)}")
    (
        time_ms,
        fc_state,
        active,
        servo_angle_cdeg,
        position_z,
        velocity_z,
        velocity_lateral,
        predicted_apogee,
        time_to_apogee,
        control_u,
    ) = RECORD_STRUCT.unpack(raw)
    return McuFlightLogRecord(
        time_ms=time_ms,
        fc_state=fc_state,
        active=active,
        servo_angle_deg=servo_angle_cdeg * 0.01,
        position_z=position_z,
        velocity_z=velocity_z,
        velocity_lateral=velocity_lateral,
        predicted_apogee=predicted_apogee,
        time_to_apogee=time_to_apogee,
        control_u=control_u,
    )


def _is_erased_record(raw: bytes, record_size: int) -> bool:
    return raw == b"\xFF" * record_size


def _scan_flash_records(data: bytes, data_offset: int, *, version: int) -> list[McuFlightLogRecord]:
    del version
    records: list[McuFlightLogRecord] = []
    pos = data_offset
    while pos + FLIGHT_LOG_RECORD_SIZE <= len(data):
        chunk = data[pos : pos + FLIGHT_LOG_RECORD_SIZE]
        if _is_erased_record(chunk, FLIGHT_LOG_RECORD_SIZE):
            break
        records.append(parse_record(chunk))
        pos += FLIGHT_LOG_RECORD_SIZE
    return records


def find_abin_offset(data: bytes) -> int | None:
    needle = struct.pack("<I", FLIGHT_LOG_BIN_MAGIC)
    idx = data.find(needle)
    return idx if idx >= 0 else None


def _region_stats(data: bytes, base_offset: int) -> tuple[int, int, bool]:
    region = data[base_offset:]
    non_ff = sum(1 for b in region if b != 0xFF)
    return len(region), non_ff, non_ff == 0


def inspect_flash_dump(
    path: str | Path,
    *,
    base_offset: int | None = None,
) -> FlashDumpReport:
    """Classify flash dump: erased, invalid, ABIN header only, or ABIN with samples."""
    data = Path(path).read_bytes()
    path_str = str(path)

    if base_offset is None:
        base_offset = find_abin_offset(data) or 0

    region_size, non_ff_bytes, erased = _region_stats(data, base_offset)

    if region_size < FLIGHT_LOG_FLASH_HEADER_SIZE:
        return FlashDumpReport(
            path=path_str,
            base_offset=base_offset,
            region_size=region_size,
            erased=erased,
            non_ff_bytes=non_ff_bytes,
            has_abin=False,
            magic=0,
            version=None,
            record_size=None,
            header_record_count=None,
            records=(),
        )

    magic = struct.unpack_from("<I", data, base_offset)[0]
    if magic != FLIGHT_LOG_BIN_MAGIC:
        return FlashDumpReport(
            path=path_str,
            base_offset=base_offset,
            region_size=region_size,
            erased=erased,
            non_ff_bytes=non_ff_bytes,
            has_abin=False,
            magic=magic,
            version=None,
            record_size=None,
            header_record_count=None,
            records=(),
        )

    _, version, record_size, header_count = FILE_HEADER_STRUCT.unpack_from(data, base_offset)
    records = tuple(
        _scan_flash_records(data, base_offset + FLIGHT_LOG_FLASH_HEADER_SIZE, version=version)
    )
    return FlashDumpReport(
        path=path_str,
        base_offset=base_offset,
        region_size=region_size,
        erased=erased,
        non_ff_bytes=non_ff_bytes,
        has_abin=True,
        magic=magic,
        version=version,
        record_size=record_size,
        header_record_count=header_count,
        records=records,
    )


def format_flash_dump_report(report: FlashDumpReport) -> str:
    lines = [
        f"File: {report.path}",
        f"Region offset: {report.base_offset:#x} ({report.region_size} bytes)",
    ]
    if report.erased:
        lines.append("Status: ERASED (all 0xFF in dump region)")
        return "\n".join(lines)

    if not report.has_abin:
        lines.append(f"Status: NO ABIN (magic at offset: {report.magic:#010x})")
        lines.append(
            f"Non-erased bytes: {report.non_ff_bytes} / {report.region_size} "
            f"({100.0 * report.non_ff_bytes / max(report.region_size, 1):.2f}%)"
        )
        if report.non_ff_bytes > 0:
            lines.append(
                "Region contains data but no valid ABIN header "
                "(wrong offset, corrupt log, or foreign data)."
            )
        else:
            lines.append("Region appears empty.")
        lines.append(
            f"Tip: if dump starts at chip base 0x08000000, try --offset {FLIGHT_LOG_FLASH_OFFSET_FROM_CHIP:#x}"
        )
        return "\n".join(lines)

    lines.append("Status: ABIN header OK")
    lines.append(
        f"Header: version={report.version}, record_size={report.record_size}, "
        f"record_count field={report.header_record_count} (stale at runtime)"
    )
    if not report.records:
        lines.append("Samples: none (header only — erased region, no UART frames yet?)")
    else:
        first = report.records[0]
        last = report.records[-1]
        lines.append(f"Samples: {report.record_count} records")
        lines.append(
            f"  first: t={first.time_s:.3f}s fc_state={first.fc_state} z={first.position_z:.1f}m"
        )
        lines.append(
            f"  last:  t={last.time_s:.3f}s fc_state={last.fc_state} z={last.position_z:.1f}m"
        )
    return "\n".join(lines)


def records_to_csv_rows(records: list[McuFlightLogRecord] | tuple[McuFlightLogRecord, ...]) -> list[list]:
    return [
        [
            r.time_s,
            r.time_ms,
            r.fc_state,
            r.active,
            r.servo_angle_deg,
            r.position_z,
            r.velocity_z,
            r.velocity_lateral,
            r.predicted_apogee,
            r.time_to_apogee,
            r.control_u,
        ]
        for r in records
    ]


def load_flash_dump(path: str | Path, *, base_offset: int = 0) -> list[McuFlightLogRecord]:
    """Load raw flash bytes read from CubeIDE/CubeProgrammer."""
    data = Path(path).read_bytes()
    if len(data) < base_offset + FLIGHT_LOG_FLASH_HEADER_SIZE:
        raise ValueError("Flash dump file too small")

    magic = struct.unpack_from("<I", data, base_offset)[0]
    if magic != FLIGHT_LOG_BIN_MAGIC:
        raise ValueError(
            f"No ABIN magic at offset {base_offset:#x} (got {magic:#010x}). "
            "Check FLIGHT_LOG_FLASH_BASE in firmware/astra/flight_log_config.h."
        )

    _, version, record_size, header_count = FILE_HEADER_STRUCT.unpack_from(data, base_offset)
    records = _scan_flash_records(
        data, base_offset + FLIGHT_LOG_FLASH_HEADER_SIZE, version=version
    )
    if not records:
        raise ValueError(
            "No flight samples in flash dump (ABIN header OK, but data region is empty).\n"
            "Typical causes:\n"
            "  • MCU did not receive UART telemetry (check port/wiring: firmware uses USART2, "
            "not necessarily the ST-Link USB COM port).\n"
            "  • Log region not erased (0xFF) before first boot — header write may fail.\n"
            "Correct test flow: boot MCU → run replay_telemetry_uart.py → read flash in CubeIDE "
            "without resetting → load the .bin here.\n"
            f"Header: version={version}, record_size={record_size}, "
            f"record_count={header_count} (count in flash is not updated at runtime)."
        )
    return records


def write_abin(path: str | Path, records: list[McuFlightLogRecord]) -> None:
    out = bytearray()
    out.extend(
        FILE_HEADER_STRUCT.pack(
            FLIGHT_LOG_BIN_MAGIC,
            FLIGHT_LOG_BIN_VERSION,
            FLIGHT_LOG_RECORD_SIZE,
            len(records),
        )
    )
    for rec in records:
        out.extend(
            RECORD_STRUCT.pack(
                rec.time_ms,
                rec.fc_state,
                rec.active,
                int(round(rec.servo_angle_deg * 100.0)),
                rec.position_z,
                rec.velocity_z,
                rec.velocity_lateral,
                rec.predicted_apogee,
                rec.time_to_apogee,
                rec.control_u,
            )
        )
    Path(path).write_bytes(bytes(out))


def first_brake_open(
    records: list[McuFlightLogRecord],
    *,
    eps: float = 1e-6,
) -> McuFlightLogRecord | None:
    """First sample where control_u is non-zero (first brake command)."""
    for rec in records:
        if abs(rec.control_u) > eps:
            return rec
    return None


def report_first_brake_open(records: list[McuFlightLogRecord]) -> None:
    hit = first_brake_open(records)
    if hit is None:
        print("First brake open: never (control_u stayed 0)")
        return
    print(
        f"First brake open: t={hit.time_s:.3f} s, "
        f"vz={hit.velocity_z:.2f} m/s, z={hit.position_z:.1f} m, "
        f"u={hit.control_u:.4f}, servo={hit.servo_angle_deg:.2f} deg"
    )


def records_to_simulation_result(records: list[McuFlightLogRecord]) -> "SimulationResult":
    from core.simulation_engine import SimulationResult

    report_first_brake_open(records)
    return SimulationResult(
        time=[r.time_s for r in records],
        logged_altitude=[r.position_z for r in records],
        logged_true_altitude=[],
        logged_velocity=[r.velocity_z for r in records],
        logged_predicted_apogee=[r.predicted_apogee for r in records],
        logged_control_signal=[r.control_u for r in records],
        logged_servo_angle=[r.servo_angle_deg for r in records],
    )


def load_mcu_log_as_simulation_result(path: str | Path) -> "SimulationResult":
    return records_to_simulation_result(load_flash_dump(path))
