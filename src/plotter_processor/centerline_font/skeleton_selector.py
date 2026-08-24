from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy import ndimage

from plotter_processor.centerline_font.candidate_score import score_candidate
from plotter_processor.centerline_font.config import CenterlineConfig
from plotter_processor.centerline_font.counter_analysis import analyze_counters
from plotter_processor.centerline_font.graph_simplifier import (
    GraphSimplificationReport,
    simplify_skeleton_graph,
)
from plotter_processor.centerline_font.models import SkeletonEdge, SkeletonNode
from plotter_processor.centerline_font.route_planner import plan_glyph_routes
from plotter_processor.centerline_font.route_quality import routing_metrics
from plotter_processor.centerline_font.skeleton_graph import build_skeleton_graph
from plotter_processor.centerline_font.skeletonizer import (
    build_skeleton,
    preprocess_skeleton,
    prune_short_spurs,
)
from plotter_processor.performance import measure_glyph_stage


@dataclass(frozen=True, slots=True)
class SelectedSkeleton:
    method: str
    skeleton: np.ndarray
    distance: np.ndarray
    component_labels: np.ndarray
    nodes: tuple[SkeletonNode, ...]
    edges: tuple[SkeletonEdge, ...]
    simplification: GraphSimplificationReport
    candidate_scores: dict[str, float]
    candidate_metrics: dict[str, dict[str, float | int | str]]
    candidate_score_components: dict[str, dict[str, float]]
    candidate_skeletons: dict[str, np.ndarray]
    fast_first: bool = False
    confidence_checks: dict[str, bool] | None = None


# Offline allowlist from build/upd12-block7-dual-candidate-audit.json. The full
# fingerprint includes algorithm version, overrides and patch identity.
_AUDITED_FAST_FIRST: dict[tuple[str, str], frozenset[str]] = {
    (
        "4dac9db3fa9ca072f7861fd916bf04bdceac6069d0f3a886f5e523d922e918f1",
        "1c9a05ecf152b1dc4f20799fa1377fcfaa0a7149b4c9755e9c0e05f7a35ff859",
    ): frozenset(
        '!"#$%\'()*+,-/023456789;=@CDFGHIJKLMNOPQRSTVWXYZ[\\]_`abcefghijklmpqrstuvwxyz}~'
        "«»БГДЖЗКЛМНОПРСТУФХЧЪЫЬЭЮЯабвгдежзийклмнопртуфхцчшэюяё–—“”„№"
    ),
}


def select_best_skeleton(
    mask: np.ndarray,
    config: CenterlineConfig,
    *,
    char: str | None = None,
    font_digest: str | None = None,
    config_fingerprint: str | None = None,
) -> SelectedSkeleton:
    selection_priority = (
        config.candidate_methods if config.skeleton_method == "auto" else (config.skeleton_method,)
    )
    audit_key = (font_digest or "", config_fingerprint or "")
    audited = _AUDITED_FAST_FIRST.get(audit_key, frozenset())
    methods = selection_priority
    if len(selection_priority) > 1 and "medial_axis" in selection_priority and audited:
        methods = ("medial_axis",) + tuple(
            method for method in selection_priority if method != "medial_axis"
        )
    prepared = preprocess_skeleton(mask)
    candidates = []
    failures: list[str] = []
    confidence_checks: dict[str, bool] | None = None
    fast_first = False
    for candidate_index, method in enumerate(methods, start=1):
        try:
            result = build_skeleton(
                mask,
                method=method,
                candidate_index=candidate_index,
                prepared=prepared,
            )
            with measure_glyph_stage("spur_pruning"):
                pruned = (
                    prune_short_spurs(
                        result.mask,
                        result.distance,
                        min_branch_width_factor=config.min_branch_width_factor,
                        ink_mask=mask,
                        max_coverage_loss=config.spur_max_coverage_loss,
                        preserve_connector_terminals=config.preserve_connector_terminals,
                    )
                    if config.spur_pruning_enabled
                    else result.mask.copy()
                )
            with measure_glyph_stage("graph_build"):
                nodes, edges = build_skeleton_graph(
                    pruned,
                    suppress_corner_diagonals=config.suppress_corner_diagonals,
                )
            with measure_glyph_stage("graph_simplify"):
                nodes, edges, report = simplify_skeleton_graph(
                    nodes, edges, distance=result.distance, config=config
                )
            report = replace(report, spurs_removed=int(result.mask.sum() - pruned.sum()))
            metrics = _candidate_metrics(mask, pruned, result.distance, nodes, edges)
            with measure_glyph_stage("routing"):
                metrics["estimated_retrace_ratio"] = float(
                    routing_metrics(edges, plan_glyph_routes(nodes, edges, config))[
                        "retrace_ratio"
                    ]
                )
            score_details = score_candidate(metrics, config.candidate_scoring)
            score = score_details.total
            candidates.append(
                (
                    score,
                    selection_priority.index(method),
                    method,
                    result,
                    pruned,
                    nodes,
                    edges,
                    report,
                    metrics,
                    score_details,
                )
            )
            if candidate_index == 1 and len(methods) > 1 and method == "medial_axis":
                confidence_checks = _confidence_checks(
                    char,
                    audited,
                    metrics,
                    max_retrace_ratio=config.max_retrace_ratio,
                )
                if all(confidence_checks.values()):
                    fast_first = True
                    break
        except ValueError as error:
            failures.append(f"{method}: {error}")
    if not candidates:
        raise ValueError("All skeleton candidates failed: " + "; ".join(failures))
    selected = min(candidates, key=lambda item: (item[0], item[1]))
    score, _, method, result, pruned, nodes, edges, report, _, _ = selected
    return SelectedSkeleton(
        method,
        pruned,
        result.distance,
        result.component_labels,
        tuple(nodes),
        tuple(edges),
        report,
        {candidate[2]: candidate[0] for candidate in candidates},
        {candidate[2]: candidate[8] for candidate in candidates},
        {candidate[2]: candidate[9].serializable() for candidate in candidates},
        {candidate[2]: candidate[4] for candidate in candidates},
        fast_first,
        confidence_checks,
    )


