#pragma once

#include "plotter/doc/path_validation.hpp"

#include <string>
#include <variant>

namespace plotter::doc {

// Reflow only translates already-materialized source geometry to the target
// content origin. Text rewrapping belongs to layout and is intentionally not
// inferred from PathDocument strokes.
enum class SourcePageTransformMode { automatic, reflow, hybrid, preserve, contain };

struct SourcePageTransformOptions final {
    SourcePageTransformMode mode{SourcePageTransformMode::contain};
    Millimetres source_page_width{}, source_page_height{};
    Rect source_content{};
    Millimetres target_page_width{}, target_page_height{};
    Rect target_content{};
    double max_upscale{1.10};
    bool require_source_content_bounds{true};
};

struct SourcePageTransformError final { std::string code, message; };
struct TransformedSourcePage final { PageTransform transform; PathDocument paths; };
using SourcePageTransformResult = std::variant<TransformedSourcePage, SourcePageTransformError>;

[[nodiscard]] SourcePageTransformResult transform_source_page_paths(
    const PathDocument& source, const SourcePageTransformOptions& options);

}  // namespace plotter::doc
