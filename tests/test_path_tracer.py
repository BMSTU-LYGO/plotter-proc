import json
from pathlib import Path

import numpy as np
import pytest

from plotter_processor.path_tracer import (
    build_adjacency,
    connected_components,
    graph_edges,
    route_edges,
    save_path_document,
    simplify_rdp,
    trace_component,
    trace_skeleton,
)


def _skeleton(*rows: str) -> np.ndarray:
    return np.array([[character == "#" for character in row] for row in rows], dtype=bool)


def test_traces_straight_line_and_covers_every_edge() -> None:
    skeleton = _skeleton(".....", ".###.", ".....")
    adjacency = build_adjacency(skeleton)
    component = connected_components(adjacency)[0]

    route = trace_component(component, adjacency)

    assert graph_edges(adjacency) <= route_edges(route)
    assert len(route) >= 3


def test_traces_t_junction_and_covers_every_edge() -> None:
    skeleton = _skeleton(".###.", "..#..", "..#..")
    adjacency = build_adjacency(skeleton)
    component = connected_components(adjacency)[0]

    route = trace_component(component, adjacency)

    assert graph_edges(adjacency) <= route_edges(route)


def test_traces_loop_and_covers_every_edge() -> None:
    skeleton = _skeleton(".###.", ".#.#.", ".###.")
    adjacency = build_adjacency(skeleton)
    component = connected_components(adjacency)[0]

    route = trace_component(component, adjacency)

    assert graph_edges(adjacency) <= route_edges(route)
    assert route[0] == route[-1]


def test_finds_and_orders_two_components() -> None:
    skeleton = _skeleton(".##....", ".......", "....##.")
    adjacency = build_adjacency(skeleton)

    components = connected_components(adjacency)

    assert len(components) == 2
    assert min(components[0]) < min(components[1])


def test_suppresses_redundant_diagonal_edges() -> None:
    skeleton = _skeleton("##", ".#")
    adjacency = build_adjacency(skeleton)

    assert (1, 1) not in adjacency[(0, 0)]
    assert len(graph_edges(adjacency)) == 2


def test_rdp_reduces_collinear_points() -> None:
    points = [(5, column) for column in range(20)]

    simplified = simplify_rdp(points, epsilon=0.8)

    assert simplified == [(5, 0), (5, 19)]


def test_builds_path_document_in_millimetres() -> None:
    skeleton = _skeleton(".....", ".###.", ".....")

    document = trace_skeleton(
        skeleton,
        dpi=254,
        page_width_mm=10.0,
        page_height_mm=10.0,
        simplify_epsilon_px=0.0,
    )

    assert len(document.strokes) == 1
    assert document.strokes[0].points[0].y == pytest.approx(0.1)
    assert all(point.x <= 0.3 for point in document.strokes[0].points)


def test_serializes_paths_json(tmp_path: Path) -> None:
    skeleton = _skeleton(".....", ".###.", ".....")
    document = trace_skeleton(
        skeleton,
        dpi=200,
        page_width_mm=210.0,
        page_height_mm=297.0,
    )
    output = tmp_path / "paths.json"

    save_path_document(document, 200, output)

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["page"] == {"width_mm": 210.0, "height_mm": 297.0, "dpi": 200}
    assert payload["strokes"][0]["component"] == 0
    assert len(payload["strokes"][0]["points"]) >= 2
