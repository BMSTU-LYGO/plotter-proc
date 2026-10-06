#include "fontc/rasterizer.hpp"

#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <iostream>

namespace {

void require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

}  // namespace

int main(int argc, char** argv) {
    require(argc == 2, "expected path to test font");
    fontc::FontFace font(argv[1]);

    const fontc::RasterGlyph raster = fontc::rasterize_glyph(font, U'Ж', 512);
    require(raster.codepoint == U'Ж', "codepoint was not preserved");
    require(raster.glyph_index != 0, "glyph index must be mapped through Unicode cmap");
    require(raster.advance_font_units > 0, "advance must stay in font units");
    require(raster.width > 0 && raster.height > 0, "raster must have positive dimensions");
    require(
        raster.grayscale.size() ==
            static_cast<std::size_t>(raster.width) * static_cast<std::size_t>(raster.height),
        "raster buffer size mismatch"
    );
    require(
        *std::max_element(raster.grayscale.begin(), raster.grayscale.end()) > 0,
        "visible glyph raster is empty"
    );
    const float expected_scale = 512.0F / static_cast<float>(font.metrics().units_per_em);
    require(
        std::abs(raster.pixels_per_font_unit - expected_scale) < 0.0001F,
        "pixel/font-unit scale mismatch"
    );

    const fontc::RasterGlyph low_resolution = fontc::rasterize_glyph(font, U'Ж', 256);
    require(low_resolution.width < raster.width, "resolution must affect raster dimensions");

    bool missing_rejected = false;
    try {
        (void)fontc::rasterize_glyph(font, 0x10FFFFU, 512);
    } catch (const fontc::FreeTypeError&) {
        missing_rejected = true;
    }
    require(missing_rejected, "missing glyph must be rejected");
}
