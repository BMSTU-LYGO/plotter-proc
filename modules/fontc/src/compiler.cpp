#include "fontc/compiler.hpp"

#include "fontc/binary_image.hpp"
#include "fontc/compiled_font.hpp"
#include "fontc/curve_fit.hpp"
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
#include <cmath>
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
    points.erase(std::unique(points.begin(), points.end()), points.end());
    return {std::move(points)};
}


[[nodiscard]] bool letter_codepoint(std::uint32_t codepoint) {
    return (codepoint >= 'A' && codepoint <= 'Z') ||
           (codepoint >= 'a' && codepoint <= 'z') ||
           (codepoint >= 0x0400U && codepoint <= 0x04FFU);
}

[[nodiscard]] double point_distance(PointFU a, PointFU b) {
    return std::hypot(static_cast<double>(a.x) - b.x,
                      static_cast<double>(a.y) - b.y);
}

[[nodiscard]] double cross(PointFU a, PointFU b, PointFU c) {
    return (static_cast<double>(b.x) - a.x) * (static_cast<double>(c.y) - a.y) -
           (static_cast<double>(b.y) - a.y) * (static_cast<double>(c.x) - a.x);
}

[[nodiscard]] bool crosses(PointFU a, PointFU b, PointFU c, PointFU d) {
    return cross(a, b, c) * cross(a, b, d) < 0.0 &&
           cross(c, d, a) * cross(c, d, b) < 0.0;
}

void join_disconnected_letter(CompiledGlyph& glyph, double max_connector_fu) {
    if (!letter_codepoint(glyph.codepoint) || glyph.strokes.size() < 2) return;
    const auto source = std::move(glyph.strokes);
    std::vector<bool> used(source.size());
    const auto primary = std::max_element(source.begin(), source.end(),
        [](const CompiledStroke& a, const CompiledStroke& b) {
            return a.points.size() < b.points.size();
        });
    const std::size_t first = static_cast<std::size_t>(primary - source.begin());
    CompiledStroke joined = source[first];
    used[first] = true;
    if (joined.points.size() >= 2 && joined.points.front().x > joined.points.back().x)
        std::reverse(joined.points.begin(), joined.points.end());
    for (std::size_t remaining = source.size() - 1; remaining > 0; --remaining) {
        const PointFU end = joined.points.back();
        double best_score = std::numeric_limits<double>::infinity();
        std::size_t chosen = source.size();
        bool reverse = false;
        for (std::size_t index = 0; index < source.size(); ++index) {
            if (used[index] || source[index].points.empty()) continue;
            for (bool backwards : {false, true}) {
                const PointFU start = backwards ? source[index].points.back() : source[index].points.front();
                double score = point_distance(end, start);
                for (const auto& obstacle : source)
                    for (std::size_t segment = 1; segment < obstacle.points.size(); ++segment)
                        if (crosses(end, start, obstacle.points[segment - 1], obstacle.points[segment]))
                            score += 1000.0;
                if (score < best_score) {
                    best_score = score;
                    chosen = index;
                    reverse = backwards;
                }
            }
        }
        if (chosen == source.size() || best_score > max_connector_fu) {
            glyph.strokes = source;
            return;
        }
        used[chosen] = true;
        const auto& points = source[chosen].points;
        if (reverse) {
            for (auto it = points.rbegin(); it != points.rend(); ++it)
                if (joined.points.empty() || *it != joined.points.back()) joined.points.push_back(*it);
        } else {
            for (PointFU point : points)
                if (joined.points.empty() || point != joined.points.back()) joined.points.push_back(point);
        }
    }
    glyph.strokes = {std::move(joined)};
}

