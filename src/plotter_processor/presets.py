from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ResolvedPreset:
    name: str | None
    font_mode: str
    connections: str | None
    workers: str | int
    artifact_level: str
    strict_centerline_quality: bool


_PRESETS: dict[str, dict[str, object]] = {
    "fast": {
        "font_mode": "outline",
        "connections": "off",
        "workers": "auto",
        "artifact_level": "minimal",
        "strict_centerline_quality": False,
    },
    "quality": {
        "font_mode": "centerline",
        "connections": "safe",
        "workers": "auto",
        "artifact_level": "normal",
        "strict_centerline_quality": True,
    },
    "debug": {
        "font_mode": "centerline",
        "connections": "safe",
        "workers": 1,
        "artifact_level": "debug",
        "strict_centerline_quality": False,
    },
}


def resolve_preset(
    name: str | None,
    *,
    font_mode: str | None,
    connections: str | None,
    workers: str | int | None,
    artifact_level: str | None,
    strict_centerline_quality: bool,
) -> ResolvedPreset:
    selected = _PRESETS.get(name, {})
    return ResolvedPreset(
        name,
        font_mode or str(selected.get("font_mode", "outline")),
        connections if connections is not None else _optional_string(
            selected.get("connections")
        ),
        workers if workers is not None else selected.get("workers", "auto"),
        artifact_level or str(selected.get("artifact_level", "normal")),
        strict_centerline_quality
        or bool(selected.get("strict_centerline_quality", False)),
    )


def _optional_string(value: object) -> str | None:
    return str(value) if value is not None else None
