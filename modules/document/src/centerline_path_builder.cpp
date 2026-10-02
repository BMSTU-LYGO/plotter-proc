#include "plotter/doc/centerline_path_builder.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <iterator>
#include <limits>
#include <optional>
#include <map>
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

[[nodiscard]] double stroke_length(const Stroke& stroke) {
    double length = 0.0;
    for (std::size_t i = 1; i < stroke.points.size(); ++i)
        length += distance(stroke.points[i - 1], stroke.points[i]);
    return length;
}

[[nodiscard]] bool is_letter(const Stroke& stroke) {
    if (!stroke.character || stroke.character->empty()) return false;
    const auto first = static_cast<unsigned char>((*stroke.character)[0]);
    return (first >= 'A' && first <= 'Z') || (first >= 'a' && first <= 'z') ||
           first == 0xD0 || first == 0xD1; // Cyrillic UTF-8
}

[[nodiscard]] double cross(Point a, Point b, Point c) {
    return (b.x.value - a.x.value) * (c.y.value - a.y.value) -
           (b.y.value - a.y.value) * (c.x.value - a.x.value);
}

[[nodiscard]] bool crosses(Point a, Point b, Point c, Point d) {
    const double ab1 = cross(a, b, c), ab2 = cross(a, b, d);
    const double cd1 = cross(c, d, a), cd2 = cross(c, d, b);
    return ab1 * ab2 < -1e-8 && cd1 * cd2 < -1e-8;
}

[[nodiscard]] std::array<Point, 4> connector_points(Point start, Point end) {
    const Point control{{(start.x.value + end.x.value) / 2.0}, start.y};
    std::array<Point, 4> result{start, start, start, end};
    for (std::size_t index = 1; index < 3; ++index) {
        const double t = static_cast<double>(index) / 3.0;
        const double u = 1.0 - t;
        result[index] = {{u * u * start.x.value + 2.0 * u * t * control.x.value + t * t * end.x.value},
                         {u * u * start.y.value + 2.0 * u * t * control.y.value + t * t * end.y.value}};
    }
    return result;
}

[[nodiscard]] bool safe_connector(const Stroke& left, const Stroke& right,
                                  const std::vector<Stroke>& strokes,
                                  std::size_t first, std::size_t last,
                                  bool allow_entry_turn = false) {
    if (left.points.size() < 2 || right.points.size() < 2 ||
        left.closed || right.closed || !is_letter(left) || !is_letter(right) ||
        left.font_sha256 != right.font_sha256) return false;
    const Point start = left.points.back(), end = right.points.front();
    const double gap = distance(start, end);
    if (gap > 2.5 || std::abs(end.y.value - start.y.value) > 2.0 ||
        end.x.value + 0.01 < start.x.value) return false;
    if (gap > 0.08 && !allow_entry_turn) {
        // Python measured terminal tangents over 0.8 mm. The final tiny
        // segment of a sampled PFC contour is too noisy for this decision.
        std::size_t left_index = left.points.size() - 1;
        double left_run = 0.0;
        while (left_index > 0 && left_run < 0.8) {
            left_run += distance(left.points[left_index], left.points[left_index - 1]);
            --left_index;
        }
        std::size_t right_index = 0;
        double right_run = 0.0;
        while (right_index + 1 < right.points.size() && right_run < 0.8) {
            right_run += distance(right.points[right_index], right.points[right_index + 1]);
            ++right_index;
        }
        const Point before = left.points[left_index];
        const Point after = right.points[right_index];
        const double left_length = distance(before, start), right_length = distance(end, after);
        if (left_length < 1e-6 || right_length < 1e-6) return false;
        const double dx = (end.x.value - start.x.value) / gap;
        const double dy = (end.y.value - start.y.value) / gap;
        constexpr double min_cosine = -0.70710678118; // 135 degrees, Python safe profile
        if (((start.x.value - before.x.value) / left_length * dx +
             (start.y.value - before.y.value) / left_length * dy) < min_cosine ||
            ((after.x.value - end.x.value) / right_length * dx +
             (after.y.value - end.y.value) / right_length * dy) < min_cosine) return false;
    }
    // Reject a connector that cuts through any contour in this word. Contact
    // with the two terminal segments is expected; the remaining ink is not.
    const auto connector = connector_points(start, end);
    for (std::size_t index = first; index < last; ++index) {
        const Stroke& obstacle = strokes[index];
        for (std::size_t segment = 1; segment < obstacle.points.size(); ++segment) {
            const Point a = obstacle.points[segment - 1];
            const Point b = obstacle.points[segment];
            constexpr double boundary_ignore_mm = 0.4;
            if ((obstacle.id == left.id && (distance(a, start) <= boundary_ignore_mm || distance(b, start) <= boundary_ignore_mm)) ||
                (obstacle.id == right.id && (distance(a, end) <= boundary_ignore_mm || distance(b, end) <= boundary_ignore_mm))) continue;
            if (crosses(start, end, a, b)) return false;
            for (std::size_t part = 1; part < connector.size(); ++part)
                if (crosses(connector[part - 1], connector[part], a, b))
                    return false;
        }
    }
    return true;
}

