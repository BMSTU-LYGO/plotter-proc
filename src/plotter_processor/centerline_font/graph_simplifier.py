from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from plotter_processor.centerline_font.config import CenterlineConfig
from plotter_processor.centerline_font.models import SkeletonEdge, SkeletonNode


@dataclass(frozen=True, slots=True)
class GraphSimplificationReport:
    spurs_removed: int = 0
    junctions_merged: int = 0
    false_junctions_removed: int = 0
    duplicate_edges_removed: int = 0


def simplify_skeleton_graph(
    nodes: list[SkeletonNode],
    edges: list[SkeletonEdge],
    *,
    distance: np.ndarray,
    config: CenterlineConfig,
) -> tuple[list[SkeletonNode], list[SkeletonEdge], GraphSimplificationReport]:
    del distance, config
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
    return list(nodes), unique, GraphSimplificationReport(duplicate_edges_removed=removed)
