#include "fontc/pruning.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstddef>
#include <limits>
#include <stdexcept>
#include <vector>

namespace fontc {
namespace {

constexpr std::size_t no_pixel = std::numeric_limits<std::size_t>::max();

struct NeighborList {
    std::array<std::size_t, 8> values{};
    std::size_t size = 0;
};

[[nodiscard]] std::size_t offset(const BinaryImage& image, int x, int y) noexcept {
    return static_cast<std::size_t>(y) * static_cast<std::size_t>(image.width) +
        static_cast<std::size_t>(x);
}

[[nodiscard]] NeighborList neighbors(const BinaryImage& image, std::size_t pixel) noexcept {
    NeighborList result;
    const int x = static_cast<int>(pixel % static_cast<std::size_t>(image.width));
    const int y = static_cast<int>(pixel / static_cast<std::size_t>(image.width));
    for (int dy = -1; dy <= 1; ++dy) {
        for (int dx = -1; dx <= 1; ++dx) {
            if ((dx == 0 && dy == 0) || x + dx < 0 || y + dy < 0 ||
                x + dx >= image.width || y + dy >= image.height) {
                continue;
            }
            const std::size_t candidate = offset(image, x + dx, y + dy);
            if (image.pixels[candidate] != 0) result.values[result.size++] = candidate;
        }
    }
    return result;
}

[[nodiscard]] float step_length(const BinaryImage& image, std::size_t a, std::size_t b) noexcept {
    const int ax = static_cast<int>(a % static_cast<std::size_t>(image.width));
    const int ay = static_cast<int>(a / static_cast<std::size_t>(image.width));
    const int bx = static_cast<int>(b % static_cast<std::size_t>(image.width));
    const int by = static_cast<int>(b / static_cast<std::size_t>(image.width));
    return ax == bx || ay == by ? 1.0F : std::sqrt(2.0F);
}

void validate(const BinaryImage& image, float min_spur_length) {
    if (image.width < 0 || image.height < 0) {
        throw std::invalid_argument("Skeleton dimensions must be non-negative");
    }
    const auto area = static_cast<std::size_t>(image.width) *
        static_cast<std::size_t>(image.height);
    if (image.pixels.size() != area) {
        throw std::invalid_argument("Skeleton buffer size does not match its dimensions");
    }
    if (std::any_of(image.pixels.begin(), image.pixels.end(), [](std::uint8_t value) {
            return value > 1;
        })) {
        throw std::invalid_argument("Skeleton pixels must be 0 or 1");
    }
    if (!std::isfinite(min_spur_length) || min_spur_length < 0.0F) {
        throw std::invalid_argument("Minimum spur length must be finite and non-negative");
    }
}

[[nodiscard]] bool mark_branch(
    const BinaryImage& image,
    std::size_t endpoint,
    float min_spur_length,
    std::vector<std::uint8_t>& removals
) {
    std::vector<std::size_t> branch{endpoint};
    std::size_t previous = no_pixel;
    std::size_t current = endpoint;
    float length = 0.0F;

    while (true) {
        const NeighborList adjacent = neighbors(image, current);
        if (current != endpoint && adjacent.size >= 3) {
            if (length >= min_spur_length) return false;
            for (std::size_t index = 0; index + 1 < branch.size(); ++index) {
                removals[branch[index]] = 1;
            }
            return branch.size() > 1;
        }

        std::size_t next = no_pixel;
        for (std::size_t index = 0; index < adjacent.size; ++index) {
            if (adjacent.values[index] == previous) continue;
            if (next != no_pixel) return false;
            next = adjacent.values[index];
        }
        if (next == no_pixel) return false;
        previous = current;
        current = next;
        length += step_length(image, previous, current);
        branch.push_back(current);
    }
}

}  // namespace

BinaryImage prune_short_spurs(const BinaryImage& skeleton, float min_spur_length) {
    validate(skeleton, min_spur_length);
    BinaryImage result = skeleton;
    if (min_spur_length <= 0.0F || result.pixels.empty()) return result;

    std::vector<std::uint8_t> removals(result.pixels.size(), 0);
    bool changed = false;
    do {
        std::fill(removals.begin(), removals.end(), 0);
        changed = false;
        for (std::size_t pixel = 0; pixel < result.pixels.size(); ++pixel) {
            if (result.pixels[pixel] != 0 && neighbors(result, pixel).size == 1) {
                changed = mark_branch(result, pixel, min_spur_length, removals) || changed;
            }
        }
        for (std::size_t pixel = 0; pixel < removals.size(); ++pixel) {
            if (removals[pixel] != 0) result.pixels[pixel] = 0;
        }
    } while (changed);
    return result;
}

}  // namespace fontc
