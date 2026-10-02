#include "fontc/compiled_font.hpp"

#include <cstdlib>
#include <iostream>
#include <stdexcept>

int main() {
    try {
        fontc::CompiledGlyph glyph{U'A', 600, {{{{0, 0}, {300, 20}}}}};
        fontc::validate_compiled_glyph(glyph);
        if (fontc::point_storage_width(glyph) != fontc::PointStorageWidth::int16) throw std::runtime_error("int16 model");
        glyph.strokes[0].points[1].x = 40000;
        if (fontc::point_storage_width(glyph) != fontc::PointStorageWidth::int32) throw std::runtime_error("int32 fallback");
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return EXIT_FAILURE; }
    return EXIT_SUCCESS;
}
