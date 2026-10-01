#pragma once

#include "plotter/doc/model.hpp"
#include "plotter/doc/path.hpp"

#include <cstdint>
#include <string>
#include <vector>

namespace plotter::doc {

struct PositionedGlyph final {
    std::string character, glyph_name;
    std::uint32_t codepoint{};
    Millimetres x{}, baseline_y{}, advance{};
    double scale_mm_per_font_unit{};
    std::uint32_t line_index{}, glyph_index{};
    std::int32_t word_index{-1}, cluster_index{};
    std::optional<std::string> font_id, font_sha256;
    FontUnits x_offset{}, y_offset{};
    std::string text_role{"letter"};
};
struct SourcePlacement final { std::uint32_t source_page{}; std::optional<Rect> source_bounds, target_bounds; std::string anchor, wrap_mode; std::int32_t z_order{}; };
struct AnchoredPlacement final { std::string element_id; std::uint32_t source_order{}; Rect target_rect{}; std::optional<Rect> mapped_rect; std::string wrap_mode, anchor_type; std::vector<std::string> warnings; bool active{}; };
struct TableFragment final { std::string table_id; std::uint32_t source_row_start{}, source_row_end{}; Rect bounds{}; };
struct LayoutPage final {
    std::uint32_t page_index{};
    std::vector<PositionedGlyph> glyphs;
    std::vector<Stroke> graphic_strokes;
    std::vector<std::string> source_element_ids, warnings;
    std::vector<SourcePlacement> placements;
    std::vector<Rect> line_boxes;
    std::vector<TableFragment> table_fragments;
    std::uint32_t line_count{};
    std::vector<std::pair<std::string, std::string>> metadata;
};
struct LayoutDocument final { std::vector<LayoutPage> pages; std::vector<std::string> warnings; std::vector<std::pair<std::string, std::string>> import_statistics, element_details, latex_statistics, layout_statistics; std::uint32_t schema_version{1}; };

}  // namespace plotter::doc
