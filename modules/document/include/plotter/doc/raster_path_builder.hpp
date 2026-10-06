#pragma once

#include "plotter/doc/model.hpp"
#include "plotter/doc/path.hpp"

#include <cstddef>
#include <cstdint>

namespace plotter::doc {

// PNG raster art can be traced as bounded contours or legacy horizontal runs.
enum class RasterTraceMode { scanline, outline };
struct RasterPathOptions final {
    std::uint8_t darkness_threshold{127};
    RasterTraceMode mode{RasterTraceMode::scanline};
    double simplify_tolerance_mm{0.08};
    double minimum_stroke_length_mm{0.35};
    std::size_t maximum_decoded_bytes{64U * 1024U * 1024U};
    std::size_t maximum_strokes{1U * 1024U * 1024U};
    std::size_t maximum_points{100000U};
    double fallback_pixels_per_mm{96.0 / 25.4};
};

class RasterPathBuilder final {
public:
    explicit RasterPathBuilder(RasterPathOptions options = {}) : options_(options) {}

    // Reads image.image_path as a non-interlaced, 8-bit PNG and converts its
    // visible dark pixels into page-space strokes. bounds takes precedence over
    // displayed dimensions; otherwise the image anchor offsets and 96-DPI
    // fallback placement are used.
    [[nodiscard]] PathDocument build(const RasterImageElement& image,
                                     Millimetres page_width,
                                     Millimetres page_height) const;

private:
    RasterPathOptions options_;
};

}  // namespace plotter::doc
