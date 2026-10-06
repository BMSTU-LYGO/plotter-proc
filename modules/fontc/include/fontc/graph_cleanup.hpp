#pragma once

#include "fontc/skeleton_graph.hpp"

namespace fontc {

[[nodiscard]] SkeletonGraph cleanup_graph(
    const SkeletonGraph& graph,
    float micro_loop_length = 2.0F
);

}  // namespace fontc
