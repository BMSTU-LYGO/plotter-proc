#include "plotter/doc/font_registry.hpp"
#include "plotter/doc/text_layout.hpp"

#include "fontc/pfc.hpp"

#include <filesystem>
#include <stdexcept>
#include <string>
#include <vector>

namespace {
void require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
}

int main() {
    const auto path = std::filesystem::temp_directory_path() / "plotter-font-layout-smoke.pfc";
    fontc::CompiledFont font;
    font.metrics = {1000, 800, -200, 0};
    font.glyphs = {{'?', 500, {}}, {'A', 600, {}}, {' ', 250, {}}};
    fontc::write_pfc(path, font);
    plotter::doc::FontRegistry registry;
    registry.register_pfc({"main", "test-hash", path});
    const auto fallback = registry.resolve("main", 0x0416U);
    require(fallback.glyph_codepoint == '?', "PFC fallback must be deterministic");
    plotter::doc::TextLayoutEngine engine(registry);
    plotter::doc::TextLayoutOptions options;
    options.page_width = {14}; options.page_height = {20};
    options.margin_left = {2}; options.margin_right = {2}; options.margin_top = {2}; options.margin_bottom = {2}; options.footer_reserve = {3};
    plotter::doc::LayoutParagraph paragraph;
    paragraph.runs = {{"A A A A A A A A A A A A", {"main", {12}, {0}, {0}}}};
    paragraph.alignment = plotter::doc::TextAlignment::justify;
    const auto result = engine.layout({paragraph}, options);
    require(result.pages.size() >= 2, "footer reserve must participate in pagination");
    require(!result.pages.front().glyphs.empty(), "glyphs must be positioned");
    require(result.pages.front().glyphs.front().font_id == "main", "font id must be carried into IR");
    plotter::doc::TextLayoutOptions word_options;
    word_options.page_width = {9}; word_options.page_height = {30};
    word_options.margin_left = {2}; word_options.margin_right = {2}; word_options.margin_top = {2}; word_options.margin_bottom = {2};
    plotter::doc::LayoutParagraph boundary;
    boundary.runs = {{"A A", {"main", {12}, {0}, {0}}}};
    boundary.source_element_id = "source-text";
    const auto word_result = engine.layout({boundary}, word_options);
    require(word_result.pages.front().glyphs.size() == 2, "spaces are deferred between words");
    const auto& left = word_result.pages.front().glyphs[0];
    const auto& right = word_result.pages.front().glyphs[1];
    require(left.line_index != right.line_index, "A A must wrap at a word boundary");
    require(right.x.value == word_options.margin_left.value, "wrapped word must begin at left margin");
    require(left.glyph_index < right.glyph_index && left.word_index < right.word_index, "glyph and word indices must be stable");
    require(word_result.pages.front().source_element_ids == std::vector<std::string>{"source-text"}, "source id must reach the layout page");
    plotter::doc::TextLayoutOptions rich_options;
    rich_options.page_width = {20}; rich_options.page_height = {60};
    rich_options.margin_left = {2}; rich_options.margin_right = {2}; rich_options.margin_top = {2}; rich_options.margin_bottom = {2};
    plotter::doc::LayoutParagraph rich;
    rich.runs = {{"A A A A A", {"main", {12}, {0}, {0}}}};
    rich.first_line_indent = {2}; rich.hanging_indent = {1}; rich.left_indent = {3}; rich.right_indent = {2};
    const auto indent_result = engine.layout({rich}, rich_options);
    const auto &indent_glyphs = indent_result.pages.front().glyphs;
    const auto following = std::find_if(indent_glyphs.begin(), indent_glyphs.end(), [&](const plotter::doc::PositionedGlyph &glyph) { return glyph.line_index != indent_glyphs.front().line_index; });
    require(following != indent_glyphs.end(), "indented paragraph must wrap onto a subsequent line");
    require(indent_glyphs.front().x.value == 6.0 && following->x.value == 5.0, "first-line, hanging, and left indents must set distinct line origins");
    plotter::doc::LayoutParagraph tabs;
    tabs.runs = {{std::string("A") + static_cast<char>(9) + "A", {"main", {12}, {0}, {0}}}};
    tabs.tab_stops = {{{8}, "left"}};
    const auto tab_result = engine.layout({tabs}, rich_options);
    require(tab_result.pages.front().glyphs.size() == 2 && tab_result.pages.front().glyphs[1].x.value == 10.0, "tab stop positions must be relative to the paragraph left edge");
    plotter::doc::LayoutParagraph spaced;
    spaced.runs = {{std::string("A") + static_cast<char>(10) + "A", {"main", {12}, {0}, {0}}}};
    spaced.line_spacing = 2.0;
    const auto spaced_result = engine.layout({spaced}, rich_options);
    const auto &boxes = spaced_result.pages.front().line_boxes;
    require(boxes.size() == 2 && boxes[1].y.value - boxes[0].y.value > 10.0, "line-spacing multiplier must control line advance");

    std::filesystem::remove(path);
}
