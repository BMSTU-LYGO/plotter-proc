from plotter_processor.latex_renderer import MathTextRenderer


def test_formula_quality_contains_bounded_topology_metrics() -> None:
    rendered = MathTextRenderer(strict_quality=True).render(r"\frac{a}{b}", 5.0)

    expected = {
        "components_before_pruning",
        "components_after_pruning",
        "graph_nodes",
        "graph_edges",
        "junction_count",
        "strokes",
        "points",
        "draw_length_mm",
        "retraced_length_mm",
        "retrace_ratio",
        "centerline_coverage_ratio",
        "needs_review",
    }
    assert expected <= rendered.quality.keys()
    assert rendered.quality["points"] <= 150_000
