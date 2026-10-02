#include "fontc/routing.hpp"

#include <cstdlib>
#include <iostream>

namespace {

void require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

fontc::SkeletonGraph graph(std::size_t node_count, const std::vector<std::pair<int, int>>& links) {
    fontc::SkeletonGraph result;
    for (std::size_t index = 0; index < node_count; ++index) {
        result.nodes.push_back({static_cast<std::uint32_t>(index), {static_cast<float>(index), 0}, {}});
    }
    for (const auto& [a, b] : links) {
        const auto id = static_cast<std::uint32_t>(result.edges.size());
        result.edges.push_back({id, static_cast<std::uint32_t>(a), static_cast<std::uint32_t>(b),
            {result.nodes[static_cast<std::size_t>(a)].position, result.nodes[static_cast<std::size_t>(b)].position}});
        result.nodes[static_cast<std::size_t>(a)].edges.push_back(id);
        result.nodes[static_cast<std::size_t>(b)].edges.push_back(id);
    }
    return result;
}

}  // namespace

int main() {
    const auto trail = fontc::route_graph(graph(3, {{0, 1}, {1, 2}}));
    require(trail.stroke_count == 1 && trail.retraced_length == 0.0F, "Euler trail mismatch");

    const auto circuit = fontc::route_graph(graph(3, {{0, 1}, {1, 2}, {2, 0}}));
    require(circuit.stroke_count == 1 && circuit.retraced_length == 0.0F, "Euler circuit mismatch");

    const auto star = graph(5, {{0, 1}, {0, 2}, {0, 3}, {0, 4}});
    const auto retraced = fontc::route_graph(star, 10.0F);
    require(retraced.stroke_count == 1, "augmented Euler route must be one stroke");
    require(retraced.retraced_length > 0.0F, "augmentation retrace was not reported");
    const auto split = fontc::route_graph(star, 0.0F);
    require(split.stroke_count == 2, "minimum-trail fallback mismatch");
    require(split.retraced_length == 0.0F && split.pen_lifts == 1, "fallback metrics mismatch");

    const auto disconnected = fontc::route_graph(graph(6, {{0, 1}, {1, 2}, {3, 4}, {4, 5}}));
    require(disconnected.stroke_count == 2, "connected components must route independently");
}
