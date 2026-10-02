#pragma once

#include "fontc/binary_image.hpp"

namespace fontc {

// Remove endpoint-to-junction branches shorter than min_spur_length pixels.
// Endpoint-to-endpoint strokes, loops, isolated pixels and junction pixels are preserved.
[[nodiscard]] BinaryImage prune_short_spurs(
    const BinaryImage& skeleton,
    float min_spur_length
);

}  // namespace fontc
