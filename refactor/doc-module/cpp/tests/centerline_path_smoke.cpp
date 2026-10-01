#include "plotter/doc/centerline_path_builder.hpp"

#include "fontc/pfc.hpp"

#include <filesystem>
#include <stdexcept>

namespace { void require(bool value, const char* message) { if (!value) throw std::runtime_error(message); } }

int main() {
    const auto path = std::filesystem::temp_directory_path() / "plotter-centerline-path-smoke.pfc";
    fontc::CompiledFont font;
    font.metrics = {1000, 800, -200, 0};
    font.glyphs = {
        {'?', 500, {}},
        {'A', 600, {fontc::CompiledStroke{{{0, 0}, {100, 100}}}}},
        {'1', 500, {fontc::CompiledStroke{{{10, 0}, {10, 100}}}}},
    };
    fontc::write_pfc(path, font);
    plotter::doc::FontRegistry fonts;
    fonts.register_pfc({"main", "font-hash", path});
    plotter::doc::LayoutPage page;
    page.page_index = 4;
    page.source_element_ids = {"source-text"};
    plotter::doc::PositionedGlyph letter;
    letter.character = "A"; letter.codepoint = 'A'; letter.x = {10}; letter.baseline_y = {20};
    letter.scale_mm_per_font_unit = 0.01; letter.glyph_index = 7; letter.word_index = 3;
    letter.font_id = "main"; letter.font_sha256 = "font-hash";
    plotter::doc::PositionedGlyph number;
    number.character = "1"; number.codepoint = '1'; number.x = {30}; number.baseline_y = {40};
    number.scale_mm_per_font_unit = 0.01; number.glyph_index = 8; number.word_index = -1;
    number.font_id = "main"; number.font_sha256 = "font-hash"; number.text_role = "page-number";
    page.glyphs = {letter, number};
    const auto paths = plotter::doc::CenterlinePathBuilder(fonts).build(page, {210}, {297});
    require(paths.strokes.size() == 2, "both text and page-number centerlines must be materialized");
    const auto& first = paths.strokes[0];
    require(first.points.size() == 2 && first.points[0].x.value == 10 && first.points[0].y.value == 20 && first.points[1].x.value == 11 && first.points[1].y.value == 19, "font units must be transformed to page millimetres with inverted Y");
    require(first.glyph_index == 7 && first.word_index == 3 && first.character == "A" && first.font_sha256 == "font-hash", "glyph provenance must be preserved");
    require(first.element_id == "source-text" && first.source_page_index == 4, "source provenance must be preserved when available");
    require(paths.strokes[1].element_type == "page-number" && paths.strokes[1].font_role == "page-number", "page-number provenance must be retained");
    std::filesystem::remove(path);
}
