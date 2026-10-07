#pragma once
#include "fontc/skeleton_graph.hpp"
#include <cstddef>

namespace fontc {
struct CurveOptions {
    float fit_error_pixels{}, max_error_pixels{}, min_segment_pixels{};
    float straight_target_pixels{}, curve_target_pixels{}, tight_target_pixels{};
};
struct CurveStats { std::size_t raw_points{}, bezier_segments{}, final_points{}; };
[[nodiscard]] SkeletonGraph fit_graph_edges(const SkeletonGraph& graph,
    const CurveOptions& options, CurveStats* stats = nullptr);
}
