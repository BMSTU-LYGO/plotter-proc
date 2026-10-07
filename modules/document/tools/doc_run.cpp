#include "plotter/doc/pipeline.hpp"
#include "plotter/doc/config_reader.hpp"
#include "plotter/doc/thread_pool.hpp"

#include <charconv>
#include <cmath>
#include <iostream>
#include <string_view>

int main(int argc, char** argv) {
    using namespace plotter::doc;
    PipelineOptions options;
    std::filesystem::path layout_config, machine_config;
    options.config.page = {"A5", {148.0}, {210.0}, {{15.0}, {15.0}, {15.0}, {15.0}}};
    options.config.machine.workspace = {{0.0}, {320.0}, {0.0}, {320.0}};
    for (int i = 1; i < argc; ++i) {
        const std::string_view argument{argv[i]};
        const auto next = [&]() -> std::string_view { return ++i < argc ? std::string_view{argv[i]} : std::string_view{}; };
        if (argument == "--input") options.input_path = next();
        else if (argument == "--output") options.output_directory = next();
        else if (argument == "--font") options.pfc_path = next();
        else if (argument == "--fallback-font") options.fallback_font_paths.emplace_back(next());
        else if (argument == "--digit-font") options.digit_font_path = next();
        else if (argument == "--font-mode") {
            const auto mode = next();
            if (mode == "centerline") options.font_mode = FontMode::centerline;
            else if (mode == "outline") options.font_mode = FontMode::outline;
            else { std::cerr << "unsupported font mode: " << mode << '\n'; return 2; }
        }
        else if (argument == "--layout-config") layout_config = next();
        else if (argument == "--cache-dir") options.cache_directory = next();
        else if (argument == "--no-cache") options.use_cache = false;
        else if (argument == "--no-preview") options.write_preview = false;
        else if (argument == "--machine-config") machine_config = next();
        else if (argument == "--page") {
            const auto page = next();
            if (page == "A4") options.config.page = {"A4", {210.0}, {297.0}, {{15.0}, {15.0}, {15.0}, {15.0}}};
            else if (page != "A5") { std::cerr << "unsupported page: " << page << '\n'; return 2; }
        } else if (argument == "--size") {
            const auto size = next();
            if (size == "small") options.font_size = {4.0 * 72.0 / 25.4};
            else if (size == "normal") options.font_size = {5.0 * 72.0 / 25.4};
            else if (size == "large") options.font_size = {6.5 * 72.0 / 25.4};
            else { std::cerr << "unsupported size: " << size << '\n'; return 2; }
        } else if (argument == "--artifact-level") {
            const auto level = next();
            if (level == "minimal") options.artifact_level = ArtifactLevel::minimal;
            else if (level == "normal") options.artifact_level = ArtifactLevel::normal;
            else if (level == "debug") options.artifact_level = ArtifactLevel::debug;
            else if (level == "audit") options.artifact_level = ArtifactLevel::audit;
            else { std::cerr << "unsupported artifact level: " << level << '\n'; return 2; }
        } else if (argument == "--threads") {
            try { options.thread_count = ThreadPool::thread_count_from_string(next()); }
            catch (const std::exception& error) { std::cerr << error.what() << '\n'; return 2; }
        }
        else if (argument == "--size-mm") {
            const auto value = next();
            double millimetres{};
            const auto parsed = std::from_chars(value.data(), value.data() + value.size(), millimetres);
            if (value.empty() || parsed.ec != std::errc{} || parsed.ptr != value.data() + value.size() ||
                !std::isfinite(millimetres) || millimetres < 1.0 || millimetres > 20.0) {
                std::cerr << "--size-mm must be between 1 and 20\n"; return 2;
            }
            options.font_size = {millimetres * 72.0 / 25.4};
        }
        else if (argument == "--join-words") options.join_words = true;
        else if (argument == "--no-join-words") options.join_words = false;
        else if (argument == "--max-word-join-distance-mm") {
            const auto value = next();
            const auto parsed = std::from_chars(value.data(), value.data() + value.size(), options.max_word_join_distance_mm);
            if (value.empty() || parsed.ec != std::errc{} || parsed.ptr != value.data() + value.size() ||
                !std::isfinite(options.max_word_join_distance_mm) || options.max_word_join_distance_mm < 0.0 ||
                options.max_word_join_distance_mm > 2.0) {
                std::cerr << "--max-word-join-distance-mm must be between 0 and 2\n"; return 2;
            }
        }
        else if (argument == "--optimize") options.optimize_geometry = true;
        else if (argument == "--simplify") options.simplify_geometry = true;
        else if (argument == "--no-simplify") options.simplify_geometry = false;
        else if (argument == "--page-numbers") options.page_numbers = true;
        else if (argument == "--handwriting") options.handwriting.enabled = true;
        else if (argument == "--document-layout") {
            const auto mode = next();
            if (mode == "auto") options.document_layout = SourcePageTransformMode::automatic;
            else if (mode == "hybrid") options.document_layout = SourcePageTransformMode::hybrid;
            else if (mode == "preserve") options.document_layout = SourcePageTransformMode::preserve;
            else if (mode == "contain") options.document_layout = SourcePageTransformMode::contain;
            else if (mode == "reflow") options.document_layout = SourcePageTransformMode::reflow;
            else { std::cerr << "unsupported document layout: " << mode << '\n'; return 2; }
        }
        else if (argument == "--help") {
            std::cout << "usage: plotter-doc --input <file> --output <directory> [--font <font.pfc|font.ttf>] [--fallback-font <font.pfc|font.ttf>]... [--digit-font <font.pfc|font.ttf>] [--font-mode centerline|outline] [--page A5|A4] [--cache-dir <directory>] [--no-cache] [--no-preview] [--layout-config <yaml>] [--machine-config <yaml>] [--size small|normal|large] [--size-mm 1..20] [--join-words|--no-join-words] [--max-word-join-distance-mm 0..2] [--artifact-level minimal|normal|debug|audit] [--threads auto|N] [--optimize] [--simplify|--no-simplify] [--page-numbers] [--handwriting] [--document-layout auto|hybrid|preserve|contain|reflow]\n";
            return 0;
        } else { std::cerr << "unknown option: " << argument << '\n'; return 2; }
    }
    if (options.input_path.empty() || options.output_directory.empty()) {
        std::cerr << "--input and --output are required\n";
        return 2;
    }
    try {
        {
            if (layout_config.empty()) layout_config = "configs/layout.yaml";
            if (machine_config.empty()) machine_config = "configs/machine.yaml";
            options.config = load_pipeline_config(layout_config, machine_config, options.config.page.name);
        }
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n'; return 2;
    }
    const PipelineResult result = run_pipeline(options);
    if (!result.ok) { std::cerr << result.error << '\n'; return 1; }
    std::cerr << "DRAW feedrates:";
    for (double feed : result.report.gcode.draw_feedrates_mm_min) std::cerr << ' ' << feed;
    std::cerr << " mm/min; estimated total: " << result.report.gcode.estimated_total_time_seconds << " s\n";
    std::cout << result.gcode_path << '\n';
    return 0;
}
