#include "fontc/compiler.hpp"

#include "fontc/binary_image.hpp"
#include "fontc/compiled_font.hpp"
#include "fontc/geometry.hpp"
#include "fontc/graph_cleanup.hpp"
#include "fontc/pfc.hpp"
#include "fontc/pruning.hpp"
#include "fontc/rasterizer.hpp"
#include "fontc/routing.hpp"
#include "fontc/skeleton_graph.hpp"
#include "fontc/thinning.hpp"

#include <algorithm>
#include <array>
#include <atomic>
#include <cstdint>
#include <exception>
#include <filesystem>
#include <fstream>
#include <limits>
#include <mutex>
#include <optional>
#include <stdexcept>
#include <string>
#include <thread>
#include <utility>
#include <vector>

namespace fontc {
namespace {

constexpr std::uint32_t kFallbackCodepoint = static_cast<std::uint32_t>('?');

[[nodiscard]] std::uint32_t decode_utf8(const std::string& bytes, std::size_t& offset) {
    const auto first = static_cast<std::uint8_t>(bytes[offset++]);
    if (first < 0x80U) return first;
    unsigned int continuation_count = 0;
    std::uint32_t codepoint = 0;
    std::uint32_t minimum = 0;
    if ((first & 0xE0U) == 0xC0U) {
        continuation_count = 1; codepoint = first & 0x1FU; minimum = 0x80U;
    } else if ((first & 0xF0U) == 0xE0U) {
        continuation_count = 2; codepoint = first & 0x0FU; minimum = 0x800U;
    } else if ((first & 0xF8U) == 0xF0U) {
        continuation_count = 3; codepoint = first & 0x07U; minimum = 0x10000U;
    } else {
        throw std::runtime_error("chars file contains invalid UTF-8 leading byte");
    }
    if (bytes.size() - offset < continuation_count) {
        throw std::runtime_error("chars file ends in an incomplete UTF-8 sequence");
    }
    for (unsigned int index = 0; index < continuation_count; ++index) {
        const auto next = static_cast<std::uint8_t>(bytes[offset++]);
        if ((next & 0xC0U) != 0x80U) throw std::runtime_error("chars file contains invalid UTF-8 continuation byte");
        codepoint = (codepoint << 6U) | (next & 0x3FU);
    }
    if (codepoint < minimum || codepoint > 0x10FFFFU ||
        (codepoint >= 0xD800U && codepoint <= 0xDFFFU)) {
        throw std::runtime_error("chars file contains an invalid Unicode codepoint");
    }
    return codepoint;
}

[[nodiscard]] CompiledStroke compile_routed_stroke(
    const RoutedStroke& routed,
    const RasterGlyph& raster
) {
    std::vector<PointFU> points = pixels_to_font_units(routed.points, raster);
    if (points.size() < 3) return {std::move(points)};
    const PointFU start = points.front();
    const PointFU end = points.back();
    points = smooth_chaikin(simplify_rdp(points, 1.0), 1);
    points.front() = start;
    points.back() = end;
    return {std::move(points)};
}


[[nodiscard]] std::optional<CompiledGlyph> compile_one(
    FontFace& face,
    std::uint32_t codepoint,
    int resolution
) {
    if (!face.glyph_metrics(codepoint).has_value()) return std::nullopt;
    const RasterGlyph raster = rasterize_glyph(face, codepoint, resolution);
    const BinaryImage mask = make_binary_mask(raster);
    const BinaryImage skeleton = thin_guo_hall(mask);
    const float min_spur_length = std::max(1.0F, static_cast<float>(resolution) / 128.0F);
    const BinaryImage pruned = prune_short_spurs(skeleton, min_spur_length);
    const SkeletonGraph graph = cleanup_graph(build_skeleton_graph(pruned));
    const RoutingResult routing = route_graph(graph);

    CompiledGlyph glyph;
    glyph.codepoint = codepoint;
    glyph.advance_font_units = raster.advance_font_units;
    glyph.strokes.reserve(routing.strokes.size());
    for (const RoutedStroke& stroke : routing.strokes) {
        CompiledStroke compiled = compile_routed_stroke(stroke, raster);
        if (!compiled.points.empty()) glyph.strokes.push_back(std::move(compiled));
    }
    return glyph;
}

[[nodiscard]] PfcHash stable_hash(const std::vector<std::uint8_t>& bytes) {
    PfcHash result{};
    constexpr std::array<std::uint64_t, 4> seeds{
        1469598103934665603ULL, 1099511628211ULL,
        7809847782465536322ULL, 0x9E3779B185EBCA87ULL,
    };
    for (std::size_t block = 0; block < seeds.size(); ++block) {
        std::uint64_t value = seeds[block];
        for (const std::uint8_t byte : bytes) {
            value ^= byte;
            value *= 1099511628211ULL;
        }
        for (unsigned int index = 0; index < 8; ++index) {
            result[block * 8 + index] = static_cast<std::uint8_t>(value >> (index * 8U));
        }
    }
    return result;
}

[[nodiscard]] std::vector<std::uint8_t> read_bytes(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary | std::ios::ate);
    if (!stream) throw std::runtime_error("cannot read file: " + path.string());
    const std::streamsize size = stream.tellg();
    if (size < 0) throw std::runtime_error("cannot determine file size: " + path.string());
    stream.seekg(0);
    std::vector<std::uint8_t> bytes(static_cast<std::size_t>(size));
    if (!bytes.empty()) stream.read(reinterpret_cast<char*>(bytes.data()), size);
    if (!stream && !bytes.empty()) throw std::runtime_error("cannot read file: " + path.string());
    return bytes;
}

[[nodiscard]] PfcMetadata metadata_for(const CompilerOptions& options) {
    PfcMetadata metadata;
    metadata.font_hash = stable_hash(read_bytes(options.font_path));
    const std::string config = "resolution=" + std::to_string(options.resolution) +
        ";mask_threshold=160;spur_divisor=128;simplify_fu=1;chaikin=1;algorithm=1";
    const std::vector<std::uint8_t> config_bytes(config.begin(), config.end());
    metadata.config_hash = stable_hash(config_bytes);
    return metadata;
}

}  // namespace

