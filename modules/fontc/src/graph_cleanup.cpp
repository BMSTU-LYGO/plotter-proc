#include "fontc/graph_cleanup.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <stdexcept>
#include <utility>
#include <vector>

namespace fontc {
namespace {

[[nodiscard]] bool same_point(const Point& left, const Point& right) noexcept {
    return left.x == right.x && left.y == right.y;
}

[[nodiscard]] bool same_edge(const Edge& left, const Edge& right) noexcept {
    const bool forward = left.a == right.a && left.b == right.b &&
        left.points.size() == right.points.size() &&
        std::equal(left.points.begin(), left.points.end(), right.points.begin(), same_point);
    const bool reverse = left.a == right.b && left.b == right.a &&
        left.points.size() == right.points.size() &&
        std::equal(left.points.begin(), left.points.end(), right.points.rbegin(), same_point);
    return forward || reverse;
}

[[nodiscard]] std::vector<Point> oriented(const Edge& edge, std::uint32_t from) {
    if (edge.a == from) return edge.points;
    return {edge.points.rbegin(), edge.points.rend()};
}

void remove_invalid_and_duplicate(std::vector<Edge>& edges) {
    std::vector<Edge> kept;
    for (Edge& edge : edges) {
        if (edge.points.size() < 2 || edge_length(edge) <= 0.0F) continue;
        if (std::none_of(kept.begin(), kept.end(), [&](const Edge& other) {
                return same_edge(edge, other);
            })) {
            kept.push_back(std::move(edge));
        }
    }
    edges = std::move(kept);
}

void validate_input(const SkeletonGraph& graph) {
    for (std::size_t index = 0; index < graph.nodes.size(); ++index) {
        if (graph.nodes[index].id != index) throw std::invalid_argument("Non-contiguous node IDs");
    }
    for (std::size_t index = 0; index < graph.edges.size(); ++index) {
        const Edge& edge = graph.edges[index];
        if (edge.id != index || edge.a >= graph.nodes.size() || edge.b >= graph.nodes.size()) {
            throw std::invalid_argument("Edge references an invalid node");
        }
    }
    for (const Node& node : graph.nodes) {
        if (std::any_of(node.edges.begin(), node.edges.end(), [&](std::uint32_t edge_id) {
                return edge_id >= graph.edges.size();
            })) throw std::invalid_argument("Node references an invalid edge");
    }
}

[[nodiscard]] SkeletonGraph rebuild(
    const SkeletonGraph& source,
    std::vector<Edge> edges,
    const std::vector<std::uint8_t>& removed_nodes
) {
    std::vector<std::uint8_t> used(source.nodes.size(), 0);
    for (const Edge& edge : edges) {
        used[edge.a] = 1;
        used[edge.b] = 1;
    }
    for (const Node& node : source.nodes) {
        if (node.edges.empty() && removed_nodes[node.id] == 0) used[node.id] = 1;
    }

    std::vector<std::uint32_t> mapped(source.nodes.size(), 0);
    SkeletonGraph result;
    for (const Node& node : source.nodes) {
        if (used[node.id] == 0 || removed_nodes[node.id] != 0) continue;
        mapped[node.id] = static_cast<std::uint32_t>(result.nodes.size());
        result.nodes.push_back({mapped[node.id], node.position, {}});
    }
    for (Edge& edge : edges) {
        edge.id = static_cast<std::uint32_t>(result.edges.size());
        edge.a = mapped[edge.a];
        edge.b = mapped[edge.b];
        result.nodes[edge.a].edges.push_back(edge.id);
        result.nodes[edge.b].edges.push_back(edge.id);
        result.edges.push_back(std::move(edge));
    }
    validate_skeleton_graph(result);
    return result;
}

}  // namespace

SkeletonGraph cleanup_graph(const SkeletonGraph& graph, float micro_loop_length) {
    validate_input(graph);
    if (!std::isfinite(micro_loop_length) || micro_loop_length < 0.0F) {
        throw std::invalid_argument("Micro-loop length must be finite and non-negative");
    }

    std::vector<Edge> edges = graph.edges;
    remove_invalid_and_duplicate(edges);
    edges.erase(std::remove_if(edges.begin(), edges.end(), [&](const Edge& edge) {
        if (edge.a != edge.b || edge_length(edge) >= micro_loop_length) return false;
        return graph.nodes[edge.a].edges.size() > 2;
    }), edges.end());

    std::vector<std::uint8_t> removed_nodes(graph.nodes.size(), 0);
    bool changed = false;
    do {
        changed = false;
        for (const Node& node : graph.nodes) {
            if (removed_nodes[node.id] != 0) continue;
            std::vector<std::size_t> incident;
            for (std::size_t index = 0; index < edges.size(); ++index) {
                if (edges[index].a == node.id || edges[index].b == node.id) incident.push_back(index);
            }
            if (incident.size() != 2 || incident[0] == incident[1]) continue;
            const Edge first = edges[incident[0]];
            const Edge second = edges[incident[1]];
            if (first.a == first.b || second.a == second.b) continue;
            const std::uint32_t first_other = first.a == node.id ? first.b : first.a;
            const std::uint32_t second_other = second.a == node.id ? second.b : second.a;
            std::vector<Point> points = oriented(first, first_other);
            std::vector<Point> tail = oriented(second, node.id);
            points.insert(points.end(), std::next(tail.begin()), tail.end());

            const std::size_t high = std::max(incident[0], incident[1]);
            const std::size_t low = std::min(incident[0], incident[1]);
            edges.erase(edges.begin() + static_cast<std::ptrdiff_t>(high));
            edges.erase(edges.begin() + static_cast<std::ptrdiff_t>(low));
            edges.push_back({0, first_other, second_other, std::move(points)});
            removed_nodes[node.id] = 1;
            changed = true;
            break;
        }
    } while (changed);

    remove_invalid_and_duplicate(edges);
    return rebuild(graph, std::move(edges), removed_nodes);
}

SkeletonGraph remove_short_graph_spurs(const SkeletonGraph& graph, float threshold_pixels,
                                       SpurCleanupStats* stats) {
    validate_skeleton_graph(graph);
    if (!std::isfinite(threshold_pixels) || threshold_pixels < 0)
        throw std::invalid_argument("Spur threshold must be finite and non-negative");
    SpurCleanupStats result{};
    result.graph_nodes_before = graph.nodes.size();
    std::vector<Edge> kept;
    kept.reserve(graph.edges.size());
    for (const Edge& edge : graph.edges) {
        const auto a_degree = graph.nodes[edge.a].edges.size();
        const auto b_degree = graph.nodes[edge.b].edges.size();
        if (((a_degree == 1 && b_degree >= 3) || (b_degree == 1 && a_degree >= 3)) &&
            edge_length(edge) < threshold_pixels) {
            ++result.removed_spurs;
            result.removed_spur_length += edge_length(edge);
        } else kept.push_back(edge);
    }
    std::vector<std::uint8_t> removed(graph.nodes.size(), 0);
    for (const Edge& edge : graph.edges) {
        if (graph.nodes[edge.a].edges.size() == 1 &&
            std::none_of(kept.begin(), kept.end(), [&](const Edge& item) { return item.id == edge.id; }))
            removed[edge.a] = 1;
        if (graph.nodes[edge.b].edges.size() == 1 &&
            std::none_of(kept.begin(), kept.end(), [&](const Edge& item) { return item.id == edge.id; }))
            removed[edge.b] = 1;
    }
    SkeletonGraph output = rebuild(graph, std::move(kept), removed);
    result.graph_nodes_after = output.nodes.size();
    if (stats) *stats = result;
    return output;
}

}  // namespace fontc
