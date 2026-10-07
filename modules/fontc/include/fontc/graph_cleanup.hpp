#pragma once

#include "fontc/skeleton_graph.hpp"

namespace fontc {

[[nodiscard]] SkeletonGraph cleanup_graph(
    const SkeletonGraph& graph,
    float micro_loop_length = 2.0F
);

struct SpurCleanupStats {
    std::size_t removed_spurs{};
    float removed_spur_length{};
    std::size_t graph_nodes_before{}, graph_nodes_after{};
};
[[nodiscard]] SkeletonGraph remove_short_graph_spurs(const SkeletonGraph& graph,
    float threshold_pixels, SpurCleanupStats* stats = nullptr);

}  // namespace fontc
