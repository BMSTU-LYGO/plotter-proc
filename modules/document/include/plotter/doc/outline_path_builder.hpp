#pragma once

#include "plotter/doc/font_registry.hpp"
#include "plotter/doc/layout.hpp"
#include "plotter/doc/path.hpp"

#include <cstddef>
#include <filesystem>

namespace plotter::doc {

struct OutlinePathOptions final {
    double flattening_tolerance_mm{0.08};
    std::size_t maximum_points_per_contour{8192};
};

// Uses the font selected during layout when constructed with FontRegistry.
// The path constructor remains available for single-font callers.
class OutlinePathBuilder final {
public:
    explicit OutlinePathBuilder(std::filesystem::path font_path, OutlinePathOptions options = {});
    explicit OutlinePathBuilder(const FontRegistry& fonts, OutlinePathOptions options = {});

    [[nodiscard]] PathDocument build(const LayoutPage& page, Millimetres page_width,
                                     Millimetres page_height) const;

private:
    const FontRegistry* fonts_{};
    std::filesystem::path font_path_;
    OutlinePathOptions options_;
};

}  // namespace plotter::doc
