from __future__ import annotations

import math
from dataclasses import dataclass
from itertools import pairwise

import numpy as np

from plotter_processor.centerline_font.models import SkeletonEdge, SkeletonNode
from plotter_processor.centerline_font.topology import (
    classify_skeleton_pixel,
    crossing_number,
    topology_neighbors,
)

Pixel = tuple[int, int]


@dataclass(frozen=True, slots=True)
class GraphValidation:
    pixels: int
    links: int
    components: int
    nodes: int
    edges: int


def build_skeleton_graph(
    skeleton: np.ndarray, *, suppress_corner_diagonals: bool = True
) -> tuple[list[SkeletonNode], list[SkeletonEdge]]:
    mask = np.asarray(skeleton, dtype=bool)
    components = _components(mask, suppress_corner_diagonals)
    nodes: list[SkeletonNode] = []
    pixel_node: dict[Pixel, int] = {}
    for component_id, component in enumerate(components):
        junctions = {
            pixel
            for pixel in component
            if classify_skeleton_pixel(
                pixel, mask, suppress_corner_diagonals=suppress_corner_diagonals
            )
            == "junction"
        }
        for cluster in _clusters(junctions, mask, suppress_corner_diagonals):
            medoid = _medoid(cluster)
            node = SkeletonNode(
                len(nodes),
                "junction",
                float(medoid[1]),
                float(medoid[0]),
                tuple(sorted(cluster)),
                component_id,
                max(
                    crossing_number(p, mask, suppress_corner_diagonals=suppress_corner_diagonals)
                    for p in cluster
                ),
            )
            nodes.append(node)
            pixel_node.update({pixel: node.id for pixel in cluster})
        for pixel in sorted(component - junctions):
            kind = classify_skeleton_pixel(
                pixel, mask, suppress_corner_diagonals=suppress_corner_diagonals
            )
            if kind not in {"endpoint", "isolated"}:
                continue
            node = SkeletonNode(
                len(nodes),
                kind if kind == "endpoint" else "dot",
                float(pixel[1]),
                float(pixel[0]),
                (pixel,),
                component_id,
                crossing_number(pixel, mask, suppress_corner_diagonals=suppress_corner_diagonals),
            )
            nodes.append(node)
            pixel_node[pixel] = node.id

    edges: list[SkeletonEdge] = []
    used_links: set[frozenset[Pixel]] = set()
    for node in nodes:
        for start_pixel in node.pixels:
            for neighbor in topology_neighbors(
                start_pixel, mask, suppress_corner_diagonals=suppress_corner_diagonals
            ):
                if pixel_node.get(neighbor) == node.id:
                    continue
                link = frozenset((start_pixel, neighbor))
                if link in used_links:
                    continue
                path = [start_pixel, neighbor]
                used_links.add(link)
                previous, current = start_pixel, neighbor
                while current not in pixel_node:
                    choices = [
                        p
                        for p in topology_neighbors(
                            current, mask, suppress_corner_diagonals=suppress_corner_diagonals
                        )
                        if p != previous
                    ]
                    if len(choices) != 1:
                        raise ValueError(
                            f"Invalid regular topology at pixel {current}: {len(choices)} continuations"
                        )
                    nxt = choices[0]
                    used_links.add(frozenset((current, nxt)))
                    path.append(nxt)
                    previous, current = current, nxt
                end_id = pixel_node[current]
                edges.append(_edge(len(edges), node.id, end_id, path, False, node.component_id))

    covered = set(pixel_node)
    covered.update(pixel for edge in edges for pixel in edge.pixels)
    for component_id, component in enumerate(components):
        remaining = component - covered
        while remaining:
            anchor = min(remaining)
            path = _walk_loop(anchor, mask, suppress_corner_diagonals)
            node = SkeletonNode(
                len(nodes), "loop", float(anchor[1]), float(anchor[0]), (anchor,), component_id, 2
            )
            nodes.append(node)
            edge = _edge(len(edges), node.id, node.id, path, True, component_id)
            edges.append(edge)
            remaining.difference_update(path)
            covered.update(path)
    validate_skeleton_graph(mask, nodes, edges, suppress_corner_diagonals=suppress_corner_diagonals)
    return nodes, edges


