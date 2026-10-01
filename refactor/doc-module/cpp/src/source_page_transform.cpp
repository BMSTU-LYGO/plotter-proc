#include "plotter/doc/source_page_transform.hpp"

#include <algorithm>

#include <cmath>
#include <iomanip>
#include <sstream>
#include <utility>

namespace plotter::doc {
namespace {

[[nodiscard]] SourcePageTransformError error(std::string code, std::string message) {
    return {std::move(code), std::move(message)};
}

[[nodiscard]] bool finite_positive(Millimetres value) {
    return std::isfinite(value.value) && value.value > 0.0;
}

[[nodiscard]] bool finite_rect(const Rect& rect) {
    return std::isfinite(rect.x.value) && std::isfinite(rect.y.value) &&
           finite_positive(rect.width) && finite_positive(rect.height);
}

[[nodiscard]] bool contains(const Rect& outer, Point point) {
    return point.x.value >= outer.x.value && point.x.value <= outer.right().value &&
           point.y.value >= outer.y.value && point.y.value <= outer.bottom().value;
}

[[nodiscard]] bool contains_page(Millimetres width, Millimetres height, const Rect& rect) {
    return rect.x.value >= 0.0 && rect.y.value >= 0.0 && rect.right().value <= width.value &&
           rect.bottom().value <= height.value;
}

[[nodiscard]] const char* mode_name(SourcePageTransformMode mode) {
    switch (mode) {
        case SourcePageTransformMode::reflow: return "reflow";
        case SourcePageTransformMode::preserve: return "preserve";
        case SourcePageTransformMode::contain: return "contain";
    }
    return "unknown";
}

[[nodiscard]] std::string number(double value) {
    std::ostringstream output;
    output << std::setprecision(12) << value;
    return output.str();
}

}  // namespace

SourcePageTransformResult transform_source_page_paths(
    const PathDocument& source, const SourcePageTransformOptions& options) {
    if (!finite_positive(options.source_page_width) || !finite_positive(options.source_page_height) ||
        !finite_positive(options.target_page_width) || !finite_positive(options.target_page_height) ||
        !finite_rect(options.source_content) || !finite_rect(options.target_content) ||
        !std::isfinite(options.max_upscale) || options.max_upscale <= 0.0)
        return error("invalid_page_transform", "source and target pages, content rectangles, and max_upscale must be finite and positive");
    if (!contains_page(options.source_page_width, options.source_page_height, options.source_content) ||
        !contains_page(options.target_page_width, options.target_page_height, options.target_content))
        return error("content_outside_page", "source and target content rectangles must be inside their pages");
    if (std::abs(source.page_width.value - options.source_page_width.value) > 1e-9 ||
        std::abs(source.page_height.value - options.source_page_height.value) > 1e-9)
        return error("source_page_mismatch", "source PathDocument dimensions must match source page dimensions");
    PathValidationOptions source_validation;
    if (const auto issues = validate_path_document(source, source_validation); !issues.empty())
        return error("invalid_source_paths", issues.front().code + ": " + issues.front().message);
    if (options.require_source_content_bounds) {
        for (const Stroke& stroke : source.strokes) for (const Point point : stroke.points)
            if (!contains(options.source_content, point))
                return error("source_path_outside_content", "source stroke " + std::to_string(stroke.id) + " leaves source content bounds");
    }

    PageTransform transform;
    transform.source_page_width = options.source_page_width;
    transform.source_page_height = options.source_page_height;
    transform.source_content = options.source_content;
    transform.target_content = options.target_content;
    switch (options.mode) {
        case SourcePageTransformMode::reflow:
            if (options.source_content.width.value > options.target_content.width.value ||
                options.source_content.height.value > options.target_content.height.value)
                return error("reflow_geometry_does_not_fit", "reflow cannot safely place materialized source geometry larger than target content");
            transform.scale = 1.0;
            transform.offset_x = {options.target_content.x.value - options.source_content.x.value};
            transform.offset_y = {options.target_content.y.value - options.source_content.y.value};
            break;
        case SourcePageTransformMode::preserve:
            transform.scale = 1.0;
            transform.offset_x = {};
            transform.offset_y = {};
            break;
        case SourcePageTransformMode::contain: {
            const double scale_x = options.target_content.width.value / options.source_content.width.value;
            const double scale_y = options.target_content.height.value / options.source_content.height.value;
            transform.scale = std::min({scale_x, scale_y, options.max_upscale});
            const double mapped_width = options.source_content.width.value * transform.scale;
            const double mapped_height = options.source_content.height.value * transform.scale;
            transform.offset_x = {options.target_content.x.value + (options.target_content.width.value - mapped_width) / 2.0 - options.source_content.x.value * transform.scale};
            transform.offset_y = {options.target_content.y.value + (options.target_content.height.value - mapped_height) / 2.0 - options.source_content.y.value * transform.scale};
            break;
        }
    }

    PathDocument target = source;
    target.page_width = options.target_page_width;
    target.page_height = options.target_page_height;
    for (Stroke& stroke : target.strokes) for (Point& point : stroke.points) {
        point.x.value = transform.offset_x.value + point.x.value * transform.scale;
        point.y.value = transform.offset_y.value + point.y.value * transform.scale;
    }
    PathValidationOptions target_validation;
    if (const auto issues = validate_path_document(target, target_validation); !issues.empty())
        return error("transformed_path_unsafe", issues.front().code + ": " + issues.front().message);
    target.metadata.emplace_back("source_page_transform", mode_name(options.mode));
    target.metadata.emplace_back("source_page_transform_scale", number(transform.scale));
    target.metadata.emplace_back("source_page_transform_offset_x_mm", number(transform.offset_x.value));
    target.metadata.emplace_back("source_page_transform_offset_y_mm", number(transform.offset_y.value));
    return TransformedSourcePage{transform, std::move(target)};
}

}  // namespace plotter::doc
