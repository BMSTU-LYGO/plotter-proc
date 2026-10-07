#pragma once

#include "plotter/doc/config.hpp"

#include <cstddef>
#include <string>
#include <vector>

namespace plotter::doc {

// A deterministic summary of a validated, generated G-code program.  Distances
// are in millimetres and times in seconds. Segment estimates assume a stop at
// each junction, so firmware lookahead can make physical execution faster.
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
    std::size_t draw_segment_count{}, segments_below_0_05mm{}, segments_below_0_10mm{};
    std::size_t feedrate_changes{};
    std::size_t pen_down_count{}, pen_lift_count{}, travel_segment_count{};
    // Effective modal feed changes across XY and Z; excludes the initial F.
    std::size_t feedrate_change_count{};
    double pen_up_travel_mm{};
    double draw_length_mm{}, min_segment_mm{}, median_segment_mm{}, mean_segment_mm{}, max_segment_mm{};
    double p25_segment_mm{}, p75_segment_mm{};
    std::size_t segments_lt_0_1mm{}, segments_lt_0_25mm{}, segments_lt_0_5mm{}, segments_lt_1mm{};
    double estimated_draw_time_seconds{}, estimated_travel_time_seconds{}, estimated_z_time_seconds{}, estimated_total_time_seconds{};
    double requested_draw_speed_mm_s{}, estimated_average_draw_speed_mm_s{}, segments_reaching_cruise_speed_ratio{};
    std::vector<double> draw_feedrates_mm_min{};
};

// Validates the restricted dialect emitted by this module.  It throws
// std::invalid_argument for an unsafe or malformed program and std::length_error
// when the executable-command limit is exceeded.
[[nodiscard]] GcodeAnalysis analyze_gcode(
    const std::string& gcode, const MachineConfig& machine,
    std::size_t max_commands = 1'000'000);

}  // namespace plotter::doc
