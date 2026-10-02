#include "plotter/doc/raster_path_builder.hpp"

#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <fstream>
#include <limits>
#include <unordered_map>
#include <numeric>
#include <stdexcept>
#include <string_view>
#include <utility>
#include <vector>

#include <zlib.h>

namespace plotter::doc {
namespace {

struct DecodedPng final {
    std::uint32_t width{}, height{};
    std::uint8_t colour_type{};
    std::vector<std::uint8_t> pixels;
    std::vector<std::array<std::uint8_t, 3>> palette;
    std::vector<std::uint8_t> palette_alpha;
};

[[nodiscard]] std::uint32_t be32(const std::uint8_t* value) {
    return (static_cast<std::uint32_t>(value[0]) << 24U) | (static_cast<std::uint32_t>(value[1]) << 16U) |
           (static_cast<std::uint32_t>(value[2]) << 8U) | static_cast<std::uint32_t>(value[3]);
}

[[nodiscard]] std::vector<std::uint8_t> read_file(const std::string& path) {
    std::ifstream stream(path, std::ios::binary);
    if (!stream) throw std::runtime_error("cannot open raster image: " + path);
    stream.seekg(0, std::ios::end);
    const auto size = stream.tellg();
    if (size < 0) throw std::runtime_error("cannot determine raster image size: " + path);
    stream.seekg(0, std::ios::beg);
    std::vector<std::uint8_t> result(static_cast<std::size_t>(size));
    if (!result.empty()) stream.read(reinterpret_cast<char*>(result.data()), static_cast<std::streamsize>(result.size()));
    if (!stream && !result.empty()) throw std::runtime_error("cannot read raster image: " + path);
    return result;
}

[[nodiscard]] std::size_t channels(std::uint8_t colour_type) {
    switch (colour_type) {
        case 0: return 1;
        case 2: return 3;
        case 3: return 1;
        case 4: return 2;
        case 6: return 4;
        default: throw std::runtime_error("PNG colour type is unsupported");
    }
}

[[nodiscard]] std::uint8_t paeth(std::uint8_t a, std::uint8_t b, std::uint8_t c) {
    const int estimate = static_cast<int>(a) + static_cast<int>(b) - static_cast<int>(c);
    const int da = std::abs(estimate - static_cast<int>(a));
    const int db = std::abs(estimate - static_cast<int>(b));
    const int dc = std::abs(estimate - static_cast<int>(c));
    return da <= db && da <= dc ? a : (db <= dc ? b : c);
}

[[nodiscard]] DecodedPng decode_png(const std::string& path, const RasterPathOptions& options) {
    const auto file = read_file(path);
    constexpr std::array<std::uint8_t, 8> signature{137, 80, 78, 71, 13, 10, 26, 10};
    if (file.size() < signature.size() || !std::equal(signature.begin(), signature.end(), file.begin())) throw std::runtime_error("raster image is not a PNG");
    DecodedPng decoded;
    std::vector<std::uint8_t> compressed;
    bool saw_header = false;
    for (std::size_t offset = signature.size(); offset < file.size();) {
        if (file.size() - offset < 12U) throw std::runtime_error("PNG chunk is truncated");
        const std::uint32_t length = be32(file.data() + offset);
        offset += 4U;
        const std::string_view type(reinterpret_cast<const char*>(file.data() + offset), 4U);
        offset += 4U;
        if (static_cast<std::uint64_t>(length) + 4U > file.size() - offset) throw std::runtime_error("PNG chunk exceeds file bounds");
        const auto* data = file.data() + offset;
        uLong checksum = crc32(0L, Z_NULL, 0U);
        checksum = crc32(checksum, reinterpret_cast<const Bytef*>(type.data()), static_cast<uInt>(type.size()));
        checksum = crc32(checksum, reinterpret_cast<const Bytef*>(data), static_cast<uInt>(length));
        if (checksum != be32(data + length)) throw std::runtime_error("PNG chunk CRC is invalid");
        if (type == "IHDR") {
            if (saw_header || length != 13U) throw std::runtime_error("PNG IHDR is invalid");
            decoded.width = be32(data); decoded.height = be32(data + 4U);
            if (!decoded.width || !decoded.height || data[8] != 8U || data[10] != 0U || data[11] != 0U || data[12] != 0U) throw std::runtime_error("PNG must be non-interlaced 8-bit data");
            decoded.colour_type = data[9];
            (void)channels(decoded.colour_type);
            saw_header = true;
        } else if (type == "PLTE") {
            if (length == 0U || length % 3U != 0U || length > 768U) throw std::runtime_error("PNG palette is invalid");
            decoded.palette.resize(length / 3U);
            for (std::size_t i = 0; i < decoded.palette.size(); ++i) decoded.palette[i] = {data[i * 3U], data[i * 3U + 1U], data[i * 3U + 2U]};
        } else if (type == "tRNS") {
            decoded.palette_alpha.assign(data, data + length);
        } else if (type == "IDAT") {
            if (!saw_header || compressed.size() > std::numeric_limits<std::size_t>::max() - length) throw std::runtime_error("PNG data is invalid");
            compressed.insert(compressed.end(), data, data + length);
        } else if (type == "IEND") {
            if (length != 0U) throw std::runtime_error("PNG IEND is invalid");
            break;
        }
        offset += static_cast<std::size_t>(length) + 4U;  // data and CRC
    }
    if (!saw_header || compressed.empty() || (decoded.colour_type == 3U && decoded.palette.empty())) throw std::runtime_error("PNG has incomplete image data");
    const std::size_t pixel_bytes = channels(decoded.colour_type);
    const std::uint64_t row_bytes_64 = static_cast<std::uint64_t>(decoded.width) * pixel_bytes;
    const std::uint64_t inflated_bytes_64 = (row_bytes_64 + 1U) * decoded.height;
    if (row_bytes_64 > std::numeric_limits<std::size_t>::max() || inflated_bytes_64 > options.maximum_decoded_bytes || inflated_bytes_64 > std::numeric_limits<uLongf>::max()) throw std::runtime_error("PNG decoded data exceeds configured bound");
    std::vector<std::uint8_t> filtered(static_cast<std::size_t>(inflated_bytes_64));
    uLongf actual = static_cast<uLongf>(filtered.size());
    const int status = uncompress(filtered.data(), &actual, compressed.data(), static_cast<uLong>(compressed.size()));
    if (status != Z_OK || actual != filtered.size()) throw std::runtime_error("PNG zlib stream is invalid or has unexpected size");
    const std::size_t row_bytes = static_cast<std::size_t>(row_bytes_64);
    decoded.pixels.resize(row_bytes * decoded.height);
    for (std::size_t row = 0; row < decoded.height; ++row) {
        const auto filter = filtered[row * (row_bytes + 1U)];
        const auto* input = filtered.data() + row * (row_bytes + 1U) + 1U;
        auto* output = decoded.pixels.data() + row * row_bytes;
        const auto* prior = row == 0 ? nullptr : output - row_bytes;
        for (std::size_t i = 0; i < row_bytes; ++i) {
            const std::uint8_t left = i < pixel_bytes ? 0U : output[i - pixel_bytes];
            const std::uint8_t up = prior ? prior[i] : 0U;
            const std::uint8_t upper_left = prior && i >= pixel_bytes ? prior[i - pixel_bytes] : 0U;
            switch (filter) {
                case 0: output[i] = input[i]; break;
                case 1: output[i] = static_cast<std::uint8_t>(input[i] + left); break;
                case 2: output[i] = static_cast<std::uint8_t>(input[i] + up); break;
                case 3: output[i] = static_cast<std::uint8_t>(input[i] + static_cast<std::uint8_t>((static_cast<unsigned>(left) + up) / 2U)); break;
                case 4: output[i] = static_cast<std::uint8_t>(input[i] + paeth(left, up, upper_left)); break;
                default: throw std::runtime_error("PNG row uses an unsupported filter");
            }
        }
    }
    return decoded;
}

[[nodiscard]] bool dark(const DecodedPng& image, std::size_t index, std::uint8_t threshold) {
    const std::size_t offset = index * channels(image.colour_type);
    std::uint8_t red{}, green{}, blue{}, alpha{255};
    switch (image.colour_type) {
        case 0: red = green = blue = image.pixels[offset]; break;
        case 2: red = image.pixels[offset]; green = image.pixels[offset + 1U]; blue = image.pixels[offset + 2U]; break;
        case 3: {
            const auto palette_index = image.pixels[offset];
            if (palette_index >= image.palette.size()) throw std::runtime_error("PNG palette index is out of range");
            const auto colour = image.palette[palette_index]; red = colour[0]; green = colour[1]; blue = colour[2];
            if (palette_index < image.palette_alpha.size()) alpha = image.palette_alpha[palette_index];
            break;
        }
        case 4: red = green = blue = image.pixels[offset]; alpha = image.pixels[offset + 1U]; break;
        case 6: red = image.pixels[offset]; green = image.pixels[offset + 1U]; blue = image.pixels[offset + 2U]; alpha = image.pixels[offset + 3U]; break;
        default: throw std::runtime_error("PNG colour type is unsupported");
    }
    const unsigned luminance = 299U * red + 587U * green + 114U * blue;
    return alpha != 0U && luminance / 1000U <= threshold;
}

struct BoundaryEdge final { std::uint64_t from{}, to{}; std::uint8_t direction{}; bool used{}; };
[[nodiscard]] double point_distance(Point a, Point b) { return std::hypot(a.x.value - b.x.value, a.y.value - b.y.value); }
[[nodiscard]] double chord_distance(Point point, Point first, Point last) {
    const double dx = last.x.value - first.x.value, dy = last.y.value - first.y.value;
    const double length = std::hypot(dx, dy);
    if (length == 0.0) return point_distance(point, first);
    return std::abs(dy * point.x.value - dx * point.y.value + last.x.value * first.y.value - last.y.value * first.x.value) / length;
}
void simplify_between(const std::vector<Point>& input, std::vector<bool>& keep,
                      std::size_t first, std::size_t last, double tolerance) {
    std::vector<std::pair<std::size_t, std::size_t>> pending{{first, last}};
    std::uint64_t work{};
    while (!pending.empty()) {
        const auto [left, right] = pending.back(); pending.pop_back();
        if (right <= left + 1U) continue;
        work += right - left;
        if (work > 50000000ULL) throw std::runtime_error("raster contour simplification exceeds work limit");
        double maximum = tolerance; std::size_t pivot = left;
        for (std::size_t index = left + 1U; index < right; ++index) {
            const double distance = chord_distance(input[index], input[left], input[right]);
            if (distance > maximum) { maximum = distance; pivot = index; }
        }
        if (pivot != left) {
            keep[pivot] = true;
            pending.emplace_back(left, pivot);
            pending.emplace_back(pivot, right);
        }
    }
}
[[nodiscard]] std::vector<Point> simplify_contour(const std::vector<Point>& input, double tolerance) {
    if (input.size() < 4U) return input;
    std::vector<bool> keep(input.size()); keep.front() = true; keep.back() = true;
    simplify_between(input, keep, 0U, input.size() - 1U, tolerance);
    std::vector<Point> output; output.reserve(input.size());
    for (std::size_t i = 0; i < input.size(); ++i) if (keep[i]) output.push_back(input[i]);
    return output;
}
[[nodiscard]] PathDocument trace_outline(const DecodedPng& png, const RasterImageElement& image,
                                          Rect box, Millimetres page_width, Millimetres page_height,
                                          const RasterPathOptions& options) {
    PathDocument result; result.page_width = page_width; result.page_height = page_height;
    result.metadata = {{"coordinate_system", "page-mm-top-left"}, {"pipeline", "png-binary-outline"}};
    const std::uint64_t width = png.width, height = png.height;
    const std::size_t count = static_cast<std::size_t>(width * height);
    std::vector<std::uint8_t> mask(count);
    for (std::size_t index = 0; index < count; ++index) mask[index] = dark(png, index, options.darkness_threshold) ? 1U : 0U;
    const auto active = [&](std::uint64_t x, std::uint64_t y) { return mask[static_cast<std::size_t>(y * width + x)] != 0U; };
    const auto vertex = [width](std::uint64_t x, std::uint64_t y) { return y * (width + 1U) + x; };
    std::vector<BoundaryEdge> edges;
    std::unordered_map<std::uint64_t, std::vector<std::size_t>> outgoing;
    const auto add_edge = [&](std::uint64_t x0, std::uint64_t y0, std::uint64_t x1, std::uint64_t y1, std::uint8_t direction) {
        const auto from = vertex(x0, y0);
        outgoing[from].push_back(edges.size());
        edges.push_back({from, vertex(x1, y1), direction, false});
        if (edges.size() > options.maximum_points * 32U) throw std::runtime_error("raster boundary exceeds complexity limit");
    };
    for (std::uint64_t y = 0; y < height; ++y) for (std::uint64_t x = 0; x < width; ++x) {
        if (!active(x,y)) continue;
        if (y == 0U || !active(x,y-1U)) add_edge(x,y,x+1U,y,0U);
        if (x+1U == width || !active(x+1U,y)) add_edge(x+1U,y,x+1U,y+1U,1U);
        if (y+1U == height || !active(x,y+1U)) add_edge(x+1U,y+1U,x,y+1U,2U);
        if (x == 0U || !active(x-1U,y)) add_edge(x,y+1U,x,y,3U);
    }
    const double sx = box.width.value / static_cast<double>(width), sy = box.height.value / static_cast<double>(height);
    std::size_t point_total{};
    for (std::size_t start = 0; start < edges.size(); ++start) {
        if (edges[start].used) continue;
        std::vector<Point> points;
        std::size_t edge_index = start;
        while (true) {
            BoundaryEdge& edge = edges[edge_index];
            if (edge.used) break;
            edge.used = true;
            const std::uint64_t vx = edge.from % (width + 1U), vy = edge.from / (width + 1U);
            points.push_back({{box.x.value + static_cast<double>(vx) * sx}, {box.y.value + static_cast<double>(vy) * sy}});
            if (edge.to == edges[start].from) break;
            const auto found = outgoing.find(edge.to);
            if (found == outgoing.end()) break;
            std::size_t next = edges.size();
            for (std::uint8_t turn : {std::uint8_t{1}, std::uint8_t{0}, std::uint8_t{3}, std::uint8_t{2}}) {
                const std::uint8_t direction = static_cast<std::uint8_t>((edge.direction + turn) & 3U);
                for (const auto candidate : found->second)
                    if (!edges[candidate].used && edges[candidate].direction == direction) { next = candidate; break; }
                if (next != edges.size()) break;
            }
            if (next == edges.size()) break;
            edge_index = next;
        }
        if (points.size() < 3U) continue;
        points.push_back(points.front());
        points = simplify_contour(points, options.simplify_tolerance_mm);
        if (points.size() < 4U) continue;
        double length{}; for (std::size_t i = 1; i < points.size(); ++i) length += point_distance(points[i-1], points[i]);
        if (length < options.minimum_stroke_length_mm) continue;
        Stroke stroke; stroke.id = result.strokes.size(); stroke.points = std::move(points); stroke.closed = true;
        stroke.element_id = image.id; stroke.element_type = "raster-image"; stroke.source_page_index = static_cast<std::int64_t>(image.source_page);
        stroke.source_path = image.image_path; stroke.semantic_role = "raster-image"; stroke.segment_types = {"raster-outline"};
        stroke.preserve_order = true; stroke.z_order = image.z_order;
        point_total += stroke.points.size();
        if (result.strokes.size() >= options.maximum_strokes || point_total > options.maximum_points)
            throw std::runtime_error("raster outline exceeds configured stroke or point bound");
        result.strokes.push_back(std::move(stroke));
    }
    return result;
}

[[nodiscard]] Rect placement(const RasterImageElement& image, const RasterPathOptions& options) {
    if (image.bounds) {
        if (!image.bounds->has_positive_area()) throw std::invalid_argument("raster image bounds must have positive area");
        return *image.bounds;
    }
    if (!(options.fallback_pixels_per_mm > 0.0) || !std::isfinite(options.fallback_pixels_per_mm)) throw std::invalid_argument("fallback pixels per millimetre must be positive");
    const Millimetres width = image.displayed_width.value_or(Millimetres{image.width.value / options.fallback_pixels_per_mm});
    const Millimetres height = image.displayed_height.value_or(Millimetres{image.height.value / options.fallback_pixels_per_mm});
    if (!(width.value > 0.0) || !(height.value > 0.0)) throw std::invalid_argument("raster image requires positive displayed dimensions or pixel dimensions");
    return {image.anchor_offset_x, image.anchor_offset_y, width, height};
}

}  // namespace

PathDocument RasterPathBuilder::build(const RasterImageElement& image, Millimetres page_width, Millimetres page_height) const {
    if (!(page_width.value > 0.0) || !(page_height.value > 0.0)) throw std::invalid_argument("page dimensions must be positive");
    const DecodedPng png = decode_png(image.image_path, options_);
    const Rect box = placement(image, options_);
    if (options_.mode == RasterTraceMode::outline)
        return trace_outline(png, image, box, page_width, page_height, options_);
    PathDocument result;
    result.page_width = page_width; result.page_height = page_height;
    result.metadata.emplace_back("coordinate_system", "page-mm-top-left");
    result.metadata.emplace_back("pipeline", "png-dark-pixel-runs");
    const double x_scale = box.width.value / static_cast<double>(png.width);
    const double y_scale = box.height.value / static_cast<double>(png.height);
    for (std::uint32_t y = 0; y < png.height; ++y) {
        std::uint32_t x = 0;
        while (x < png.width) {
            while (x < png.width && !dark(png, static_cast<std::size_t>(y) * png.width + x, options_.darkness_threshold)) ++x;
            const std::uint32_t start = x;
            while (x < png.width && dark(png, static_cast<std::size_t>(y) * png.width + x, options_.darkness_threshold)) ++x;
            if (start == x) continue;
            Stroke stroke;
            stroke.id = result.strokes.size();
            stroke.points = {{{box.x.value + static_cast<double>(start) * x_scale}, {box.y.value + (static_cast<double>(y) + 0.5) * y_scale}},
                             {{box.x.value + static_cast<double>(x) * x_scale}, {box.y.value + (static_cast<double>(y) + 0.5) * y_scale}}};
            stroke.element_id = image.id; stroke.element_type = "raster-image"; stroke.source_page_index = static_cast<std::int64_t>(image.source_page);
            stroke.source_path = image.image_path; stroke.semantic_role = "raster-image"; stroke.segment_types = {"raster-pixel-run"};
            stroke.preserve_order = true; stroke.z_order = image.z_order;
            if (result.strokes.size() >= options_.maximum_strokes) throw std::runtime_error("raster image exceeds configured stroke bound");
            result.strokes.push_back(std::move(stroke));
        }
    }
    return result;
}

}  // namespace plotter::doc
