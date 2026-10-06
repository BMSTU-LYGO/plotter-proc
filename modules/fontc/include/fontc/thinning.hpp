#pragma once

#include "fontc/binary_image.hpp"

namespace fontc {

// Deterministic Guo-Hall thinning. The input and output use 8-connected ink pixels.
[[nodiscard]] BinaryImage thin_guo_hall(const BinaryImage& image);

}  // namespace fontc
