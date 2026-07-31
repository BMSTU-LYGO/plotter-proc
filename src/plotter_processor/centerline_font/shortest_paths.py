from __future__ import annotations

import heapq
from dataclasses import dataclass

from plotter_processor.centerline_font.models import SkeletonEdge


@dataclass(frozen=True, slots=True)
class ShortestPath:
    start_node_id: int
    end_node_id: int
    edge_ids: tuple[int, ...]
    node_ids: tuple[int, ...]
    length_px: float


def shortest_path(edges: list[SkeletonEdge], start: int, end: int) -> ShortestPath:
    adjacency: dict[int, list[tuple[int, int, float]]] = {}
    for edge in edges:
        adjacency.setdefault(edge.start_node_id, []).append((edge.end_node_id, edge.id, edge.length_px))
        adjacency.setdefault(edge.end_node_id, []).append((edge.start_node_id, edge.id, edge.length_px))
    queue: list[tuple[float, tuple[int, ...], int, tuple[int, ...]]] = [(0.0, (), start, (start,))]
    best: dict[int, tuple[float, tuple[int, ...]]] = {}
    while queue:
        length, edge_ids, node, node_ids = heapq.heappop(queue)
        key = (round(length, 9), edge_ids)
        if node in best and best[node] <= key:
            continue
        best[node] = key
        if node == end:
            return ShortestPath(start, end, edge_ids, node_ids, length)
        for neighbor, edge_id, weight in sorted(adjacency.get(node, []), key=lambda item: item[1]):
            heapq.heappush(queue, (length + weight, edge_ids + (edge_id,), neighbor, node_ids + (neighbor,)))
    raise ValueError(f"No graph path between nodes {start} and {end}")


def odd_node_shortest_paths(
    edges: list[SkeletonEdge], odd_node_ids: tuple[int, ...]
) -> dict[tuple[int, int], ShortestPath]:
    return {
        (left, right): shortest_path(edges, left, right)
        for index, left in enumerate(odd_node_ids)
        for right in odd_node_ids[index + 1 :]
    }
