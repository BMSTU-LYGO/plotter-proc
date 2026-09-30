#pragma once

#include "fontc/rasterizer.hpp"

#include <cstdint>
#include <vector>

namespace fontc {

struct BinaryImage {
    int width;
    int height;
    std::vector<std::uint8_t> pixels;

    [[nodiscard]] std::uint8_t at(int x, int y) const noexcept {
        return pixels[static_cast<std::size_t>(y) * static_cast<std::size_t>(width) +
                      static_cast<std::size_t>(x)];
    }
};

// FreeType coverage >= threshold becomes ink (1); everything else is background (0).
// Morphological closing is intentionally absent until regression data justifies it.
[[nodiscard]] BinaryImage make_binary_mask(const RasterGlyph& raster, int threshold = 160);

}  // namespace fontc
