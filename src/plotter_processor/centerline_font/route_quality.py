from __future__ import annotations

from plotter_processor.centerline_font.models import ComponentRoute, SkeletonEdge


def routing_metrics(edges: list[SkeletonEdge], routes: list[ComponentRoute]) -> dict[str, float | int | bool]:
    retraced = sum(route.retraced_length_px for route in routes)
    original = sum(edge.length_px for edge in edges)
    degree: dict[int, int] = {}
    for edge in edges:
        degree[edge.start_node_id] = degree.get(edge.start_node_id, 0) + 1
        degree[edge.end_node_id] = degree.get(edge.end_node_id, 0) + 1
    return {
        "graph_edges": len(edges),
        "odd_vertices": sum(value % 2 for value in degree.values()),
        "strokes_before_routing": len(edges),
        "strokes_after_routing": len(routes),
        "pen_lifts_saved": max(0, len(edges) - len(routes)),
        "retraced_edges": sum(step.duplicated for route in routes for step in route.steps),
        "retraced_length": round(retraced, 6),
        "retrace_ratio": round(retraced / max(original, 1e-9), 6),
        "fallback_used": len(routes) > len({route.component_id for route in routes}),
    }
