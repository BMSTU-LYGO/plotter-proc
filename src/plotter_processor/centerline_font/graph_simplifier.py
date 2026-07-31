from __future__ import annotations

from dataclasses import dataclass, replace

import numpy as np

from plotter_processor.centerline_font.config import CenterlineConfig
from plotter_processor.centerline_font.models import SkeletonEdge, SkeletonNode


@dataclass(frozen=True, slots=True)
class GraphSimplificationReport:
    spurs_removed: int = 0
    junctions_merged: int = 0
    false_junctions_removed: int = 0
    duplicate_edges_removed: int = 0
    micro_loops_removed: int = 0


def simplify_skeleton_graph(
    nodes: list[SkeletonNode],
    edges: list[SkeletonEdge],
    *,
    distance: np.ndarray,
    config: CenterlineConfig,
) -> tuple[list[SkeletonNode], list[SkeletonEdge], GraphSimplificationReport]:
    seen: set[tuple[int, int, tuple[tuple[int, int], ...]]] = set()
    unique: list[SkeletonEdge] = []
    removed = 0
    for edge in edges:
        forward = (edge.start_node_id, edge.end_node_id, edge.pixels)
        reverse = (edge.end_node_id, edge.start_node_id, tuple(reversed(edge.pixels)))
        key = min(forward, reverse)
        if key in seen:
            removed += 1
            continue
        seen.add(key)
        unique.append(edge)
    component_edges: dict[int, int] = {}
    for edge in unique:
        component_edges[edge.component_id] = component_edges.get(edge.component_id, 0) + 1
    kept: list[SkeletonEdge] = []
    micro_loops = 0
    for edge in unique:
        radii = [float(distance[pixel]) for pixel in edge.pixels]
        local_width = 2 * float(np.median(radii)) if radii else 0.0
        is_loop = edge.closed or edge.start_node_id == edge.end_node_id
        if (
            is_loop
            and component_edges[edge.component_id] > 1
            and edge.length_px < local_width * config.max_micro_loop_width_factor
        ):
            micro_loops += 1
            continue
        kept.append(edge)
    degrees: dict[int, int] = {}
    for edge in kept:
        degrees[edge.start_node_id] = degrees.get(edge.start_node_id, 0) + 1
        degrees[edge.end_node_id] = degrees.get(edge.end_node_id, 0) + 1
    normalized: list[SkeletonNode] = []
    false_junctions = junctions_merged = 0
    for node in nodes:
        if node.kind == "junction":
            if len(node.pixels) > config.max_junction_cluster_px:
                raise ValueError(
                    f"Junction cluster has {len(node.pixels)} pixels; maximum is "
                    f"{config.max_junction_cluster_px}"
                )
            junctions_merged += max(0, len(node.pixels) - 1)
            degree = degrees.get(node.id, 0)
            if degree < 3:
                false_junctions += 1
                node = replace(node, kind="endpoint" if degree == 1 else "regular")
        normalized.append(node)
    return (
        normalized,
        kept,
        GraphSimplificationReport(
            junctions_merged=junctions_merged,
            false_junctions_removed=false_junctions,
            duplicate_edges_removed=removed,
            micro_loops_removed=micro_loops,
        ),
    )
