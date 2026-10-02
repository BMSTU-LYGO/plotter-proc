#include "plotter/doc/centerline_path_builder.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>
#include <utility>

namespace plotter::doc {
namespace {
void append_unique(std::vector<Point>& output, Point value) {
    if (output.empty() || output.back().x.value != value.x.value || output.back().y.value != value.y.value) output.push_back(value);
}

[[nodiscard]] double distance(Point left, Point right) {
    return std::hypot(left.x.value - right.x.value, left.y.value - right.y.value);
}

void append_connector(std::vector<Point>& output, Point end) {
    const Point start = output.back();
    if (distance(start, end) < 1e-9) return;
    const Point control{{(start.x.value + end.x.value) / 2.0}, start.y};
    for (double t : {1.0 / 3.0, 2.0 / 3.0, 1.0}) {
        const double u = 1.0 - t;
        append_unique(output, {{u * u * start.x.value + 2.0 * u * t * control.x.value + t * t * end.x.value},
                               {u * u * start.y.value + 2.0 * u * t * control.y.value + t * t * end.y.value}});
    }
}

[[nodiscard]] Stroke join_one_word(const std::vector<Stroke>& strokes, std::size_t first, std::size_t last) {
    if (last == first + 1) return strokes[first];
    Stroke joined = strokes[first];
    joined.points.clear();
    joined.closed = false;
    joined.glyph_index.reset();
    joined.contour_index.reset();
    joined.character.reset();
    joined.source_glyph_indices.clear();
    joined.source_characters.clear();
    joined.segment_types.clear();
    joined.connection_ids.clear();
    joined.semantic_role = "word";
    joined.preserve_order = true;
    std::vector<bool> used(last - first);
    std::size_t remaining = used.size();
    while (remaining > 0) {
        std::size_t earliest = 0;
        while (used[earliest]) ++earliest;
        const auto glyph = strokes[first + earliest].glyph_index;
        std::size_t chosen = earliest;
        bool reverse = false;
        double best = std::numeric_limits<double>::infinity();
        for (std::size_t offset = earliest; offset < used.size(); ++offset) {
            if (strokes[first + offset].glyph_index != glyph) break;
            if (used[offset] || strokes[first + offset].points.empty()) continue;
            const Stroke& candidate = strokes[first + offset];
            const double forward = joined.points.empty() ? 0.0 : distance(joined.points.back(), candidate.points.front());
            const double backward = joined.points.empty() ? 0.0 : distance(joined.points.back(), candidate.points.back());
            const double score = std::min(forward, backward);
            if (score < best) { best = score; chosen = offset; reverse = backward < forward; }
        }
        used[chosen] = true;
        --remaining;
        const Stroke& source = strokes[first + chosen];
        if (source.points.empty()) continue;
        if (!joined.points.empty()) {
            append_connector(joined.points, reverse ? source.points.back() : source.points.front());
            joined.segment_types.push_back("connector");
            joined.connection_ids.push_back(static_cast<std::int64_t>(source.id));
        }
        if (reverse) {
            for (auto it = source.points.rbegin(); it != source.points.rend(); ++it) append_unique(joined.points, *it);
        } else {
            for (Point point : source.points) append_unique(joined.points, point);
        }
        joined.segment_types.insert(joined.segment_types.end(), source.segment_types.begin(), source.segment_types.end());
        if (source.glyph_index && (joined.source_glyph_indices.empty() || joined.source_glyph_indices.back() != *source.glyph_index)) {
            joined.source_glyph_indices.push_back(*source.glyph_index);
            joined.source_characters += source.character.value_or("");
        }
        if (joined.font_sha256 != source.font_sha256) joined.font_sha256.reset();
        if (joined.element_id != source.element_id) joined.element_id.reset();
    }
    return joined;
}

void join_words(PathDocument& document) {
    std::vector<Stroke> joined;
    joined.reserve(document.strokes.size());
    for (std::size_t first = 0; first < document.strokes.size();) {
        std::size_t last = first + 1;
        const Stroke& start = document.strokes[first];
        if (start.word_index && *start.word_index >= 0 && start.element_type == "text") {
            while (last < document.strokes.size() && document.strokes[last].word_index == start.word_index &&
                   document.strokes[last].element_type == start.element_type) ++last;
        }
        joined.push_back(join_one_word(document.strokes, first, last));
        first = last;
    }
    for (std::size_t index = 0; index < joined.size(); ++index) joined[index].id = index;
    document.strokes = std::move(joined);
    document.metadata.emplace_back("word_joining", "one-pen-down");
}
}

PathDocument CenterlinePathBuilder::build(const LayoutPage& page, Millimetres page_width,
                                          Millimetres page_height, bool join_word_strokes) const {
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
    if (join_word_strokes) join_words(result);
    return result;
}
}  // namespace plotter::doc
