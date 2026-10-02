#include "fontc/thinning.hpp"

#include <algorithm>
#include <cstddef>
#include <stdexcept>
#include <vector>

namespace fontc {
namespace {

[[nodiscard]] std::size_t offset(const BinaryImage& image, int x, int y) noexcept {
    return static_cast<std::size_t>(y) * static_cast<std::size_t>(image.width) +
        static_cast<std::size_t>(x);
}

[[nodiscard]] bool ink(const BinaryImage& image, int x, int y) noexcept {
    return image.pixels[offset(image, x, y)] != 0;
}

[[nodiscard]] bool removable(const BinaryImage& image, int x, int y, int pass) noexcept {
    const bool p2 = ink(image, x, y - 1);
    const bool p3 = ink(image, x + 1, y - 1);
    const bool p4 = ink(image, x + 1, y);
    const bool p5 = ink(image, x + 1, y + 1);
    const bool p6 = ink(image, x, y + 1);
    const bool p7 = ink(image, x - 1, y + 1);
    const bool p8 = ink(image, x - 1, y);
    const bool p9 = ink(image, x - 1, y - 1);

    const int transitions = static_cast<int>(!p2 && (p3 || p4)) +
        static_cast<int>(!p4 && (p5 || p6)) +
        static_cast<int>(!p6 && (p7 || p8)) +
        static_cast<int>(!p8 && (p9 || p2));
    const int neighbors_a = static_cast<int>(p9 || p2) + static_cast<int>(p3 || p4) +
        static_cast<int>(p5 || p6) + static_cast<int>(p7 || p8);
    const int neighbors_b = static_cast<int>(p2 || p3) + static_cast<int>(p4 || p5) +
        static_cast<int>(p6 || p7) + static_cast<int>(p8 || p9);
    const int neighbors = std::min(neighbors_a, neighbors_b);
    const bool preserve = pass == 0 ? ((p6 || p7 || !p9) && p8)
                                    : ((p2 || p3 || !p5) && p4);
    return transitions == 1 && (neighbors == 2 || neighbors == 3) && !preserve;
}

void validate(const BinaryImage& image) {
    if (image.width < 0 || image.height < 0) {
        throw std::invalid_argument("Binary image dimensions must be non-negative");
    }
    const auto area = static_cast<std::size_t>(image.width) *
        static_cast<std::size_t>(image.height);
    if (image.pixels.size() != area) {
        throw std::invalid_argument("Binary image buffer size does not match its dimensions");
    }
    if (std::any_of(image.pixels.begin(), image.pixels.end(), [](std::uint8_t value) {
            return value > 1;
        })) {
        throw std::invalid_argument("Binary image pixels must be 0 or 1");
    }
}

}  // namespace

BinaryImage thin_guo_hall(const BinaryImage& image) {
    validate(image);
    BinaryImage result = image;
    if (result.width < 3 || result.height < 3) return result;

    std::vector<std::size_t> removed;
    bool changed = false;
    do {
        changed = false;
        for (int pass = 0; pass < 2; ++pass) {
            removed.clear();
            for (int y = 1; y < result.height - 1; ++y) {
                for (int x = 1; x < result.width - 1; ++x) {
                    if (ink(result, x, y) && removable(result, x, y, pass)) {
                        removed.push_back(offset(result, x, y));
                    }
                }
            }
            for (const std::size_t index : removed) result.pixels[index] = 0;
            changed = changed || !removed.empty();
        }
    } while (changed);
    return result;
}

}  // namespace fontc
