#include "fontc/geometry.hpp"

#include <algorithm>
#include <cmath>
#include <limits>
#include <stdexcept>

namespace fontc {
namespace {
[[nodiscard]] std::int32_t rounded(double value) {
    if (!std::isfinite(value) || value < std::numeric_limits<std::int32_t>::min() || value > std::numeric_limits<std::int32_t>::max())
        throw std::out_of_range("Font-unit coordinate does not fit int32");
    return static_cast<std::int32_t>(std::llround(value));
}
[[nodiscard]] double distance_squared(PointFU p, PointFU a, PointFU b) noexcept {
    const double dx = static_cast<double>(b.x) - a.x, dy = static_cast<double>(b.y) - a.y;
    const double px = static_cast<double>(p.x) - a.x, py = static_cast<double>(p.y) - a.y;
    const double length = dx * dx + dy * dy;
    if (length == 0.0) return px * px + py * py;
    const double t = std::clamp((px * dx + py * dy) / length, 0.0, 1.0);
    const double ex = px - t * dx, ey = py - t * dy;
    return ex * ex + ey * ey;
}
}  // namespace

PointFU pixel_to_font_units(const Point& pixel, const RasterGlyph& raster) {
    if (!std::isfinite(raster.pixels_per_font_unit) || raster.pixels_per_font_unit <= 0.0F)
        throw std::invalid_argument("Raster glyph has an invalid pixels_per_font_unit");
    const double scale = static_cast<double>(raster.pixels_per_font_unit);
    const double x = static_cast<double>(pixel.x) - static_cast<double>(raster.origin_x);
    const double y = static_cast<double>(raster.origin_y) - static_cast<double>(pixel.y);
    return {rounded(x / scale), rounded(y / scale)};
}
std::vector<PointFU> pixels_to_font_units(const std::vector<Point>& pixels, const RasterGlyph& raster) {
    std::vector<PointFU> result; result.reserve(pixels.size());
    for (const Point point : pixels) result.push_back(pixel_to_font_units(point, raster));
    return result;
}
std::vector<PointFU> simplify_rdp(const std::vector<PointFU>& points, double tolerance) {
    if (!std::isfinite(tolerance) || tolerance < 0.0) throw std::invalid_argument("RDP tolerance must be finite and non-negative");
    if (points.size() < 3) return points;
    std::vector<bool> keep(points.size()); keep.front() = keep.back() = true;
    std::vector<std::pair<std::size_t, std::size_t>> work{{0, points.size() - 1}};
    const double threshold = tolerance * tolerance;
    while (!work.empty()) {
        const auto [first, last] = work.back(); work.pop_back();
        double greatest = -1.0; std::size_t selected = first;
        for (std::size_t i = first + 1; i < last; ++i) { const double d = distance_squared(points[i], points[first], points[last]); if (d > greatest) { greatest = d; selected = i; } }
        if (greatest > threshold) { keep[selected] = true; work.emplace_back(first, selected); work.emplace_back(selected, last); }
    }
    std::vector<PointFU> result; result.reserve(points.size());
    for (std::size_t i = 0; i < points.size(); ++i) if (keep[i]) result.push_back(points[i]);
    return result;
}
std::vector<PointFU> smooth_chaikin(const std::vector<PointFU>& points, unsigned iterations) {
    std::vector<PointFU> current = points;
    for (unsigned pass = 0; pass < iterations && current.size() >= 3; ++pass) {
        std::vector<PointFU> next; next.reserve(current.size() * 2U); next.push_back(current.front());
        for (std::size_t i = 0; i + 1 < current.size(); ++i) {
            const PointFU a = current[i], b = current[i + 1];
            next.push_back({rounded((3.0 * a.x + b.x) / 4.0), rounded((3.0 * a.y + b.y) / 4.0)});
            next.push_back({rounded((a.x + 3.0 * b.x) / 4.0), rounded((a.y + 3.0 * b.y) / 4.0)});
        }
        next.push_back(current.back()); current = std::move(next);
    }
    return current;
}
CompiledStroke compile_edge_geometry(const Edge& edge, const SkeletonGraph& graph, const RasterGlyph& raster, double tolerance, unsigned iterations) {
    if (edge.a >= graph.nodes.size() || edge.b >= graph.nodes.size()) throw std::invalid_argument("Edge refers to a missing graph node");
    auto points = pixels_to_font_units(edge.points, raster);
    const PointFU start = pixel_to_font_units(graph.nodes[edge.a].position, raster);
    const PointFU end = pixel_to_font_units(graph.nodes[edge.b].position, raster);
    if (points.empty()) points = {start, end}; else if (points.size() == 1) points.push_back(end);
    points.front() = start; points.back() = end;
    points = smooth_chaikin(simplify_rdp(points, tolerance), iterations);
    points.front() = start; points.back() = end;
    return {std::move(points)};
}
}  // namespace fontc
