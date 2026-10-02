#include "fontc/routing.hpp"

#include <algorithm>
#include <bit>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <functional>
#include <limits>
#include <numeric>
#include <queue>
#include <stdexcept>
#include <utility>
#include <vector>

namespace fontc {
namespace {

constexpr std::uint32_t virtual_edge = std::numeric_limits<std::uint32_t>::max();

struct Occurrence {
    std::uint32_t edge_id;
    std::uint32_t a;
    std::uint32_t b;
    bool duplicated;
};

struct Traversal {
    std::size_t occurrence;
    std::uint32_t from;
};

struct ShortestPath {
    float length = std::numeric_limits<float>::infinity();
    std::vector<std::uint32_t> edges;
};

[[nodiscard]] std::vector<std::vector<std::uint32_t>> adjacency(const SkeletonGraph& graph) {
    std::vector<std::vector<std::uint32_t>> result(graph.nodes.size());
    for (const Edge& edge : graph.edges) {
        result[edge.a].push_back(edge.id);
        if (edge.b != edge.a) result[edge.b].push_back(edge.id);
    }
    for (auto& edges : result) std::sort(edges.begin(), edges.end());
    return result;
}

[[nodiscard]] std::vector<std::vector<std::uint32_t>> edge_components(
    const SkeletonGraph& graph,
    const std::vector<std::vector<std::uint32_t>>& adjacent
) {
    std::vector<std::uint8_t> seen(graph.edges.size(), 0);
    std::vector<std::vector<std::uint32_t>> components;
    for (const Edge& seed : graph.edges) {
        if (seen[seed.id] != 0) continue;
        std::vector<std::uint32_t> component;
        std::vector<std::uint32_t> stack{seed.id};
        seen[seed.id] = 1;
        while (!stack.empty()) {
            const std::uint32_t edge_id = stack.back();
            stack.pop_back();
            component.push_back(edge_id);
            const Edge& edge = graph.edges[edge_id];
            for (const std::uint32_t node : {edge.a, edge.b}) {
                for (const std::uint32_t candidate : adjacent[node]) {
                    if (seen[candidate] == 0) {
                        seen[candidate] = 1;
                        stack.push_back(candidate);
                    }
                }
            }
        }
        std::sort(component.begin(), component.end());
        components.push_back(std::move(component));
    }
    return components;
}

[[nodiscard]] ShortestPath shortest_path(
    const SkeletonGraph& graph,
    const std::vector<std::vector<std::uint32_t>>& adjacent,
    std::uint32_t source,
    std::uint32_t target
) {
    const float infinity = std::numeric_limits<float>::infinity();
    std::vector<float> distance(graph.nodes.size(), infinity);
    std::vector<std::uint32_t> previous_edge(graph.nodes.size(), virtual_edge);
    using QueueItem = std::pair<float, std::uint32_t>;
    std::priority_queue<QueueItem, std::vector<QueueItem>, std::greater<>> queue;
    distance[source] = 0.0F;
    queue.emplace(0.0F, source);
    while (!queue.empty()) {
        const auto [cost, node] = queue.top();
        queue.pop();
        if (cost > distance[node]) continue;
        if (node == target) break;
        for (const std::uint32_t edge_id : adjacent[node]) {
            const Edge& edge = graph.edges[edge_id];
            const std::uint32_t next = edge.a == node ? edge.b : edge.a;
            const float candidate = cost + edge_length(edge);
            if (candidate < distance[next] ||
                (candidate == distance[next] && edge_id < previous_edge[next])) {
                distance[next] = candidate;
                previous_edge[next] = edge_id;
                queue.emplace(candidate, next);
            }
        }
    }
    if (!std::isfinite(distance[target])) throw std::runtime_error("Odd vertices are disconnected");
    std::vector<std::uint32_t> path;
    for (std::uint32_t node = target; node != source;) {
        const std::uint32_t edge_id = previous_edge[node];
        if (edge_id == virtual_edge) throw std::runtime_error("Broken shortest path");
        path.push_back(edge_id);
        const Edge& edge = graph.edges[edge_id];
        node = edge.a == node ? edge.b : edge.a;
    }
    std::reverse(path.begin(), path.end());
    return {distance[target], std::move(path)};
}

[[nodiscard]] std::vector<std::pair<std::size_t, std::size_t>> match_odd_vertices(
    const std::vector<std::uint32_t>& odd,
    const std::vector<std::vector<ShortestPath>>& paths,
    std::size_t exact_limit
) {
    if (odd.size() <= exact_limit && odd.size() <= 20) {
        const std::uint64_t full = (std::uint64_t{1} << odd.size()) - 1U;
        std::vector<float> memo(static_cast<std::size_t>(full + 1U), -1.0F);
        std::vector<std::size_t> choice(memo.size(), 0);
        std::function<float(std::uint64_t)> solve = [&](std::uint64_t mask) -> float {
            if (mask == 0) return 0.0F;
            if (memo[mask] >= 0.0F) return memo[mask];
            const std::size_t left = static_cast<std::size_t>(std::countr_zero(mask));
            float best = std::numeric_limits<float>::infinity();
            for (std::size_t right = left + 1; right < odd.size(); ++right) {
                if ((mask & (std::uint64_t{1} << right)) == 0) continue;
                const std::uint64_t rest = mask & ~(std::uint64_t{1} << left) &
                    ~(std::uint64_t{1} << right);
                const float cost = paths[left][right].length + solve(rest);
                if (cost < best) {
                    best = cost;
                    choice[mask] = right;
                }
            }
            memo[mask] = best;
            return best;
        };
        (void)solve(full);
        std::vector<std::pair<std::size_t, std::size_t>> pairs;
        for (std::uint64_t mask = full; mask != 0;) {
            const std::size_t left = static_cast<std::size_t>(std::countr_zero(mask));
            const std::size_t right = choice[mask];
            pairs.emplace_back(left, right);
            mask &= ~(std::uint64_t{1} << left);
            mask &= ~(std::uint64_t{1} << right);
        }
        return pairs;
    }

    std::vector<std::size_t> remaining(odd.size());
    for (std::size_t index = 0; index < odd.size(); ++index) remaining[index] = index;
    std::vector<std::pair<std::size_t, std::size_t>> pairs;
    while (!remaining.empty()) {
        const std::size_t left = remaining.front();
        const auto best = std::min_element(std::next(remaining.begin()), remaining.end(),
            [&](std::size_t a, std::size_t b) {
                return paths[left][a].length < paths[left][b].length;
            });
        const std::size_t right = *best;
        remaining.erase(best);
        remaining.erase(remaining.begin());
        pairs.emplace_back(left, right);
    }
    return pairs;
}

[[nodiscard]] std::vector<Traversal> hierholzer(
    const std::vector<Occurrence>& occurrences,
    std::uint32_t start,
    std::size_t node_count
) {
    std::vector<std::vector<std::size_t>> adjacent(node_count);
    for (std::size_t index = 0; index < occurrences.size(); ++index) {
        adjacent[occurrences[index].a].push_back(index);
        adjacent[occurrences[index].b].push_back(index);
    }
    std::vector<std::uint8_t> used(occurrences.size(), 0);
    struct StackItem { std::uint32_t node; std::size_t occurrence; std::uint32_t from; };
    std::vector<StackItem> stack{{start, occurrences.size(), start}};
    std::vector<Traversal> circuit;
    while (!stack.empty()) {
        const std::uint32_t node = stack.back().node;
        auto& options = adjacent[node];
        while (!options.empty() && used[options.back()] != 0) options.pop_back();
        if (!options.empty()) {
            const std::size_t occurrence_id = options.back();
            options.pop_back();
            if (used[occurrence_id] != 0) continue;
            used[occurrence_id] = 1;
            const Occurrence& occurrence = occurrences[occurrence_id];
            const std::uint32_t next = occurrence.a == node ? occurrence.b : occurrence.a;
            stack.push_back({next, occurrence_id, node});
        } else {
            const StackItem item = stack.back();
            stack.pop_back();
            if (item.occurrence != occurrences.size()) circuit.push_back({item.occurrence, item.from});
        }
    }
    std::reverse(circuit.begin(), circuit.end());
    if (circuit.size() != occurrences.size()) throw std::runtime_error("Incomplete Euler traversal");
    return circuit;
}

[[nodiscard]] RoutedStroke assemble(
    const SkeletonGraph& graph,
    const std::vector<Occurrence>& occurrences,
    const std::vector<Traversal>& traversal
) {
    RoutedStroke stroke;
    for (const Traversal& step : traversal) {
        const Occurrence& occurrence = occurrences[step.occurrence];
        if (occurrence.edge_id == virtual_edge) continue;
        const Edge& edge = graph.edges[occurrence.edge_id];
        std::vector<Point> points = edge.a == step.from
            ? edge.points : std::vector<Point>(edge.points.rbegin(), edge.points.rend());
        if (!stroke.points.empty() && !points.empty()) points.erase(points.begin());
        stroke.points.insert(stroke.points.end(), points.begin(), points.end());
        stroke.edge_ids.push_back(edge.id);
    }
    return stroke;
}

}  // namespace

RoutingResult route_graph(
    const SkeletonGraph& graph,
    float max_retrace_ratio,
    std::size_t exact_matching_max_odd_vertices
) {
    validate_skeleton_graph(graph);
    if (!std::isfinite(max_retrace_ratio) || max_retrace_ratio < 0.0F) {
        throw std::invalid_argument("Maximum retrace ratio must be finite and non-negative");
    }
    RoutingResult result;
    const auto adjacent = adjacency(graph);
    for (const auto& component : edge_components(graph, adjacent)) {
        std::vector<std::uint32_t> degree(graph.nodes.size(), 0);
        std::vector<std::uint32_t> component_nodes;
        std::vector<Occurrence> occurrences;
        for (const std::uint32_t edge_id : component) {
            const Edge& edge = graph.edges[edge_id];
            result.original_length += edge_length(edge);
            occurrences.push_back({edge.id, edge.a, edge.b, false});
            degree[edge.a] += edge.a == edge.b ? 2U : 1U;
            if (edge.b != edge.a) degree[edge.b] += 1U;
        }
        for (std::uint32_t node = 0; node < degree.size(); ++node) {
            if (degree[node] != 0) component_nodes.push_back(node);
        }
        std::vector<std::uint32_t> odd;
        for (const std::uint32_t node : component_nodes) if (degree[node] % 2U != 0) odd.push_back(node);

        if (odd.size() <= 2) {
            const std::uint32_t start = odd.empty() ? component_nodes.front() : odd.front();
            result.strokes.push_back(assemble(graph, occurrences,
                hierholzer(occurrences, start, graph.nodes.size())));
            continue;
        }

        std::vector<std::vector<ShortestPath>> paths(odd.size(), std::vector<ShortestPath>(odd.size()));
        for (std::size_t left = 0; left < odd.size(); ++left) {
            for (std::size_t right = left + 1; right < odd.size(); ++right) {
                paths[left][right] = shortest_path(graph, adjacent, odd[left], odd[right]);
                paths[right][left] = paths[left][right];
            }
        }
        const auto pairs = match_odd_vertices(odd, paths, exact_matching_max_odd_vertices);
        float duplicated_length = 0.0F;
        for (const auto& [left, right] : pairs) {
            duplicated_length += paths[left][right].length;
            for (const std::uint32_t edge_id : paths[left][right].edges) {
                const Edge& edge = graph.edges[edge_id];
                occurrences.push_back({edge.id, edge.a, edge.b, true});
            }
        }
        const float component_length = std::accumulate(component.begin(), component.end(), 0.0F,
            [&](float total, std::uint32_t edge_id) { return total + edge_length(graph.edges[edge_id]); });
        if (duplicated_length / component_length <= max_retrace_ratio) {
            result.retraced_length += duplicated_length;
            result.strokes.push_back(assemble(graph, occurrences,
                hierholzer(occurrences, component_nodes.front(), graph.nodes.size())));
        } else {
            occurrences.resize(component.size());
            const std::uint32_t virtual_node = static_cast<std::uint32_t>(graph.nodes.size());
            for (const std::uint32_t node : odd) {
                occurrences.push_back({virtual_edge, virtual_node, node, false});
            }
            const auto circuit = hierholzer(occurrences, virtual_node, graph.nodes.size() + 1);
            std::vector<Traversal> trail;
            for (const Traversal& step : circuit) {
                if (occurrences[step.occurrence].edge_id == virtual_edge) {
                    if (!trail.empty()) {
                        result.strokes.push_back(assemble(graph, occurrences, trail));
                        trail.clear();
                    }
                } else {
                    trail.push_back(step);
                }
            }
            if (!trail.empty()) result.strokes.push_back(assemble(graph, occurrences, trail));
        }
    }

    for (const Node& node : graph.nodes) {
        if (node.edges.empty()) result.strokes.push_back({{node.position}, {}});
    }
    result.stroke_count = result.strokes.size();
    result.pen_lifts = result.stroke_count == 0 ? 0 : result.stroke_count - 1;
    result.retraced_ratio = result.retraced_length / std::max(result.original_length, 1.0F);
    return result;
}

}  // namespace fontc