std::vector<std::uint32_t> read_codepoints_file(const std::filesystem::path& path) {
    const std::vector<std::uint8_t> raw = read_bytes(path);
    const std::string bytes(raw.begin(), raw.end());
    std::vector<std::uint32_t> codepoints;
    for (std::size_t offset = 0; offset < bytes.size();) codepoints.push_back(decode_utf8(bytes, offset));
    codepoints.push_back(kFallbackCodepoint);
    std::sort(codepoints.begin(), codepoints.end());
    codepoints.erase(std::unique(codepoints.begin(), codepoints.end()), codepoints.end());
    return codepoints;
}

CompilationReport compile_font(const CompilerOptions& options) {
    if (options.resolution <= 0) throw std::invalid_argument("resolution must be positive");
    if (!std::filesystem::is_regular_file(options.font_path)) {
        throw std::runtime_error("font file does not exist or is not a regular file: " + options.font_path.string());
    }
    if (!std::filesystem::is_regular_file(options.chars_file)) {
        throw std::runtime_error("chars file does not exist or is not a regular file: " + options.chars_file.string());
    }
    if (std::filesystem::exists(options.output_path) && !options.force) {
        throw std::runtime_error("output already exists (pass --force to replace it): " + options.output_path.string());
    }
    if (!options.output_path.parent_path().empty()) std::filesystem::create_directories(options.output_path.parent_path());

    const std::vector<std::uint32_t> codepoints = read_codepoints_file(options.chars_file);
    FontFace probe(options.font_path);
    const FontMetrics metrics = probe.metrics();
    std::vector<std::optional<CompiledGlyph>> results(codepoints.size());
    std::atomic<std::size_t> next{0};
    std::atomic<std::size_t> missing{0};
    std::atomic<bool> cancelled{false};
    std::exception_ptr failure;
    std::mutex failure_mutex;

    std::size_t worker_count = options.threads;
    if (worker_count == 0) worker_count = std::thread::hardware_concurrency();
    worker_count = std::max<std::size_t>(1, worker_count);
    worker_count = std::min(worker_count, codepoints.size());
    std::vector<std::thread> workers;
    workers.reserve(worker_count);
    for (std::size_t worker = 0; worker < worker_count; ++worker) {
        workers.emplace_back([&] {
            try {
                FontFace face(options.font_path);  // FreeType faces are deliberately worker-local.
                while (!cancelled.load(std::memory_order_relaxed)) {
                    const std::size_t index = next.fetch_add(1, std::memory_order_relaxed);
                    if (index >= codepoints.size()) break;
                    results[index] = compile_one(face, codepoints[index], options.resolution);
                    if (!results[index].has_value()) missing.fetch_add(1, std::memory_order_relaxed);
                }
            } catch (...) {
                std::lock_guard lock(failure_mutex);
                if (failure == nullptr) failure = std::current_exception();
                cancelled.store(true, std::memory_order_relaxed);
            }
        });
    }
    for (std::thread& worker : workers) worker.join();
    if (failure != nullptr) std::rethrow_exception(failure);

    const auto fallback = std::lower_bound(codepoints.begin(), codepoints.end(), kFallbackCodepoint);
    if (fallback == codepoints.end() || !results[static_cast<std::size_t>(fallback - codepoints.begin())].has_value()) {
        throw std::runtime_error("font is missing required fallback glyph '?'");
    }
    CompiledFont compiled;
    compiled.metrics = metrics;
    compiled.glyphs.reserve(codepoints.size() - missing.load(std::memory_order_relaxed));
    for (auto& glyph : results) if (glyph.has_value()) compiled.glyphs.push_back(std::move(*glyph));
    write_pfc(options.output_path, compiled, metadata_for(options));
    return {codepoints.size(), compiled.glyphs.size(), missing.load(std::memory_order_relaxed)};
}

}  // namespace fontc