def _confidence_checks(
    char: str | None,
    audited: frozenset[str],
    metrics: dict[str, float | int | str],
    *,
    max_retrace_ratio: float,
) -> dict[str, bool]:
    """Conservative gate calibrated against the complete dual-candidate corpus."""
    counter_count = int(metrics["counter_count"])
    return {
        "audited_winner": char is not None and char in audited,
        "coverage": float(metrics["mask_coverage"]) >= 0.70,
        "extra": float(metrics["reconstruction_extra"]) <= 0.10,
        "topology": int(metrics["component_count"]) >= 1
        and int(metrics["micro_loop_count"]) <= 4,
        "retrace": float(metrics["estimated_retrace_ratio"]) <= max_retrace_ratio,
        "junction_count": int(metrics["junction_count"]) <= 8,
        "short_edges": int(metrics["short_edge_count"]) <= 6,
        "quality_gate": counter_count == 0
        or float(metrics["counter_preservation_ratio"]) >= 1.0,
    }


def _odd_count(edges: list[SkeletonEdge]) -> int:
    degree: dict[int, int] = {}
    for edge in edges:
        if edge.start_node_id == edge.end_node_id:
            degree[edge.start_node_id] = degree.get(edge.start_node_id, 0) + 2
        else:
            degree[edge.start_node_id] = degree.get(edge.start_node_id, 0) + 1
            degree[edge.end_node_id] = degree.get(edge.end_node_id, 0) + 1
    return sum(value % 2 for value in degree.values())


def _candidate_metrics(
    mask: np.ndarray,
    skeleton: np.ndarray,
    distance: np.ndarray,
    nodes: list[SkeletonNode],
    edges: list[SkeletonEdge],
) -> dict[str, float | int | str]:
    radii = distance[skeleton]
    radius = max(1, round(float(np.median(radii)))) if radii.size else 1
    reconstructed = ndimage.binary_dilation(skeleton, iterations=radius)
    coverage = float((reconstructed & mask).sum()) / max(1, int(mask.sum()))
    extra = float((reconstructed & ~mask).sum()) / max(1, int(reconstructed.sum()))
    mean_radius = float(np.mean(radii)) if radii.size else 0.0
    radius_cv = float(np.std(radii) / mean_radius) if mean_radius else 0.0
    loops = sum(edge.closed or edge.start_node_id == edge.end_node_id for edge in edges)
    short_edges = sum(edge.length_px < max(2.0, 2 * mean_radius) for edge in edges)
    components = len({node.component_id for node in nodes})
    false_negative = float((mask & ~reconstructed).sum()) / max(1, int(mask.sum()))
    false_positive = float((reconstructed & ~mask).sum()) / max(1, int(reconstructed.sum()))
    mask_boundary = mask & ~ndimage.binary_erosion(mask)
    boundary_distance = ndimage.distance_transform_edt(~mask_boundary)
    endpoint_nodes = [node for node in nodes if node.kind == "endpoint"]
    endpoint_penalty = sum(boundary_distance[round(node.y), round(node.x)] for node in endpoint_nodes)
    endpoint_penalty /= max(1, len(endpoint_nodes) * max(mask.shape))
    counters = analyze_counters(mask, reconstructed)
    return {
        "reconstruction_method": "median_radius_candidate_score",
        "mask_coverage": round(coverage, 6),
        "reconstruction_extra": round(extra, 6),
        "distance_balance_cv": round(radius_cv, 6),
        "endpoint_count": sum(node.kind == "endpoint" for node in nodes),
        "junction_count": sum(node.kind == "junction" for node in nodes),
        "micro_loop_count": loops,
        "short_edge_count": short_edges,
        "component_count": components,
        "odd_vertex_count": _odd_count(edges),
        "edge_count": len(edges),
        "shape_false_negative_ratio": round(false_negative, 6),
        "shape_false_positive_ratio": round(false_positive, 6),
        "endpoint_boundary_penalty": round(float(endpoint_penalty), 6),
        "counter_count": counters.significant_count,
        "counter_preservation_ratio": counters.preservation_ratio,
        "curvature_penalty": 0.0,
    }
