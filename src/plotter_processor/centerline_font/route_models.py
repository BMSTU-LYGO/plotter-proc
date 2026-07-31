from dataclasses import dataclass

from plotter_processor.centerline_font.models import ComponentRoute, RouteEdgeStep


@dataclass(frozen=True, slots=True)
class RoutedEdgeOccurrence:
    occurrence_id: int
    source_edge_id: int
    start_node_id: int
    end_node_id: int
    duplicated: bool
    weight: float


__all__ = ["ComponentRoute", "RouteEdgeStep", "RoutedEdgeOccurrence"]
