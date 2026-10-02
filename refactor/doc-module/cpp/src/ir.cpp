#include "plotter/doc/ir.hpp"

#include <algorithm>
#include <cmath>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <utility>

namespace plotter::doc {
namespace {
class Json final {
public:
    void raw(std::string_view value) { out_ += value; }
    void key(std::string_view value) { string(value); out_ += ':'; }
    void string(std::string_view value) {
        out_ += '"';
        for (const unsigned char c : value) {
            switch (c) { case '"': out_ += "\\\""; break; case '\\': out_ += "\\\\"; break; case '\b': out_ += "\\b"; break; case '\f': out_ += "\\f"; break; case '\n': out_ += "\\n"; break; case '\r': out_ += "\\r"; break; case '\t': out_ += "\\t"; break; default: if (c < 0x20U) { static constexpr char hex[] = "0123456789abcdef"; out_ += "\\u00"; out_ += hex[c >> 4U]; out_ += hex[c & 15U]; } else { out_ += static_cast<char>(c); } }
        }
        out_ += '"';
    }
    void number(double value) {
        if (!std::isfinite(value)) throw std::invalid_argument("stage IR cannot encode non-finite number");
        if (value == 0.0) value = 0.0;
        std::ostringstream stream; stream.imbue(std::locale::classic()); stream << std::setprecision(std::numeric_limits<double>::max_digits10) << value; out_ += stream.str();
    }
    void integer(std::int64_t value) { out_ += std::to_string(value); }
    [[nodiscard]] std::string take() && { return std::move(out_); }
private: std::string out_;
};
template <typename T, typename Writer> void array(Json& json, const std::vector<T>& values, Writer writer) { json.raw("["); bool first = true; for (const auto& value : values) { if (!first) json.raw(","); first = false; writer(value); } json.raw("]"); }
void nullable(Json& j, const std::optional<std::string>& value) { if (value) j.string(*value); else j.raw("null"); }
void nullable(Json& j, const std::optional<Millimetres>& value) { if (value) j.number(value->value); else j.raw("null"); }
void rect(Json& j, const Rect& r) { j.raw("{"); j.key("height_mm"); j.number(r.height.value); j.raw(","); j.key("width_mm"); j.number(r.width.value); j.raw(","); j.key("x_mm"); j.number(r.x.value); j.raw(","); j.key("y_mm"); j.number(r.y.value); j.raw("}"); }
void nullable_rect(Json& j, const std::optional<Rect>& r) { if (r) rect(j, *r); else j.raw("null"); }
void strings(Json& j, const std::vector<std::string>& values) { array(j, values, [&j](const auto& value) { j.string(value); }); }
void metadata(Json& j, const std::vector<std::pair<std::string, std::string>>& values) { auto ordered = values; std::sort(ordered.begin(), ordered.end()); j.raw("{"); bool first = true; for (const auto& [key, value] : ordered) { if (!first) j.raw(","); first = false; j.key(key); j.string(value); } j.raw("}"); }
void metadata_pairs(Json& j, const std::vector<std::pair<std::string, std::string>>& values) { array(j, values, [&j](const auto& item) { j.raw("["); j.string(item.first); j.raw(","); j.string(item.second); j.raw("]"); }); }
void point(Json& j, const Point& p) { j.raw("["); j.number(p.x.value); j.raw(","); j.number(p.y.value); j.raw("]"); }
void optional_string(Json& j, const std::optional<std::string>& value) { nullable(j, value); }
void optional_integer(Json& j, const std::optional<std::int64_t>& value) { if (value) j.integer(*value); else j.raw("null"); }
void integers(Json& j, const std::vector<std::int64_t>& values) { array(j, values, [&j](auto value) { j.integer(value); }); }
void stroke(Json& j, const Stroke& s) {
    j.raw("{");
    j.key("character"); optional_string(j,s.character); j.raw(","); j.key("closed"); j.raw(s.closed ? "true" : "false"); j.raw(",");
    j.key("connection_ids"); integers(j,s.connection_ids); j.raw(","); j.key("contour_index"); optional_integer(j,s.contour_index); j.raw(","); j.key("element_id"); optional_string(j,s.element_id); j.raw(","); j.key("element_type"); optional_string(j,s.element_type); j.raw(","); j.key("font_role"); optional_string(j,s.font_role); j.raw(","); j.key("font_sha256"); optional_string(j,s.font_sha256); j.raw(","); j.key("glyph_index"); optional_integer(j,s.glyph_index); j.raw(",");
    j.key("id"); j.integer(static_cast<std::int64_t>(s.id)); j.raw(","); j.key("layout_group"); optional_string(j,s.layout_group); j.raw(","); j.key("points"); array(j, s.points, [&j](const Point& p) { point(j, p); }); j.raw(","); j.key("preserve_order"); j.raw(s.preserve_order ? "true" : "false"); j.raw(","); j.key("segment_types"); strings(j,s.segment_types); j.raw(","); j.key("semantic_role"); optional_string(j,s.semantic_role); j.raw(","); j.key("source_characters"); j.string(s.source_characters); j.raw(","); j.key("source_glyph_indices"); integers(j,s.source_glyph_indices); j.raw(","); j.key("source_page_index"); optional_integer(j,s.source_page_index); j.raw(","); j.key("source_path"); optional_string(j,s.source_path); j.raw(","); j.key("word_index"); optional_integer(j,s.word_index); j.raw(","); j.key("z_order"); j.integer(s.z_order); j.raw("}");
}
void style(Json& j, const TextStyle& s) { j.raw("{"); j.key("baseline_shift"); nullable(j,s.baseline_shift); j.raw(","); j.key("bold"); j.raw(s.bold?"true":"false"); j.raw(","); j.key("font_size_pt"); if(s.font_size) j.number(s.font_size->value); else j.raw("null"); j.raw(","); j.key("italic"); j.raw(s.italic?"true":"false"); j.raw(","); j.key("strike"); j.raw(s.strike?"true":"false"); j.raw(","); j.key("underline"); nullable(j,s.underline); j.raw("}"); }
void optional_double(Json& j, const std::optional<double>& value) { if (value) j.number(*value); else j.raw("null"); }
void optional_millimetres(Json& j, const std::optional<Millimetres>& value) { nullable(j, value); }
void paragraph(Json& j, const Paragraph& p) {
    j.raw("{");
    j.key("alignment"); nullable(j,p.alignment); j.raw(",");
    j.key("bbox"); nullable_rect(j,p.bounds); j.raw(",");
    j.key("first_line_indent_mm"); optional_millimetres(j,p.first_line_indent); j.raw(",");
    j.key("hanging_indent_mm"); optional_millimetres(j,p.hanging_indent); j.raw(",");
    j.key("left_indent_mm"); optional_millimetres(j,p.left_indent); j.raw(",");
    j.key("line_spacing"); optional_double(j,p.line_spacing); j.raw(",");
    j.key("right_indent_mm"); optional_millimetres(j,p.right_indent); j.raw(",");
    j.key("runs"); array(j,p.runs,[&j](const TextRun& r){j.raw("{");j.key("bbox");nullable_rect(j,r.bounds);j.raw(",");j.key("style");style(j,r.style);j.raw(",");j.key("text");j.string(r.text);j.raw("}");}); j.raw(",");
    j.key("semantic_role"); nullable(j,p.semantic_role); j.raw(",");
    j.key("space_after_mm"); optional_millimetres(j,p.space_after); j.raw(",");
    j.key("space_before_mm"); optional_millimetres(j,p.space_before); j.raw(",");
    j.key("style_id"); nullable(j,p.style_id); j.raw(",");
    j.key("style_name"); nullable(j,p.style_name); j.raw(",");
    j.key("tab_stops"); array(j,p.tab_stops,[&j](const TabStop& t){j.raw("{");j.key("alignment");j.string(t.alignment);j.raw(",");j.key("position_mm");j.number(t.position.value);j.raw("}");});
    j.raw("}");
}
void image_extra(Json& j, const RasterImageElement& e) {
    j.raw(",");j.key("displayed_width_mm");nullable(j,e.displayed_width);
    j.raw(",");j.key("displayed_height_mm");nullable(j,e.displayed_height);
    j.raw(",");j.key("anchor_type");j.string(e.anchor_type);
    j.raw(",");j.key("wrap_mode");j.string(e.wrap_mode);
    j.raw(",");j.key("wrap_side");j.string(e.wrap_side);
    j.raw(",");j.key("distance_left_mm");j.number(e.distance_left.value);
    j.raw(",");j.key("distance_right_mm");j.number(e.distance_right.value);
    j.raw(",");j.key("distance_top_mm");j.number(e.distance_top.value);
    j.raw(",");j.key("distance_bottom_mm");j.number(e.distance_bottom.value);
    j.raw(",");j.key("relative_to_h");nullable(j,e.relative_to_h);
    j.raw(",");j.key("relative_to_v");nullable(j,e.relative_to_v);
    j.raw(",");j.key("behind_text");j.raw(e.behind_text?"true":"false");
    j.raw(",");j.key("z_order");j.integer(e.z_order);
    j.raw(",");j.key("rotation_deg");j.number(e.rotation.value);
    j.raw(",");j.key("anchor_offset_x_mm");j.number(e.anchor_offset_x.value);
    j.raw(",");j.key("anchor_offset_y_mm");j.number(e.anchor_offset_y.value);
}
void vector_extra(Json& j, const VectorElement& e) {
    j.raw(",");j.key("anchor_type");j.string(e.anchor_type);
    j.raw(",");j.key("wrap_mode");j.string(e.wrap_mode);
    j.raw(",");j.key("wrap_side");j.string(e.wrap_side);
    j.raw(",");j.key("z_order");j.integer(e.z_order);
}
void vector_path_extra(Json& j, const VectorPath& p) {
    j.raw(",");j.key("element_id");nullable(j,p.element_id);
    j.raw(",");j.key("element_type");nullable(j,p.element_type);
    j.raw(",");j.key("source_path");nullable(j,p.source_path);
    j.raw(",");j.key("semantic_role");nullable(j,p.semantic_role);
    j.raw(",");j.key("layout_group");nullable(j,p.layout_group);
    j.raw(",");j.key("source_page_index");if(p.source_page)j.integer(*p.source_page);else j.raw("null");
    j.raw(",");j.key("preserve_order");j.raw(p.preserve_order?"true":"false");
    j.raw(",");j.key("z_order");j.integer(p.z_order);
}
void math_extra(Json& j, const MathElement& e) {
    j.raw(",");j.key("visual_image_path");nullable(j,e.visual_image_path);
    j.raw(",");j.key("visual_pixels_per_mm");optional_double(j,e.visual_pixels_per_mm);
    j.raw(",");j.key("absorbed_element_ids");strings(j,e.absorbed_element_ids);
    j.raw(",");j.key("detection_confidence");optional_double(j,e.detection_confidence);
}
void line_extra(Json& j, const LineElement& e) {
    j.raw(",");j.key("line_width_mm");nullable(j,e.line_width);
    j.raw(",");j.key("dash_style");nullable(j,e.dash_style);
    j.raw(",");j.key("semantic_role");j.string(e.semantic_role);
    j.raw(",");j.key("confidence");optional_double(j,e.confidence);
}
void arrow_extra(Json& j, const ArrowElement& e) {
    j.raw(",");j.key("head_at_start");j.raw(e.head_at_start?"true":"false");
    j.raw(",");j.key("head_at_end");j.raw(e.head_at_end?"true":"false");
    j.raw(",");j.key("head_style");j.string(e.head_style);
    j.raw(",");j.key("start_head_style");j.string(e.start_head_style);
    j.raw(",");j.key("end_head_style");j.string(e.end_head_style);
    j.raw(",");j.key("confidence");optional_double(j,e.confidence);
    j.raw(",");j.key("stroke_color");nullable(j,e.stroke_color);
    j.raw(",");j.key("source_identity");nullable(j,e.source_identity);
    j.raw(",");j.key("line_width_mm");nullable(j,e.line_width);
}
void table_extra(Json& j, const TableElement& e) {
    j.raw(",");j.key("cells");array(j,e.cells,[&j](const TableCell& c){
        j.raw("{");j.key("row");j.integer(c.row);j.raw(",");j.key("column");j.integer(c.column);
        j.raw(",");j.key("row_span");j.integer(c.row_span);j.raw(",");j.key("column_span");j.integer(c.column_span);
        j.raw(",");j.key("paragraphs");array(j,c.paragraphs,[&j](const Paragraph& p){paragraph(j,p);});
        j.raw(",");j.key("width_mm");nullable(j,c.width);j.raw(",");j.key("height_mm");nullable(j,c.height);
        j.raw(",");j.key("borders");j.raw("{");j.key("top");j.raw(c.borders.top?"true":"false");
        j.raw(",");j.key("right");j.raw(c.borders.right?"true":"false");j.raw(",");j.key("bottom");j.raw(c.borders.bottom?"true":"false");
        j.raw(",");j.key("left");j.raw(c.borders.left?"true":"false");j.raw("}");
        j.raw(",");j.key("vertical_alignment");nullable(j,c.vertical_alignment);j.raw("}");
    });
    j.raw(",");j.key("column_widths_mm");array(j,e.column_widths,[&j](Millimetres m){j.number(m.value);});
    j.raw(",");j.key("repeat_header_rows");j.integer(e.repeat_header_rows);
    j.raw(",");j.key("source_kind");j.string(e.source_kind);
    j.raw(",");j.key("alignment");nullable(j,e.alignment);
    j.raw(",");j.key("left_indent_mm");nullable(j,e.left_indent);
    j.raw(",");j.key("preferred_width_mm");nullable(j,e.preferred_width);
    j.raw(",");j.key("row_heights_mm");array(j,e.row_heights,[&j](const std::optional<Millimetres>& value){nullable(j,value);});
}
void document(Json& j, const Document& d) { j.raw("{"); j.key("metadata"); j.raw("{"); j.key("properties"); metadata_pairs(j, d.metadata.properties); j.raw(","); j.key("source_format"); j.string(d.metadata.source_format); j.raw(","); j.key("title"); nullable(j, d.metadata.title); j.raw("},"); j.key("pages"); array(j, d.pages, [&j](const SourcePage& p) { j.raw("{"); j.key("content_bbox"); nullable_rect(j, p.content_bounds); j.raw(","); j.key("elements"); j.raw("["); for (std::size_t i = 0; i < p.elements.size(); ++i) { if (i) j.raw(","); std::visit([&j](const auto& e) { j.raw("{"); j.key("id"); j.string(e.id); j.raw(","); j.key("source_order"); j.integer(e.source_order); j.raw(","); j.key("source_page_index"); j.integer(e.source_page); j.raw(","); j.key("type"); if constexpr (std::is_same_v<std::decay_t<decltype(e)>, TextElement>) j.string("text"); else if constexpr (std::is_same_v<std::decay_t<decltype(e)>, RasterImageElement>) j.string("image"); else if constexpr (std::is_same_v<std::decay_t<decltype(e)>, VectorElement>) j.string("vector"); else if constexpr (std::is_same_v<std::decay_t<decltype(e)>, MathElement>) j.string("math"); else if constexpr (std::is_same_v<std::decay_t<decltype(e)>, LineElement>) j.string("line"); else if constexpr (std::is_same_v<std::decay_t<decltype(e)>, ArrowElement>) j.string("arrow"); else j.string("table"); if constexpr (std::is_same_v<std::decay_t<decltype(e)>, TextElement>) { j.raw(","); j.key("bbox"); nullable_rect(j,e.bounds); j.raw(","); j.key("paragraphs"); array(j,e.paragraphs,[&j](const Paragraph& p){paragraph(j,p);}); } else if constexpr (std::is_same_v<std::decay_t<decltype(e)>, RasterImageElement>) { j.raw(",");j.key("bbox");nullable_rect(j,e.bounds);j.raw(",");j.key("image_path");j.string(e.image_path);j.raw(",");j.key("pixels");j.raw("[");j.number(e.width.value);j.raw(",");j.number(e.height.value);j.raw("]"); image_extra(j,e); } else if constexpr (std::is_same_v<std::decay_t<decltype(e)>, MathElement>) { j.raw(",");j.key("bbox");nullable_rect(j,e.bounds);j.raw(",");j.key("expression");j.string(e.expression);j.raw(",");j.key("source_syntax");j.string(e.source_syntax);j.raw(",");j.key("display_mode");j.raw(e.display_mode?"true":"false"); math_extra(j,e); } else if constexpr (std::is_same_v<std::decay_t<decltype(e)>, LineElement>) { j.raw(",");j.key("bbox");nullable_rect(j,e.bounds);j.raw(",");j.key("start");point(j,e.start);j.raw(",");j.key("end");point(j,e.end); line_extra(j,e); } else if constexpr (std::is_same_v<std::decay_t<decltype(e)>, ArrowElement>) { j.raw(",");j.key("bbox");nullable_rect(j,e.bounds);j.raw(",");j.key("points");array(j,e.points,[&j](const Point& p){point(j,p);}); arrow_extra(j,e); } else if constexpr (std::is_same_v<std::decay_t<decltype(e)>, VectorElement>) { j.raw(",");j.key("bbox");nullable_rect(j,e.bounds);j.raw(",");j.key("paths");j.raw("["); for(std::size_t n=0;n<e.paths.size();++n){if(n)j.raw(",");j.raw("{");j.key("closed");j.raw(e.paths[n].closed?"true":"false");j.raw(",");j.key("points");array(j,e.paths[n].points,[&j](const Point& p){point(j,p);});vector_path_extra(j,e.paths[n]);j.raw("}");}j.raw("]"); vector_extra(j,e); } else if constexpr (std::is_same_v<std::decay_t<decltype(e)>, TableElement>) { j.raw(",");j.key("bbox");nullable_rect(j,e.bounds);j.raw(",");j.key("columns");j.integer(e.columns);j.raw(",");j.key("rows");j.integer(e.rows); table_extra(j,e); } j.raw("}"); }, p.elements[i]); } j.raw("],"); j.key("height_mm"); nullable(j, p.height); j.raw(","); j.key("source_page_index"); j.integer(p.source_page); j.raw(","); j.key("width_mm"); nullable(j, p.width); j.raw("}"); }); j.raw(","); j.key("schema_version"); j.integer(d.schema_version); j.raw(","); j.key("source_path"); j.string(d.source_path); j.raw(","); j.key("warnings"); strings(j, d.warnings); j.raw("}"); }
void layout_page_extra(Json& j, const LayoutPage& p) {
    j.raw(",");j.key("source_element_ids");strings(j,p.source_element_ids);
    j.raw(",");j.key("placements");array(j,p.placements,[&j](const SourcePlacement& placement){
        j.raw("{");j.key("source_page_index");j.integer(placement.source_page);
        j.raw(",");j.key("source_bbox");nullable_rect(j,placement.source_bounds);
        j.raw(",");j.key("target_bbox");nullable_rect(j,placement.target_bounds);
        j.raw(",");j.key("anchor");j.string(placement.anchor);
        j.raw(",");j.key("wrap_mode");j.string(placement.wrap_mode);
        j.raw(",");j.key("z_order");j.integer(placement.z_order);j.raw("}");
    });
    j.raw(",");j.key("line_boxes");array(j,p.line_boxes,[&j](const Rect& box){rect(j,box);});
    j.raw(",");j.key("table_fragments");array(j,p.table_fragments,[&j](const TableFragment& fragment){
        j.raw("{");j.key("table_id");j.string(fragment.table_id);
        j.raw(",");j.key("source_row_start");j.integer(fragment.source_row_start);
        j.raw(",");j.key("source_row_end");j.integer(fragment.source_row_end);
        j.raw(",");j.key("bbox");rect(j,fragment.bounds);j.raw("}");
    });
    j.raw(",");j.key("line_count");j.integer(p.line_count);
    j.raw(",");j.key("metadata");metadata_pairs(j,p.metadata);
}
void layout_document_extra(Json& j, const LayoutDocument& d) {
    j.raw(",");j.key("import_statistics");metadata_pairs(j,d.import_statistics);
    j.raw(",");j.key("element_details");metadata_pairs(j,d.element_details);
    j.raw(",");j.key("latex_statistics");metadata_pairs(j,d.latex_statistics);
    j.raw(",");j.key("layout_statistics");metadata_pairs(j,d.layout_statistics);
}
void layout(Json& j, const LayoutDocument& d) { j.raw("{"); j.key("pages"); array(j, d.pages, [&j](const LayoutPage& p) { j.raw("{"); j.key("graphic_strokes"); array(j, p.graphic_strokes, [&j](const Stroke& s) { stroke(j,s); }); j.raw(","); j.key("math_glyphs"); array(j,p.math_glyphs,[&j](const PositionedGlyph& g){ j.raw("{"); j.key("char"); j.string(g.character); j.raw(","); j.key("glyph_index"); j.integer(g.glyph_index); j.raw(","); j.key("source_element_id"); optional_string(j,g.source_element_id); j.raw("}"); }); j.raw(","); j.key("glyphs"); array(j, p.glyphs, [&j](const PositionedGlyph& g) { j.raw("{"); j.key("advance_mm"); j.number(g.advance.value); j.raw(","); j.key("baseline_y_mm"); j.number(g.baseline_y.value); j.raw(","); j.key("char"); j.string(g.character); j.raw(","); j.key("codepoint"); j.integer(g.codepoint); j.raw(","); j.key("font_id"); optional_string(j,g.font_id); j.raw(","); j.key("font_sha256"); optional_string(j,g.font_sha256); j.raw(","); j.key("source_element_id"); optional_string(j,g.source_element_id); j.raw(","); j.key("glyph_index"); j.integer(g.glyph_index); j.raw(","); j.key("cluster_index"); j.integer(g.cluster_index); j.raw(","); j.key("glyph_name"); j.string(g.glyph_name); j.raw(","); j.key("line_index"); j.integer(g.line_index); j.raw(","); j.key("scale_mm_per_font_unit"); j.number(g.scale_mm_per_font_unit); j.raw(","); j.key("text_role"); j.string(g.text_role); j.raw(","); j.key("bold"); j.raw(g.bold ? "true" : "false"); j.raw(","); j.key("italic"); j.raw(g.italic ? "true" : "false"); j.raw(","); j.key("baseline_shift"); nullable(j,g.baseline_shift); j.raw(","); j.key("word_index"); j.integer(g.word_index); j.raw(","); j.key("x_mm"); j.number(g.x.value); j.raw(","); j.key("x_offset_font_units"); j.number(g.x_offset.value); j.raw(","); j.key("y_offset_font_units"); j.number(g.y_offset.value); j.raw("}"); }); j.raw(","); j.key("page_index"); j.integer(p.page_index); j.raw(","); j.key("warnings"); strings(j,p.warnings); layout_page_extra(j,p); j.raw("}"); }); j.raw(","); j.key("schema_version"); j.integer(d.schema_version); j.raw(","); j.key("warnings"); strings(j,d.warnings); layout_document_extra(j,d); j.raw("}"); }
void paths(Json& j, const PathDocument& p) { j.raw("{"); j.key("format"); j.string("plotter-paths"); j.raw(","); j.key("metadata"); metadata(j,p.metadata); j.raw(","); j.key("page"); j.raw("{"); j.key("height_mm"); j.number(p.page_height.value); j.raw(","); j.key("width_mm"); j.number(p.page_width.value); j.raw("},"); j.key("strokes"); array(j,p.strokes,[&j](const Stroke& s){stroke(j,s);}); j.raw(","); j.key("warnings"); strings(j,p.warnings); j.raw("}"); }
std::string envelope(StageKind stage, auto writer) { Json j; j.raw("{"); j.key("format"); j.string(stage_schema_name(stage)); j.raw(","); j.key("ir_version"); j.integer(kStageIrSchemaVersion); j.raw(","); j.key("stage"); j.string(stage_name(stage)); j.raw(","); j.key("value"); writer(j); j.raw("}"); return std::move(j).take(); }
}  // namespace
std::string_view stage_name(StageKind stage) noexcept { switch(stage) { case StageKind::document: return "document"; case StageKind::layout: return "layout"; case StageKind::paths: return "paths"; } return "unknown"; }
std::string_view stage_schema_name(StageKind stage) noexcept { switch(stage) { case StageKind::document: return "plotter-document-ir-v1"; case StageKind::layout: return "plotter-layout-ir-v1"; case StageKind::paths: return "plotter-path-ir-v1"; } return "unknown"; }
std::string serialize_stage_ir(const Document& value) { return envelope(StageKind::document, [&value](Json& j) { document(j,value); }); }
std::string serialize_stage_ir(const LayoutDocument& value) { return envelope(StageKind::layout, [&value](Json& j) { layout(j,value); }); }
std::string serialize_stage_ir(const PathDocument& value) { return envelope(StageKind::paths, [&value](Json& j) { paths(j,value); }); }
namespace {
std::size_t skip_ws(std::string_view s, std::size_t p) { while (p < s.size() && (s[p] == char(32) || s[p] == char(10) || s[p] == char(13) || s[p] == char(9))) ++p; return p; }
bool quoted_end(std::string_view s, std::size_t p, std::size_t& end) { if (p >= s.size() || s[p] != char(34)) return false; ++p; while (p < s.size()) { if (s[p] == char(92)) { p += 2; continue; } if (s[p++] == char(34)) { end = p; return true; } } return false; }
bool value_end(std::string_view s, std::size_t p, std::size_t& end) { p = skip_ws(s,p); if (p >= s.size()) return false; if (s[p] == char(34)) return quoted_end(s,p,end); if (s[p] != char(123) && s[p] != char(91)) { end=p; while(end<s.size() && s[end]!=char(44) && s[end]!=char(125) && s[end]!=char(93)) ++end; return end>p; } const char open=s[p], close=open==char(123)?char(125):char(93); int depth=0; bool q=false; for(;p<s.size();++p) { char c=s[p]; if(q) { if(c==char(92)) ++p; else if(c==char(34)) q=false; continue; } if(c==char(34)) q=true; else if(c==open) ++depth; else if(c==close && --depth==0) { end=p+1; return true; } } return false; }
std::string unquote(std::string_view s) { if(s.size()<2 || s.front()!=char(34) || s.back()!=char(34)) return {}; std::string o; for(std::size_t i=1;i+1<s.size();++i) { if(s[i]==char(92) && i+2<s.size()) { const char c=s[++i]; switch(c){case char(34):o+=char(34);break;case char(92):o+=char(92);break;case char(110):o+=char(10);break;case char(114):o+=char(13);break;case char(116):o+=char(9);break;default:return {};}} else o+=s[i]; } return o; }
std::optional<std::string_view> member(std::string_view s, std::string_view name) { std::string key=std::string(1,char(34))+std::string(name)+std::string(1,char(34)); const auto at=s.find(key); if(at==std::string_view::npos) return std::nullopt; auto p=skip_ws(s,at+key.size()); if(p>=s.size() || s[p++]!=char(58)) return std::nullopt; const auto begin=skip_ws(s,p); std::size_t end{}; if(!value_end(s,begin,end)) return std::nullopt; return s.substr(begin,end-begin); }
}  // namespace
ParsedStageIr deserialize_stage_ir(std::string_view json) {
    auto format=member(json,"format"), version=member(json,"ir_version"), stage=member(json,"stage"), value=member(json,"value");
    if(!format || !version || !stage || !value) return IrParseError{"stage IR requires format, ir_version, stage and value"};
    std::uint32_t n{}; try { std::size_t used{}; n=static_cast<std::uint32_t>(std::stoul(std::string(*version),&used)); if(used != version->size()) throw std::invalid_argument("x"); } catch(...) { return IrParseError{"ir_version must be an unsigned integer"}; }
    if(n != kStageIrSchemaVersion) return IrParseError{"unsupported stage IR version"};
    const auto text=unquote(*stage); StageKind kind; if(text=="document") kind=StageKind::document; else if(text=="layout") kind=StageKind::layout; else if(text=="paths") kind=StageKind::paths; else return IrParseError{"unknown stage"};
    if(unquote(*format) != stage_schema_name(kind)) return IrParseError{"stage IR format does not match stage"};
    return StageIrEnvelope{kind,n,std::string(*value)};
}

}  // namespace plotter::doc
