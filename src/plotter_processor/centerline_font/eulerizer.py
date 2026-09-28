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


def eulerize_component(
    component_id: int,
    edges: list[SkeletonEdge],
    *,
    exact_matching_max_odd_vertices: int = 20,
) -> EulerizedComponent:
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
        if len(odd) > exact_matching_max_odd_vertices:
            start, end, duplicate_edges = _greedy_open_matching(odd, paths)
        else:
            choices = []
            for index, start_candidate in enumerate(odd):
                for end_candidate in odd[index + 1 :]:
                    remaining = tuple(
                        node for node in odd if node not in {start_candidate, end_candidate}
                    )
                    matching = minimum_odd_node_matching(remaining, paths)
                    choices.append(
                        (matching.total_length_px, start_candidate, end_candidate, matching)
                    )
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


def _greedy_open_matching(odd, paths) -> tuple[int, int, list[int]]:
    """Bound matching work for dense skeletons with many odd vertices."""
    pairs = [(left, right) for index, left in enumerate(odd) for right in odd[index + 1 :]]
    start, end = max(
        pairs,
        key=lambda pair: (round(paths[pair].length_px, 9), -pair[0], -pair[1]),
    )
    remaining = set(odd) - {start, end}
    duplicate_edges: list[int] = []
    while remaining:
        left, right = min(
            (pair for pair in pairs if pair[0] in remaining and pair[1] in remaining),
            key=lambda pair: (round(paths[pair].length_px, 9), pair),
        )
        duplicate_edges.extend(paths[left, right].edge_ids)
        remaining.difference_update((left, right))
    return start, end, duplicate_edges
