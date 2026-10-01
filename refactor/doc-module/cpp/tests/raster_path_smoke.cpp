#include "plotter/doc/raster_path_builder.hpp"

#include <array>
#include <cassert>
#include <cstdint>
#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <vector>

#include <zlib.h>

namespace {
void write_be32(std::ofstream& output, std::uint32_t value) {
    const std::array<std::uint8_t, 4> bytes{static_cast<std::uint8_t>(value >> 24U), static_cast<std::uint8_t>(value >> 16U), static_cast<std::uint8_t>(value >> 8U), static_cast<std::uint8_t>(value)};
    output.write(reinterpret_cast<const char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
}
void chunk(std::ofstream& output, const char* type, const std::vector<std::uint8_t>& data, bool corrupt_crc = false) {
    write_be32(output, static_cast<std::uint32_t>(data.size())); output.write(type, 4); if (!data.empty()) output.write(reinterpret_cast<const char*>(data.data()), static_cast<std::streamsize>(data.size()));
    uLong crc = crc32(0L, Z_NULL, 0U); crc = crc32(crc, reinterpret_cast<const Bytef*>(type), 4U);
    if (!data.empty()) crc = crc32(crc, data.data(), static_cast<uInt>(data.size()));
    write_be32(output, static_cast<std::uint32_t>(crc) ^ (corrupt_crc ? 1U : 0U));
}
}

int main() {
    const auto file = std::filesystem::temp_directory_path() / "plotter-raster-path-smoke.png";
    const std::vector<std::uint8_t> filtered{0, 0, 0, 255, 1, 255, 1, 0}; // rows: 0,0,255 then 255,0,0 using Sub
    uLongf size = compressBound(static_cast<uLong>(filtered.size())); std::vector<std::uint8_t> compressed(size);
    if (compress2(compressed.data(), &size, filtered.data(), static_cast<uLong>(filtered.size()), Z_BEST_COMPRESSION) != Z_OK) throw std::runtime_error("cannot encode test PNG");
    compressed.resize(size);
    std::ofstream output(file, std::ios::binary);
    constexpr std::array<std::uint8_t, 8> signature{137, 80, 78, 71, 13, 10, 26, 10}; output.write(reinterpret_cast<const char*>(signature.data()), static_cast<std::streamsize>(signature.size()));
    std::vector<std::uint8_t> ihdr{0, 0, 0, 3, 0, 0, 0, 2, 8, 0, 0, 0, 0}; chunk(output, "IHDR", ihdr); chunk(output, "IDAT", compressed); chunk(output, "IEND", {}); output.close();
    plotter::doc::RasterImageElement image; image.id = "source-image"; image.source_page = 2; image.image_path = file.string(); image.width = {3}; image.height = {2}; image.bounds = {{{10}, {20}, {6}, {4}}}; image.z_order = 7;
    const auto paths = plotter::doc::RasterPathBuilder{}.build(image, {210}, {297});
    assert(paths.strokes.size() == 2);
    assert(paths.strokes[0].points[0].x.value == 10.0 && paths.strokes[0].points[1].x.value == 14.0 && paths.strokes[0].points[0].y.value == 21.0);
    assert(paths.strokes[1].points[0].x.value == 12.0 && paths.strokes[1].points[1].x.value == 16.0 && paths.strokes[1].points[0].y.value == 23.0);
    assert(paths.strokes[0].element_id == "source-image" && paths.strokes[0].source_page_index == 2 && paths.strokes[0].source_path == file.string() && paths.strokes[0].z_order == 7);
    const auto corrupt = std::filesystem::temp_directory_path() / "plotter-raster-path-corrupt-smoke.png";
    std::ofstream corrupt_output(corrupt, std::ios::binary);
    corrupt_output.write(reinterpret_cast<const char*>(signature.data()), static_cast<std::streamsize>(signature.size()));
    chunk(corrupt_output, "IHDR", ihdr); chunk(corrupt_output, "IDAT", compressed, true); chunk(corrupt_output, "IEND", {}); corrupt_output.close();
    bool rejected = false;
    image.image_path = corrupt.string();
    try { (void)plotter::doc::RasterPathBuilder{}.build(image, {210}, {297}); } catch (const std::runtime_error&) { rejected = true; }
    assert(rejected);
    std::filesystem::remove(file); std::filesystem::remove(corrupt);
}