void append_connector(std::vector<Point>& output, Point end) {
    const Point start = output.back();
    if (distance(start, end) < 1e-9) return;
    const auto connector = connector_points(start, end);
    for (std::size_t index = 1; index < connector.size(); ++index)
        append_unique(output, connector[index]);
}

[[nodiscard]] std::optional<Stroke> retraced_entry(const Stroke& previous,
                                                   const Stroke& main,
                                                   const std::vector<Stroke>& strokes,
                                                   std::size_t first, std::size_t last) {
    // Enter at an interior point, trace back over existing ink to the original
    // start, then draw the whole main route. This creates no new mark inside
    // the letter and saves a lift when the original endpoint is obstructed.
    double prefix = 0.0;
    std::optional<Stroke> best;
    double best_cost = std::numeric_limits<double>::infinity();
    std::size_t considered = 0;
    double last_sample = -1.0;
    for (std::size_t index = 1; index + 1 < main.points.size() && considered < 16; ++index) {
        prefix += distance(main.points[index - 1], main.points[index]);
        if (prefix > 6.0) break;
        if (prefix - last_sample < 0.4) continue;
        last_sample = prefix;
        if (distance(previous.points.back(), main.points[index]) > 2.5) continue;
        ++considered;
        Stroke candidate = main;
        candidate.points.clear();
        for (std::size_t point = index + 1; point > 0; --point)
            candidate.points.push_back(main.points[point - 1]);
        candidate.points.insert(candidate.points.end(), main.points.begin() + 1, main.points.end());
        if (!safe_connector(previous, candidate, strokes, first, last, true)) continue;
        const double cost = distance(previous.points.back(), candidate.points.front()) + prefix;
        if (cost < best_cost) { best_cost = cost; best = std::move(candidate); }
    }
    return best;
}

