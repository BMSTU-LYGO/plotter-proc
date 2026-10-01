#include "plotter/doc/math_path_builder.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <optional>
#include <string_view>
#include <utility>
#include <vector>

namespace plotter::doc {
namespace {

struct DecodedCharacter final { std::uint32_t codepoint{}; std::string utf8; };
struct RawPoint final { double x{}, y{}; };
struct RawStroke final { std::vector<RawPoint> points; std::size_t character_index{}; };

[[nodiscard]] MathPathBuildError error(std::string code, std::string message) {
    return {std::move(code), std::move(message)};
}

[[nodiscard]] std::optional<std::vector<DecodedCharacter>> decode_utf8(std::string_view text) {
    std::vector<DecodedCharacter> output;
    for (std::size_t index = 0; index < text.size();) {
        const unsigned char first = static_cast<unsigned char>(text[index]);
        std::uint32_t codepoint = 0;
        std::size_t length = 0;
        if (first < 0x80U) { codepoint = first; length = 1; }
        else if ((first & 0xE0U) == 0xC0U && index + 1 < text.size()) {
            codepoint = (static_cast<std::uint32_t>(first & 0x1FU) << 6U) |
                        (static_cast<unsigned char>(text[index + 1]) & 0x3FU);
            length = codepoint >= 0x80U ? 2U : 0U;
        } else if ((first & 0xF0U) == 0xE0U && index + 2 < text.size()) {
            codepoint = (static_cast<std::uint32_t>(first & 0x0FU) << 12U) |
                        (static_cast<std::uint32_t>(static_cast<unsigned char>(text[index + 1]) & 0x3FU) << 6U) |
                        (static_cast<unsigned char>(text[index + 2]) & 0x3FU);
            length = (codepoint >= 0x800U && !(codepoint >= 0xD800U && codepoint <= 0xDFFFU)) ? 3U : 0U;
        } else if ((first & 0xF8U) == 0xF0U && index + 3 < text.size()) {
            codepoint = (static_cast<std::uint32_t>(first & 0x07U) << 18U) |
                        (static_cast<std::uint32_t>(static_cast<unsigned char>(text[index + 1]) & 0x3FU) << 12U) |
                        (static_cast<std::uint32_t>(static_cast<unsigned char>(text[index + 2]) & 0x3FU) << 6U) |
                        (static_cast<unsigned char>(text[index + 3]) & 0x3FU);
            length = codepoint >= 0x10000U && codepoint <= 0x10FFFFU ? 4U : 0U;
        }
        if (length == 0U) return std::nullopt;
        for (std::size_t continuation = 1; continuation < length; ++continuation)
            if ((static_cast<unsigned char>(text[index + continuation]) & 0xC0U) != 0x80U) return std::nullopt;
        output.push_back({codepoint, std::string{text.substr(index, length)}});
        index += length;
    }
    return output;
}

[[nodiscard]] bool is_linear_source(const MathElement& element) {
    if (element.source_syntax.empty() || element.source_syntax == "omml" ||
        element.source_syntax == "pdf-text-layer-heuristic" || element.source_syntax == "plain") {
        return element.expression.find_first_of("\\^_{}") == std::string::npos;
    }
    return false;
}

void append_unique(std::vector<Point>& output, Point value) {
    if (output.empty() || output.back().x.value != value.x.value || output.back().y.value != value.y.value)
        output.push_back(value);
}

}  // namespace

MathPathBuildResult MathPathBuilder::build(const MathElement& element,
                                           const MathPathBuildOptions& options) const {
    if (element.visual_image_path)
        return error("unsupported_visual_math", "math element '" + element.id + "' has a visual image; raster math vectorization is not available");
    if (!is_linear_source(element))
        return error("unsupported_math_syntax", "math element '" + element.id + "' requires structural math layout: " + element.source_syntax);
    if (!element.bounds || !element.bounds->has_positive_area())
        return error("missing_math_bounds", "math element '" + element.id + "' needs positive bounds for safe placement");
    if (options.font_id.empty() || options.font_size.value <= 0.0)
        return error("invalid_math_font", "math path building needs a PFC font id and a positive font size");
    if (options.page_width.value <= 0.0 || options.page_height.value <= 0.0)
        return error("invalid_page_bounds", "math path building needs positive page dimensions");
    const Rect bounds = *element.bounds;
    if (bounds.x.value < 0.0 || bounds.y.value < 0.0 || bounds.right().value > options.page_width.value ||
        bounds.bottom().value > options.page_height.value)
        return error("math_bounds_outside_page", "math element '" + element.id + "' is outside page bounds");
    const auto decoded = decode_utf8(element.expression);
    if (!decoded) return error("invalid_math_utf8", "math element '" + element.id + "' has invalid UTF-8");
    if (decoded->empty()) return error("empty_math_expression", "math element '" + element.id + "' has no linear expression");

    std::vector<RawStroke> raw_strokes;
    std::vector<ResolvedGlyph> glyphs;
    glyphs.reserve(decoded->size());
    double cursor_x = 0.0;
    double min_x = std::numeric_limits<double>::infinity();
    double min_y = std::numeric_limits<double>::infinity();
    double max_x = -std::numeric_limits<double>::infinity();
    double max_y = -std::numeric_limits<double>::infinity();
    for (std::size_t character_index = 0; character_index < decoded->size(); ++character_index) {
        ResolvedGlyph resolved;
        GlyphGeometry geometry;
        try {
            resolved = fonts_.resolve(options.font_id, (*decoded)[character_index].codepoint);
            geometry = fonts_.glyph_geometry(resolved.font_id, resolved.glyph_codepoint);
        } catch (const std::exception& exception) {
            return error("invalid_math_font", "math element '" + element.id + "' could not resolve its PFC glyph: " + exception.what());
        }
        const double glyph_scale = to_millimetres(options.font_size).value / static_cast<double>(resolved.units_per_em);
        for (const FontStroke& source_stroke : geometry.strokes) {
            RawStroke stroke;
            stroke.character_index = character_index;
            for (const FontPoint point : source_stroke.points) {
                const RawPoint raw{cursor_x + point.x.value * glyph_scale, -point.y.value * glyph_scale};
                if (stroke.points.empty() || stroke.points.back().x != raw.x || stroke.points.back().y != raw.y)
                    stroke.points.push_back(raw);
                min_x = std::min(min_x, raw.x); max_x = std::max(max_x, raw.x);
                min_y = std::min(min_y, raw.y); max_y = std::max(max_y, raw.y);
            }
            if (stroke.points.size() >= 2U) raw_strokes.push_back(std::move(stroke));
        }
        cursor_x += resolved.advance.value * glyph_scale;
        glyphs.push_back(resolved);
    }
    if (raw_strokes.empty())
        return error("math_expression_has_no_paths", "math element '" + element.id + "' has no drawable PFC glyph paths");

    const double raw_width = max_x - min_x;
    const double raw_height = max_y - min_y;
    const double fit_x = raw_width > 0.0 ? bounds.width.value / raw_width : 1.0;
    const double fit_y = raw_height > 0.0 ? bounds.height.value / raw_height : 1.0;
    const double scale = std::min({1.0, fit_x, fit_y});
    if (!std::isfinite(scale) || scale <= 0.0)
        return error("invalid_math_geometry", "math element '" + element.id + "' cannot be fitted into its bounds");
    const double rendered_width = raw_width * scale;
    const double rendered_height = raw_height * scale;
    const double offset_x = bounds.x.value + (bounds.width.value - rendered_width) / 2.0 - min_x * scale;
    const double offset_y = bounds.y.value + (bounds.height.value - rendered_height) / 2.0 - min_y * scale;

    PathDocument output;
    output.page_width = options.page_width;
    output.page_height = options.page_height;
    output.metadata = {{"coordinate_system", "page-mm-top-left"}, {"pipeline", "pfc-math-centerline"}};
    for (const RawStroke& raw : raw_strokes) {
        Stroke stroke;
        stroke.id = output.strokes.size();
        stroke.glyph_index = static_cast<std::int64_t>(raw.character_index);
        stroke.contour_index = static_cast<std::int64_t>(stroke.id);
        stroke.source_page_index = static_cast<std::int64_t>(element.source_page);
        stroke.character = (*decoded)[raw.character_index].utf8;
        stroke.element_id = element.id;
        stroke.element_type = "math";
        stroke.font_role = "math";
        stroke.font_sha256 = glyphs[raw.character_index].font_sha256;
        stroke.source_glyph_indices.push_back(static_cast<std::int64_t>(raw.character_index));
        stroke.source_characters = (*decoded)[raw.character_index].utf8;
        stroke.segment_types = {"math-glyph"};
        for (const RawPoint point : raw.points)
            append_unique(stroke.points, {{offset_x + point.x * scale}, {offset_y + point.y * scale}});
        stroke.closed = stroke.points.size() > 2U && stroke.points.front().x.value == stroke.points.back().x.value &&
                        stroke.points.front().y.value == stroke.points.back().y.value;
        if (stroke.points.size() >= (stroke.closed ? 3U : 2U)) output.strokes.push_back(std::move(stroke));
    }
    if (output.strokes.empty())
        return error("math_expression_has_no_paths", "math element '" + element.id + "' has no valid PFC contours");
    return output;
}

}  // namespace plotter::doc
