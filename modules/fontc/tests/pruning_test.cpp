#include "fontc/pruning.hpp"

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

int main() {
    const auto line = image(11, 7, {1, 4, 2, 4, 3, 4, 4, 4, 5, 4, 6, 4, 7, 4, 8, 4, 9, 4});
    require(fontc::prune_short_spurs(line, 4.0F).pixels == line.pixels, "plain stroke changed");

    const auto tee = image(11, 8, {
        1, 5, 2, 5, 3, 5, 4, 5, 5, 5, 6, 5, 7, 5, 8, 5, 9, 5,
        5, 2, 5, 3, 5, 4,
    });
    const auto pruned = fontc::prune_short_spurs(tee, 3.0F);
    require(count(pruned) < count(tee), "short spur was not removed");
    require(pruned.at(1, 5) == 1 && pruned.at(9, 5) == 1, "long branches were removed");
    require(pruned.at(5, 2) == 0, "spur endpoint survived");

    const auto loop = image(7, 7, {
        2, 2, 3, 2, 4, 2, 4, 3, 4, 4, 3, 4, 2, 4, 2, 3,
    });
    require(fontc::prune_short_spurs(loop, 10.0F).pixels == loop.pixels, "loop changed");

    const auto isolated = image(5, 5, {2, 2});
    require(fontc::prune_short_spurs(isolated, 10.0F).pixels == isolated.pixels, "isolated pixel changed");
}
