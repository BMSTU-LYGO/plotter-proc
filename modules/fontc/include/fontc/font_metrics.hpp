#pragma once

#include <cstdint>

namespace fontc {

// Kept FreeType-independent so PFC runtime consumers need no rasterizer headers.
struct FontMetrics {
    std::int32_t units_per_em = 0;
    std::int32_t ascender = 0;
    std::int32_t descender = 0;
    std::int32_t line_gap = 0;
};

}  // namespace fontc
