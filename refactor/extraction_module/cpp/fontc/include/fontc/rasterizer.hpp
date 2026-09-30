#pragma once

#include "fontc/font_face.hpp"

#include <cstdint>
#include <vector>

namespace fontc {

struct RasterGlyph {
    std::uint32_t codepoint;
    std::uint32_t glyph_index;
    int advance_font_units;
    int width;
    int height;
    int origin_x;
    int origin_y;
    float pixels_per_font_unit;
    std::vector<std::uint8_t> grayscale;
};

// Raster coordinates map back to font units as:
// x_fu = (x_px - origin_x) / pixels_per_font_unit
// y_fu = (origin_y - y_px) / pixels_per_font_unit
[[nodiscard]] RasterGlyph rasterize_glyph(
    FontFace& font,
    std::uint32_t codepoint,
    int resolution = 1024
);

}  // namespace fontc