def validate_skeleton_graph(
    skeleton: np.ndarray,
    nodes: list[SkeletonNode],
    edges: list[SkeletonEdge],
    *,
    suppress_corner_diagonals: bool = True,
) -> GraphValidation:
    expected = set(zip(*np.nonzero(skeleton), strict=True))
    actual = {pixel for node in nodes for pixel in node.pixels}
    actual.update(pixel for edge in edges for pixel in edge.pixels)
    if expected != actual:
        raise ValueError("Skeleton graph does not cover every skeleton pixel")
    node_map = {node.id: node for node in nodes}
    for edge in edges:
        if len(edge.pixels) < 2 or edge.length_px <= 0:
            raise ValueError("Skeleton graph contains a zero-length edge")
        if (
            node_map[edge.start_node_id].component_id != edge.component_id
            or node_map[edge.end_node_id].component_id != edge.component_id
        ):
            raise ValueError("Skeleton edge crosses connected components")
    links = {
        frozenset((pixel, neighbor))
        for pixel in expected
        for neighbor in topology_neighbors(
            pixel, skeleton, suppress_corner_diagonals=suppress_corner_diagonals
        )
    }
    return GraphValidation(
        len(expected), len(links), len({n.component_id for n in nodes}), len(nodes), len(edges)
    )


validate_graph_coverage = validate_skeleton_graph


def _edge(
    edge_id: int, start: int, end: int, pixels: list[Pixel], closed: bool, component: int
) -> SkeletonEdge:
    length = sum(math.hypot(b[1] - a[1], b[0] - a[0]) for a, b in pairwise(pixels))
    return SkeletonEdge(edge_id, start, end, tuple(pixels), closed, component, length)


def _components(mask: np.ndarray, suppress: bool) -> list[set[Pixel]]:
    remaining = set(zip(*np.nonzero(mask), strict=True))
    result: list[set[Pixel]] = []
    while remaining:
        seed = min(remaining)
        component = {seed}
        stack = [seed]
        remaining.remove(seed)
        while stack:
            for neighbor in topology_neighbors(
                stack.pop(), mask, suppress_corner_diagonals=suppress
            ):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    component.add(neighbor)
                    stack.append(neighbor)
        result.append(component)
    return result


def _clusters(pixels: set[Pixel], mask: np.ndarray, suppress: bool) -> list[set[Pixel]]:
    remaining = set(pixels)
    result: list[set[Pixel]] = []
    while remaining:
        seed = min(remaining)
        cluster = {seed}
        stack = [seed]
        remaining.remove(seed)
        while stack:
            for neighbor in topology_neighbors(
                stack.pop(), mask, suppress_corner_diagonals=suppress
            ):
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    cluster.add(neighbor)
                    stack.append(neighbor)
        result.append(cluster)
    return result


def _medoid(pixels: set[Pixel]) -> Pixel:
    cy = sum(p[0] for p in pixels) / len(pixels)
    cx = sum(p[1] for p in pixels) / len(pixels)
    return min(pixels, key=lambda p: ((p[0] - cy) ** 2 + (p[1] - cx) ** 2, p))


def _walk_loop(anchor: Pixel, mask: np.ndarray, suppress: bool) -> list[Pixel]:
    path = [anchor]
    previous: Pixel | None = None
    current = anchor
    for _ in range(int(mask.sum()) + 1):
        choices = [
            p
            for p in topology_neighbors(current, mask, suppress_corner_diagonals=suppress)
            if p != previous
        ]
        if not choices:
            break
        nxt = min(choices)
        if nxt == anchor:
            break
        if nxt in path:
            raise ValueError("Loop traversal repeated a skeleton pixel")
        path.append(nxt)
        previous, current = current, nxt
    return path
