from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from plotter_processor.cli import main as plotter_main
from plotter_processor.config import load_yaml


def build_run_arguments(
    config_path: Path,
    profile_name: str,
    *,
    input_path: Path,
    font_path: Path,
    build_root: Path,
) -> list[str]:
    config = load_yaml(config_path)
    if config.get("version") != 1:
        raise ValueError("run config version must be 1")
    common = _mapping(config.get("common"), "common")
    profiles = _mapping(config.get("profiles"), "profiles")
    if profile_name not in profiles:
        available = ", ".join(sorted(str(name) for name in profiles))
        raise ValueError(f"Unknown run profile {profile_name!r}; available: {available}")
    profile = _mapping(profiles[profile_name], f"profiles.{profile_name}")
    flags = {**common, **_mapping(profile.get("flags"), f"profiles.{profile_name}.flags")}
    context = {
        "build_root": str(build_root),
        "font": str(font_path),
        "input": str(input_path),
        "profile": profile_name,
    }
    arguments = ["run", str(input_path)]
    for name, raw_value in flags.items():
        if not isinstance(name, str) or not name or "_" in name:
            raise ValueError(f"Invalid CLI flag name in run config: {name!r}")
        value = _format_value(raw_value, context)
        if value is False or value is None:
            continue
        arguments.append(f"--{name}")
        if value is not True:
            arguments.append(str(value))
    return arguments


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise TypeError(f"run config {label} must be a mapping")
    return value


def _format_value(value: Any, context: Mapping[str, str]) -> Any:
    if isinstance(value, str):
        try:
            return value.format_map(context)
        except KeyError as error:
            raise ValueError(f"Unknown run config placeholder: {error.args[0]}") from error
    if isinstance(value, (bool, int, float)) or value is None:
        return value
    raise ValueError(f"Run config flag values must be scalar, got {type(value).__name__}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Plotter Processor using a YAML profile")
    parser.add_argument("profile")
    parser.add_argument("--config", type=Path, default=Path("configs/run_conf.yaml"))
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--font", type=Path, required=True)
    parser.add_argument("--build-root", type=Path, default=Path("build"))
    args = parser.parse_args()
    try:
        run_arguments = build_run_arguments(
            args.config,
            args.profile,
            input_path=args.input,
            font_path=args.font,
            build_root=args.build_root,
        )
    except (OSError, TypeError, ValueError) as error:
        parser.error(str(error))
    return plotter_main(run_arguments)


if __name__ == "__main__":
    raise SystemExit(main())
