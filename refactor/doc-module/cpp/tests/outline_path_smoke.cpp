#include "plotter/doc/outline_path_builder.hpp"

#include <cassert>
#include <filesystem>
#include <stdexcept>

int main() {
    const auto font = std::filesystem::current_path() / "assets" / "1.ttf";
    if (!std::filesystem::is_regular_file(font)) throw std::runtime_error("outline smoke font is missing");
    plotter::doc::LayoutPage page; page.page_index = 3; page.source_element_ids = {"source-text"};
    plotter::doc::PositionedGlyph glyph; glyph.character = "A"; glyph.codepoint = 'A'; glyph.x = {10}; glyph.baseline_y = {20}; glyph.scale_mm_per_font_unit = 0.01; glyph.glyph_index = 4; glyph.word_index = 1; glyph.font_sha256 = "font-hash";
    page.glyphs = {glyph};
    const auto paths = plotter::doc::OutlinePathBuilder(font).build(page, {210}, {297});
    assert(!paths.strokes.empty());
    for (const auto& stroke : paths.strokes) { assert(stroke.closed && stroke.points.size() >= 3U); assert(stroke.element_id == "source-text" && stroke.source_page_index == 3 && stroke.source_path == font.string()); assert(stroke.segment_types == std::vector<std::string>{"outline-glyph"}); }
}
