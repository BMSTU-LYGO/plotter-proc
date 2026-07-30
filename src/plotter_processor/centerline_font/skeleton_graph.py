from __future__ import annotations

import numpy as np
from scipy import ndimage

from plotter_processor.centerline_font.models import SkeletonEdge, SkeletonNode


def build_skeleton_graph(
    skeleton: np.ndarray,
) -> tuple[list[SkeletonNode], list[SkeletonEdge]]:
    mask = np.asarray(skeleton, dtype=bool)
    degrees = ndimage.convolve(
        mask.astype(np.uint8),
        np.array([[1, 1, 1], [1, 0, 1], [1, 1, 1]], dtype=np.uint8),
        mode="constant",
    )
    junction_mask = mask & (degrees >= 3)
    labels, count = ndimage.label(
        junction_mask, structure=np.ones((3, 3), dtype=np.uint8)
    )
    nodes: list[SkeletonNode] = []
    pixel_node: dict[tuple[int, int], int] = {}
    for label in range(1, count + 1):
        pixels = tuple(sorted(zip(*np.nonzero(labels == label), strict=True)))
        cy = sum(p[0] for p in pixels) / len(pixels)
        cx = sum(p[1] for p in pixels) / len(pixels)
        medoid = min(pixels, key=lambda p: ((p[0] - cy) ** 2 + (p[1] - cx) ** 2, p))
        node = SkeletonNode(
            len(nodes), "junction", float(medoid[1]), float(medoid[0]), pixels
        )
        nodes.append(node)
        pixel_node.update({pixel: node.id for pixel in pixels})
    for pixel in sorted(zip(*np.nonzero(mask & (degrees <= 1)), strict=True)):
        kind = "endpoint" if degrees[pixel] == 1 else "dot"
        node = SkeletonNode(
            len(nodes), kind, float(pixel[1]), float(pixel[0]), (pixel,)
        )
        nodes.append(node)
        pixel_node[pixel] = node.id

    edges: list[SkeletonEdge] = []
    used_links: set[frozenset[tuple[int, int]]] = set()
    for node in nodes:
        for start_pixel in node.pixels:
            for neighbor in _neighbors(start_pixel, mask):
                if pixel_node.get(neighbor) == node.id:
                    continue
                link = frozenset((start_pixel, neighbor))
                if link in used_links:
                    continue
                path = [start_pixel, neighbor]
                used_links.add(link)
                previous, current = start_pixel, neighbor
                while current not in pixel_node:
                    choices = [p for p in _neighbors(current, mask) if p != previous]
                    if not choices:
                        break
                    nxt = min(choices)
                    used_links.add(frozenset((current, nxt)))
                    path.append(nxt)
                    previous, current = current, nxt
                end_id = pixel_node.get(current, node.id)
                edges.append(
                    SkeletonEdge(len(edges), node.id, end_id, tuple(path), False)
                )

    covered = set(pixel_node)
    covered.update(pixel for edge in edges for pixel in edge.pixels)
    remaining = set(zip(*np.nonzero(mask), strict=True)) - covered
    while remaining:
        anchor = min(remaining)
        path = _walk_loop(anchor, mask)
        node = SkeletonNode(len(nodes), "loop", float(anchor[1]), float(anchor[0]), (anchor,))
        nodes.append(node)
        edges.append(SkeletonEdge(len(edges), node.id, node.id, tuple(path), True))
        remaining.difference_update(path)
    validate_graph_coverage(mask, nodes, edges)
    return nodes, edges


def validate_graph_coverage(
    skeleton: np.ndarray, nodes: list[SkeletonNode], edges: list[SkeletonEdge]
) -> None:
    expected = set(zip(*np.nonzero(skeleton), strict=True))
    actual = {pixel for node in nodes for pixel in node.pixels}
    actual.update(pixel for edge in edges for pixel in edge.pixels)
    if expected != actual:
        raise ValueError("Skeleton graph does not cover every skeleton pixel")
    for edge in edges:
        if len(edge.pixels) < 2:
            raise ValueError("Skeleton graph contains a zero-length edge")


def _walk_loop(anchor: tuple[int, int], mask: np.ndarray) -> list[tuple[int, int]]:
    path = [anchor]
    previous = None
    current = anchor
    for _ in range(int(mask.sum()) + 1):
        choices = [p for p in _neighbors(current, mask) if p != previous]
        if not choices:
            break
        nxt = min(choices)
        if nxt == anchor:
            break
        if nxt in path:
            break
        path.append(nxt)
        previous, current = current, nxt
    return path


def _neighbors(pixel: tuple[int, int], mask: np.ndarray) -> list[tuple[int, int]]:
    y, x = pixel
    return [
        (ny, nx)
        for ny in range(max(0, y - 1), min(mask.shape[0], y + 2))
        for nx in range(max(0, x - 1), min(mask.shape[1], x + 2))
        if (ny, nx) != pixel and mask[ny, nx]
    ]
