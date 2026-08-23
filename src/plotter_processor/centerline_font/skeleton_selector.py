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
from plotter_processor.centerline_font.skeletonizer import build_skeleton, prune_short_spurs
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


def select_best_skeleton(mask: np.ndarray, config: CenterlineConfig) -> SelectedSkeleton:
    methods = (
        config.candidate_methods if config.skeleton_method == "auto" else (config.skeleton_method,)
    )
    candidates = []
    failures: list[str] = []
    for candidate_index, method in enumerate(methods, start=1):
        try:
            result = build_skeleton(
                mask, method=method, candidate_index=candidate_index
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
                    methods.index(method),
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
    )


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
