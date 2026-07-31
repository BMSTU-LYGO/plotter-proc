from __future__ import annotations

from dataclasses import dataclass

from plotter_processor.centerline_font.models import SkeletonEdge
from plotter_processor.centerline_font.odd_matching import minimum_odd_node_matching
from plotter_processor.centerline_font.route_models import RoutedEdgeOccurrence
from plotter_processor.centerline_font.shortest_paths import odd_node_shortest_paths


@dataclass(frozen=True, slots=True)
class EulerizedComponent:
    component_id: int
    occurrences: tuple[RoutedEdgeOccurrence, ...]
    start_node_id: int
    end_node_id: int
    original_length_px: float
    duplicated_length_px: float


def eulerize_component(component_id: int, edges: list[SkeletonEdge]) -> EulerizedComponent:
    if not edges:
        raise ValueError("Cannot eulerize an empty component")
    degrees: dict[int, int] = {}
    for edge in edges:
        if edge.start_node_id == edge.end_node_id:
            degrees[edge.start_node_id] = degrees.get(edge.start_node_id, 0) + 2
        else:
            degrees[edge.start_node_id] = degrees.get(edge.start_node_id, 0) + 1
            degrees[edge.end_node_id] = degrees.get(edge.end_node_id, 0) + 1
    odd = tuple(sorted(node for node, degree in degrees.items() if degree % 2))
    duplicate_edges: list[int] = []
    if len(odd) <= 2:
        start = odd[0] if odd else min(degrees)
        end = odd[1] if len(odd) == 2 else start
    else:
        paths = odd_node_shortest_paths(edges, odd)
        choices = []
        for index, start_candidate in enumerate(odd):
            for end_candidate in odd[index + 1 :]:
                remaining = tuple(
                    node for node in odd if node not in {start_candidate, end_candidate}
                )
                matching = minimum_odd_node_matching(remaining, paths)
                choices.append((matching.total_length_px, start_candidate, end_candidate, matching))
        _, start, end, matching = min(
            choices, key=lambda item: (round(item[0], 9), item[1], item[2], item[3].pairs)
        )
        duplicate_edges = [edge_id for path in matching.paths for edge_id in path.edge_ids]
    by_id = {edge.id: edge for edge in edges}
    occurrences = [
        RoutedEdgeOccurrence(
            index, edge.id, edge.start_node_id, edge.end_node_id, False, edge.length_px
        )
        for index, edge in enumerate(sorted(edges, key=lambda item: item.id))
    ]
    for edge_id in duplicate_edges:
        edge = by_id[edge_id]
        occurrences.append(
            RoutedEdgeOccurrence(
                len(occurrences),
                edge.id,
                edge.start_node_id,
                edge.end_node_id,
                True,
                edge.length_px,
            )
        )
    return EulerizedComponent(
        component_id,
        tuple(occurrences),
        start,
        end,
        sum(edge.length_px for edge in edges),
        sum(by_id[edge_id].length_px for edge_id in duplicate_edges),
    )
