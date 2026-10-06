#include "plotter/doc/font_registry.hpp"

#include "fontc/runtime_font.hpp"

#include <ft2build.h>
#include FT_FREETYPE_H

#include <algorithm>
#include <limits>
#include <stdexcept>
#include <utility>

namespace plotter::doc {

struct FreeTypeHandle final {
    FT_Library library{};
    FT_Face face{};
    explicit FreeTypeHandle(const std::filesystem::path& path) {
        if (FT_Init_FreeType(&library) != 0) throw std::runtime_error("cannot initialize FreeType");
        const auto native = path.string();
        if (FT_New_Face(library, native.c_str(), 0, &face) != 0) {
            FT_Done_FreeType(library); library = nullptr;
            throw std::runtime_error("cannot open outline font: " + native);
        }
    }
    ~FreeTypeHandle() { if (face) FT_Done_Face(face); if (library) FT_Done_FreeType(library); }
    FreeTypeHandle(const FreeTypeHandle&) = delete;
    FreeTypeHandle& operator=(const FreeTypeHandle&) = delete;
};

void FontRegistry::register_pfc(FontRegistration registration) {
    if (registration.id.empty()) throw std::invalid_argument("font id must not be empty");
    if (registration.pfc_path.empty()) throw std::invalid_argument("PFC path must not be empty");
    if (entries_.contains(registration.id)) throw std::invalid_argument("font id is already registered");
    const std::string id = registration.id;
    auto runtime = std::make_shared<fontc::RuntimeFont>(registration.pfc_path);
    if (registration.sha256.empty()) {
        constexpr char hex[] = "0123456789abcdef";
        for (const std::uint8_t byte : runtime->metadata().font_hash) {
            registration.sha256 += hex[byte >> 4U];
            registration.sha256 += hex[byte & 0x0FU];
        }
    }
    entries_.emplace(id, Entry{std::move(registration), std::move(runtime), {}});
}

void FontRegistry::register_outline_font(FontRegistration registration) {
    if (registration.id.empty()) throw std::invalid_argument("font id must not be empty");
    if (registration.pfc_path.empty()) throw std::invalid_argument("outline font path must not be empty");
    if (entries_.contains(registration.id)) throw std::invalid_argument("font id is already registered");
    const std::string id = registration.id;
    auto outline = std::make_shared<FreeTypeHandle>(registration.pfc_path);
    entries_.emplace(id, Entry{std::move(registration), {}, std::move(outline)});
}

void FontRegistry::set_fallback_font(std::string id) {
    fallback_font_ids_.clear();
    add_fallback_font(std::move(id));
}

void FontRegistry::add_fallback_font(std::string id) {
    if (!contains(id)) throw std::invalid_argument("fallback font is not registered");
    if (std::find(fallback_font_ids_.begin(), fallback_font_ids_.end(), id) == fallback_font_ids_.end())
        fallback_font_ids_.push_back(std::move(id));
}

void FontRegistry::set_digit_font(std::string id) {
    if (!contains(id)) throw std::invalid_argument("digit font is not registered");
    digit_font_id_ = std::move(id);
}

bool FontRegistry::contains(std::string_view id) const noexcept { return entries_.contains(id); }

const FontRegistration& FontRegistry::font(std::string_view id) const { return entry(id).registration; }

const std::filesystem::path& FontRegistry::outline_font_path(std::string_view id) const {
    const Entry& selected = entry(id);
    if (!selected.outline) throw std::runtime_error("registered font has no outline source");
    return selected.registration.pfc_path;
}

const FontRegistry::Entry& FontRegistry::entry(std::string_view id) const {
    const auto found = entries_.find(id);
    if (found == entries_.end()) throw std::out_of_range("requested font is not registered");
    return found->second;
}

ResolvedGlyph FontRegistry::resolve(std::string_view requested_font_id, std::uint32_t codepoint) const {
    const Entry& requested = entry(requested_font_id);
    const auto contains_glyph = [](const Entry& item, std::uint32_t value) {
        if (item.runtime) return item.runtime->contains(value);
        return FT_Get_Char_Index(item.outline->face, static_cast<FT_ULong>(value)) != 0U;
    };
    const Entry* selected = &requested;
    std::uint32_t selected_codepoint = codepoint;
    if (codepoint >= '0' && codepoint <= '9' && !digit_font_id_.empty() &&
        contains_glyph(entry(digit_font_id_), codepoint)) {
        selected = &entry(digit_font_id_);
    } else if (!contains_glyph(requested, codepoint)) {
        bool found = false;
        for (const std::string& id : fallback_font_ids_) {
            const Entry& candidate = entry(id);
            if (contains_glyph(candidate, codepoint)) {
                selected = &candidate;
                found = true;
                break;
            }
        }
        if (!found) selected_codepoint = '?';
    }
    if (selected->runtime) {
        const auto& glyph = selected->runtime->lookup(selected_codepoint);
        const auto& metrics = selected->runtime->metrics();
        if (metrics.units_per_em <= 0) throw std::runtime_error("PFC units_per_em must be positive");
        return {selected->registration.id, selected->registration.sha256, codepoint, glyph.codepoint,
                {static_cast<double>(glyph.advance_font_units)}, metrics.units_per_em, metrics.ascender,
                metrics.descender, metrics.line_gap, selected != &requested || glyph.codepoint != codepoint};
    }
    FT_Face face = selected->outline->face;
    const FT_UInt glyph_index = FT_Get_Char_Index(face, static_cast<FT_ULong>(selected_codepoint));
    if (!glyph_index || FT_Load_Glyph(face, glyph_index, FT_LOAD_NO_SCALE | FT_LOAD_NO_HINTING | FT_LOAD_NO_BITMAP) != 0)
        throw std::runtime_error("outline font has no usable glyph");
    const auto units = static_cast<std::int32_t>(face->units_per_EM);
    if (units <= 0) throw std::runtime_error("outline font has invalid units_per_em");
    return {selected->registration.id, selected->registration.sha256, codepoint, selected_codepoint,
            {static_cast<double>(face->glyph->metrics.horiAdvance)}, units,
            static_cast<std::int32_t>(face->ascender), static_cast<std::int32_t>(face->descender),
            static_cast<std::int32_t>(face->height - (face->ascender - face->descender)), selected != &requested || selected_codepoint != codepoint};
}

}  // namespace plotter::doc

