import json
import math
from collections.abc import Iterable
from itertools import pairwise
from pathlib import Path

import numpy as np

from plotter_processor.models import PathDocument, Point, Stroke

Node = tuple[int, int]  # row, column
Edge = frozenset[Node]

_NEIGHBOR_OFFSETS = (
    (-1, -1),
    (-1, 0),
    (-1, 1),
    (0, -1),
    (0, 1),
    (1, -1),
    (1, 0),
    (1, 1),
)


def build_adjacency(skeleton: np.ndarray) -> dict[Node, set[Node]]:
    pixels = np.argwhere(np.asarray(skeleton, dtype=bool))
    nodes = {(int(row), int(column)) for row, column in pixels}
    adjacency: dict[Node, set[Node]] = {node: set() for node in nodes}

    for row, column in nodes:
        for delta_row, delta_column in _NEIGHBOR_OFFSETS:
            neighbor = (row + delta_row, column + delta_column)
            if neighbor not in nodes or neighbor <= (row, column):
                continue
            if delta_row != 0 and delta_column != 0:
                orthogonal_a = (row, column + delta_column)
                orthogonal_b = (row + delta_row, column)
                if orthogonal_a in nodes or orthogonal_b in nodes:
                    continue
            adjacency[(row, column)].add(neighbor)
            adjacency[neighbor].add((row, column))

    return adjacency


def connected_components(adjacency: dict[Node, set[Node]]) -> list[set[Node]]:
    remaining = set(adjacency)
    components: list[set[Node]] = []
    while remaining:
        start = min(remaining)
        component: set[Node] = set()
        stack = [start]
        remaining.remove(start)
        while stack:
            node = stack.pop()
            component.add(node)
            for neighbor in adjacency[node]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    stack.append(neighbor)
        components.append(component)

    components.sort(key=lambda component: (min(node[0] for node in component), min(
        node[1] for node in component
    )))
    return components


def trace_component(component: set[Node], adjacency: dict[Node, set[Node]]) -> list[Node]:
    if not component:
        return []

    odd_nodes = [node for node in component if len(adjacency[node]) % 2 == 1]
    start = min(odd_nodes or component, key=lambda node: (node[1], node[0]))
    visited_edges: set[Edge] = set()
    route = [start]

    def candidates(node: Node, incoming: tuple[int, int] | None) -> list[Node]:
        return sorted(
            adjacency[node],
            key=lambda candidate: _neighbor_priority(node, candidate, incoming),
        )

    stack: list[tuple[Node, tuple[int, int] | None, list[Node], int]] = [
        (start, None, candidates(start, None), 0)
    ]
    while stack:
        node, incoming, neighbors, index = stack[-1]
        while index < len(neighbors):
            neighbor = neighbors[index]
            index += 1
            stack[-1] = (node, incoming, neighbors, index)
            edge = frozenset((node, neighbor))
            if edge in visited_edges:
                continue
            visited_edges.add(edge)
            route.append(neighbor)
            direction = (neighbor[0] - node[0], neighbor[1] - node[1])
            stack.append((neighbor, direction, candidates(neighbor, direction), 0))
            break
        else:
            stack.pop()
            if stack:
                route.append(stack[-1][0])

    return _remove_consecutive_duplicates(route)


def trace_skeleton(
    skeleton: np.ndarray,
    *,
    dpi: int,
    page_width_mm: float,
    page_height_mm: float,
    simplify_epsilon_px: float = 0.8,
    min_stroke_points: int = 2,
) -> PathDocument:
    if dpi <= 0:
        raise ValueError("dpi must be positive")
    if simplify_epsilon_px < 0:
        raise ValueError("simplify_epsilon_px must be non-negative")
    if min_stroke_points < 2:
        raise ValueError("min_stroke_points must be at least 2")

    adjacency = build_adjacency(skeleton)
    components = connected_components(adjacency)
    scale = 25.4 / dpi
    strokes: list[Stroke] = []
    warnings: list[str] = []

    for component_index, component in enumerate(components):
        pixel_route = trace_component(component, adjacency)
        if len(pixel_route) < 2:
            warnings.append(f"Component {component_index} contains no drawable edge")
            continue
        simplified = simplify_rdp(pixel_route, simplify_epsilon_px)
        points = _nodes_to_points(simplified, scale)
        points = _remove_nearby_points(points, minimum_distance_mm=0.05)
        if len(points) < min_stroke_points:
            warnings.append(f"Component {component_index} became too small after simplification")
            continue
        strokes.append(Stroke(points=points, source_component=component_index))

    if not strokes:
        raise ValueError("Skeleton contains no drawable paths.")

    return PathDocument(
        page_width_mm=page_width_mm,
        page_height_mm=page_height_mm,
        strokes=strokes,
        warnings=warnings,
    )


