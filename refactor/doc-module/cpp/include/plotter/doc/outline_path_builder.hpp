#pragma once

#include "plotter/doc/layout.hpp"
#include "plotter/doc/path.hpp"

#include <cstddef>
#include <filesystem>

namespace plotter::doc {

struct OutlinePathOptions final {
    // Maximum deviation of a flattened curve from its chord in page millimetres.
    double flattening_tolerance_mm{0.08};
    std::size_t maximum_points_per_contour{8192};
};

// Reads glyph contours from a TrueType/OpenType font with FreeType. The layout
// already owns shaping and placement; this class only converts its positioned
// glyphs into closed page-space outline paths.
class OutlinePathBuilder final {
public:
    explicit OutlinePathBuilder(std::filesystem::path font_path, OutlinePathOptions options = {});

    [[nodiscard]] PathDocument build(const LayoutPage& page, Millimetres page_width,
                                     Millimetres page_height) const;

private:
    std::filesystem::path font_path_;
    OutlinePathOptions options_;
};

}  // namespace plotter::doc