namespace plotter::doc {
std::optional<std::pair<FontUnits, FontUnits>> FontRegistry::glyph_vertical_bounds(
    std::string_view font_id, std::uint32_t codepoint) const {
    const Entry& selected = entry(font_id);
    if (!selected.runtime) return std::nullopt;
    const auto& glyph = selected.runtime->lookup(codepoint);
    double bottom = std::numeric_limits<double>::infinity();
    double top = -std::numeric_limits<double>::infinity();
    for (const auto& stroke : glyph.strokes) {
        for (const auto& point : stroke.points) {
            bottom = std::min(bottom, static_cast<double>(point.y));
            top = std::max(top, static_cast<double>(point.y));
        }
    }
    if (bottom > top) return std::nullopt;
    return std::pair{FontUnits{bottom}, FontUnits{top}};
}

GlyphGeometry FontRegistry::glyph_geometry(std::string_view font_id, std::uint32_t codepoint) const {
    const Entry& selected = entry(font_id);
    if (!selected.runtime) throw std::runtime_error("centerline glyph geometry requires a PFC font");
    const fontc::CompiledGlyph& glyph = selected.runtime->lookup(codepoint);
    GlyphGeometry result;
    result.glyph_codepoint = glyph.codepoint;
    result.strokes.reserve(glyph.strokes.size());
    for (const auto& source : glyph.strokes) {
        FontStroke stroke;
        stroke.points.reserve(source.points.size());
        for (const auto point : source.points) {
            stroke.points.push_back({{static_cast<double>(point.x)}, {static_cast<double>(point.y)}});
        }
        result.strokes.push_back(std::move(stroke));
    }
    return result;
}
}  // namespace plotter::doc
