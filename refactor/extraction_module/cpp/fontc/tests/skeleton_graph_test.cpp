#include "fontc/skeleton_graph.hpp"

#include <cstdlib>
#include <iostream>
#include <vector>

namespace {

void require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

fontc::BinaryImage image(int width, int height, const std::vector<int>& points) {
    fontc::BinaryImage result{width, height, std::vector<std::uint8_t>(
        static_cast<std::size_t>(width) * static_cast<std::size_t>(height), 0)};
    for (std::size_t index = 0; index < points.size(); index += 2) {
        result.pixels[static_cast<std::size_t>(points[index + 1] * width + points[index])] = 1;
    }
    return result;
}

}  // namespace

int main() {
    const auto line = fontc::build_skeleton_graph(image(7, 5, {1, 2, 2, 2, 3, 2, 4, 2, 5, 2}));
    require(line.nodes.size() == 2 && line.edges.size() == 1, "line graph mismatch");

    const auto tee = fontc::build_skeleton_graph(image(9, 9, {
        1, 5, 2, 5, 3, 5, 4, 5, 5, 5, 6, 5, 7, 5,
        4, 2, 4, 3, 4, 4,
    }));
    require(tee.nodes.size() == 4, "junction cluster was not collapsed");
    require(tee.edges.size() == 3, "T-junction edge count mismatch");

    const auto loop = fontc::build_skeleton_graph(image(7, 7, {
        2, 1, 3, 1, 4, 2, 4, 3, 3, 4, 2, 4, 1, 3, 1, 2,
    }));
    require(loop.nodes.size() == 1 && loop.edges.size() == 1, "closed loop mismatch");
    require(loop.edges[0].a == loop.edges[0].b, "loop must be represented by a self-edge");

    const auto mixed = fontc::build_skeleton_graph(image(8, 8, {1, 1, 2, 2, 3, 3, 6, 6}));
    require(mixed.nodes.size() == 3, "diagonal/isolated components mismatch");
    require(mixed.edges.size() == 1, "diagonal chain was not contracted");
}
