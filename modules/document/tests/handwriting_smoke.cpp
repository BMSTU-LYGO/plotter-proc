#include "plotter/doc/handwriting.hpp"

#include <stdexcept>

namespace {
void require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
bool same_points(const std::vector<plotter::doc::Point>& left, const std::vector<plotter::doc::Point>& right) {
    if (left.size() != right.size()) return false;
    for (std::size_t index = 0; index < left.size(); ++index)
        if (left[index].x.value != right[index].x.value || left[index].y.value != right[index].y.value) return false;
    return true;
}
}

int main() {
    plotter::doc::PathDocument document;
    document.page_width = {30}; document.page_height = {20};
    plotter::doc::Stroke body;
    body.id = 7; body.points = {{{4}, {10}}, {{6}, {9}}}; body.glyph_index = 2; body.word_index = 1;
    body.element_id = "body-text"; body.element_type = "text"; body.font_role = "body"; body.source_characters = "a";
    plotter::doc::Stroke page_number;
    page_number.id = 8; page_number.points = {{{20}, {18}}, {{21}, {17}}}; page_number.glyph_index = 3; page_number.word_index = -1;
    page_number.element_id = "footer"; page_number.element_type = "page-number"; page_number.font_role = "page-number"; page_number.source_characters = "1";
    plotter::doc::Stroke graphic;
    graphic.id = 9; graphic.points = {{{25}, {2}}, {{26}, {3}}}; graphic.element_type = "vector";
    document.strokes = {body, page_number, graphic};
    plotter::doc::HandwritingOptions options;
    options.enabled = true; options.seed = 73; options.baseline_jitter = {0.08}; options.rotation = {1};
    options.glyph_scale_percent = 3; options.glyph_slant = 0.03; options.word_width_percent = 3;
    const auto first = plotter::doc::apply_handwriting(document, options);
    const auto second = plotter::doc::apply_handwriting(document, options);
    require(std::holds_alternative<plotter::doc::PathDocument>(first) && std::holds_alternative<plotter::doc::PathDocument>(second), "safe body handwriting must succeed");
    const auto& first_paths = std::get<plotter::doc::PathDocument>(first);
    const auto& second_paths = std::get<plotter::doc::PathDocument>(second);
    require(same_points(first_paths.strokes[0].points, second_paths.strokes[0].points), "same seed must be deterministic");
    require(!same_points(first_paths.strokes[0].points, document.strokes[0].points), "body glyph must vary");
    require(same_points(first_paths.strokes[1].points, document.strokes[1].points) && same_points(first_paths.strokes[2].points, document.strokes[2].points), "page numbers and nontext must remain unchanged");
    require(first_paths.strokes[0].id == 7 && first_paths.strokes[0].glyph_index == 2 && first_paths.strokes[0].word_index == 1 && first_paths.strokes[0].element_id == "body-text", "provenance and order must be preserved");
    options.keep_outs = {{{{5}, {9.5}}, {1}, {0}}};
    const auto protected_result = plotter::doc::apply_handwriting(document, options);
    require(std::holds_alternative<plotter::doc::HandwritingError>(protected_result), "pre-existing keep-out collision must be reported explicitly");
}
