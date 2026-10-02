#include "plotter/doc/centerline_path_builder.hpp"

#include <algorithm>
#include <stdexcept>

namespace plotter::doc {
namespace {
void append_unique(std::vector<Point>& output, Point value) {
    if (output.empty() || output.back().x.value != value.x.value || output.back().y.value != value.y.value) output.push_back(value);
}
}

PathDocument CenterlinePathBuilder::build(const LayoutPage& page, Millimetres page_width,
                                          Millimetres page_height) const {
    PathDocument result;
    result.page_width = page_width;
    result.page_height = page_height;
    result.metadata.emplace_back("coordinate_system", "page-mm-top-left");
    result.metadata.emplace_back("pipeline", "pfc-centerline");
    const std::optional<std::string> source_id = page.source_element_ids.size() == 1
        ? std::optional<std::string>{page.source_element_ids.front()} : std::nullopt;
    for (const PositionedGlyph& positioned : page.glyphs) {
        if (!positioned.font_id) throw std::invalid_argument("positioned glyph has no font id");
        const GlyphGeometry geometry = fonts_.glyph_geometry(*positioned.font_id, positioned.codepoint);
        for (std::size_t contour = 0; contour < geometry.strokes.size(); ++contour) {
            Stroke stroke;
            stroke.id = result.strokes.size();
            stroke.contour_index = static_cast<std::int64_t>(contour);
            stroke.glyph_index = static_cast<std::int64_t>(positioned.glyph_index);
            stroke.word_index = static_cast<std::int64_t>(positioned.word_index);
            stroke.source_page_index = static_cast<std::int64_t>(page.page_index);
            stroke.character = positioned.character;
            stroke.element_id = source_id;
            stroke.element_type = positioned.text_role == "page-number" ? "page-number" : "text";
            stroke.font_role = positioned.text_role == "page-number" ? "page-number" : "body";
            stroke.font_sha256 = positioned.font_sha256;
            stroke.source_glyph_indices.push_back(static_cast<std::int64_t>(positioned.glyph_index));
            stroke.source_characters = positioned.character;
            stroke.segment_types = {"glyph"};
            const FontStroke& template_stroke = geometry.strokes[contour];
            for (const FontPoint point : template_stroke.points) {
                append_unique(stroke.points, {{positioned.x.value + point.x.value * positioned.scale_mm_per_font_unit},
                                               {positioned.baseline_y.value - point.y.value * positioned.scale_mm_per_font_unit}});
            }
            stroke.closed = stroke.points.size() > 2 && stroke.points.front().x.value == stroke.points.back().x.value && stroke.points.front().y.value == stroke.points.back().y.value;
            if (stroke.points.size() >= (stroke.closed ? 3U : 2U)) result.strokes.push_back(std::move(stroke));
        }
    }
    return result;
}
}  // namespace plotter::doc
