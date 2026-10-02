#include "fontc/skeleton_graph.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <limits>
#include <set>
#include <stdexcept>
#include <utility>
#include <vector>

namespace fontc {
namespace {

constexpr int no_node = -1;

struct NeighborList {
    std::array<std::size_t, 8> values{};
    std::size_t size = 0;
};

[[nodiscard]] std::size_t index_of(const BinaryImage& image, int x, int y) noexcept {
    return static_cast<std::size_t>(y) * static_cast<std::size_t>(image.width) +
        static_cast<std::size_t>(x);
}

[[nodiscard]] Point point_of(const BinaryImage& image, std::size_t pixel) noexcept {
    return {
        static_cast<float>(pixel % static_cast<std::size_t>(image.width)),
        static_cast<float>(pixel / static_cast<std::size_t>(image.width)),
    };
}

[[nodiscard]] NeighborList neighbors(const BinaryImage& image, std::size_t pixel) noexcept {
    NeighborList result;
    const int x = static_cast<int>(pixel % static_cast<std::size_t>(image.width));
    const int y = static_cast<int>(pixel / static_cast<std::size_t>(image.width));
    for (int dy = -1; dy <= 1; ++dy) {
        for (int dx = -1; dx <= 1; ++dx) {
            if ((dx == 0 && dy == 0) || x + dx < 0 || y + dy < 0 ||
                x + dx >= image.width || y + dy >= image.height) continue;
            const std::size_t candidate = index_of(image, x + dx, y + dy);
            if (image.pixels[candidate] != 0) result.values[result.size++] = candidate;
        }
    }
    return result;
}

[[nodiscard]] std::pair<std::size_t, std::size_t> link(std::size_t a, std::size_t b) noexcept {
    return std::minmax(a, b);
}

void validate_image(const BinaryImage& image) {
    if (image.width < 0 || image.height < 0) throw std::invalid_argument("Invalid skeleton size");
    const auto area = static_cast<std::size_t>(image.width) * static_cast<std::size_t>(image.height);
    if (image.pixels.size() != area) throw std::invalid_argument("Invalid skeleton buffer size");
    if (std::any_of(image.pixels.begin(), image.pixels.end(), [](std::uint8_t value) {
            return value > 1;
        })) throw std::invalid_argument("Skeleton pixels must be 0 or 1");
}

[[nodiscard]] Point cluster_position(
    const BinaryImage& image,
    const std::vector<std::size_t>& cluster
) noexcept {
    float x = 0.0F;
    float y = 0.0F;
    for (const std::size_t pixel : cluster) {
        const Point point = point_of(image, pixel);
        x += point.x;
        y += point.y;
    }
    const float count = static_cast<float>(cluster.size());
    return {x / count, y / count};
}

void add_edge(SkeletonGraph& graph, std::uint32_t a, std::uint32_t b, std::vector<Point> points) {
    if (points.size() < 2) return;
    const std::uint32_t id = static_cast<std::uint32_t>(graph.edges.size());
    graph.edges.push_back({id, a, b, std::move(points)});
    graph.nodes[a].edges.push_back(id);
    graph.nodes[b].edges.push_back(id);
}

}  // namespace

float edge_length(const Edge& edge) noexcept {
    float length = 0.0F;
    for (std::size_t index = 1; index < edge.points.size(); ++index) {
        length += std::hypot(
            edge.points[index].x - edge.points[index - 1].x,
            edge.points[index].y - edge.points[index - 1].y
        );
    }
    return length;
}

SkeletonGraph build_skeleton_graph(const BinaryImage& skeleton) {
    validate_image(skeleton);
    SkeletonGraph graph;
    if (skeleton.pixels.empty()) return graph;

    std::vector<int> pixel_node(skeleton.pixels.size(), no_node);
    std::vector<std::vector<std::size_t>> node_pixels;
    std::vector<std::uint8_t> clustered(skeleton.pixels.size(), 0);

    for (std::size_t seed = 0; seed < skeleton.pixels.size(); ++seed) {
        if (skeleton.pixels[seed] == 0 || clustered[seed] != 0 || neighbors(skeleton, seed).size < 3) continue;
        std::vector<std::size_t> cluster;
        std::vector<std::size_t> stack{seed};
        clustered[seed] = 1;
        while (!stack.empty()) {
            const std::size_t pixel = stack.back();
            stack.pop_back();
            cluster.push_back(pixel);
            const NeighborList adjacent = neighbors(skeleton, pixel);
            for (std::size_t index = 0; index < adjacent.size; ++index) {
                const std::size_t candidate = adjacent.values[index];
                if (clustered[candidate] == 0 && neighbors(skeleton, candidate).size >= 3) {
                    clustered[candidate] = 1;
                    stack.push_back(candidate);
                }
            }
        }
        std::sort(cluster.begin(), cluster.end());
        const std::uint32_t id = static_cast<std::uint32_t>(graph.nodes.size());
        graph.nodes.push_back({id, cluster_position(skeleton, cluster), {}});
        node_pixels.push_back(cluster);
        for (const std::size_t pixel : cluster) pixel_node[pixel] = static_cast<int>(id);
    }

    for (std::size_t pixel = 0; pixel < skeleton.pixels.size(); ++pixel) {
        if (skeleton.pixels[pixel] == 0 || pixel_node[pixel] != no_node) continue;
        const std::size_t degree = neighbors(skeleton, pixel).size;
        if (degree == 1 || degree == 0) {
            const std::uint32_t id = static_cast<std::uint32_t>(graph.nodes.size());
            graph.nodes.push_back({id, point_of(skeleton, pixel), {}});
            node_pixels.push_back({pixel});
            pixel_node[pixel] = static_cast<int>(id);
        }
    }

    std::set<std::pair<std::size_t, std::size_t>> used;
    std::vector<std::uint8_t> covered(skeleton.pixels.size(), 0);
    for (std::size_t node_id = 0; node_id < node_pixels.size(); ++node_id) {
        for (const std::size_t pixel : node_pixels[node_id]) {
            covered[pixel] = 1;
            const NeighborList adjacent = neighbors(skeleton, pixel);
            for (std::size_t neighbor_index = 0; neighbor_index < adjacent.size; ++neighbor_index) {
                const std::size_t neighbor = adjacent.values[neighbor_index];
                if (pixel_node[neighbor] == static_cast<int>(node_id) || used.contains(link(pixel, neighbor))) continue;
                std::vector<Point> points{graph.nodes[node_id].position};
                std::size_t previous = pixel;
                std::size_t current = neighbor;
                used.insert(link(previous, current));
                while (pixel_node[current] == no_node) {
                    covered[current] = 1;
                    points.push_back(point_of(skeleton, current));
                    const NeighborList choices = neighbors(skeleton, current);
                    std::size_t next = std::numeric_limits<std::size_t>::max();
                    for (std::size_t choice = 0; choice < choices.size; ++choice) {
                        if (choices.values[choice] == previous) continue;
                        if (next != std::numeric_limits<std::size_t>::max()) {
                            throw std::runtime_error("Invalid degree-2 skeleton chain");
                        }
                        next = choices.values[choice];
                    }
                    if (next == std::numeric_limits<std::size_t>::max()) {
                        throw std::runtime_error("Broken skeleton chain");
                    }
                    previous = current;
                    current = next;
                    used.insert(link(previous, current));
                }
                const auto end = static_cast<std::uint32_t>(pixel_node[current]);
                points.push_back(graph.nodes[end].position);
                add_edge(graph, static_cast<std::uint32_t>(node_id), end, std::move(points));
            }
        }
    }

    for (std::size_t anchor = 0; anchor < skeleton.pixels.size(); ++anchor) {
        if (skeleton.pixels[anchor] == 0 || covered[anchor] != 0 || pixel_node[anchor] != no_node) continue;
        const NeighborList start_neighbors = neighbors(skeleton, anchor);
        if (start_neighbors.size != 2) throw std::runtime_error("Unrepresented skeleton topology");
        const std::uint32_t node_id = static_cast<std::uint32_t>(graph.nodes.size());
        graph.nodes.push_back({node_id, point_of(skeleton, anchor), {}});
        node_pixels.push_back({anchor});
        pixel_node[anchor] = static_cast<int>(node_id);
        covered[anchor] = 1;
        std::vector<Point> points{point_of(skeleton, anchor)};
        std::size_t previous = anchor;
        std::size_t current = start_neighbors.values[0];
        while (current != anchor) {
            if (covered[current] != 0) throw std::runtime_error("Loop traversal repeated a pixel");
            covered[current] = 1;
            points.push_back(point_of(skeleton, current));
            const NeighborList adjacent = neighbors(skeleton, current);
            std::size_t next = adjacent.values[0] == previous ? adjacent.values[1] : adjacent.values[0];
            previous = current;
            current = next;
        }
        points.push_back(point_of(skeleton, anchor));
        add_edge(graph, node_id, node_id, std::move(points));
    }

    validate_skeleton_graph(graph);
    return graph;
}

void validate_skeleton_graph(const SkeletonGraph& graph) {
    for (std::size_t index = 0; index < graph.nodes.size(); ++index) {
        if (graph.nodes[index].id != index) throw std::runtime_error("Non-contiguous node IDs");
    }
    for (std::size_t index = 0; index < graph.edges.size(); ++index) {
        const Edge& edge = graph.edges[index];
        if (edge.id != index || edge.a >= graph.nodes.size() || edge.b >= graph.nodes.size()) {
            throw std::runtime_error("Edge references an invalid node");
        }
        if (edge.points.size() < 2 || edge_length(edge) <= 0.0F) {
            throw std::runtime_error("Graph contains a zero-length edge");
        }
    }
    for (const Node& node : graph.nodes) {
        for (const std::uint32_t edge_id : node.edges) {
            if (edge_id >= graph.edges.size()) throw std::runtime_error("Node references an invalid edge");
            const Edge& edge = graph.edges[edge_id];
            if (edge.a != node.id && edge.b != node.id) throw std::runtime_error("Invalid node adjacency");
        }
    }
}

}  // namespace fontc
