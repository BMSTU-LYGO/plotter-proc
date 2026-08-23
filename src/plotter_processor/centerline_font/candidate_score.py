from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class CandidateScoringWeights:
    coverage: float = 4.0
    outside: float = 4.0
    topology: float = 1.0
    spur: float = 2.0
    micro_loop: float = 2.0
    radius_balance: float = 0.5
    endpoint: float = 1.0
    retrace: float = 0.5
    shape_preservation: float = 4.0
    counter_preservation: float = 3.0
    curvature: float = 0.5


@dataclass(frozen=True, slots=True)
class CenterlineCandidateScore:
    total: float
    coverage_penalty: float
    outside_penalty: float
    topology_penalty: float
    spur_penalty: float
    loop_penalty: float
    radius_balance_penalty: float
    endpoint_penalty: float
    retrace_penalty: float
    shape_preservation_penalty: float
    counter_preservation_penalty: float
    curvature_penalty: float

    def serializable(self) -> dict[str, float]:
        return {key: round(float(value), 6) for key, value in asdict(self).items()}


def score_candidate(
    metrics: dict[str, float | int | str], weights: CandidateScoringWeights
) -> CenterlineCandidateScore:
    coverage = (1.0 - float(metrics["mask_coverage"])) * weights.coverage
    outside = float(metrics["reconstruction_extra"]) * weights.outside
    # Topology remains relevant, but is normalized and no longer dominates geometry.
    topology = (
        int(metrics["junction_count"]) * 0.25
        + int(metrics["odd_vertex_count"]) * 0.1
        + max(0, int(metrics["component_count"]) - 1)
    ) * weights.topology
    spur = int(metrics["short_edge_count"]) * 0.1 * weights.spur
    loops = int(metrics["micro_loop_count"]) * 0.25 * weights.micro_loop
    radius = float(metrics["distance_balance_cv"]) * weights.radius_balance
    endpoint = float(metrics["endpoint_boundary_penalty"]) * weights.endpoint
    retrace = float(metrics["estimated_retrace_ratio"]) * weights.retrace
    shape = (
        float(metrics["shape_false_negative_ratio"])
        + float(metrics["shape_false_positive_ratio"])
    ) * weights.shape_preservation
    counter = (1.0 - float(metrics["counter_preservation_ratio"])) * weights.counter_preservation
    curvature = float(metrics["curvature_penalty"]) * weights.curvature
    values = (
        coverage,
        outside,
        topology,
        spur,
        loops,
        radius,
        endpoint,
        retrace,
        shape,
        counter,
        curvature,
    )
    return CenterlineCandidateScore(
        round(sum(values), 6),
        coverage,
        outside,
        topology,
        spur,
        loops,
        radius,
        endpoint,
        retrace,
        shape,
        counter,
        curvature,
    )
