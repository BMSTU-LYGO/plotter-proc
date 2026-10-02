#include "plotter/doc/outline_path_builder.hpp"

#include <cassert>
#include <filesystem>
#include <stdexcept>
#include <string>
#include <vector>

int main() {
    const auto primary = std::filesystem::current_path() / "assets" / "1.ttf";
    const auto fallback = std::filesystem::current_path() / "assets" / "TimofeyHand-Regular.ttf";
    if (!std::filesystem::is_regular_file(primary) || !std::filesystem::is_regular_file(fallback)) throw std::runtime_error("outline smoke fonts are missing");
    plotter::doc::FontRegistry fonts;
    fonts.register_outline_font({"primary", "primary-hash", primary});
    fonts.register_outline_font({"fallback", "fallback-hash", fallback});
    plotter::doc::LayoutPage page; page.page_index = 3; page.source_element_ids = {"source-text"};
    plotter::doc::PositionedGlyph glyph;
    glyph.character = "A"; glyph.codepoint = 'A'; glyph.x = {10}; glyph.baseline_y = {20};
    glyph.scale_mm_per_font_unit = 0.01; glyph.glyph_index = 4; glyph.word_index = 1;
    glyph.font_id = "fallback"; glyph.font_sha256 = "fallback-hash"; glyph.bold = true; glyph.italic = true;
    page.glyphs = {glyph};
    const auto paths = plotter::doc::OutlinePathBuilder(fonts).build(page, {210}, {297});
    assert(!paths.strokes.empty());
    for (const auto& stroke : paths.strokes) {
        assert(stroke.closed && stroke.points.size() >= 3U);
        assert(stroke.element_id == "source-text" && stroke.source_page_index == 3);
        assert(stroke.source_path == fallback.string() && stroke.font_sha256 == "fallback-hash");
        assert(stroke.segment_types == std::vector<std::string>{"outline-glyph"});
    }
}
