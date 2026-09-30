#include "fontc/binary_image.hpp"

#include <cstdlib>
#include <iostream>
#include <stdexcept>

namespace {

void require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

}  // namespace

int main() {
    const fontc::RasterGlyph raster{U'A', 1, 600, 3, 2, 0, 0, 1.0F, {0, 159, 160, 255, 42, 200}};
    const fontc::BinaryImage mask = fontc::make_binary_mask(raster, 160);
    require(mask.width == 3 && mask.height == 2, "dimensions changed");
    require(mask.pixels == std::vector<std::uint8_t>({0, 0, 1, 1, 0, 1}), "threshold mismatch");

    bool invalid_threshold_rejected = false;
    try {
        (void)fontc::make_binary_mask(raster, 256);
    } catch (const std::invalid_argument&) {
        invalid_threshold_rejected = true;
    }
    require(invalid_threshold_rejected, "invalid threshold must be rejected");
}
