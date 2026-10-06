#include "fontc/geometry.hpp"

#include <cstdlib>
#include <iostream>
#include <stdexcept>

namespace { void require(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); } }

int main() {
    try {
        fontc::RasterGlyph raster{};
        raster.origin_x = 10; raster.origin_y = 40; raster.pixels_per_font_unit = 2.0F;
        require(fontc::pixel_to_font_units({14.0F, 34.0F}, raster) == fontc::PointFU{2, 3}, "pixel mapping");
        require(fontc::simplify_rdp({{0, 0}, {5, 0}, {10, 0}}, 0.1).size() == 2, "RDP collinear reduction");
        const auto smooth = fontc::smooth_chaikin({{0, 0}, {4, 8}, {8, 0}});
        require(smooth.front() == fontc::PointFU{0, 0} && smooth.back() == fontc::PointFU{8, 0}, "Chaikin endpoints");
        fontc::SkeletonGraph graph{
            {{0, {10.0F, 40.0F}, {}}, {1, {30.0F, 40.0F}, {}}},
            {{0, 0, 1, {{11.0F, 39.0F}, {20.0F, 30.0F}, {29.0F, 39.0F}}}}
        };
        const auto edge = fontc::compile_edge_geometry(graph.edges[0], graph, raster, 0.0);
        require(edge.points.front() == fontc::PointFU{0, 0} && edge.points.back() == fontc::PointFU{10, 0}, "graph endpoints fixed");
    } catch (const std::exception& error) { std::cerr << error.what() << '\n'; return EXIT_FAILURE; }
    return EXIT_SUCCESS;
}
