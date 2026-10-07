#include "plotter/doc/centerline_path_builder.hpp"

#include "fontc/pfc.hpp"

#include <algorithm>
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
        {'B', 600, {fontc::CompiledStroke{{{0, 0}, {100, 100}}}, fontc::CompiledStroke{{{50, 100}, {50, 150}}}}},
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
    plotter::doc::LayoutPage joined_page;
    joined_page.source_element_ids = {"source-text"};
    auto first_letter = letter; first_letter.glyph_index = 1; first_letter.word_index = 0;
    auto second_letter = letter; second_letter.character = "B"; second_letter.codepoint = 'B';
    second_letter.x = {11.5}; second_letter.glyph_index = 2; second_letter.word_index = 0;
    auto next_word = letter; next_word.x = {40}; next_word.glyph_index = 3; next_word.word_index = 1;
    joined_page.glyphs = {first_letter, second_letter, next_word};
    const auto joined = plotter::doc::CenterlinePathBuilder(fonts).build(joined_page, {210}, {297}, true);
    require(joined.strokes.size() == 3, "word body joins while disconnected contour stays separate");
    require(joined.strokes.front().source_characters == "AB" &&
            joined.strokes.front().source_glyph_indices == std::vector<std::int64_t>{1, 2},
            "joined word must retain glyph provenance");
    require(joined.strokes.front().word_index == 0 && joined.strokes.back().word_index == 1,
            "joining must stop at the word boundary");
    require(joined.strokes[1].semantic_role == "secondary", "disconnected contour follows the word body");

    plotter::doc::Stroke body;
    body.id = 1; body.points = {{{1}, {5}}, {{2}, {5}}};
    body.glyph_index = 1; body.character = "м"; body.font_sha256 = "font-hash";
    auto adjacent = body;
    adjacent.id = 2; adjacent.glyph_index = 2;
    adjacent.points = {{{2.5}, {5}}, {{3.5}, {5}}};
    const auto continuous = plotter::doc::build_word_route({body, adjacent});
    require(continuous.moves.size() == 1 && continuous.moves[0].stroke.points.size() == 4,
            "safe adjacent Cyrillic strokes should form one draw group");
    std::reverse(adjacent.points.begin(), adjacent.points.end());
    const auto reversible = plotter::doc::build_word_route({body, adjacent});
    require(reversible.moves.size() == 1 &&
            reversible.moves[0].stroke.points.back().x.value == 3.5,
            "reversing a stroke must recover a safe continuous route");
    adjacent.points = {{{5}, {5}}, {{6}, {5}}};
    const auto separated = plotter::doc::build_word_route({body, adjacent});
    require(separated.moves.size() == 3 && separated.moves[1].kind == plotter::doc::WordMoveKind::travel,
            "long whitespace must require a pen-up transition");

    auto dotted = body;
    dotted.character = "ё"; dotted.id = 3; dotted.glyph_index = 3;
    dotted.points = {{{7}, {5}}, {{8}, {5}}};
    auto dot_a = dotted; dot_a.id = 4; dot_a.points = {{{7.2}, {4}}, {{7.3}, {4}}};
    auto dot_b = dotted; dot_b.id = 5; dot_b.points = {{{7.7}, {4}}, {{7.8}, {4}}};
    const auto diacritic = plotter::doc::build_word_route({dotted, dot_a, dot_b});
    require(diacritic.moves.size() == 5 &&
            diacritic.moves[2].stroke.semantic_role == "auxiliary" &&
            diacritic.moves[4].stroke.semantic_role == "auxiliary",
            "both dots of ё must remain separate auxiliary passes");
    std::filesystem::remove(path);
}
