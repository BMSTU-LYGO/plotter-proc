#pragma once

#include "plotter/doc/font_registry.hpp"
#include "plotter/doc/layout.hpp"

#include <optional>
#include <cstdint>
#include <string>
#include <vector>

namespace plotter::doc {

enum class TextAlignment { left, center, right, justify };

struct LayoutTextStyle final {
    std::string font_id;
    Points font_size{12.0};
    Millimetres letter_spacing{};
    Millimetres word_spacing{};
};
struct LayoutTextRun final { std::string utf8; LayoutTextStyle style{}; };
struct LayoutParagraph final {
    std::vector<LayoutTextRun> runs;
    TextAlignment alignment{TextAlignment::left};
    Millimetres space_before{}, space_after{};
    std::optional<Millimetres> line_height;
    Millimetres first_line_indent{}, hanging_indent{}, left_indent{}, right_indent{};
    std::optional<double> line_spacing;
    std::vector<TabStop> tab_stops;
    bool page_break_before{};
    std::optional<std::string> source_element_id;
};
struct TextLayoutOptions final {
    Millimetres page_width{210.0}, page_height{297.0};
    Millimetres margin_left{15.0}, margin_top{15.0}, margin_right{15.0}, margin_bottom{15.0};
    // Reserved at the bottom of every page; footer drawing is a later stage.
    Millimetres footer_reserve{};
};

class TextLayoutEngine final {
public:
    explicit TextLayoutEngine(const FontRegistry& fonts) : fonts_(fonts) {}
    [[nodiscard]] LayoutDocument layout(const std::vector<LayoutParagraph>& paragraphs,
                                        const TextLayoutOptions& options) const;
private:
    const FontRegistry& fonts_;
};

}  // namespace plotter::doc
