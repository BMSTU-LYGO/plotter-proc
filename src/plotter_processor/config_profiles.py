from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MachineConfigProfile:
    raw: dict[str, object]
    feedrate: dict[str, object]
    workspace: dict[str, object]
    gcode: dict[str, object]
    page_change: dict[str, object]
    motion_analysis: dict[str, object]
    path_simplification: dict[str, object]


@dataclass(frozen=True, slots=True)
class PaperConfigProfile:
    name: str
    width_mm: float
    height_mm: float
    margins: dict[str, object]
    pagination: dict[str, object]
    grid: dict[str, object]
    holes: tuple[dict[str, object], ...]
    hole_clearance_mm: object


@dataclass(frozen=True, slots=True)
class PenConfigProfile:
    values: dict[str, object]


@dataclass(frozen=True, slots=True)
class HandwritingConfigProfile:
    variation: dict[str, object]
    spacing: dict[str, object]
    connections: dict[str, object]
    stroke_order: dict[str, object]
    routing: dict[str, object]
    retrace: dict[str, object]


@dataclass(frozen=True, slots=True)
class ConversionConfigProfile:
    size_name: str
    sizes: dict[str, object]
    size: dict[str, object]
    vector: dict[str, object]
    preview: dict[str, object]
    layout: dict[str, object]
    paragraphs: dict[str, object]
    tables: dict[str, object]
    images: dict[str, object]
    latex: dict[str, object]
    document_layout: dict[str, object]


@dataclass(frozen=True, slots=True)
class PipelineConfigProfiles:
    machine: MachineConfigProfile
    paper: PaperConfigProfile
    pen: PenConfigProfile
    handwriting: HandwritingConfigProfile
    conversion: ConversionConfigProfile


def resolve_config_profiles(
    layout: Mapping[str, object],
    machine: Mapping[str, object],
    *,
    page: str,
    size: str,
) -> PipelineConfigProfiles:
    pages = _mapping(layout, "pages")
    page_values = _mapping(pages, page)
    sizes = _mapping(layout, "sizes")
    handwriting = _mapping(layout, "handwriting")
    connections_value = layout.get("connections", handwriting.get("joining", {}))
    if not isinstance(connections_value, Mapping):
        raise TypeError("connections must be a mapping")
    resolved_machine = _resolve_page_position(machine, page)
    return PipelineConfigProfiles(
        MachineConfigProfile(
            resolved_machine,
            _mapping(resolved_machine, "feedrate_mm_min"),
            _mapping(resolved_machine, "workspace_mm"),
            _mapping(resolved_machine, "gcode"),
            _mapping(resolved_machine, "page_change"),
            _mapping(resolved_machine, "motion_analysis"),
            _mapping(resolved_machine, "path_simplification"),
        ),
        PaperConfigProfile(
            page,
            _positive(page_values, "width_mm"),
            _positive(page_values, "height_mm"),
            _mapping(layout, "margins_mm"),
            _mapping(layout, "pagination"),
            _mapping(layout, "grid"),
            _mappings(page_values, "holes"),
            page_values.get("hole_clearance_mm", 0.0),
        ),
        PenConfigProfile(_mapping(machine, "pen")),
        HandwritingConfigProfile(
            _mapping(handwriting, "variation"),
            _mapping(handwriting, "spacing"),
            dict(connections_value),
            _mapping(handwriting, "stroke_order"),
            _mapping(handwriting, "routing"),
            _mapping(handwriting, "retrace"),
        ),
        ConversionConfigProfile(
            size,
            dict(sizes),
            _mapping(sizes, size),
            _mapping(layout, "vector"),
            _mapping(layout, "preview"),
            _mapping(layout, "layout"),
            _mapping(layout, "paragraphs"),
            _mapping(layout, "tables"),
            _mapping(layout, "images"),
            _mapping(layout, "latex"),
            _mapping(layout, "document_layout"),
        ),
    )


def _resolve_page_position(
    machine: Mapping[str, object], page: str
) -> dict[str, object]:
    resolved = dict(machine)
    profiles = machine.get("page_position_profiles")
    if profiles is None:
        _mapping(machine, "page_origin_mm")
        return resolved
    if not isinstance(profiles, Mapping):
        raise TypeError("page_position_profiles must be a mapping")
    profile = profiles.get(page)
    if profile is None:
        _mapping(machine, "page_origin_mm")
        return resolved
    if not isinstance(profile, Mapping):
        raise TypeError(f"page_position_profiles.{page} must be a mapping")
    resolved["page_origin_mm"] = {
        "x": _number(profile, "origin_x_mm"),
        "y": _number(profile, "origin_y_mm"),
    }
    return resolved


def _mapping(values: Mapping[str, object], key: str) -> dict[str, object]:
    value = values.get(key)
    if not isinstance(value, Mapping):
        raise TypeError(f"Missing or invalid configuration group: {key}")
    return dict(value)


def _mappings(
    values: Mapping[str, object], key: str
) -> tuple[dict[str, object], ...]:
    value = values.get(key, ())
    if not isinstance(value, list):
        raise TypeError(f"Missing or invalid configuration list: {key}")
    if not all(isinstance(item, Mapping) for item in value):
        raise TypeError(f"All {key} entries must be mappings")
    return tuple(dict(item) for item in value)


def _positive(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"Missing or invalid positive field: {key}")
    return float(value)


def _number(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Missing or invalid numeric field: {key}")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{key} must be finite")
    return number
