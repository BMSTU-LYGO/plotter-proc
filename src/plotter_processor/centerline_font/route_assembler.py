from __future__ import annotations

from plotter_processor.centerline_font.models import (
    CenterlineStroke,
    ComponentRoute,
    SmoothedEdge,
)


def assemble_component_route(
    route: ComponentRoute, edge_geometry: dict[int, SmoothedEdge]
) -> CenterlineStroke:
    points = []
    retraced = 0.0
    for step in route.steps:
        try:
            edge = edge_geometry[step.edge_id]
        except KeyError as error:
            raise ValueError(f"Route references unknown edge {step.edge_id}") from error
        edge_points = tuple(reversed(edge.points)) if step.reversed else edge.points
        if points:
            if points[-1] != edge_points[0]:
                raise ValueError(
                    f"Non-adjacent route jump at edge {step.edge_id}: {points[-1]} != {edge_points[0]}"
                )
            points.extend(edge_points[1:])
        else:
            points.extend(edge_points)
        if step.duplicated:
            retraced += edge.length_font_units
    if route.closed and len(points) > 1 and points[-1] == points[0]:
        points.pop()
    return CenterlineStroke(
        route.component_id,
        tuple(points),
        route.closed,
        route.component_id,
        retraced,
    )
