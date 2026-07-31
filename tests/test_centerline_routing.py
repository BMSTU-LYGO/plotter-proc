from dataclasses import replace

from plotter_processor.centerline_font.config import load_centerline_config
from plotter_processor.centerline_font.models import (
    SkeletonEdge,
    SkeletonNode,
    SmoothedEdge,
)
from plotter_processor.centerline_font.route_assembler import assemble_component_route
from plotter_processor.centerline_font.route_planner import plan_glyph_routes
from plotter_processor.config import load_yaml
from plotter_processor.models import Point


def _node(node_id: int, component: int = 0) -> SkeletonNode:
    return SkeletonNode(node_id, "endpoint", float(node_id), 0.0, ((0, node_id),), component, 1)


def _edge(edge_id: int, start: int, end: int, component: int = 0) -> SkeletonEdge:
    return SkeletonEdge(edge_id, start, end, ((0, start), (0, end)), False, component, 1.0)


def _config():
    return load_centerline_config(load_yaml("configs/layout.yaml"))


def test_line_and_ring_need_no_retrace() -> None:
    line = plan_glyph_routes([_node(0), _node(1)], [_edge(0, 0, 1)], _config())
    assert len(line) == 1
    assert line[0].retraced_length_px == 0
    ring_edge = SkeletonEdge(0, 0, 0, ((0, 0), (0, 1), (1, 1)), True, 0, 3.0)
    ring = plan_glyph_routes([_node(0)], [ring_edge], _config())
    assert len(ring) == 1
    assert ring[0].closed
    assert ring[0].retraced_length_px == 0


def test_t_graph_is_one_route_with_minimum_retrace() -> None:
    nodes = [_node(index) for index in range(4)]
    edges = [_edge(0, 0, 1), _edge(1, 1, 2), _edge(2, 1, 3)]
    routes = plan_glyph_routes(nodes, edges, _config())
    assert len(routes) == 1
    assert routes[0].retraced_length_px == 1.0
    assert {step.edge_id for step in routes[0].steps} == {0, 1, 2}


def test_two_components_remain_two_routes() -> None:
    nodes = [_node(0), _node(1), _node(2, 1), _node(3, 1)]
    edges = [_edge(0, 0, 1), _edge(1, 2, 3, 1)]
    routes = plan_glyph_routes(nodes, edges, _config())
    assert len(routes) == 2
    assert {route.component_id for route in routes} == {0, 1}


def test_expensive_t_route_uses_two_minimum_trails_fallback() -> None:
    nodes = [_node(index) for index in range(4)]
    edges = [_edge(0, 0, 1), _edge(1, 1, 2), _edge(2, 1, 3)]
    routes = plan_glyph_routes(
        nodes, edges, replace(_config(), max_retrace_ratio=0.1)
    )
    assert len(routes) == 2
    assert sum(len(route.steps) for route in routes) == 3


def test_route_assembler_reuses_exact_edge_geometry_without_connector() -> None:
    nodes = [_node(index) for index in range(4)]
    edges = [_edge(0, 0, 1), _edge(1, 1, 2), _edge(2, 1, 3)]
    route = plan_glyph_routes(nodes, edges, _config())[0]
    geometry = {
        edge.id: SmoothedEdge(
            edge.id,
            edge.start_node_id,
            edge.end_node_id,
            0,
            (Point(float(edge.start_node_id), 0), Point(float(edge.end_node_id), 0)),
            1.0,
            False,
        )
        for edge in edges
    }
    stroke = assemble_component_route(route, geometry)
    assert len(stroke.points) == len(route.steps) + 1
    assert stroke.retraced_length_font_units == 1.0
