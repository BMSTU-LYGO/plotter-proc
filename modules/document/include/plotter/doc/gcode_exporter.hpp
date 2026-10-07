#pragma once

#include "plotter/doc/config.hpp"

#include <cstddef>
#include <filesystem>
#include <string>

namespace plotter::doc {

inline constexpr std::size_t kDefaultMaxGcodeCommands = 1'000'000;

[[nodiscard]] Point to_machine_point(Point page_point, const PathDocument& document,
                                     const MachineConfig& machine);
[[nodiscard]] std::string generate_gcode(const PathDocument& document,
                                         const MachineConfig& machine,
                                         std::size_t max_commands = kDefaultMaxGcodeCommands);
[[nodiscard]] std::string normalize_modal_feedrate(const std::string& gcode);
void write_gcode_atomic(const std::string& gcode, const std::filesystem::path& output);

}  // namespace plotter::doc