void join_one_word(const std::vector<Stroke>& strokes, std::size_t first,
                   std::size_t last, std::vector<Stroke>& output) {
    std::vector<Stroke> secondary;
    std::optional<Stroke> combined;
    std::optional<Stroke> previous_main;
    for (std::size_t begin = first; begin < last;) {
        std::size_t end = begin + 1;
        while (end < last && strokes[end].glyph_index == strokes[begin].glyph_index) ++end;
        std::size_t main_index = begin;
        double main_length = -1.0;
        double total_length = 0.0;
        for (std::size_t index = begin; index < end; ++index) {
            const Stroke& candidate = strokes[index];
            const double length = stroke_length(candidate);
            total_length += length;
            if (!candidate.closed && length > main_length) {
                main_length = length;
                main_index = index;
            }
        }
        // As in Python, ambiguous or closed-only glyphs do not supply an
        // entry/exit for joining with the next letter.
        const bool has_main = main_length > 0.0 &&
            main_length / total_length >= 0.35;
        for (std::size_t index = begin; index < end; ++index)
            if (!has_main || index != main_index) secondary.push_back(strokes[index]);
        if (has_main) {
            Stroke main = strokes[main_index];
            if (main.points.front().x.value > main.points.back().x.value)
                std::reverse(main.points.begin(), main.points.end());
            bool connected = combined && previous_main &&
                safe_connector(*previous_main, main, strokes, first, last);
            if (!connected && combined && previous_main) {
                if (auto alternate = retraced_entry(*previous_main, main, strokes, first, last)) {
                    main = std::move(*alternate);
                    connected = true;
                }
            }
            if (!connected && combined && previous_main) {
                // The other endpoint may be trapped inside the previous
                // glyph. Return along its existing ink to a clear exit.
                const Stroke& previous = *previous_main;
                double suffix = 0.0;
                double best_cost = std::numeric_limits<double>::infinity();
                std::optional<Stroke> best_main;
                std::size_t best_index = 0;
                std::size_t considered = 0;
                double last_sample = -1.0;
                for (std::size_t index = previous.points.size() - 1;
                     index > 1 && considered < 16;) {
                    suffix += distance(previous.points[index], previous.points[index - 1]);
                    --index;
                    if (suffix > 6.0) break;
                    if (suffix - last_sample < 0.4) continue;
                    last_sample = suffix;
                    ++considered;
                    Stroke exit = previous;
                    exit.points.resize(index + 1);
                    std::optional<Stroke> entry;
                    if (safe_connector(exit, main, strokes, first, last, true))
                        entry = main;
                    else entry = retraced_entry(exit, main, strokes, first, last);
                    if (!entry) continue;
                    const double cost = suffix + distance(exit.points.back(), entry->points.front());
                    if (cost < best_cost) {
                        best_cost = cost;
                        best_index = index;
                        best_main = std::move(*entry);
                    }
                }
                if (best_main) {
                    for (std::size_t point = previous.points.size() - 1; point > best_index; --point)
                        append_unique(combined->points, previous.points[point - 1]);
                    combined->segment_types.push_back("retrace");
                    main = std::move(*best_main);
                    connected = true;
                }
            }
            if (connected) {
                append_connector(combined->points, main.points.front());
                combined->points.insert(combined->points.end(), main.points.begin() + 1, main.points.end());
                combined->segment_types.push_back("connector");
                combined->segment_types.insert(combined->segment_types.end(),
                                               main.segment_types.begin(), main.segment_types.end());
                combined->connection_ids.push_back(static_cast<std::int64_t>(main.id));
                combined->source_glyph_indices.insert(combined->source_glyph_indices.end(),
                    main.source_glyph_indices.begin(), main.source_glyph_indices.end());
                combined->source_characters += main.source_characters;
                combined->glyph_index.reset();
                combined->contour_index.reset();
                combined->character.reset();
                combined->semantic_role = "word";
                combined->preserve_order = true;
            } else {
                if (combined) output.push_back(std::move(*combined));
                combined = main;
            }
            previous_main = main;
        } else {
            if (combined) output.push_back(std::move(*combined));
            combined.reset();
            previous_main.reset();
        }
        begin = end;
    }
    if (combined) output.push_back(std::move(*combined));
    output.insert(output.end(), std::make_move_iterator(secondary.begin()),
                  std::make_move_iterator(secondary.end()));
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
        const std::size_t output_start = joined.size();
        join_one_word(document.strokes, first, last, joined);
        if (start.element_type == "text")
            for (std::size_t index = output_start; index < joined.size(); ++index)
                joined[index].preserve_order = true;
        first = last;
    }
    for (std::size_t index = 0; index < joined.size(); ++index) joined[index].id = index;
    document.strokes = std::move(joined);
    document.metadata.emplace_back("word_joining", "safe-main-strokes");
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
    // A page repeats the same glyphs many times. Decode each PFC geometry
    // once, then only scale and place its points for each occurrence.
    std::map<std::pair<std::string, std::uint32_t>, GlyphGeometry> glyph_cache;
    for (const PositionedGlyph& positioned : page.glyphs) {
        if (!positioned.font_id) throw std::invalid_argument("positioned glyph has no font id");
        const auto key = std::pair{*positioned.font_id, positioned.codepoint};
        auto [cached, inserted] = glyph_cache.try_emplace(key);
        if (inserted) cached->second = fonts_.glyph_geometry(*positioned.font_id, positioned.codepoint);
        const GlyphGeometry& geometry = cached->second;
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
