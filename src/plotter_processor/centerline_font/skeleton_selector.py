from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from plotter_processor.centerline_font.config import CenterlineConfig
from plotter_processor.centerline_font.graph_simplifier import (
    GraphSimplificationReport,
    simplify_skeleton_graph,
)
from plotter_processor.centerline_font.models import SkeletonEdge, SkeletonNode
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


def select_best_skeleton(mask: np.ndarray, config: CenterlineConfig) -> SelectedSkeleton:
    methods = config.candidate_methods if config.skeleton_method == "auto" else (config.skeleton_method,)
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
            odd = _odd_count(edges)
            junctions = sum(node.kind == "junction" for node in nodes)
            score = len(edges) + junctions * 2 + odd * 0.5
            candidates.append((score, methods.index(method), method, result, pruned, nodes, edges, report))
        except ValueError as error:
            failures.append(f"{method}: {error}")
    if not candidates:
        raise ValueError("All skeleton candidates failed: " + "; ".join(failures))
    selected = min(candidates, key=lambda item: (item[0], item[1]))
    score, _, method, result, pruned, nodes, edges, report = selected
    return SelectedSkeleton(
        method,
        pruned,
        result.distance,
        result.component_labels,
        tuple(nodes),
        tuple(edges),
        report,
        {candidate[2]: candidate[0] for candidate in candidates},
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
