from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np
from scipy import ndimage

from plotter_processor.centerline_font.config import CenterlineConfig
from plotter_processor.centerline_font.graph_simplifier import (
    GraphSimplificationReport,
    simplify_skeleton_graph,
)
from plotter_processor.centerline_font.models import SkeletonEdge, SkeletonNode
from plotter_processor.centerline_font.route_planner import plan_glyph_routes
from plotter_processor.centerline_font.route_quality import routing_metrics
from plotter_processor.centerline_font.skeleton_graph import build_skeleton_graph
from plotter_processor.centerline_font.skeletonizer import build_skeleton, prune_short_spurs


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
    candidate_metrics: dict[str, dict[str, float | int]]
    candidate_skeletons: dict[str, np.ndarray]


def select_best_skeleton(mask: np.ndarray, config: CenterlineConfig) -> SelectedSkeleton:
    methods = (
        config.candidate_methods if config.skeleton_method == "auto" else (config.skeleton_method,)
    )
    candidates = []
    failures: list[str] = []
    for method in methods:
        try:
            result = build_skeleton(mask, method=method)
            pruned = prune_short_spurs(
                result.mask,
                result.distance,
                min_branch_width_factor=config.min_branch_width_factor,
            )
            nodes, edges = build_skeleton_graph(
                pruned,
                suppress_corner_diagonals=config.suppress_corner_diagonals,
            )
            nodes, edges, report = simplify_skeleton_graph(
                nodes, edges, distance=result.distance, config=config
            )
            report = replace(report, spurs_removed=int(result.mask.sum() - pruned.sum()))
            metrics = _candidate_metrics(mask, pruned, result.distance, nodes, edges)
            metrics["estimated_retrace_ratio"] = float(
                routing_metrics(edges, plan_glyph_routes(nodes, edges, config))["retrace_ratio"]
            )
            score = _candidate_score(metrics)
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
                )
            )
        except ValueError as error:
            failures.append(f"{method}: {error}")
    if not candidates:
        raise ValueError("All skeleton candidates failed: " + "; ".join(failures))
    selected = min(candidates, key=lambda item: (item[0], item[1]))
    score, _, method, result, pruned, nodes, edges, report, _ = selected
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
) -> dict[str, float | int]:
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
    return {
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
    }


def _candidate_score(metrics: dict[str, float | int]) -> float:
    """Lower is better; combine geometry and topology instead of edge count alone."""
    topology = (
        int(metrics["edge_count"])
        + int(metrics["junction_count"]) * 2
        + int(metrics["odd_vertex_count"]) * 0.5
    )
    geometry_tiebreaker = (
        float(metrics["estimated_retrace_ratio"]) * 100
        + int(metrics["micro_loop_count"]) * 3
        + int(metrics["short_edge_count"]) * 0.1
        + int(metrics["component_count"]) * 0.1
        + (1 - float(metrics["mask_coverage"])) * 2
        + float(metrics["reconstruction_extra"]) * 2
        + float(metrics["distance_balance_cv"]) * 0.1
    )
    return round(
        topology + min(0.000099, geometry_tiebreaker * 0.000001),
        6,
    )
