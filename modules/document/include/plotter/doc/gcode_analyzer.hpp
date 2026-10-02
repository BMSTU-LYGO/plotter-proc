#pragma once

#include "plotter/doc/config.hpp"

#include <cstddef>
#include <string>

namespace plotter::doc {

// A deterministic summary of a validated, generated G-code program.  Distances
// are in millimetres and times are ideal feedrate-based estimates.
struct GcodeAnalysis final {
    std::size_t gcode_command_count{};
    std::size_t motion_command_count{};
    std::size_t z_command_count{};
    std::size_t dwell_count{};
    std::size_t page_count{1};
    std::size_t page_change_count{};
    double dwell_time_seconds{};
    double ideal_motion_time_seconds{};
    double ideal_total_time_seconds{};
    double xy_motion_distance_mm{};
    double z_motion_distance_mm{};
};

// Validates the restricted dialect emitted by this module.  It throws
// std::invalid_argument for an unsafe or malformed program and std::length_error
// when the executable-command limit is exceeded.
[[nodiscard]] GcodeAnalysis analyze_gcode(
    const std::string& gcode, const MachineConfig& machine,
    std::size_t max_commands = 1'000'000);

}  // namespace plotter::doc
