#pragma once

#include "plotter/doc/artifact_writer.hpp"
#include "plotter/doc/config.hpp"
#include "plotter/doc/font_registry.hpp"

#include <filesystem>
#include <string>

namespace plotter::doc {

struct PipelineOptions final {
    std::filesystem::path input_path;
    std::filesystem::path output_directory;
    std::filesystem::path pfc_path;
    std::string font_id{"body"};
    std::string font_sha256;
    Points font_size{12.0};
    PipelineConfig config{};
    ArtifactLevel artifact_level{ArtifactLevel::normal};
    bool optimize_geometry{};
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

}  // namespace plotter::doc
