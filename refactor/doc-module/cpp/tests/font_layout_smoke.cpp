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
    std::filesystem::remove(path);
}
