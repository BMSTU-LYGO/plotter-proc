#pragma once

#include "fontc/compiled_font.hpp"
#include "fontc/rasterizer.hpp"
#include "fontc/skeleton_graph.hpp"

#include <vector>

namespace fontc {

[[nodiscard]] PointFU pixel_to_font_units(const Point& pixel, const RasterGlyph& raster);
[[nodiscard]] std::vector<PointFU> pixels_to_font_units(const std::vector<Point>& pixels, const RasterGlyph& raster);
[[nodiscard]] std::vector<PointFU> simplify_rdp(const std::vector<PointFU>& points, double tolerance_font_units);
[[nodiscard]] std::vector<PointFU> smooth_chaikin(const std::vector<PointFU>& points, unsigned iterations = 1);

// The graph-node endpoints overwrite results after smoothing, so shared
// junctions and open ends always remain exactly coincident.
[[nodiscard]] CompiledStroke compile_edge_geometry(
    const Edge& edge, const SkeletonGraph& graph, const RasterGlyph& raster,
    double simplify_tolerance_font_units, unsigned chaikin_iterations = 1
);

}  // namespace fontc
