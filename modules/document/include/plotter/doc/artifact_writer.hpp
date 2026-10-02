#pragma once

#include "plotter/doc/report.hpp"

#include <filesystem>
#include <stdexcept>
#include <string>

namespace plotter::doc {

enum class ArtifactLevel { minimal, normal, debug, audit };

struct ArtifactOptions final {
    std::filesystem::path output_directory;
    ArtifactLevel level{ArtifactLevel::normal};
    bool write_preview{true};
};

struct ArtifactPaths final {
    std::filesystem::path job_json, report_json, paths_json, preview_svg;
};

class ArtifactError final : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

[[nodiscard]] std::string_view artifact_level_name(ArtifactLevel level) noexcept;
[[nodiscard]] ArtifactPaths write_artifacts(const PlotterJob& job,
                                            const PipelineReport& report,
                                            const ArtifactOptions& options);
void write_error_artifacts(const std::filesystem::path& output_directory,
                           std::string message,
                           ArtifactLevel level = ArtifactLevel::normal);

}  // namespace plotter::doc
