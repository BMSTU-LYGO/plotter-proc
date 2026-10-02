#pragma once

#include "plotter/doc/artifact_writer.hpp"
#include "plotter/doc/config.hpp"
#include "plotter/doc/font_registry.hpp"
#include "plotter/doc/page_numbers.hpp"
#include "plotter/doc/handwriting.hpp"
#include "plotter/doc/source_page_transform.hpp"
#include "plotter/doc/path_simplifier.hpp"

#include <filesystem>
#include <cstddef>
#include <string>

namespace plotter::doc {

enum class FontMode { centerline, outline };

struct PipelineOptions final {
    std::filesystem::path input_path;
    std::filesystem::path output_directory;
    std::filesystem::path pfc_path;
    std::filesystem::path fallback_font_path;
    std::filesystem::path cache_directory;
    bool use_cache{true};
    std::string font_id{"body"};
    std::string font_sha256;
    Points font_size{5.0 * 72.0 / 25.4};
    FontMode font_mode{FontMode::centerline};
    PipelineConfig config{};
    ArtifactLevel artifact_level{ArtifactLevel::normal};
    std::size_t thread_count{1};
    bool optimize_geometry{};
    bool simplify_geometry{};
    bool page_numbers{};
    HandwritingOptions handwriting{};
    SourcePageTransformMode document_layout{SourcePageTransformMode::automatic};
    double preserve_max_upscale{1.10};
};

struct PipelineResult final {
    bool ok{};
    std::string error;
    PlotterJob job;
    PipelineReport report;
    ArtifactPaths artifacts;
    std::filesystem::path gcode_path;
};

[[nodiscard]] PipelineResult run_pipeline(const PipelineOptions& options);
[[nodiscard]] PipelineResult run_pipeline(const Document& document, const PipelineOptions& options);

}  // namespace plotter::doc
