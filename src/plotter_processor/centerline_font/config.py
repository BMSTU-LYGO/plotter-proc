from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from plotter_processor.centerline_font.candidate_score import CandidateScoringWeights


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
    spur_pruning_enabled: bool
    spur_max_coverage_loss: float
    preserve_connector_terminals: bool
    preserve_counter_edges: bool
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
    candidate_scoring: CandidateScoringWeights
    glyph_overrides: dict[str, dict[str, object]]
    font_overrides: dict[str, dict[str, dict[str, object]]]
    glyph_patch_file: Path | None

    def serializable(self) -> dict[str, Any]:
        data = asdict(self)
        data["cache_directory"] = str(self.cache_directory)
        data["glyph_patch_file"] = (
            str(self.glyph_patch_file) if self.glyph_patch_file is not None else None
        )
        data["candidate_methods"] = list(self.candidate_methods)
        return data


def load_centerline_config(config: Mapping[str, object]) -> CenterlineConfig:
    root = _mapping(config, "centerline")
    render = _mapping(root, "render")
    skeleton = _mapping(root, "skeleton")
    spur_pruning_value = skeleton.get("spur_pruning", {})
    if not isinstance(spur_pruning_value, Mapping):
        raise TypeError("centerline.skeleton.spur_pruning must be a mapping")
    routing = _mapping(root, "routing")
    strokes = _mapping(root, "strokes")
    quality = _mapping(root, "quality")
    cache = _mapping(root, "cache")
    debug = _mapping(root, "debug")
    scoring_value = root.get("candidate_scoring", {})
    if not isinstance(scoring_value, Mapping):
        raise TypeError("centerline.candidate_scoring must be a mapping")
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
        spur_pruning_enabled=_optional_boolean(spur_pruning_value, "enabled", True),
        spur_max_coverage_loss=_optional_number(
            spur_pruning_value, "max_coverage_loss", 0.01, 0, 1
        ),
        preserve_connector_terminals=_optional_boolean(
            spur_pruning_value, "preserve_connector_terminals", True
        ),
        preserve_counter_edges=_optional_boolean(
            spur_pruning_value, "preserve_counter_edges", True
        ),
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
        candidate_scoring=_candidate_scoring(scoring_value),
        glyph_overrides=_glyph_overrides(root.get("glyph_overrides", {})),
        font_overrides=_font_overrides(root.get("font_overrides", {})),
        glyph_patch_file=_optional_path(root.get("glyph_patch_file")),
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


def _optional_boolean(values: Mapping[str, object], key: str, default: bool) -> bool:
    if key not in values:
        return default
    return _boolean(values, key)


def _optional_number(
    values: Mapping[str, object],
    key: str,
    default: float,
    minimum: float,
    maximum: float | None = None,
) -> float:
    if key not in values:
        return default
    return _number(values, key, minimum, maximum)


def _string(values: Mapping[str, object], key: str) -> str:
    value = values.get(key)
    if not isinstance(value, str) or not value:
        raise TypeError(f"Invalid centerline string: {key}")
    return value


def _glyph_overrides(value: object) -> dict[str, dict[str, object]]:
    if not isinstance(value, Mapping):
        raise TypeError("centerline.glyph_overrides must be a mapping")
    allowed = {
        "em_resolution_px",
        "padding_px",
        "threshold",
        "closing_radius_px",
        "skeleton_method",
        "candidate_methods",
        "simplify_tolerance_px",
        "min_branch_width_factor",
        "max_junction_cluster_px",
        "max_micro_loop_width_factor",
        "spline_smoothing_factor",
        "output_step_px",
        "junction_max_angle_deg",
        "max_retrace_ratio",
        "candidate_scoring",
        "spur_pruning",
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


def _font_overrides(value: object) -> dict[str, dict[str, dict[str, object]]]:
    if not isinstance(value, Mapping):
        raise TypeError("centerline.font_overrides must be a mapping")
    result: dict[str, dict[str, dict[str, object]]] = {}
    for digest, settings in value.items():
        if not isinstance(digest, str) or len(digest) != 64:
            raise ValueError("Each font override key must be a 64-character SHA-256")
        if not isinstance(settings, Mapping) or set(settings) != {"glyphs"}:
            raise ValueError(f"Font override {digest!r} must contain only a glyphs mapping")
        glyphs = _glyph_overrides(settings["glyphs"])
        result[digest.lower()] = glyphs
    return result


def _optional_path(value: object) -> Path | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise TypeError("centerline.glyph_patch_file must be a non-empty path")
    return Path(value)


def _candidate_scoring(values: Mapping[str, object]) -> CandidateScoringWeights:
    defaults = CandidateScoringWeights()
    names = {
        "coverage_weight": "coverage",
        "outside_weight": "outside",
        "topology_weight": "topology",
        "spur_weight": "spur",
        "micro_loop_weight": "micro_loop",
        "radius_balance_weight": "radius_balance",
        "endpoint_weight": "endpoint",
        "retrace_weight": "retrace",
        "shape_preservation_weight": "shape_preservation",
        "counter_preservation_weight": "counter_preservation",
        "curvature_weight": "curvature",
    }
    unknown = set(values) - set(names)
    if unknown:
        raise ValueError(f"Unknown candidate scoring fields: {sorted(unknown)}")
    resolved = {field: getattr(defaults, field) for field in names.values()}
    for key, field in names.items():
        if key in values:
            resolved[field] = _number(values, key, 0)
    return CandidateScoringWeights(**resolved)
