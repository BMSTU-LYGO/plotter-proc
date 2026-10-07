#include "fontc/graph_cleanup.hpp"

#include <cstdlib>
#include <iostream>

namespace {

void require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

}  // namespace

int main() {
    fontc::SkeletonGraph chain{
        {{0, {0, 0}, {0}}, {1, {1, 0}, {0, 1}}, {2, {2, 0}, {1}}},
        {{0, 0, 1, {{0, 0}, {1, 0}}}, {1, 1, 2, {{1, 0}, {2, 0}}}},
    };
    const auto collapsed = fontc::cleanup_graph(chain);
    require(collapsed.nodes.size() == 2, "false degree-2 node survived");
    require(collapsed.edges.size() == 1, "degree-2 edges were not merged");
    require(collapsed.edges[0].points.size() == 3, "merged geometry was lost");

    fontc::SkeletonGraph duplicate{
        {{0, {0, 0}, {0, 1, 2}}, {1, {2, 0}, {0, 1, 2}}},
        {
            {0, 0, 1, {{0, 0}, {2, 0}}},
            {1, 1, 0, {{2, 0}, {0, 0}}},
            {2, 0, 1, {{0, 0}, {0, 0}}},
        },
    };
    const auto unique = fontc::cleanup_graph(duplicate);
    require(unique.edges.size() == 1, "duplicate/zero-length edges survived");

    fontc::SkeletonGraph micro_loop{
        {{0, {0, 0}, {0, 0, 1}}, {1, {3, 0}, {1}}},
        {
            {0, 0, 0, {{0, 0}, {0.25F, 0}, {0, 0}}},
            {1, 0, 1, {{0, 0}, {3, 0}}},
        },
    };
    const auto no_micro_loop = fontc::cleanup_graph(micro_loop, 2.0F);
    require(no_micro_loop.edges.size() == 1, "obvious micro-loop survived");

    fontc::SkeletonGraph standalone_loop{{{0, {0, 0}, {0, 0}}}, {{0, 0, 0, {{0, 0}, {1, 0}, {0, 0}}}}};
    require(fontc::cleanup_graph(standalone_loop, 3.0F).edges.size() == 1, "standalone loop removed");

    fontc::SkeletonGraph spur{
        {{0,{0,0},{0}}, {1,{10,0},{0,1,2}}, {2,{20,0},{1}}, {3,{10,1},{2}}},
        {{0,0,1,{{0,0},{10,0}}}, {1,1,2,{{10,0},{20,0}}}, {2,1,3,{{10,0},{10,1}}}}
    };
    fontc::SpurCleanupStats stats;
    const auto cleaned = fontc::remove_short_graph_spurs(spur, 2.0F, &stats);
    require(cleaned.edges.size() == 2 && stats.removed_spurs == 1, "short endpoint-to-junction spur survived");
    require(cleaned.nodes.size() == 3 && stats.graph_nodes_before == 4, "spur cleanup changed essential topology");
    require(fontc::remove_short_graph_spurs(spur, 0.5F).edges.size() == 3, "long branch removed");
    require(fontc::remove_short_graph_spurs(chain, 5.0F).edges.size() == 2, "endpoint-to-endpoint component removed");
}
