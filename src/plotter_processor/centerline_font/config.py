from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class CenterlineConfig:
    algorithm_version: int
    em_resolution_px: int
    padding_px: int
    threshold: int
    closing_radius_px: int
    skeleton_method: str
    candidate_methods: tuple[str, ...]
    use_crossing_number: bool
    suppress_corner_diagonals: bool
    min_branch_width_factor: float
    max_junction_cluster_px: int
    max_micro_loop_width_factor: float
    routing_strategy: str
    allow_retrace: bool
    minimize_retrace_length: bool
    max_retrace_ratio: float
    exact_matching_max_odd_vertices: int
    fallback_strategy: str
    deterministic: bool
    tangent_sample_px: int
    junction_max_angle_deg: float
    resample_step_px: float
    simplify_tolerance_px: float
    spline_smoothing_factor: float
    output_step_px: float
    max_points_per_stroke: int
    min_mask_coverage: float
    max_reconstruction_extra: float
    max_endpoint_factor: float
    fail_on_low_quality: bool
    cache_enabled: bool
    cache_directory: Path
    debug_enabled: bool
    glyph_overrides: dict[str, dict[str, object]]

    def serializable(self) -> dict[str, Any]:
        data = asdict(self)
        data["cache_directory"] = str(self.cache_directory)
        data["candidate_methods"] = list(self.candidate_methods)
        return data


def load_centerline_config(config: Mapping[str, object]) -> CenterlineConfig:
    root = _mapping(config, "centerline")
    render = _mapping(root, "render")
    skeleton = _mapping(root, "skeleton")
    routing = _mapping(root, "routing")
    strokes = _mapping(root, "strokes")
    quality = _mapping(root, "quality")
    cache = _mapping(root, "cache")
    debug = _mapping(root, "debug")
    result = CenterlineConfig(
        algorithm_version=_integer(root, "algorithm_version", 1),
        em_resolution_px=_integer(render, "em_resolution_px", 512),
        padding_px=_integer(render, "padding_px", 16),
        threshold=_integer(render, "threshold", 1, 254),
        closing_radius_px=_integer(render, "closing_radius_px", 0),
        skeleton_method=_choice(skeleton, "method", {"auto", "medial_axis", "skeletonize"}),
        candidate_methods=_choices(skeleton, "candidate_methods", {"medial_axis", "skeletonize"}),
        use_crossing_number=_boolean(skeleton, "use_crossing_number"),
        suppress_corner_diagonals=_boolean(skeleton, "suppress_corner_diagonals"),
        min_branch_width_factor=_number(skeleton, "min_branch_width_factor", 0),
        max_junction_cluster_px=_integer(skeleton, "max_junction_cluster_px", 1),
        max_micro_loop_width_factor=_number(skeleton, "max_micro_loop_width_factor", 0),
        routing_strategy=_choice(
            routing, "strategy", {"edge", "minimum_strokes", "one_stroke_per_component"}
        ),
        allow_retrace=_boolean(routing, "allow_retrace"),
        minimize_retrace_length=_boolean(routing, "minimize_retrace_length"),
        max_retrace_ratio=_number(routing, "max_retrace_ratio", 0, 1),
        exact_matching_max_odd_vertices=_integer(routing, "exact_matching_max_odd_vertices", 2),
        fallback_strategy=_choice(routing, "fallback_strategy", {"minimum_strokes", "edge"}),
        deterministic=_boolean(routing, "deterministic"),
        tangent_sample_px=_integer(strokes, "tangent_sample_px", 1),
        junction_max_angle_deg=_number(strokes, "junction_max_angle_deg", 0, 90),
        resample_step_px=_number(strokes, "resample_step_px", 0, exclusive_min=True),
        simplify_tolerance_px=_number(strokes, "simplify_tolerance_px", 0),
        spline_smoothing_factor=_number(strokes, "spline_smoothing_factor", 0),
        output_step_px=_number(strokes, "output_step_px", 0, exclusive_min=True),
        max_points_per_stroke=_integer(strokes, "max_points_per_stroke", 2),
        min_mask_coverage=_number(quality, "min_mask_coverage", 0, 1),
        max_reconstruction_extra=_number(quality, "max_reconstruction_extra", 0, 1),
        max_endpoint_factor=_number(quality, "max_endpoint_factor", 0),
        fail_on_low_quality=_boolean(quality, "fail_on_low_quality"),
        cache_enabled=_boolean(cache, "enabled"),
        cache_directory=Path(_string(cache, "directory")),
        debug_enabled=_boolean(debug, "enabled"),
        glyph_overrides=_glyph_overrides(root.get("glyph_overrides", {})),
    )
    return result


def _mapping(values: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = values.get(key)
    if not isinstance(value, Mapping):
        raise TypeError(f"Missing or invalid centerline mapping: {key}")
    return value


def _integer(
    values: Mapping[str, object], key: str, minimum: int, maximum: int | None = None
) -> int:
    value = values.get(key)
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value < minimum
        or (maximum is not None and value > maximum)
    ):
        raise ValueError(f"Invalid centerline integer: {key}")
    return value


def _number(
    values: Mapping[str, object],
    key: str,
    minimum: float,
    maximum: float | None = None,
    *,
    exclusive_min: bool = False,
) -> float:
    value = values.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TypeError(f"Invalid centerline number: {key}")
    number = float(value)
    if (
        number < minimum
        or (exclusive_min and number == minimum)
        or (maximum is not None and number > maximum)
    ):
        raise ValueError(f"Invalid centerline number: {key}")
    return number


def _choice(values: Mapping[str, object], key: str, choices: set[str]) -> str:
    value = values.get(key)
    if not isinstance(value, str) or value not in choices:
        raise ValueError(f"Invalid centerline choice: {key}")
    return value


def _choices(values: Mapping[str, object], key: str, choices: set[str]) -> tuple[str, ...]:
    value = values.get(key)
    if not isinstance(value, list) or not value or any(item not in choices for item in value):
        raise ValueError(f"Invalid centerline choices: {key}")
    return tuple(value)


def _boolean(values: Mapping[str, object], key: str) -> bool:
    value = values.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"Invalid centerline boolean: {key}")
    return value


def _string(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise TypeError(f"Invalid centerline string: {key}")
    return value


def _glyph_overrides(value: object) -> dict[str, dict[str, object]]:
    if not isinstance(value, Mapping):
        raise TypeError("centerline.glyph_overrides must be a mapping")
    allowed = {
        "skeleton_method",
        "simplify_tolerance_px",
        "min_branch_width_factor",
        "max_retrace_ratio",
    }
    result: dict[str, dict[str, object]] = {}
    for char, override in value.items():
        if not isinstance(char, str) or len(char) != 1 or not isinstance(override, Mapping):
            raise TypeError("Each centerline glyph override must map one character to settings")
        unknown = set(override) - allowed
        if unknown:
            raise ValueError(f"Unknown glyph override fields for {char!r}: {sorted(unknown)}")
        result[char] = dict(override)
    return result
