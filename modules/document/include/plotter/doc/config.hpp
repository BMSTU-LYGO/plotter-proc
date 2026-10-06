#pragma once

#include "plotter/doc/job.hpp"
#include "plotter/doc/path_validation.hpp"

#include <cstdint>
#include <string>
#include <vector>

namespace plotter::doc {

struct Margins final { Millimetres left{}, right{}, top{}, bottom{}; };
struct PageConfig final { std::string name{"A4"}; Millimetres width{210.0}, height{297.0}; Margins margins{}; Millimetres line_gap{5.0}; };
struct WorkspaceConfig final { Millimetres min_x{}, max_x{220.0}, min_y{}, max_y{220.0}; };
struct FeedrateConfig final {
    double draw_mm_min{2000.0}, draw_fast_mm_min{2000.0};
    double travel_mm_min{6000.0}, z_mm_min{1200.0};
};
struct PenConfig final { Millimetres up_z{2.5}, down_z{1.0}; std::uint32_t down_settle_ms{20}; };
struct GcodeConfig final { bool home{}; bool absolute_positioning{true}; bool units_mm{true}; std::uint32_t decimals{3}; };
struct PageChangeConfig final {
    bool enabled{};
    double pause_seconds{};
    bool keep_steppers_enabled{};
    std::string park_mode{"corner"};
    std::string park_corner{"top_right"};
    Millimetres park_inset{};
    Point park_machine_point{};
    std::string wait_command{"dwell"};
};

struct MachineConfig final {
    WorkspaceConfig workspace{};
    Point page_origin{};
    bool invert_x{};
    bool invert_y{};
    PenConfig pen{};
    FeedrateConfig feedrate{};
    GcodeConfig gcode{};
    PageChangeConfig page_change{};
    std::vector<CircularKeepOut> keep_out{};
};
struct PipelineConfig final { PageConfig page{}; MachineConfig machine{}; };

enum class PreflightSeverity { warning, error };
struct PreflightIssue final { PreflightSeverity severity{PreflightSeverity::error}; std::string code, message; };
struct PreflightReport final { std::vector<PreflightIssue> issues; [[nodiscard]] bool ok() const noexcept; };

[[nodiscard]] PreflightReport validate_config(const PipelineConfig& config);
[[nodiscard]] PreflightReport preflight(const PathDocument& paths, const PipelineConfig& config);
[[nodiscard]] PreflightReport preflight(const PlotterJob& job, const PipelineConfig& config);

}  // namespace plotter::doc
