#!/usr/bin/env python3
"""Plot MCU flash dump (.bin) with ASTRA-style plots."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import matplotlib.pyplot as plt

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.mcu_flight_log import load_mcu_log_as_simulation_result
from gui.visualizer import Visualizer


def main() -> None:
    parser = argparse.ArgumentParser(description="Plot MCU flash dump (.bin).")
    parser.add_argument("path", help="Path to flash dump (.bin)")
    parser.add_argument("--from-burnout", action="store_true")
    parser.add_argument("--until-apogee", action="store_true")
    args = parser.parse_args()

    result = load_mcu_log_as_simulation_result(args.path)
    visualizer = Visualizer()
    for tab_name in ("Altitude", "Apogee", "Control", "Servo"):
        fig = plt.figure(figsize=(8, 4))
        visualizer._figures[tab_name] = fig  # noqa: SLF001
    visualizer.plot(
        result,
        show_from_burnout=args.from_burnout,
        show_until_apogee=args.until_apogee,
    )
    plt.show()


if __name__ == "__main__":
    main()
