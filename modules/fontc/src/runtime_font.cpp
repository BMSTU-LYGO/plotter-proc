#include "fontc/runtime_font.hpp"

#include <limits>
#include <stdexcept>

namespace fontc {

RuntimeFont::RuntimeFont(const std::filesystem::path& pfc_path)
    : font_(PfcFont::load(pfc_path)) {
    if (font_.find(static_cast<std::uint32_t>('?')) == nullptr) {
        throw PfcError("PFC is missing required fallback glyph '?'");
    }
}

const CompiledGlyph& RuntimeFont::lookup(std::uint32_t codepoint) const {
    const CompiledGlyph* glyph = font_.lookup(codepoint);
    if (glyph == nullptr) throw PfcError("PFC lookup failed: fallback glyph is unavailable");
    return *glyph;
}

RuntimeWord RuntimeFont::build_word(std::u32string_view text) const {
    RuntimeWord word;
    for (const char32_t character : text) {
        const CompiledGlyph& glyph = lookup(static_cast<std::uint32_t>(character));
        for (const CompiledStroke& source : glyph.strokes) {
            CompiledStroke stroke;
            stroke.points.reserve(source.points.size());
            for (const PointFU point : source.points) {
                const std::int64_t translated = static_cast<std::int64_t>(point.x) + word.advance_font_units;
                if (translated < std::numeric_limits<std::int32_t>::min() ||
                    translated > std::numeric_limits<std::int32_t>::max()) {
                    throw std::overflow_error("runtime word coordinate exceeds int32");
                }
                stroke.points.push_back({static_cast<std::int32_t>(translated), point.y});
            }
            word.strokes.push_back(std::move(stroke));
        }
        word.advance_font_units += glyph.advance_font_units;
    }
    return word;
}

}  // namespace fontc
