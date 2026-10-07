#!/usr/bin/env python3
"""Create equal-geometry feedrate trials from one generated F6000 document."""
import argparse
import re
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("base", type=Path, help="G-code generated with draw F6000")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    base = args.base.read_text()
    marker = "G1 F6000.000\n"
    if marker not in base:
        raise SystemExit("base G-code has no draw F6000 marker")
    up = re.search(r"G0 Z([\d.]+)", base)
    down = re.search(r"G1 Z([\d.]+)", base)
    if not up or not down:
        raise SystemExit("base G-code has no pen transitions")
    # A long calibration stroke exposes feedrate differences alongside the text.
    calibration = (
        "; 100 mm calibration stroke\nM204 T2000.000\n"
        "G0 X20.000 Y80.000 F6000.000\n"
        f"G1 Z{down.group(1)} F1200.000\nG4 P20\n"
        "M204 T1500.000\nG1 F6000.000\nG1 X120.000 Y80.000\n"
        f"G0 Z{up.group(1)} F1200.000\n"
    )
    base = base.replace("M400\nM84\n", calibration + "M400\nM84\n", 1)
    args.output.mkdir(parents=True, exist_ok=True)
    for speed in (2000, 4000, 6000):
        result = base.replace(marker, f"G1 F{speed}.000\n")
        (args.output / f"bench_F{speed}.gcode").write_text(result)


if __name__ == "__main__":
    main()
