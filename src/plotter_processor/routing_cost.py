from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RoutingCost:
    travel_distance_mm: float = 0.0
    pen_lifts: int = 0
    retrace_distance_mm: float = 0.0
    direction_change_deg: float = 0.0
    connection_penalty: float = 0.0
    collision_risk: float = 0.0


@dataclass(frozen=True, slots=True)
class RoutingCostWeights:
    travel: float = 1.0
    pen_lift: float = 8.0
    retrace: float = 1.5
    direction_change: float = 1 / 90
    connection_quality: float = 2.0
    collision_risk: float = 100.0


DEFAULT_ROUTING_COST_WEIGHTS = RoutingCostWeights()


def routing_cost(
    value: RoutingCost,
    weights: RoutingCostWeights = DEFAULT_ROUTING_COST_WEIGHTS,
) -> float:
    return (
        value.travel_distance_mm * weights.travel
        + value.pen_lifts * weights.pen_lift
        + value.retrace_distance_mm * weights.retrace
        + value.direction_change_deg * weights.direction_change
        + value.connection_penalty * weights.connection_quality
        + value.collision_risk * weights.collision_risk
    )
