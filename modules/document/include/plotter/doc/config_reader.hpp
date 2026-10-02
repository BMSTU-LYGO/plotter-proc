#pragma once

#include "plotter/doc/config.hpp"

#include <filesystem>
#include <string_view>

namespace plotter::doc {

// Reads the scalar/profile subset used by the existing project YAML files.
// Unsupported syntax on a consumed key is an error, not a silent default.
[[nodiscard]] PipelineConfig load_pipeline_config(const std::filesystem::path& layout_yaml,
                                                  const std::filesystem::path& machine_yaml,
                                                  std::string_view page_name);

}  // namespace plotter::doc
