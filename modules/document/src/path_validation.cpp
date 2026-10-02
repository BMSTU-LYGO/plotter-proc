#include "plotter/doc/path_validation.hpp"

#include <algorithm>
#include <cmath>

namespace plotter::doc {
namespace {

bool finite(Point point) {
    return std::isfinite(point.x.value) && std::isfinite(point.y.value);
}

bool inside_page(Point point, const PathDocument& document) {
    return point.x.value >= 0.0 && point.y.value >= 0.0 &&
           point.x.value <= document.page_width.value &&
           point.y.value <= document.page_height.value;
}

double distance_to_segment(Point start, Point end, Point center) {
    const double dx = end.x.value - start.x.value;
    const double dy = end.y.value - start.y.value;
    const double squared = dx * dx + dy * dy;
    if (squared == 0.0) {
        return std::hypot(start.x.value - center.x.value, start.y.value - center.y.value);
    }
    const double projection = std::clamp(
        ((center.x.value - start.x.value) * dx +
         (center.y.value - start.y.value) * dy) / squared,
        0.0, 1.0);
    return std::hypot(start.x.value + projection * dx - center.x.value,
                      start.y.value + projection * dy - center.y.value);
}

bool intersects_keep_out(Point start, Point end, const CircularKeepOut& zone) {
    return distance_to_segment(start, end, zone.center) <=
           zone.radius.value + zone.clearance.value + 1e-9;
}

}  // namespace

std::vector<PathValidationIssue> validate_path_document(
    const PathDocument& document, const PathValidationOptions& options) {
    std::vector<PathValidationIssue> issues;
    if (!std::isfinite(document.page_width.value) ||
        !std::isfinite(document.page_height.value) ||
        document.page_width.value <= 0.0 || document.page_height.value <= 0.0) {
        issues.push_back({0, "invalid_page_size", "Page dimensions must be finite and positive"});
        return issues;
    }
    if (options.require_nonempty && document.strokes.empty()) {
        issues.push_back({0, "empty_document", "Path document has no strokes"});
    }
    for (const auto& zone : options.keep_outs) {
        if (!finite(zone.center) || !std::isfinite(zone.radius.value) ||
            !std::isfinite(zone.clearance.value) || zone.radius.value <= 0.0 ||
            zone.clearance.value < 0.0) {
            issues.push_back({0, "invalid_keep_out", "Keep-out values must be finite with positive radius"});
            return issues;
        }
    }
    for (std::size_t index = 0; index < document.strokes.size(); ++index) {
        const auto& stroke = document.strokes[index];
        if (stroke.points.size() < 2) {
            issues.push_back({index, "short_stroke", "Stroke needs at least two points"});
            continue;
        }
        if (stroke.points.size() > options.max_points_per_stroke) {
            issues.push_back({index, "too_many_points", "Stroke exceeds point limit"});
        }
        bool invalid = false;
        bool outside = false;
        for (const Point point : stroke.points) {
            invalid |= !finite(point);
            outside |= finite(point) && !inside_page(point, document);
        }
        if (invalid) {
            issues.push_back({index, "invalid_coordinate", "Stroke has a non-finite point"});
            continue;
        }
        if (outside && options.require_page_bounds) {
            issues.push_back({index, "outside_page", "Stroke leaves page bounds"});
        }
        bool has_length = false;
        bool in_keep_out = false;
        for (std::size_t point = 1; point < stroke.points.size(); ++point) {
            const Point start = stroke.points[point - 1];
            const Point end = stroke.points[point];
            has_length |= start.x.value != end.x.value || start.y.value != end.y.value;
            for (const auto& zone : options.keep_outs) {
                in_keep_out |= intersects_keep_out(start, end, zone);
            }
        }
        if (stroke.closed) {
            const Point start = stroke.points.back();
            const Point end = stroke.points.front();
            has_length |= start.x.value != end.x.value || start.y.value != end.y.value;
            for (const auto& zone : options.keep_outs) {
                in_keep_out |= intersects_keep_out(start, end, zone);
            }
        }
        if (!has_length) {
            issues.push_back({index, "degenerate_stroke", "Stroke has no drawing length"});
        }
        if (in_keep_out) {
            issues.push_back({index, "keep_out", "Draw path intersects a keep-out zone"});
        }
    }
    return issues;
}

}  // namespace plotter::doc
