from plotter_processor.routing_cost import RoutingCost, routing_cost


def test_pen_lift_costs_more_than_short_safe_retrace() -> None:
    lift = routing_cost(RoutingCost(pen_lifts=1))
    short_retrace = routing_cost(RoutingCost(retrace_distance_mm=0.5))

    assert lift > short_retrace


def test_collision_risk_dominates_visual_improvements() -> None:
    safe = routing_cost(
        RoutingCost(
            travel_distance_mm=2,
            direction_change_deg=45,
            connection_penalty=1,
        )
    )
    colliding = routing_cost(RoutingCost(collision_risk=1))

    assert colliding > safe