[[nodiscard]] std::optional<CompiledGlyph> compile_one(
    FontFace& face,
    std::uint32_t codepoint,
    int resolution, const CompilerOptions& options, CompilationReport& report
) {
    if (!face.glyph_metrics(codepoint).has_value()) return std::nullopt;
    const RasterGlyph raster = rasterize_glyph(face, codepoint, resolution);
    const BinaryImage mask = make_binary_mask(raster);
    const BinaryImage skeleton = thin_guo_hall(mask);
    const float pixels_per_mm = static_cast<float>(resolution / options.reference_em_mm);
    const BinaryImage pruned = prune_short_spurs(skeleton, 0.0F);
    const SkeletonGraph raw_graph = cleanup_graph(build_skeleton_graph(pruned));
    SpurCleanupStats spur_stats;
    const SkeletonGraph clean_graph = remove_short_graph_spurs(raw_graph,
        static_cast<float>(options.spur_threshold_mm)*pixels_per_mm, &spur_stats);
    const CurveOptions curves{static_cast<float>(options.curve_fit_tolerance_mm)*pixels_per_mm,
        static_cast<float>(options.curve_max_error_mm)*pixels_per_mm,
        static_cast<float>(options.min_segment_length_mm)*pixels_per_mm,
        static_cast<float>(options.straight_segment_target_mm)*pixels_per_mm,
        static_cast<float>(options.curve_segment_target_mm)*pixels_per_mm,
        static_cast<float>(options.tight_curve_segment_target_mm)*pixels_per_mm};
    CurveStats curve_stats;
    const SkeletonGraph graph = fit_graph_edges(clean_graph, curves, &curve_stats);
    const RoutingResult routing = route_graph(graph);
    for (const Edge& edge : raw_graph.edges) report.raw_centerline_points += edge.points.size();
    report.clean_centerline_points = curve_stats.raw_points;
    report.removed_spurs = spur_stats.removed_spurs;
    report.removed_spur_length_mm = spur_stats.removed_spur_length/pixels_per_mm;
    report.graph_nodes_before = spur_stats.graph_nodes_before;
    report.graph_nodes_after = spur_stats.graph_nodes_after;
    report.bezier_segment_count = curve_stats.bezier_segments;
    report.final_path_points = curve_stats.final_points;
    report.stroke_count = routing.stroke_count;

    CompiledGlyph glyph;
    glyph.codepoint = codepoint;
    glyph.advance_font_units = raster.advance_font_units;
    glyph.strokes.reserve(routing.strokes.size());
    for (const RoutedStroke& stroke : routing.strokes) {
        CompiledStroke compiled = compile_routed_stroke(stroke, raster);
        if (!compiled.points.empty()) glyph.strokes.push_back(std::move(compiled));
    }
    // The source Ж/ж skeleton has several short pieces of one visible form.
    // Keep deliberately detached accents and stems as separate components.
    const bool fragmented_zhe = codepoint == 0x0416U || codepoint == 0x0436U;
    join_disconnected_letter(glyph, fragmented_zhe
        ? std::numeric_limits<double>::infinity()
        : static_cast<double>(face.metrics().units_per_em) * 0.20);
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
        ";em_mm=" + std::to_string(options.reference_em_mm) +
        ";spur=" + std::to_string(options.spur_threshold_mm) +
        ";fit=" + std::to_string(options.curve_fit_tolerance_mm) +
        ";error=" + std::to_string(options.curve_max_error_mm) +
        ";min=" + std::to_string(options.min_segment_length_mm) +
        ";straight=" + std::to_string(options.straight_segment_target_mm) +
        ";curve=" + std::to_string(options.curve_segment_target_mm) +
        ";tight=" + std::to_string(options.tight_curve_segment_target_mm) + ";algorithm=6";
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
    for (double value : {options.reference_em_mm, options.curve_fit_tolerance_mm,
                         options.curve_max_error_mm, options.min_segment_length_mm,
                         options.straight_segment_target_mm, options.curve_segment_target_mm,
                         options.tight_curve_segment_target_mm})
        if (!std::isfinite(value) || value <= 0) throw std::invalid_argument("Invalid curve option");
    if (!std::isfinite(options.spur_threshold_mm) || options.spur_threshold_mm < 0)
        throw std::invalid_argument("Invalid spur threshold");
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
    std::vector<CompilationReport> glyph_reports(codepoints.size());
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
                    results[index] = compile_one(face, codepoints[index], options.resolution, options, glyph_reports[index]);
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

    CompiledFont compiled;
    compiled.metrics = metrics;
    compiled.glyphs.reserve(codepoints.size() - missing.load(std::memory_order_relaxed));
    for (auto& glyph : results) if (glyph.has_value()) compiled.glyphs.push_back(std::move(*glyph));
    std::vector<PfcFont> specials;
    for (const auto& path : options.special_pfc_paths) specials.push_back(PfcFont::load(path));
    const auto merge_stats = merge_special_glyphs(compiled, specials, codepoints);
    if (std::none_of(compiled.glyphs.begin(), compiled.glyphs.end(), [](const auto& glyph) {
            return glyph.codepoint == kFallbackCodepoint;
        })) throw std::runtime_error("font is missing required fallback glyph '?'");
    write_pfc(options.output_path, compiled, metadata_for(options));
    CompilationReport report;
    report.requested_codepoints = codepoints.size();
    report.compiled_glyphs = compiled.glyphs.size();
    report.skipped_missing_glyphs = merge_stats.missing_codepoints;
    report.merge_stats = merge_stats;
    for (const auto& item : glyph_reports) {
        report.raw_centerline_points += item.raw_centerline_points;
        report.clean_centerline_points += item.clean_centerline_points;
        report.removed_spurs += item.removed_spurs;
        report.removed_spur_length_mm += item.removed_spur_length_mm;
        report.graph_nodes_before += item.graph_nodes_before;
        report.graph_nodes_after += item.graph_nodes_after;
        report.stroke_count += item.stroke_count;
        report.bezier_segment_count += item.bezier_segment_count;
        report.final_path_points += item.final_path_points;
    }
    return report;
}

}  // namespace fontc
