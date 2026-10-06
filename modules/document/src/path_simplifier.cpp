#include "plotter/doc/path_simplifier.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <utility>
#include <vector>

namespace plotter::doc {
namespace {

double squared_distance(const Point& left, const Point& right) {
    const double dx = right.x.value - left.x.value;
    const double dy = right.y.value - left.y.value;
    return dx * dx + dy * dy;
}

double point_segment_distance(const Point& point, const Point& start, const Point& end) {
    const double dx = end.x.value - start.x.value;
    const double dy = end.y.value - start.y.value;
    const double length_squared = dx * dx + dy * dy;
    if (length_squared == 0.0) return std::sqrt(squared_distance(point, start));
    const double t = std::clamp(((point.x.value - start.x.value) * dx +
                                 (point.y.value - start.y.value) * dy) / length_squared, 0.0, 1.0);
    return std::hypot(point.x.value - (start.x.value + t * dx),
                      point.y.value - (start.y.value + t * dy));
}

std::vector<Point> dedupe(const std::vector<Point>& points, double epsilon) {
    if (points.empty()) return {};
    std::vector<Point> result{points.front()};
    const double epsilon_squared = epsilon * epsilon;
    for (std::size_t index = 1; index < points.size(); ++index) {
        if (squared_distance(result.back(), points[index]) >= epsilon_squared) result.push_back(points[index]);
    }
    if (result.size() == 1 && points.size() > 1) result.push_back(points.back());
    return result;
}

std::pair<std::vector<Point>, double> rdp(const std::vector<Point>& points, double epsilon) {
    if (points.size() <= 2 || epsilon == 0.0) return {points, 0.0};
    std::vector<bool> keep(points.size());
    keep.front() = keep.back() = true;
    double observed{};
    std::vector<std::pair<std::size_t, std::size_t>> pending{{0, points.size() - 1}};
    while (!pending.empty()) {
        const auto [first, last] = pending.back();
        pending.pop_back();
        double maximum{};
        std::size_t maximum_index = first;
        for (std::size_t index = first + 1; index < last; ++index) {
            const double candidate = point_segment_distance(points[index], points[first], points[last]);
            if (candidate > maximum) { maximum = candidate; maximum_index = index; }
        }
        if (maximum <= epsilon) { observed = std::max(observed, maximum); continue; }
        keep[maximum_index] = true;
        pending.emplace_back(first, maximum_index);
        pending.emplace_back(maximum_index, last);
    }
    std::vector<Point> result;
    for (std::size_t index = 0; index < points.size(); ++index) if (keep[index]) result.push_back(points[index]);
    return {std::move(result), observed};
}

std::pair<std::vector<Point>, double> simplify_points(const Stroke& stroke, double duplicate_epsilon,
                                                       double max_deviation) {
    const auto source = dedupe(stroke.points, duplicate_epsilon);
    if (!stroke.closed) return rdp(source, max_deviation);
    if (source.size() < 3) return {source, 0.0};
    std::vector<Point> ring = source;
    if (squared_distance(ring.front(), ring.back()) == 0.0) ring.pop_back();
    if (ring.size() < 3) return {source, 0.0};
    ring.push_back(ring.front());
    auto [reduced, observed] = rdp(ring, max_deviation);
    if (!reduced.empty() && squared_distance(reduced.front(), reduced.back()) == 0.0) reduced.pop_back();
    if (reduced.size() < 3) return {source, 0.0};
    return {std::move(reduced), observed};
}

void require_tolerance(double value) {
    if (value < 0.0 || !std::isfinite(value)) throw std::invalid_argument("path simplification tolerance must be finite and non-negative");
}

}  // namespace

PathDocument simplify_path_document(const PathDocument& document, const PathSimplificationOptions& options,
                                    PathSimplificationReport* report) {
    require_tolerance(options.duplicate_epsilon.value);
    require_tolerance(options.min_segment_length.value);
    require_tolerance(options.max_deviation.value);
    PathDocument result = document;
    PathSimplificationReport local;
    for (auto& stroke : result.strokes) {
        local.points_before += stroke.points.size();
        // RDP owns the geometric error budget; min_segment_length intentionally
        // only tightens near-duplicate removal and cannot remove a visible corner.
        const double dedupe_epsilon = std::min(options.duplicate_epsilon.value, options.min_segment_length.value);
        auto [points, observed] = simplify_points(stroke, dedupe_epsilon, options.max_deviation.value);
        stroke.points = std::move(points);
        local.points_after += stroke.points.size();
        local.max_observed_deviation.value = std::max(local.max_observed_deviation.value, observed);
    }
    if (report) *report = local;
    return result;
}

}  // namespace plotter::doc
