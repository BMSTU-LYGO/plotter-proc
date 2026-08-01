from plotter_processor.centerline_font.candidate_score import (
    CandidateScoringWeights,
    score_candidate,
)


def _metrics(**updates):
    values = {
        "mask_coverage": 0.9,
        "reconstruction_extra": 0.05,
        "junction_count": 1,
        "odd_vertex_count": 2,
        "component_count": 1,
        "short_edge_count": 0,
        "micro_loop_count": 0,
        "distance_balance_cv": 0.1,
        "endpoint_boundary_penalty": 0.05,
        "estimated_retrace_ratio": 0.1,
        "shape_false_negative_ratio": 0.1,
        "shape_false_positive_ratio": 0.05,
        "counter_preservation_ratio": 1.0,
        "curvature_penalty": 0.0,
    }
    values.update(updates)
    return values


def test_shape_preservation_can_beat_simpler_topology() -> None:
    weights = CandidateScoringWeights()
    preserved = score_candidate(_metrics(junction_count=2), weights)
    damaged = score_candidate(
        _metrics(junction_count=0, mask_coverage=0.55, shape_false_negative_ratio=0.45), weights
    )
    assert preserved.total < damaged.total
    assert damaged.shape_preservation_penalty > preserved.shape_preservation_penalty


def test_candidate_score_is_explainable_and_serializable() -> None:
    result = score_candidate(_metrics(), CandidateScoringWeights())
    parts = result.serializable()
    assert parts["total"] > 0
    assert parts["coverage_penalty"] == 0.4
    assert set(parts) >= {"outside_penalty", "topology_penalty", "counter_preservation_penalty"}
