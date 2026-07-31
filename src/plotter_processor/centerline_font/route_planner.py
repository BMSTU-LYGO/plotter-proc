from __future__ import annotations

from plotter_processor.centerline_font.config import CenterlineConfig
from plotter_processor.centerline_font.eulerizer import eulerize_component
from plotter_processor.centerline_font.models import (
    ComponentRoute,
    RouteEdgeStep,
    SkeletonEdge,
    SkeletonNode,
)
from plotter_processor.centerline_font.route_models import RoutedEdgeOccurrence


def plan_glyph_routes(
    nodes: list[SkeletonNode], edges: list[SkeletonEdge], config: CenterlineConfig
) -> list[ComponentRoute]:
    del nodes
    routes: list[ComponentRoute] = []
    component_ids = sorted({edge.component_id for edge in edges})
    for component_id in component_ids:
        component_edges = [edge for edge in edges if edge.component_id == component_id]
        if config.routing_strategy == "edge":
            routes.extend(_edge_routes(component_id, component_edges))
            continue
        eulerized = eulerize_component(component_id, component_edges)
        steps = _hierholzer(eulerized)
        ratio = eulerized.duplicated_length_px / max(eulerized.original_length_px, 1e-9)
        if ratio > config.max_retrace_ratio and config.fallback_strategy == "minimum_strokes":
            routes.extend(_minimum_trail_routes(component_id, component_edges))
            continue
        routes.append(
            ComponentRoute(
                component_id,
                tuple(steps),
                eulerized.start_node_id,
                eulerized.end_node_id,
                eulerized.start_node_id == eulerized.end_node_id,
                eulerized.original_length_px,
                eulerized.duplicated_length_px,
                ratio,
            )
        )
    validate_route_coverage(edges, routes)
    return routes


def validate_route_coverage(edges: list[SkeletonEdge], routes: list[ComponentRoute]) -> None:
    known = {edge.id for edge in edges}
    used = {step.edge_id for route in routes for step in route.steps}
    if not known <= used:
        raise ValueError("Euler routes do not cover every original graph edge")
    if any(step.edge_id not in known for route in routes for step in route.steps):
        raise ValueError("Euler route references an unknown graph edge")


def _hierholzer(component) -> list[RouteEdgeStep]:
    circuit = _occurrence_circuit(component.occurrences, component.start_node_id)
    return [
        RouteEdgeStep(
            occurrence.source_edge_id,
            reversed_step,
            occurrence.duplicated,
            occurrence.occurrence_id,
        )
        for occurrence, reversed_step in circuit
    ]


def _occurrence_circuit(
    source_occurrences: tuple[RoutedEdgeOccurrence, ...], start_node_id: int
) -> list[tuple[RoutedEdgeOccurrence, bool]]:
    occurrences = {occ.occurrence_id: occ for occ in source_occurrences}
    adjacency: dict[int, list[int]] = {}
    for occ in source_occurrences:
        adjacency.setdefault(occ.start_node_id, []).append(occ.occurrence_id)
        adjacency.setdefault(occ.end_node_id, []).append(occ.occurrence_id)
    for values in adjacency.values():
        values.sort(reverse=True)
    used: set[int] = set()
    stack: list[tuple[int, int | None, bool]] = [(start_node_id, None, False)]
    circuit: list[tuple[int, bool]] = []
    while stack:
        node = stack[-1][0]
        while adjacency.get(node) and adjacency[node][-1] in used:
            adjacency[node].pop()
        if adjacency.get(node):
            occurrence_id = adjacency[node].pop()
            if occurrence_id in used:
                continue
            used.add(occurrence_id)
            occ = occurrences[occurrence_id]
            reversed_step = node == occ.end_node_id and node != occ.start_node_id
            next_node = occ.start_node_id if reversed_step else occ.end_node_id
            stack.append((next_node, occurrence_id, reversed_step))
        else:
            _, occurrence_id, reversed_step = stack.pop()
            if occurrence_id is not None:
                circuit.append((occurrence_id, reversed_step))
    circuit.reverse()
    if len(circuit) != len(occurrences):
        raise ValueError("Corrupted Euler traversal")
    return [
        (occurrences[occurrence_id], reversed_step)
        for occurrence_id, reversed_step in circuit
    ]


def _minimum_trail_routes(
    component_id: int, edges: list[SkeletonEdge]
) -> list[ComponentRoute]:
    degree: dict[int, int] = {}
    occurrences = [
        RoutedEdgeOccurrence(index, edge.id, edge.start_node_id, edge.end_node_id, False, edge.length_px)
        for index, edge in enumerate(edges)
    ]
    for edge in edges:
        degree[edge.start_node_id] = degree.get(edge.start_node_id, 0) + 1
        degree[edge.end_node_id] = degree.get(edge.end_node_id, 0) + 1
    odd = sorted(node for node, value in degree.items() if value % 2)
    if len(odd) <= 2:
        eulerized = eulerize_component(component_id, edges)
        steps = _hierholzer(eulerized)
        return [ComponentRoute(component_id, tuple(steps), eulerized.start_node_id, eulerized.end_node_id, eulerized.start_node_id == eulerized.end_node_id, eulerized.original_length_px, 0.0, 0.0)]
    virtual = min(degree) - 1
    for node in odd:
        occurrences.append(
            RoutedEdgeOccurrence(len(occurrences), -1, virtual, node, False, 0.0)
        )
    circuit = _occurrence_circuit(tuple(occurrences), virtual)
    trails: list[list[tuple[RoutedEdgeOccurrence, bool]]] = []
    current: list[tuple[RoutedEdgeOccurrence, bool]] = []
    for occurrence, reversed_step in circuit:
        if occurrence.source_edge_id == -1:
            if current:
                trails.append(current)
                current = []
        else:
            current.append((occurrence, reversed_step))
    if current:
        trails.append(current)
    original_length = sum(edge.length_px for edge in edges)
    result: list[ComponentRoute] = []
    for trail in trails:
        first, first_reversed = trail[0]
        last, last_reversed = trail[-1]
        start = first.end_node_id if first_reversed else first.start_node_id
        end = last.start_node_id if last_reversed else last.end_node_id
        steps = tuple(
            RouteEdgeStep(occ.source_edge_id, reversed_step, False, occ.occurrence_id)
            for occ, reversed_step in trail
        )
        result.append(ComponentRoute(component_id, steps, start, end, False, original_length, 0.0, 0.0))
    return result


def _edge_routes(component_id: int, edges: list[SkeletonEdge]) -> list[ComponentRoute]:
    return [
        ComponentRoute(component_id, (RouteEdgeStep(edge.id, False, False, 0),), edge.start_node_id, edge.end_node_id, edge.closed, edge.length_px, 0.0, 0.0)
        for edge in edges
    ]
