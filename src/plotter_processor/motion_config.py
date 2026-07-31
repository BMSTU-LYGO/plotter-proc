from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class PenMotionConfig:
    up_z_mm: float
    down_z_mm: float
    down_settle_ms: int


@dataclass(frozen=True, slots=True)
class FeedrateConfig:
    draw_mm_min: float
    travel_mm_min: float
    z_mm_min: float


@dataclass(frozen=True, slots=True)
class ResolvedMotionProfile:
    name: str
    pen: PenMotionConfig
    feedrate: FeedrateConfig


def resolve_motion_profile(
    machine: dict[str, Any], requested: str | None = None
) -> ResolvedMotionProfile:
    section = machine.get("motion_profiles")
    if section is None:
        if requested not in (None, "safe"):
            raise ValueError("Legacy machine config only provides the safe motion profile")
        return _build("safe", _mapping(machine, "pen"), _mapping(machine, "feedrate_mm_min"))
    if not isinstance(section, dict):
        raise TypeError("motion_profiles must be a mapping")
    profiles = _mapping(section, "profiles")
    name = requested or section.get("default")
    if not isinstance(name, str) or name not in profiles:
        available = ", ".join(sorted(profiles))
        raise ValueError(f"Unknown motion profile {name!r}. Available profiles: {available}")
    raw = profiles[name]
    if not isinstance(raw, dict):
        raise TypeError(f"motion profile {name!r} must be a mapping")
    return _build(name, _mapping(raw, "pen"), _mapping(raw, "feedrate_mm_min"))


def apply_motion_profile(machine: dict[str, Any], profile: ResolvedMotionProfile) -> dict[str, Any]:
    resolved = dict(machine)
    resolved["pen"] = {
        "up_z_mm": profile.pen.up_z_mm,
        "down_z_mm": profile.pen.down_z_mm,
        "down_settle_ms": profile.pen.down_settle_ms,
    }
    resolved["feedrate_mm_min"] = {
        "draw": profile.feedrate.draw_mm_min,
        "travel": profile.feedrate.travel_mm_min,
        "z": profile.feedrate.z_mm_min,
    }
    return resolved


def _build(name: str, pen: dict[str, Any], feed: dict[str, Any]) -> ResolvedMotionProfile:
    settle = pen.get("down_settle_ms", pen.get("settle_ms"))
    if isinstance(settle, bool) or not isinstance(settle, int) or settle < 0:
        raise ValueError("pen.down_settle_ms must be a non-negative integer")
    up = _number(pen, "up_z_mm")
    down = _number(pen, "down_z_mm")
    if up <= down:
        raise ValueError("pen.up_z_mm must be greater than pen.down_z_mm")
    return ResolvedMotionProfile(
        name,
        PenMotionConfig(up, down, settle),
        FeedrateConfig(_positive(feed, "draw"), _positive(feed, "travel"), _positive(feed, "z")),
    )


def _mapping(data: dict[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key)
    if not isinstance(value, dict):
        raise TypeError(f"{key} must be a mapping")
    return value


def _number(data: dict[str, Any], key: str) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"{key} must be a number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{key} must be finite")
    return result


def _positive(data: dict[str, Any], key: str) -> float:
    value = _number(data, key)
    if value <= 0:
        raise ValueError(f"{key} must be positive")
    return value
