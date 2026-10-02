#include "plotter/doc/table_path_builder.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <string>
#include <stdexcept>
#include <utility>
#include <vector>

namespace plotter::doc {
namespace {

constexpr double kDimensionEpsilon = 1e-9;

struct Segment final {
    Point first{};
    Point second{};
};

[[nodiscard]] bool finite_positive(Millimetres value) {
    return std::isfinite(value.value) && value.value > kDimensionEpsilon;
}

[[nodiscard]] std::vector<double> resolve_dimensions(
    std::size_t count, double available, const std::vector<std::optional<Millimetres>>& preferred,
    const std::vector<TableCell>& cells, bool columns) {
    std::vector<double> dimensions(count, 0.0);
    if (count == 0 || !std::isfinite(available) || available <= kDimensionEpsilon) return dimensions;

    double assigned{};
    for (std::size_t index = 0; index < count; ++index) {
        if (index < preferred.size() && preferred[index] && finite_positive(*preferred[index])) {
            dimensions[index] = preferred[index]->value;
            assigned += dimensions[index];
        }
    }
    // A single-cell width or height supplies a useful grid dimension only
    // when that dimension has not already been supplied by the table grid.
    for (const TableCell& cell : cells) {
        const std::size_t index = columns ? cell.column : cell.row;
        const std::uint32_t span = columns ? cell.column_span : cell.row_span;
        const auto supplied = columns ? cell.width : cell.height;
        if (index >= count || span != 1 || dimensions[index] != 0.0 || !supplied || !finite_positive(*supplied)) continue;
        dimensions[index] = supplied->value;
        assigned += dimensions[index];
    }

    // Preserve the table's bounds even if source dimensions disagree with it.
    if (assigned > available) {
        const double scale = available / assigned;
        for (double& dimension : dimensions) dimension *= scale;
        return dimensions;
    }
    std::size_t missing{};
    for (const double dimension : dimensions) if (dimension == 0.0) ++missing;
    if (missing != 0) {
        const double share = (available - assigned) / static_cast<double>(missing);
        for (double& dimension : dimensions) if (dimension == 0.0) dimension = share;
    } else {
        // Allocate rounding or unspecified trailing space to the final band.
        dimensions.back() += available - assigned;
    }
    return dimensions;
}

[[nodiscard]] std::vector<double> offsets(double start, const std::vector<double>& dimensions) {
    std::vector<double> result;
    result.reserve(dimensions.size() + 1);
    result.push_back(start);
    for (const double dimension : dimensions) result.push_back(result.back() + dimension);
    return result;
}

[[nodiscard]] bool same_point(Point left, Point right) {
    return std::abs(left.x.value - right.x.value) < kDimensionEpsilon &&
           std::abs(left.y.value - right.y.value) < kDimensionEpsilon;
}


void append_unique(std::vector<Segment>& segments, Segment segment) {
    if (same_point(segment.first, segment.second)) return;
    const bool horizontal = std::abs(segment.first.y.value - segment.second.y.value) < kDimensionEpsilon;
    for (Segment& existing : segments) {
        const bool existing_horizontal = std::abs(existing.first.y.value - existing.second.y.value) < kDimensionEpsilon;
        if (horizontal != existing_horizontal) continue;
        if (horizontal && std::abs(existing.first.y.value - segment.first.y.value) < kDimensionEpsilon) {
            const double left = std::min(segment.first.x.value, segment.second.x.value);
            const double right = std::max(segment.first.x.value, segment.second.x.value);
            const double existing_left = std::min(existing.first.x.value, existing.second.x.value);
            const double existing_right = std::max(existing.first.x.value, existing.second.x.value);
            if (std::max(left, existing_left) <= std::min(right, existing_right) + kDimensionEpsilon) {
                existing = {{{std::min(left, existing_left)}, {segment.first.y.value}}, {{std::max(right, existing_right)}, {segment.first.y.value}}};
                return;
            }
        } else if (!horizontal && std::abs(existing.first.x.value - segment.first.x.value) < kDimensionEpsilon) {
            const double top = std::min(segment.first.y.value, segment.second.y.value);
            const double bottom = std::max(segment.first.y.value, segment.second.y.value);
            const double existing_top = std::min(existing.first.y.value, existing.second.y.value);
            const double existing_bottom = std::max(existing.first.y.value, existing.second.y.value);
            if (std::max(top, existing_top) <= std::min(bottom, existing_bottom) + kDimensionEpsilon) {
                existing = {{{segment.first.x.value}, {std::min(top, existing_top)}}, {{segment.first.x.value}, {std::max(bottom, existing_bottom)}}};
                return;
            }
        }
    }
    segments.push_back(segment);
}

std::vector<std::pair<std::uint32_t, std::string>> decode_utf8(const std::string& input) {
    std::vector<std::pair<std::uint32_t, std::string>> result;
    for (std::size_t i = 0; i < input.size();) {
        const unsigned char first = static_cast<unsigned char>(input[i]); std::uint32_t codepoint = 0xFFFDU; std::size_t length = 1;
        if (first < 0x80U) codepoint = first;
        else if ((first & 0xE0U) == 0xC0U && i + 1 < input.size() && (static_cast<unsigned char>(input[i + 1]) & 0xC0U) == 0x80U) { codepoint = (static_cast<std::uint32_t>(first & 0x1FU) << 6U) | (static_cast<unsigned char>(input[i + 1]) & 0x3FU); length = codepoint >= 0x80U ? 2 : 1; }
        else if ((first & 0xF0U) == 0xE0U && i + 2 < input.size() && (static_cast<unsigned char>(input[i + 1]) & 0xC0U) == 0x80U && (static_cast<unsigned char>(input[i + 2]) & 0xC0U) == 0x80U) { codepoint = (static_cast<std::uint32_t>(first & 0x0FU) << 12U) | (static_cast<std::uint32_t>(static_cast<unsigned char>(input[i + 1]) & 0x3FU) << 6U) | (static_cast<unsigned char>(input[i + 2]) & 0x3FU); length = (codepoint >= 0x800U && !(codepoint >= 0xD800U && codepoint <= 0xDFFFU)) ? 3 : 1; }
        else if ((first & 0xF8U) == 0xF0U && i + 3 < input.size() && (static_cast<unsigned char>(input[i + 1]) & 0xC0U) == 0x80U && (static_cast<unsigned char>(input[i + 2]) & 0xC0U) == 0x80U && (static_cast<unsigned char>(input[i + 3]) & 0xC0U) == 0x80U) { codepoint = (static_cast<std::uint32_t>(first & 0x07U) << 18U) | (static_cast<std::uint32_t>(static_cast<unsigned char>(input[i + 1]) & 0x3FU) << 12U) | (static_cast<std::uint32_t>(static_cast<unsigned char>(input[i + 2]) & 0x3FU) << 6U) | (static_cast<unsigned char>(input[i + 3]) & 0x3FU); length = (codepoint >= 0x10000U && codepoint <= 0x10FFFFU) ? 4 : 1; }
        result.emplace_back(codepoint, input.substr(i, length)); i += length;
    }
    return result;
}

bool clip_line(Point& first, Point& second, const Rect& clip) {
    const double dx = second.x.value - first.x.value, dy = second.y.value - first.y.value; double low = 0.0, high = 1.0;
    const auto test = [&](double p, double q) { if (std::abs(p) < kDimensionEpsilon) return q >= 0.0; const double ratio = q / p; if (p < 0.0) { if (ratio > high) return false; if (ratio > low) low = ratio; } else { if (ratio < low) return false; if (ratio < high) high = ratio; } return true; };
    if (!test(-dx, first.x.value - clip.x.value) || !test(dx, clip.right().value - first.x.value) || !test(-dy, first.y.value - clip.y.value) || !test(dy, clip.bottom().value - first.y.value)) return false;
    const Point original = first; first = {{original.x.value + low * dx}, {original.y.value + low * dy}}; second = {{original.x.value + high * dx}, {original.y.value + high * dy}}; return true;
}

void append_cell_text(PathDocument& result, const TableElement& table, const TableCell& cell, const Rect& cell_bounds, const FontRegistry& fonts, const std::string& font_id, Points default_size, Millimetres padding, std::int64_t& glyph_index) {
    const Rect clip{{cell_bounds.x.value + padding.value}, {cell_bounds.y.value + padding.value}, {cell_bounds.width.value - 2.0 * padding.value}, {cell_bounds.height.value - 2.0 * padding.value}};
    if (!clip.has_positive_area()) return;
    double baseline = clip.y.value;
    const std::string group = table.id + ":r" + std::to_string(cell.row) + "c" + std::to_string(cell.column);
    for (const Paragraph& paragraph : cell.paragraphs) {
        double max_line = 0.0;
        for (const TextRun& run : paragraph.runs) {
            const Points size = run.style.font_size.value_or(default_size); if (size.value <= 0.0) throw std::invalid_argument("table cell text requires a positive font size");
            const ResolvedGlyph probe = fonts.resolve(font_id, static_cast<std::uint32_t>('?'));
            max_line = std::max(max_line, to_millimetres(size).value * std::max(1.2, static_cast<double>(probe.ascender - probe.descender + probe.line_gap) / static_cast<double>(probe.units_per_em)));
        }
        if (max_line == 0.0) continue;
        baseline += max_line;
        double x = clip.x.value;
        for (const TextRun& run : paragraph.runs) {
            const Points size = run.style.font_size.value_or(default_size); const Millimetres size_mm = to_millimetres(size);
            for (const auto& [codepoint, utf8] : decode_utf8(run.text)) {
                if (codepoint == '\n' || codepoint == '\r') { baseline += max_line; x = clip.x.value; continue; }
                const ResolvedGlyph glyph = fonts.resolve(font_id, codepoint); const double scale = size_mm.value / static_cast<double>(glyph.units_per_em);
                for (const FontStroke& contour : fonts.glyph_geometry(glyph.font_id, glyph.glyph_codepoint).strokes) {
                    for (std::size_t point = 1; point < contour.points.size(); ++point) {
                        Point first{{x + contour.points[point - 1].x.value * scale}, {baseline - contour.points[point - 1].y.value * scale}}; Point second{{x + contour.points[point].x.value * scale}, {baseline - contour.points[point].y.value * scale}};
                        if (!clip_line(first, second, clip) || same_point(first, second)) continue;
                        Stroke stroke; stroke.id = result.strokes.size(); stroke.points = {first, second}; stroke.glyph_index = glyph_index; stroke.source_page_index = static_cast<std::int64_t>(table.source_page); stroke.character = utf8; stroke.element_id = table.id; stroke.element_type = "table-cell-text"; stroke.font_role = "table-cell"; stroke.font_sha256 = glyph.font_sha256; stroke.source_glyph_indices = {glyph_index}; stroke.source_characters = utf8; stroke.semantic_role = "table-cell-text"; stroke.layout_group = group; stroke.segment_types = {"glyph", "table-cell-text"}; result.strokes.push_back(std::move(stroke));
                    }
                }
                ++glyph_index; x += font_units_to_millimetres(glyph.advance, size_mm, glyph.units_per_em).value;
            }
        }
        baseline += paragraph.space_after.value_or(Millimetres{}).value;
    }
}

[[nodiscard]] std::string source_order(std::uint32_t value) {
    return std::to_string(value);
}

}  // namespace

TablePathBuilder::TablePathBuilder(const FontRegistry& fonts, std::string font_id, Points font_size, Millimetres cell_padding)
    : fonts_(&fonts), font_id_(std::move(font_id)), font_size_(font_size), cell_padding_(cell_padding) {
    if (font_id_.empty() || font_size_.value <= 0.0 || cell_padding_.value < 0.0) throw std::invalid_argument("table text builder requires a font id, positive size, and nonnegative padding");
}

PathDocument TablePathBuilder::build(const TableElement& table, Millimetres page_width,
                                     Millimetres page_height) const {
    PathDocument result;
    result.page_width = page_width;
    result.page_height = page_height;
    result.metadata.emplace_back("coordinate_system", "page-mm-top-left");
    result.metadata.emplace_back("pipeline", "table-borders");
    result.metadata.emplace_back("table_id", table.id);
    result.metadata.emplace_back("table_source_kind", table.source_kind);
    result.metadata.emplace_back("table_source_order", source_order(table.source_order));

    if (!table.bounds || !table.bounds->has_positive_area()) {
        result.warnings.push_back("table_bounds_missing_or_invalid:" + table.id);
        return result;
    }
    if (table.rows == 0 || table.columns == 0) {
        result.warnings.push_back("table_grid_empty:" + table.id);
        return result;
    }
    for (const TableCell& cell : table.cells) {
        for (const Paragraph& paragraph : cell.paragraphs) {
            if (!fonts_ && std::any_of(paragraph.runs.begin(), paragraph.runs.end(), [](const TextRun& run) { return !run.text.empty(); }))
                throw std::runtime_error("table cell text path building is not implemented");
        }
    }

    std::vector<std::optional<Millimetres>> column_preferences;
    column_preferences.reserve(table.column_widths.size());
    for (const Millimetres width : table.column_widths) column_preferences.push_back(width);
    const auto widths = resolve_dimensions(table.columns, table.bounds->width.value, column_preferences, table.cells, true);
    const auto heights = resolve_dimensions(table.rows, table.bounds->height.value, table.row_heights, table.cells, false);
    const auto xs = offsets(table.bounds->x.value, widths);
    const auto ys = offsets(table.bounds->y.value, heights);

    std::vector<Segment> segments;
    std::int64_t next_glyph{};
    for (const TableCell& cell : table.cells) {
        const std::size_t row = cell.row;
        const std::size_t column = cell.column;
        const std::size_t row_end = std::min<std::size_t>(table.rows, row + std::max(1U, cell.row_span));
        const std::size_t column_end = std::min<std::size_t>(table.columns, column + std::max(1U, cell.column_span));
        if (row >= table.rows || column >= table.columns || row_end <= row || column_end <= column) {
            result.warnings.push_back("table_cell_outside_grid:" + table.id);
            continue;
        }
        const double left = xs[column];
        const double right = xs[column_end];
        const double top = ys[row];
        const double bottom = ys[row_end];
        if (cell.borders.top) append_unique(segments, {{{left}, {top}}, {{right}, {top}}});
        if (cell.borders.right) append_unique(segments, {{{right}, {top}}, {{right}, {bottom}}});
        if (cell.borders.bottom) append_unique(segments, {{{right}, {bottom}}, {{left}, {bottom}}});
        if (cell.borders.left) append_unique(segments, {{{left}, {bottom}}, {{left}, {top}}});
        if (fonts_) append_cell_text(result, table, cell, {{left}, {top}, {right - left}, {bottom - top}}, *fonts_, font_id_, font_size_, cell_padding_, next_glyph);
    }

    for (const Segment& segment : segments) {
        Stroke stroke;
        stroke.id = result.strokes.size();
        stroke.points = {segment.first, segment.second};
        stroke.element_id = table.id;
        stroke.element_type = "table";
        stroke.source_page_index = static_cast<std::int64_t>(table.source_page);
        stroke.semantic_role = "table-border";
        stroke.segment_types = {"table-border"};
        stroke.preserve_order = true;
        result.strokes.push_back(std::move(stroke));
    }
    return result;
}

}  // namespace plotter::doc
