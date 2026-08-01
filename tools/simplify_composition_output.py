from __future__ import annotations

import argparse
from pathlib import Path

from plotter_processor.config import load_yaml
from plotter_processor.gcode_exporter import generate_gcode, write_gcode_atomic
from plotter_processor.motion_config import apply_motion_profile, resolve_motion_profile
from plotter_processor.path_builder import load_path_document, save_path_document
from plotter_processor.path_simplifier import simplify_path_document
from plotter_processor.svg_exporter import export_plotter_preview


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--machine-config", type=Path, default=Path("configs/machine.yaml"))
    parser.add_argument("--motion-profile", default="fast")
    args = parser.parse_args()
    machine = load_yaml(args.machine_config)
    profile = resolve_motion_profile(machine, args.motion_profile)
    machine = apply_motion_profile(machine, profile)
    settings = machine["path_simplification"]
    paths = load_path_document(args.output_dir / "paths.json")
    paths, _ = simplify_path_document(
        paths,
        duplicate_epsilon_mm=float(settings["duplicate_epsilon_mm"]),
        min_segment_length_mm=float(settings["min_segment_length_mm"]),
        max_deviation_mm=float(settings["max_deviation_mm"]["centerline"]),
    )
    save_path_document(paths, args.output_dir / "paths.json")
    for name in ("composition-preview.svg", "plotter-preview.svg", "font-source-preview.svg"):
        export_plotter_preview(paths, args.output_dir / name)
    write_gcode_atomic(generate_gcode(paths, machine), args.output_dir / "output.gcode")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
