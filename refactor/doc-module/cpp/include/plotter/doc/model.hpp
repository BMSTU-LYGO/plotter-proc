#pragma once

#include "plotter/doc/geometry.hpp"

#include <cstdint>
#include <optional>
#include <string>
#include <variant>
#include <vector>

namespace plotter::doc {

struct TextStyle final {
    std::optional<std::string> underline;
    bool strike{};
    bool bold{};
    bool italic{};
    std::optional<Points> font_size;
    std::optional<std::string> baseline_shift;
};

struct TextRun final { std::string text; TextStyle style{}; std::optional<Rect> bounds; };
struct TabStop final { Millimetres position{}; std::string alignment{"left"}; };
struct Paragraph final {
    std::vector<TextRun> runs;
    std::optional<std::string> alignment;
    std::optional<Millimetres> first_line_indent, hanging_indent, left_indent, right_indent;
    std::optional<Millimetres> space_before, space_after;
    std::optional<double> line_spacing;
    std::vector<TabStop> tab_stops;
    std::optional<std::string> style_id, style_name, semantic_role;
    std::optional<Rect> bounds;
};

struct TextElement final { std::string id; std::uint32_t source_order{}, source_page{}; std::vector<Paragraph> paragraphs; std::optional<Rect> bounds; };
struct RasterImageElement final {
    std::string id; std::uint32_t source_order{}, source_page{}; std::string image_path;
    Pixels width{}, height{}; std::optional<Millimetres> displayed_width, displayed_height; std::optional<Rect> bounds;
    std::string anchor_type{"flow"}, wrap_mode{"inline"}, wrap_side{"both"};
    Millimetres distance_left{}, distance_right{}, distance_top{}, distance_bottom{};
    std::optional<std::string> relative_to_h, relative_to_v;
    bool behind_text{};
    std::int32_t z_order{};
    Degrees rotation{};
    Millimetres anchor_offset_x{}, anchor_offset_y{};
};
struct VectorPath final {
    std::vector<Point> points;
    bool closed{};
    std::optional<std::string> element_id, element_type, source_path, semantic_role, layout_group;
    std::optional<std::uint32_t> source_page;
    bool preserve_order{};
    std::int32_t z_order{};
};
struct VectorElement final { std::string id; std::uint32_t source_order{}, source_page{}; std::vector<VectorPath> paths; std::optional<Rect> bounds; std::string anchor_type{"absolute"}, wrap_mode{"none"}, wrap_side{"both"}; std::int32_t z_order{}; };
struct MathElement final {
    std::string id; std::uint32_t source_order{}, source_page{}; std::string expression, source_syntax; bool display_mode{}; std::optional<Rect> bounds;
    std::optional<std::string> visual_image_path; std::optional<double> visual_pixels_per_mm;
    std::vector<std::string> absorbed_element_ids; std::optional<double> detection_confidence;
};
struct LineElement final { std::string id; std::uint32_t source_order{}, source_page{}; Point start{}, end{}; std::optional<Millimetres> line_width; std::optional<std::string> dash_style; std::optional<Rect> bounds; std::string semantic_role{"line"}; std::optional<double> confidence; };
struct ArrowElement final { std::string id; std::uint32_t source_order{}, source_page{}; std::vector<Point> points; bool head_at_start{}, head_at_end{}; std::string head_style{"open"}; std::optional<Rect> bounds; std::optional<double> confidence; std::string start_head_style{"none"}, end_head_style{"none"}; std::optional<std::string> stroke_color, source_identity; std::optional<Millimetres> line_width; };
struct CellBorders final { bool top{true}, right{true}, bottom{true}, left{true}; };
struct TableCell final { std::uint32_t row{}, column{}, row_span{1}, column_span{1}; std::vector<Paragraph> paragraphs; std::optional<Millimetres> width, height; CellBorders borders{}; std::optional<std::string> vertical_alignment; };
struct TableElement final { std::string id; std::uint32_t source_order{}, source_page{}, rows{}, columns{}; std::vector<TableCell> cells; std::vector<Millimetres> column_widths; std::optional<Rect> bounds; std::uint32_t repeat_header_rows{}; std::string source_kind{"docx-table"}; std::optional<std::string> alignment; std::optional<Millimetres> left_indent, preferred_width; std::vector<std::optional<Millimetres>> row_heights; };

using SourceElement = std::variant<TextElement, RasterImageElement, VectorElement, MathElement, LineElement, ArrowElement, TableElement>;

// Reader adapters normalize source coordinates to millimetres. In particular,
// PDF points are converted at the adapter boundary before constructing a page.
struct SourcePage final { std::uint32_t source_page{}; std::optional<Millimetres> width, height; std::vector<SourceElement> elements; std::optional<Rect> content_bounds; };
struct DocumentMetadata final { std::string source_format{"unknown"}; std::optional<std::string> title; std::vector<std::pair<std::string, std::string>> properties; };
struct Document final { std::string source_path; std::vector<SourcePage> pages; std::vector<std::string> warnings; DocumentMetadata metadata{}; std::uint32_t schema_version{1}; };

}  // namespace plotter::doc
