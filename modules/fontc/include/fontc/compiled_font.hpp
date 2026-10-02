#pragma once

#include "fontc/font_metrics.hpp"

#include <cstdint>
#include <vector>

namespace fontc {

struct PointFU {
    std::int32_t x = 0;
    std::int32_t y = 0;
    [[nodiscard]] friend constexpr bool operator==(PointFU, PointFU) = default;
};

enum class PointStorageWidth : std::uint8_t { int16 = 2, int32 = 4 };

struct CompiledStroke { std::vector<PointFU> points; };

struct CompiledGlyph {
    std::uint32_t codepoint = 0;
    std::int32_t advance_font_units = 0;
    std::vector<CompiledStroke> strokes;
};

struct CompiledFont {
    FontMetrics metrics;
    std::vector<CompiledGlyph> glyphs;
};

[[nodiscard]] PointStorageWidth point_storage_width(const CompiledGlyph& glyph) noexcept;
void validate_compiled_glyph(const CompiledGlyph& glyph);

}  // namespace fontc
