#include "fontc/compiled_font.hpp"

#include <limits>
#include <stdexcept>

namespace fontc {
PointStorageWidth point_storage_width(const CompiledGlyph& glyph) noexcept {
    constexpr auto lo = std::numeric_limits<std::int16_t>::min();
    constexpr auto hi = std::numeric_limits<std::int16_t>::max();
    for (const auto& stroke : glyph.strokes) for (const PointFU point : stroke.points)
        if (point.x < lo || point.x > hi || point.y < lo || point.y > hi) return PointStorageWidth::int32;
    return PointStorageWidth::int16;
}
void validate_compiled_glyph(const CompiledGlyph& glyph) {
    if (glyph.codepoint > 0x10FFFFU || (glyph.codepoint >= 0xD800U && glyph.codepoint <= 0xDFFFU))
        throw std::invalid_argument("Compiled glyph codepoint is not a Unicode scalar value");
    for (const auto& stroke : glyph.strokes) if (stroke.points.empty())
        throw std::invalid_argument("Compiled glyph contains an empty stroke");
}
}  // namespace fontc
