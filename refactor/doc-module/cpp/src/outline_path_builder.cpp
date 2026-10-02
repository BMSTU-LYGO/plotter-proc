#include "plotter/doc/outline_path_builder.hpp"

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <limits>
#include <map>
#include <memory>
#include <stdexcept>
#include <utility>
#include <vector>

#include <ft2build.h>
#include FT_FREETYPE_H
#include FT_OUTLINE_H
#include FT_SYNTHESIS_H

namespace plotter::doc {
namespace {

struct RawPoint final { double x{}, y{}; };
struct DecomposeContext final {
    std::vector<std::vector<RawPoint>> contours;
    std::vector<RawPoint> current;
    double origin_x{}, baseline_y{}, scale{};
    bool italic{};
    double tolerance{};
    std::size_t maximum_points{};
    bool overflow{};
};

void append(DecomposeContext& context, RawPoint point) {
    if (context.overflow) return;
    if (!context.current.empty() && std::hypot(context.current.back().x - point.x, context.current.back().y - point.y) < 0.03) return;
    if (context.current.size() >= context.maximum_points) { context.overflow = true; return; }
    context.current.push_back(point);
}

[[nodiscard]] RawPoint transform(const FT_Vector& point, const DecomposeContext& context) {
    // FreeType's synthetic oblique is a shear in font space.
    // Applying it here keeps the positioned glyph's page-space origin intact.
    constexpr double kItalicShear = 0.2125565616700221;
    const double oblique_x = static_cast<double>(point.x) + (context.italic ? static_cast<double>(point.y) * kItalicShear : 0.0);
    return {context.origin_x + oblique_x * context.scale,
            context.baseline_y - static_cast<double>(point.y) * context.scale};
}

[[nodiscard]] double distance_to_chord(RawPoint point, RawPoint start, RawPoint end) {
    const double dx = end.x - start.x; const double dy = end.y - start.y;
    const double squared = dx * dx + dy * dy;
    if (squared == 0.0) return std::hypot(point.x - start.x, point.y - start.y);
    return std::abs(dy * point.x - dx * point.y + end.x * start.y - end.y * start.x) / std::sqrt(squared);
}

void quadratic(DecomposeContext& context, RawPoint start, RawPoint control, RawPoint end, unsigned depth = 0U) {
    if (context.overflow) return;
    if (depth >= 20U || distance_to_chord(control, start, end) <= context.tolerance) { append(context, end); return; }
    const RawPoint left_mid{(start.x + control.x) / 2.0, (start.y + control.y) / 2.0};
    const RawPoint right_mid{(control.x + end.x) / 2.0, (control.y + end.y) / 2.0};
    const RawPoint split{(left_mid.x + right_mid.x) / 2.0, (left_mid.y + right_mid.y) / 2.0};
    quadratic(context, start, left_mid, split, depth + 1U);
    quadratic(context, split, right_mid, end, depth + 1U);
}

void cubic(DecomposeContext& context, RawPoint start, RawPoint first, RawPoint second, RawPoint end, unsigned depth = 0U) {
    if (context.overflow) return;
    if (depth >= 20U || std::max(distance_to_chord(first, start, end), distance_to_chord(second, start, end)) <= context.tolerance) { append(context, end); return; }
    const RawPoint a{(start.x + first.x) / 2.0, (start.y + first.y) / 2.0};
    const RawPoint b{(first.x + second.x) / 2.0, (first.y + second.y) / 2.0};
    const RawPoint c{(second.x + end.x) / 2.0, (second.y + end.y) / 2.0};
    const RawPoint d{(a.x + b.x) / 2.0, (a.y + b.y) / 2.0};
    const RawPoint e{(b.x + c.x) / 2.0, (b.y + c.y) / 2.0};
    const RawPoint split{(d.x + e.x) / 2.0, (d.y + e.y) / 2.0};
    cubic(context, start, a, d, split, depth + 1U);
    cubic(context, split, e, c, end, depth + 1U);
}

int move_to(const FT_Vector* point, void* user) {
    auto& context = *static_cast<DecomposeContext*>(user);
    if (context.current.size() >= 2U) context.contours.push_back(std::move(context.current));
    context.current.clear(); append(context, transform(*point, context)); return 0;
}
int line_to(const FT_Vector* point, void* user) {
    auto& context = *static_cast<DecomposeContext*>(user); append(context, transform(*point, context)); return 0;
}
int conic_to(const FT_Vector* control, const FT_Vector* point, void* user) {
    auto& context = *static_cast<DecomposeContext*>(user);
    if (context.current.empty()) return 1;
    quadratic(context, context.current.back(), transform(*control, context), transform(*point, context)); return 0;
}
int cubic_to(const FT_Vector* first, const FT_Vector* second, const FT_Vector* point, void* user) {
    auto& context = *static_cast<DecomposeContext*>(user);
    if (context.current.empty()) return 1;
    cubic(context, context.current.back(), transform(*first, context), transform(*second, context), transform(*point, context)); return 0;
}

class Face final {
public:
    explicit Face(const std::filesystem::path& path) {
        if (FT_Init_FreeType(&library_) != 0) throw std::runtime_error("cannot initialize FreeType");
        const auto native = path.string();
        if (FT_New_Face(library_, native.c_str(), 0, &face_) != 0) { FT_Done_FreeType(library_); library_ = nullptr; throw std::runtime_error("cannot open outline font: " + native); }
    }
    ~Face() { if (face_) FT_Done_Face(face_); if (library_) FT_Done_FreeType(library_); }
    [[nodiscard]] FT_Face get() const noexcept { return face_; }
private:
    FT_Library library_{}; FT_Face face_{};
};

}  // namespace

static void validate_options(const OutlinePathOptions& options) {
    if (!(options.flattening_tolerance_mm > 0.0) || !std::isfinite(options.flattening_tolerance_mm)) throw std::invalid_argument("outline flattening tolerance must be positive");
    if (options.maximum_points_per_contour < 3U) throw std::invalid_argument("outline contour point bound must be at least three");
}

OutlinePathBuilder::OutlinePathBuilder(std::filesystem::path font_path, OutlinePathOptions options)
    : font_path_(std::move(font_path)), options_(options) {
    if (font_path_.empty()) throw std::invalid_argument("outline font path is empty");
    validate_options(options_);
}

OutlinePathBuilder::OutlinePathBuilder(const FontRegistry& fonts, OutlinePathOptions options)
    : fonts_(&fonts), options_(options) { validate_options(options_); }

PathDocument OutlinePathBuilder::build(const LayoutPage& page, Millimetres page_width, Millimetres page_height) const {
    if (!(page_width.value > 0.0) || !(page_height.value > 0.0)) throw std::invalid_argument("page dimensions must be positive");
    std::map<std::filesystem::path, std::unique_ptr<Face>> faces;
    PathDocument result; result.page_width = page_width; result.page_height = page_height;
    result.metadata = {{"coordinate_system", "page-mm-top-left"}, {"pipeline", "freetype-outline"}};
    const std::optional<std::string> element_id = page.source_element_ids.size() == 1U ? std::optional<std::string>{page.source_element_ids.front()} : std::nullopt;
    FT_Outline_Funcs callbacks{move_to, line_to, conic_to, cubic_to, 0, 0};
    for (const PositionedGlyph& glyph : page.glyphs) {
        const std::filesystem::path& selected_path = fonts_ != nullptr && glyph.font_id ? fonts_->outline_font_path(*glyph.font_id) : font_path_;
        if (selected_path.empty()) throw std::invalid_argument("positioned glyph has no outline font source");
        auto [face_entry, inserted] = faces.try_emplace(selected_path);
        if (inserted) face_entry->second = std::make_unique<Face>(selected_path);
        Face& font = *face_entry->second;
        if (!(glyph.scale_mm_per_font_unit > 0.0) || !std::isfinite(glyph.scale_mm_per_font_unit)) throw std::invalid_argument("positioned glyph has invalid outline scale");
        const FT_UInt glyph_index = FT_Get_Char_Index(font.get(), static_cast<FT_ULong>(glyph.codepoint));
        if (glyph_index == 0U) throw std::runtime_error("outline font is missing positioned glyph");
        if (FT_Load_Glyph(font.get(), glyph_index, FT_LOAD_NO_SCALE | FT_LOAD_NO_HINTING | FT_LOAD_NO_BITMAP) != 0) throw std::runtime_error("cannot load outline glyph");
        const FT_GlyphSlot slot = font.get()->glyph;
        if (glyph.bold) FT_GlyphSlot_Embolden(slot);
        if (slot->format != FT_GLYPH_FORMAT_OUTLINE) continue;
        DecomposeContext context{{}, {}, glyph.x.value, glyph.baseline_y.value, glyph.scale_mm_per_font_unit, glyph.italic, options_.flattening_tolerance_mm, options_.maximum_points_per_contour, false};
        if (FT_Outline_Decompose(&slot->outline, &callbacks, &context) != 0 || context.overflow) throw std::runtime_error("cannot safely decompose outline glyph");
        if (context.current.size() >= 2U) context.contours.push_back(std::move(context.current));
        for (std::size_t contour = 0; contour < context.contours.size(); ++contour) {
            auto& points = context.contours[contour];
            if (points.size() < 2U) continue;
            if (points.front().x != points.back().x || points.front().y != points.back().y) points.push_back(points.front());
            if (points.size() < 3U) continue;
            Stroke stroke; stroke.id = result.strokes.size(); stroke.contour_index = static_cast<std::int64_t>(contour);
            stroke.glyph_index = static_cast<std::int64_t>(glyph.glyph_index); stroke.word_index = static_cast<std::int64_t>(glyph.word_index);
            stroke.source_page_index = static_cast<std::int64_t>(page.page_index); stroke.character = glyph.character; stroke.element_id = element_id;
            stroke.element_type = glyph.text_role == "page-number" ? "page-number" : "text"; stroke.font_role = glyph.text_role == "page-number" ? "page-number" : "body";
            stroke.font_sha256 = glyph.font_sha256; stroke.source_path = selected_path.string(); stroke.source_glyph_indices = {static_cast<std::int64_t>(glyph.glyph_index)};
            stroke.source_characters = glyph.character; stroke.segment_types = {"outline-glyph"}; stroke.closed = true;
            for (const RawPoint point : points) stroke.points.push_back({{point.x}, {point.y}});
            result.strokes.push_back(std::move(stroke));
        }
    }
    return result;
}

}  // namespace plotter::doc
