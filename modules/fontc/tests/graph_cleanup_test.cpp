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
}
