#pragma once

#include "fontc/binary_image.hpp"

#include <cstdint>
#include <vector>

namespace fontc {

struct Point {
    float x;
    float y;
};

struct Node {
    std::uint32_t id;
    Point position;
    std::vector<std::uint32_t> edges;
};

struct Edge {
    std::uint32_t id;
    std::uint32_t a;
    std::uint32_t b;
    std::vector<Point> points;
};

struct SkeletonGraph {
    std::vector<Node> nodes;
    std::vector<Edge> edges;
};

[[nodiscard]] SkeletonGraph build_skeleton_graph(const BinaryImage& skeleton);
void validate_skeleton_graph(const SkeletonGraph& graph);
[[nodiscard]] float edge_length(const Edge& edge) noexcept;

}  // namespace fontc