def simplify_rdp(points: list[Node], epsilon: float) -> list[Node]:
    points = _remove_consecutive_duplicates(points)
    if len(points) <= 2 or epsilon <= 0:
        return points

    start = points[0]
    end = points[-1]
    distances = [_point_segment_distance(point, start, end) for point in points[1:-1]]
    if not distances:
        return points
    maximum = max(distances)
    index = distances.index(maximum) + 1
    if maximum <= epsilon:
        return [start, end]

    left = simplify_rdp(points[: index + 1], epsilon)
    right = simplify_rdp(points[index:], epsilon)
    return left[:-1] + right


def save_path_document(document: PathDocument, dpi: int, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "page": {
            "width_mm": document.page_width_mm,
            "height_mm": document.page_height_mm,
            "dpi": dpi,
        },
        "strokes": [
            {
                "component": stroke.source_component,
                "points": [[round(point.x, 4), round(point.y, 4)] for point in stroke.points],
            }
            for stroke in document.strokes
        ],
        "warnings": document.warnings,
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def load_path_document(input_path: str | Path) -> tuple[PathDocument, int]:
    path = Path(input_path)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        page = payload["page"]
        dpi = int(page["dpi"])
        strokes = [
            Stroke(
                source_component=int(item["component"]),
                points=[Point(x=float(point[0]), y=float(point[1])) for point in item["points"]],
            )
            for item in payload["strokes"]
        ]
        warnings = [str(warning) for warning in payload.get("warnings", [])]
        document = PathDocument(
            page_width_mm=float(page["width_mm"]),
            page_height_mm=float(page["height_mm"]),
            strokes=strokes,
            warnings=warnings,
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise ValueError(f"Invalid paths JSON: {path}") from error
    return document, dpi


def graph_edges(adjacency: dict[Node, set[Node]]) -> set[Edge]:
    return {
        frozenset((node, neighbor))
        for node, neighbors in adjacency.items()
        for neighbor in neighbors
    }


def route_edges(route: Iterable[Node]) -> set[Edge]:
    return {frozenset((first, second)) for first, second in pairwise(route)}


def _neighbor_priority(
    node: Node,
    neighbor: Node,
    incoming: tuple[int, int] | None,
) -> tuple[float, int, int]:
    if incoming is None:
        turn_cost = 0.0
    else:
        outgoing = (neighbor[0] - node[0], neighbor[1] - node[1])
        dot = incoming[0] * outgoing[0] + incoming[1] * outgoing[1]
        incoming_length = math.hypot(*incoming)
        outgoing_length = math.hypot(*outgoing)
        cosine = dot / (incoming_length * outgoing_length)
        turn_cost = 1.0 - cosine
    return (turn_cost, neighbor[1], neighbor[0])


def _point_segment_distance(point: Node, start: Node, end: Node) -> float:
    point_y, point_x = point
    start_y, start_x = start
    end_y, end_x = end
    delta_x = end_x - start_x
    delta_y = end_y - start_y
    if delta_x == 0 and delta_y == 0:
        return math.hypot(point_x - start_x, point_y - start_y)
    projection = (
        (point_x - start_x) * delta_x + (point_y - start_y) * delta_y
    ) / (delta_x * delta_x + delta_y * delta_y)
    projection = max(0.0, min(1.0, projection))
    nearest_x = start_x + projection * delta_x
    nearest_y = start_y + projection * delta_y
    return math.hypot(point_x - nearest_x, point_y - nearest_y)


def _nodes_to_points(nodes: list[Node], scale: float) -> list[Point]:
    return [Point(x=column * scale, y=row * scale) for row, column in nodes]


def _remove_consecutive_duplicates(points: list[Node]) -> list[Node]:
    if not points:
        return []
    result = [points[0]]
    for point in points[1:]:
        if point != result[-1]:
            result.append(point)
    return result


def _remove_nearby_points(points: list[Point], minimum_distance_mm: float) -> list[Point]:
    if not points:
        return []
    result = [points[0]]
    for point in points[1:-1]:
        if math.hypot(point.x - result[-1].x, point.y - result[-1].y) >= minimum_distance_mm:
            result.append(point)
    if len(points) > 1 and points[-1] != result[-1]:
        result.append(points[-1])
    return result
