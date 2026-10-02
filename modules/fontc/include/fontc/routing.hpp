#pragma once

#include "fontc/skeleton_graph.hpp"

#include <cstddef>
#include <cstdint>
#include <vector>

namespace fontc {

struct RoutedStroke {
    std::vector<Point> points;
    std::vector<std::uint32_t> edge_ids;
};

struct RoutingResult {
    std::vector<RoutedStroke> strokes;
    std::size_t stroke_count = 0;
    std::size_t pen_lifts = 0;
    float original_length = 0.0F;
    float retraced_length = 0.0F;
    float retraced_ratio = 0.0F;
};

[[nodiscard]] RoutingResult route_graph(
    const SkeletonGraph& graph,
    float max_retrace_ratio = 0.45F,
    std::size_t exact_matching_max_odd_vertices = 20
);

}  // namespace fontc
