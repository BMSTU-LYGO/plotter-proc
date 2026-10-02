#pragma once

#include "plotter/doc/import.hpp"

#include <cstddef>
#include <filesystem>
#include <optional>
#include <string>
#include <variant>

namespace plotter::doc {

// The adapter intentionally accepts SVG line-art only: svg/g containers,
// basic primitives, and M/m, L/l, H/h, V/v, C/c, Q/q, Z/z path commands.
// Paint servers, clipping, nested viewports and CSS are rejected because this
// small self-contained reader cannot preserve their geometry faithfully.
struct SvgImportOptions final {
    std::size_t max_file_bytes{2'000'000};
    std::size_t max_nodes{10'000};
    std::size_t max_points{100'000};
    std::size_t max_group_depth{64};
    std::size_t ellipse_segments{64};
    double curve_tolerance_mm{0.05};
    double min_segment_length_mm{0.001};
    std::size_t max_points_per_contour{5'000};
    std::size_t max_curve_recursion_depth{20};
};

struct SvgIntrinsicSize final { Millimetres width{}; Millimetres height{}; };
struct SvgAdapterError final { std::string message; };

using SvgIntrinsicSizeResult = std::variant<SvgIntrinsicSize, SvgAdapterError>;
using SvgDocumentResult = std::variant<Document, SvgAdapterError>;

[[nodiscard]] SvgIntrinsicSizeResult svg_intrinsic_size_mm(
    const std::filesystem::path& path,
    const SvgImportOptions& options = {});

[[nodiscard]] SvgDocumentResult read_svg_document(
    const std::filesystem::path& path,
    const SvgImportOptions& options = {});

}  // namespace plotter::doc
