#include "fontc/thinning.hpp"
#include "fontc/binary_image.hpp"
#include "fontc/rasterizer.hpp"

#include <algorithm>
#include <cstdlib>
#include <iostream>
#include <vector>

namespace {

void require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

fontc::BinaryImage image(int width, int height, const std::vector<int>& points) {
    fontc::BinaryImage result{width, height, std::vector<std::uint8_t>(
        static_cast<std::size_t>(width) * static_cast<std::size_t>(height), 0)};
    for (std::size_t index = 0; index < points.size(); index += 2) {
        result.pixels[static_cast<std::size_t>(points[index + 1] * width + points[index])] = 1;
    }
    return result;
}

std::size_t count(const fontc::BinaryImage& value) {
    return static_cast<std::size_t>(std::count(value.pixels.begin(), value.pixels.end(), 1));
}

}  // namespace

int main(int argc, char** argv) {
    require(argc == 2, "expected path to test font");
    const auto line = image(7, 5, {1, 2, 2, 2, 3, 2, 4, 2, 5, 2});
    require(fontc::thin_guo_hall(line).pixels == line.pixels, "one-pixel line changed");

    const auto cross = image(7, 7, {3, 1, 3, 2, 1, 3, 2, 3, 3, 3, 4, 3, 5, 3, 3, 4, 3, 5});
    require(fontc::thin_guo_hall(cross).pixels == cross.pixels, "cross changed");
    const auto tee = image(7, 7, {1, 2, 2, 2, 3, 2, 4, 2, 5, 2, 3, 3, 3, 4, 3, 5});
    require(fontc::thin_guo_hall(tee).pixels == tee.pixels, "T-junction changed");

    fontc::BinaryImage block{9, 9, std::vector<std::uint8_t>(81, 0)};
    for (int y = 2; y <= 6; ++y) {
        for (int x = 3; x <= 5; ++x) block.pixels[static_cast<std::size_t>(y * 9 + x)] = 1;
    }
    const auto thinned = fontc::thin_guo_hall(block);
    require(count(thinned) < count(block), "thick stroke was not thinned");
    require(count(thinned) > 0, "thick stroke disappeared");
    require(fontc::thin_guo_hall(thinned).pixels == thinned.pixels, "thinning is not idempotent");

    fontc::BinaryImage ring{9, 9, std::vector<std::uint8_t>(81, 0)};
    for (int y = 2; y <= 6; ++y) {
        for (int x = 2; x <= 6; ++x) {
            if (x <= 3 || x >= 5 || y <= 3 || y >= 5) {
                ring.pixels[static_cast<std::size_t>(y * 9 + x)] = 1;
            }
        }
    }
    const auto thin_ring = fontc::thin_guo_hall(ring);
    require(count(thin_ring) > 0, "loop disappeared");
    require(thin_ring.at(4, 4) == 0, "loop hole was filled");

    const auto components = image(9, 5, {1, 2, 2, 2, 3, 2, 5, 2, 6, 2, 7, 2});
    require(fontc::thin_guo_hall(components).pixels == components.pixels, "components changed");

    fontc::FontFace font(argv[1]);
    const auto glyph_mask = fontc::make_binary_mask(fontc::rasterize_glyph(font, U'Ж', 256));
    const auto glyph_skeleton = fontc::thin_guo_hall(glyph_mask);
    require(count(glyph_skeleton) > 0, "real glyph skeleton is empty");
    require(count(glyph_skeleton) < count(glyph_mask), "real glyph was not thinned");
}
