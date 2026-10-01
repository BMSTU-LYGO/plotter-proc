#include "plotter/doc/font_registry.hpp"

#include "fontc/runtime_font.hpp"

#include <stdexcept>
#include <utility>

namespace plotter::doc {

void FontRegistry::register_pfc(FontRegistration registration) {
    if (registration.id.empty()) throw std::invalid_argument("font id must not be empty");
    if (registration.pfc_path.empty()) throw std::invalid_argument("PFC path must not be empty");
    if (entries_.contains(registration.id)) throw std::invalid_argument("font id is already registered");
    const std::string id = registration.id;
    auto runtime = std::make_shared<fontc::RuntimeFont>(registration.pfc_path);
    entries_.emplace(id, Entry{std::move(registration), std::move(runtime)});
}

void FontRegistry::set_fallback_font(std::string id) {
    if (!contains(id)) throw std::invalid_argument("fallback font is not registered");
    fallback_font_id_ = std::move(id);
}

bool FontRegistry::contains(std::string_view id) const noexcept { return entries_.contains(id); }

const FontRegistration& FontRegistry::font(std::string_view id) const { return entry(id).registration; }

const FontRegistry::Entry& FontRegistry::entry(std::string_view id) const {
    const auto found = entries_.find(id);
    if (found == entries_.end()) throw std::out_of_range("requested font is not registered");
    return found->second;
}

ResolvedGlyph FontRegistry::resolve(std::string_view requested_font_id, std::uint32_t codepoint) const {
    const Entry& requested = entry(requested_font_id);
    const Entry* selected = &requested;
    const fontc::CompiledGlyph* glyph = requested.runtime->contains(codepoint)
        ? &requested.runtime->lookup(codepoint) : nullptr;
    if (glyph == nullptr && !fallback_font_id_.empty()) {
        const Entry& fallback = entry(fallback_font_id_);
        if (fallback.runtime->contains(codepoint)) {
            selected = &fallback;
            glyph = &fallback.runtime->lookup(codepoint);
        }
    }
    if (glyph == nullptr) glyph = &requested.runtime->lookup(codepoint);
    const fontc::FontMetrics& metrics = selected->runtime->metrics();
    if (metrics.units_per_em <= 0) throw std::runtime_error("PFC units_per_em must be positive");
    return {selected->registration.id, selected->registration.sha256, codepoint, glyph->codepoint,
            {static_cast<double>(glyph->advance_font_units)}, metrics.units_per_em, metrics.ascender,
            metrics.descender, metrics.line_gap, glyph->codepoint != codepoint};
}

}  // namespace plotter::doc

namespace plotter::doc {
GlyphGeometry FontRegistry::glyph_geometry(std::string_view font_id, std::uint32_t codepoint) const {
    const fontc::CompiledGlyph& glyph = entry(font_id).runtime->lookup(codepoint);
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
