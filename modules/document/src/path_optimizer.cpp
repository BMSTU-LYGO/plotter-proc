#include "plotter/doc/path_optimizer.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <optional>
#include <set>
#include <tuple>
#include <utility>

namespace plotter::doc {
namespace {

constexpr double kNextGroupPenaltyMm = 0.35;
constexpr double kEpsilon = 1e-9;

double distance(const Point& left, const Point& right) {
    return std::hypot(right.x.value - left.x.value, right.y.value - left.y.value);
}

double length(const std::vector<Point>& points) {
    double result{};
    for (std::size_t index = 1; index < points.size(); ++index) {
        result += distance(points[index - 1], points[index]);
    }
    return result;
}

bool same_point(const Point& left, const Point& right, double tolerance) {
    return distance(left, right) <= tolerance;
}

std::string value_or(const std::optional<std::string>& value, const char* fallback) {
    return value ? *value : fallback;
}

std::string semantic_key(const Stroke& stroke) {
    // Every field below is a boundary: reordering across it could change document
    // stacking, text ownership, or provenance even when endpoints are nearer.
    const auto primary = stroke.element_id ? "element:" + *stroke.element_id
                          : stroke.glyph_index ? "glyph:" + std::to_string(*stroke.glyph_index)
                                               : "unassigned";
    return primary + "|page:" + (stroke.source_page_index ? std::to_string(*stroke.source_page_index) : "") +
           "|layout:" + value_or(stroke.layout_group, "") +
           "|role:" + value_or(stroke.semantic_role, "") +
           "|type:" + value_or(stroke.element_type, "") +
           "|z:" + std::to_string(stroke.z_order);
}

bool allows_retrace(const Stroke& stroke, const PathOptimizerOptions& options) {
    const std::vector<std::string> kinds = stroke.segment_types.empty()
                                               ? std::vector<std::string>{"glyph"}
                                               : stroke.segment_types;
    return std::all_of(kinds.begin(), kinds.end(), [&](const std::string& kind) {
        return std::find(options.retrace_segment_types.begin(), options.retrace_segment_types.end(), kind) !=
               options.retrace_segment_types.end();
    });
}

double point_segment_distance(const Point& point, const Point& start, const Point& end) {
    const double dx = end.x.value - start.x.value;
    const double dy = end.y.value - start.y.value;
    const double squared = dx * dx + dy * dy;
    if (squared == 0.0) return distance(point, start);
    const double t = std::clamp(((point.x.value - start.x.value) * dx +
                                 (point.y.value - start.y.value) * dy) / squared, 0.0, 1.0);
    return std::hypot(point.x.value - (start.x.value + t * dx),
                      point.y.value - (start.y.value + t * dy));
}

bool clear_of_keep_outs(const std::vector<Point>& points, const std::vector<CircularKeepOut>& keep_outs) {
    for (std::size_t index = 1; index < points.size(); ++index) {
        for (const auto& zone : keep_outs) {
            if (point_segment_distance(zone.center, points[index - 1], points[index]) <=
                zone.radius.value + zone.clearance.value + kEpsilon) return false;
        }
    }
    return true;
}

Stroke orient(const Stroke& source, const std::optional<Point>& previous,
              const std::vector<Point>& next_endpoints) {
    Stroke result = source;
    if (result.preserve_order || result.points.empty()) return result;
    if (result.closed) {
        if (!previous) return result;
        const auto start = std::min_element(result.points.begin(), result.points.end(),
            [&](const Point& left, const Point& right) {
                return distance(*previous, left) < distance(*previous, right);
            });
        std::rotate(result.points.begin(), start, result.points.end());
        return result;
    }
    if (result.points.size() < 2) return result;
    const double forward = previous ? distance(*previous, result.points.front()) : 0.0;
    const double reverse = previous ? distance(*previous, result.points.back()) : 0.0;
    bool reverse_points = reverse < forward;
    const double preferred = std::min(forward, reverse);
    const double alternate = std::max(forward, reverse);
    if (!next_endpoints.empty() && alternate <= preferred + kNextGroupPenaltyMm) {
        const Point& preferred_end = reverse_points ? result.points.front() : result.points.back();
        const Point& alternate_end = reverse_points ? result.points.back() : result.points.front();
        const auto nearest = [&](const Point& point) {
            double best = std::numeric_limits<double>::infinity();
            for (const auto& endpoint : next_endpoints) best = std::min(best, distance(point, endpoint));
            return best;
        };
        const double preferred_cost = preferred + nearest(preferred_end);
        const double alternate_cost = alternate + nearest(alternate_end);
        if (alternate_cost < preferred_cost) reverse_points = !reverse_points;
    }
    if (reverse_points) std::reverse(result.points.begin(), result.points.end());
    return result;
}

std::vector<Point> endpoints(const std::vector<Stroke>& group) {
    std::vector<Point> result;
    for (const auto& stroke : group) if (!stroke.points.empty()) {
        result.push_back(stroke.points.front());
        result.push_back(stroke.points.back());
    }
    return result;
}

std::optional<std::pair<Stroke, double>> merge_retrace(
    const Stroke& previous, const Stroke& following, const PathOptimizerOptions& options,
    std::size_t repeats) {
    if (!previous.glyph_index || !following.glyph_index ||
        semantic_key(previous) != semantic_key(following) ||
        previous.glyph_index != following.glyph_index || previous.closed || following.closed ||
        previous.preserve_order || following.points.size() < 2 || previous.points.size() < 2 ||
        repeats >= options.max_retrace_repeats || !allows_retrace(previous, options) ||
        !allows_retrace(following, options)) return std::nullopt;
    struct Match { double retrace; std::size_t junction; bool reverse; };
    std::optional<Match> best;
    for (std::size_t index = 0; index + 1 < previous.points.size(); ++index) {
        const double retrace = length({previous.points.begin() + static_cast<std::ptrdiff_t>(index), previous.points.end()});
        if (retrace > options.max_retrace_length.value + kEpsilon) continue;
        for (const bool reverse : {false, true}) {
            const Point& start = reverse ? following.points.back() : following.points.front();
            if (!same_point(previous.points[index], start, options.endpoint_tolerance.value)) continue;
            if (!best || std::tie(retrace, index, reverse) < std::tie(best->retrace, best->junction, best->reverse)) {
                best = {retrace, index, reverse};
            }
        }
    }
    if (!best) return std::nullopt;
    const double original = length(previous.points) + length(following.points);
    const Point& following_start = best->reverse ? following.points.back() : following.points.front();
    // A retrace is only worthwhile when the pen-up move it replaces is longer.
    if (best->retrace >= distance(previous.points.back(), following_start) ||
        best->retrace / std::max(original, kEpsilon) > options.max_retrace_ratio) return std::nullopt;
    Stroke merged = previous;
    for (std::size_t index = previous.points.size() - 1; index > best->junction; --index) {
        merged.points.push_back(previous.points[index - 1]);
    }
    std::vector<Point> following_points = following.points;
    if (best->reverse) std::reverse(following_points.begin(), following_points.end());
    merged.points.insert(merged.points.end(), std::next(following_points.begin()), following_points.end());
    if (!clear_of_keep_outs(merged.points, options.keep_outs)) return std::nullopt;
    merged.segment_types.push_back("retrace");
    merged.segment_types.insert(merged.segment_types.end(), following.segment_types.begin(), following.segment_types.end());
    for (const auto glyph : following.source_glyph_indices) {
        if (std::find(merged.source_glyph_indices.begin(), merged.source_glyph_indices.end(), glyph) == merged.source_glyph_indices.end())
            merged.source_glyph_indices.push_back(glyph);
    }
    for (const auto id : following.connection_ids) {
        if (std::find(merged.connection_ids.begin(), merged.connection_ids.end(), id) == merged.connection_ids.end())
            merged.connection_ids.push_back(id);
    }
    if (merged.source_characters.empty()) merged.source_characters = following.source_characters;
    merged.preserve_order = true;
    return std::pair{std::move(merged), best->retrace};
}

}  // namespace

PathDocument optimize_paths(const PathDocument& document, const PathOptimizerOptions& options,
                            PathOptimizationReport* report) {
    PathDocument result = document;
    result.strokes.clear();
    PathOptimizationReport local_report;
    std::vector<std::vector<Stroke>> groups;
    for (const auto& stroke : document.strokes) {
        if (groups.empty() || semantic_key(groups.back().front()) != semantic_key(stroke)) groups.emplace_back();
        groups.back().push_back(stroke);
    }
    std::optional<Point> previous;
    for (std::size_t group_index = 0; group_index < groups.size(); ++group_index) {
        auto group = groups[group_index];
        if (std::any_of(group.begin(), group.end(), [](const Stroke& stroke) { return stroke.preserve_order; })) {
            result.strokes.insert(result.strokes.end(), group.begin(), group.end());
            if (!group.empty() && !group.back().points.empty()) previous = group.back().points.back();
            continue;
        }
        const auto next = group_index + 1 < groups.size() ? endpoints(groups[group_index + 1]) : std::vector<Point>{};
        while (!group.empty()) {
            std::size_t selected{};
            Stroke candidate = orient(group.front(), previous, group.size() == 1 ? next : std::vector<Point>{});
            double best = previous && !candidate.points.empty() ? distance(*previous, candidate.points.front()) : 0.0;
            for (std::size_t index = 1; index < group.size(); ++index) {
                Stroke alternative = orient(group[index], previous, group.size() == 1 ? next : std::vector<Point>{});
                const double cost = previous && !alternative.points.empty() ? distance(*previous, alternative.points.front()) : 0.0;
                if (cost < best) { selected = index; candidate = std::move(alternative); best = cost; }
            }
            group.erase(group.begin() + static_cast<std::ptrdiff_t>(selected));
            result.strokes.push_back(std::move(candidate));
            if (!result.strokes.back().points.empty()) previous = result.strokes.back().points.back();
        }
    }
    if (options.enable_safe_retrace) {
        std::vector<Stroke> merged;
        std::size_t repeats{};
        for (const auto& stroke : result.strokes) {
            if (!merged.empty()) {
                if (const auto candidate = merge_retrace(merged.back(), stroke, options, repeats)) {
                    merged.back() = candidate->first;
                    local_report.retrace_distance.value += candidate->second;
                    ++local_report.retrace_merges;
                    ++repeats;
                    continue;
                }
            }
            merged.push_back(stroke);
        }
        result.strokes = std::move(merged);
    }
    for (std::size_t index = 0; index < result.strokes.size(); ++index) result.strokes[index].id = index;
    if (report) *report = local_report;
    return result;
}

}  // namespace plotter::doc
