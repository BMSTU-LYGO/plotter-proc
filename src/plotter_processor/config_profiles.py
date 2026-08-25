from __future__ import annotations

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
    return PipelineConfigProfiles(
        MachineConfigProfile(
            dict(machine),
            _mapping(machine, "feedrate_mm_min"),
            _mapping(machine, "workspace_mm"),
            _mapping(machine, "gcode"),
            _mapping(machine, "page_change"),
            _mapping(machine, "motion_analysis"),
            _mapping(machine, "path_simplification"),
        ),
        PaperConfigProfile(
            page,
            _positive(page_values, "width_mm"),
            _positive(page_values, "height_mm"),
            _mapping(layout, "margins_mm"),
            _mapping(layout, "pagination"),
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


def _mapping(values: Mapping[str, object], key: str) -> dict[str, object]:
    value = values.get(key)
    if not isinstance(value, Mapping):
        raise TypeError(f"Missing or invalid configuration group: {key}")
    return dict(value)


def _positive(values: Mapping[str, object], key: str) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"Missing or invalid positive field: {key}")
    return float(value)
