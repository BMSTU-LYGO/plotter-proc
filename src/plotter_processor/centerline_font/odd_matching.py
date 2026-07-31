from __future__ import annotations

from dataclasses import dataclass
from functools import cache

from plotter_processor.centerline_font.shortest_paths import ShortestPath


@dataclass(frozen=True, slots=True)
class MatchingResult:
    pairs: tuple[tuple[int, int], ...]
    paths: tuple[ShortestPath, ...]
    total_length_px: float


def minimum_odd_node_matching(
    odd_node_ids: tuple[int, ...],
    shortest_paths: dict[tuple[int, int], ShortestPath],
) -> MatchingResult:
    nodes = tuple(sorted(odd_node_ids))
    if len(nodes) % 2:
        raise ValueError("Odd-node matching requires an even node count")

    def path(left: int, right: int) -> ShortestPath:
        return shortest_paths[tuple(sorted((left, right)))]

    @cache
    def solve(remaining: tuple[int, ...]) -> tuple[float, tuple[tuple[int, int], ...]]:
        if not remaining:
            return 0.0, ()
        left = remaining[0]
        candidates = []
        for index, right in enumerate(remaining[1:], start=1):
            rest = remaining[1:index] + remaining[index + 1 :]
            cost, pairs = solve(rest)
            pair = (left, right)
            candidates.append((cost + path(*pair).length_px, (pair,) + pairs))
        return min(candidates, key=lambda item: (round(item[0], 9), item[1]))

    total, pairs = solve(nodes)
    return MatchingResult(pairs, tuple(path(*pair) for pair in pairs), total)
