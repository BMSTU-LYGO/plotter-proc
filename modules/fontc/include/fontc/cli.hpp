#pragma once

#include <cstddef>
#include <filesystem>
#include <optional>
#include <string>
#include <vector>

namespace fontc {

struct CompilerOptions {
    std::filesystem::path font_path;
    std::filesystem::path chars_file;
    std::filesystem::path output_path;
    std::vector<std::filesystem::path> special_pfc_paths;
    bool merge_only = false;
    int resolution = 1024;
    std::size_t threads = 0;  // 0 means hardware_concurrency.
    bool force = false;
    std::optional<std::filesystem::path> debug_dir;
    double reference_em_mm = 5.0;
    double spur_threshold_mm = 0.04;
    double curve_fit_tolerance_mm = 0.035;
    double curve_max_error_mm = 0.025;
    double min_segment_length_mm = 0.035;
    double straight_segment_target_mm = 0.25;
    double curve_segment_target_mm = 0.12;
    double tight_curve_segment_target_mm = 0.06;
};

struct ParseResult {
    std::optional<CompilerOptions> options;
    std::string message;
    int exit_code = 0;
};

[[nodiscard]] ParseResult parse_command_line(int argc, char** argv);
[[nodiscard]] std::string usage();

}  // namespace fontc
