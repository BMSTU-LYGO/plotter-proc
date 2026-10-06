#include "fontc/binary_image.hpp"
#include "fontc/rasterizer.hpp"

#include <cstddef>
#include <stdexcept>

namespace fontc {

BinaryImage make_binary_mask(const RasterGlyph& raster, int threshold) {
    if (raster.width < 0 || raster.height < 0) {
        throw std::invalid_argument("Raster dimensions must be non-negative");
    }
    const auto area = static_cast<std::size_t>(raster.width) *
        static_cast<std::size_t>(raster.height);
    if (raster.grayscale.size() != area) {
        throw std::invalid_argument("Raster buffer size does not match its dimensions");
    }
    if (threshold < 0 || threshold > 255) {
        throw std::invalid_argument("Mask threshold must be in [0, 255]");
    }

    BinaryImage result{raster.width, raster.height, std::vector<std::uint8_t>(area)};
    for (std::size_t index = 0; index < area; ++index) {
        result.pixels[index] = raster.grayscale[index] >= threshold ? 1U : 0U;
    }
    return result;
}

}  // namespace fontc
