#include "fontc/rasterizer.hpp"

#include <algorithm>
#include <cstddef>
#include <limits>
#include <string>

namespace fontc {
namespace {

[[nodiscard]] std::uint8_t bitmap_pixel(const FT_Bitmap& bitmap, int x, int y) {
    const int pitch = bitmap.pitch;
    const int row_stride = pitch >= 0 ? pitch : -pitch;
    const int source_y = pitch >= 0 ? y : static_cast<int>(bitmap.rows) - 1 - y;
    const auto* row = bitmap.buffer + static_cast<std::ptrdiff_t>(source_y) * row_stride;
    if (bitmap.pixel_mode == FT_PIXEL_MODE_GRAY) {
        if (bitmap.num_grays <= 1) return row[x] == 0 ? 0 : 255;
        const unsigned int scaled = static_cast<unsigned int>(row[x]) * 255U;
        return static_cast<std::uint8_t>(scaled / (bitmap.num_grays - 1U));
    }
    if (bitmap.pixel_mode == FT_PIXEL_MODE_MONO) {
        return (row[x / 8] & (0x80U >> (x % 8))) == 0 ? 0 : 255;
    }
    throw FreeTypeError("Unsupported FreeType bitmap pixel mode");
}

[[nodiscard]] int checked_dimension(unsigned int value, const char* name) {
    if (value > static_cast<unsigned int>(std::numeric_limits<int>::max())) {
        throw FreeTypeError(std::string("Raster dimension is too large: ") + name);
    }
    return static_cast<int>(value);
}

}  // namespace

RasterGlyph rasterize_glyph(FontFace& font, std::uint32_t codepoint, int resolution) {
    if (resolution <= 0) throw std::invalid_argument("Raster resolution must be positive");
    const auto glyph = font.glyph_metrics(codepoint);
    if (!glyph.has_value()) {
        throw FreeTypeError("Font is missing requested codepoint U+" + std::to_string(codepoint));
    }

    FT_Face face = font.native_handle();
    if (FT_Set_Pixel_Sizes(face, 0, static_cast<FT_UInt>(resolution)) != 0) {
        throw FreeTypeError("Cannot set FreeType raster resolution");
    }
    if (FT_Load_Glyph(face, glyph->glyph_index, FT_LOAD_DEFAULT | FT_LOAD_NO_BITMAP) != 0) {
        throw FreeTypeError("Cannot load glyph outline for rasterization");
    }
    if (FT_Render_Glyph(face->glyph, FT_RENDER_MODE_NORMAL) != 0) {
        throw FreeTypeError("Cannot rasterize glyph outline");
    }

    const FT_GlyphSlot slot = face->glyph;
    const FT_Bitmap& bitmap = slot->bitmap;
    const int bitmap_width = checked_dimension(bitmap.width, "width");
    const int bitmap_height = checked_dimension(bitmap.rows, "height");
    const int padding = std::max(2, resolution / 64);
    if (bitmap_width > std::numeric_limits<int>::max() - 2 * padding ||
        bitmap_height > std::numeric_limits<int>::max() - 2 * padding) {
        throw FreeTypeError("Padded raster dimensions overflow");
    }
    const int width = bitmap_width + 2 * padding;
    const int height = bitmap_height + 2 * padding;
    const auto area = static_cast<std::size_t>(width) * static_cast<std::size_t>(height);
    std::vector<std::uint8_t> pixels(area, 0);

    for (int y = 0; y < bitmap_height; ++y) {
        for (int x = 0; x < bitmap_width; ++x) {
            const auto destination = static_cast<std::size_t>(y + padding) *
                static_cast<std::size_t>(width) + static_cast<std::size_t>(x + padding);
            pixels[destination] = bitmap_pixel(bitmap, x, y);
        }
    }

    return RasterGlyph{
        codepoint,
        glyph->glyph_index,
        glyph->advance_font_units,
        width,
        height,
        padding - slot->bitmap_left,
        padding + slot->bitmap_top,
        static_cast<float>(resolution) / static_cast<float>(font.metrics().units_per_em),
        std::move(pixels),
    };
}

}  // namespace fontc
