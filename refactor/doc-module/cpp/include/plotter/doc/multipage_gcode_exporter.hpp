#pragma once

#include "plotter/doc/gcode_exporter.hpp"

#include <cstddef>
#include <string>

namespace plotter::doc {

[[nodiscard]] std::string generate_job_gcode(
    const PlotterJob& job, const MachineConfig& machine,
    std::size_t max_commands = kDefaultMaxGcodeCommands);

}  // namespace plotter::doc
