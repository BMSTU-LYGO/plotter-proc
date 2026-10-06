#pragma once

#include "plotter/doc/path_validation.hpp"

#include <cstddef>
#include <string>
#include <vector>

namespace plotter::doc {

struct PathOptimizerOptions final {
    bool enable_safe_retrace{true};
    Millimetres max_retrace_length{1.2};
    std::size_t max_retrace_repeats{1};
    Millimetres endpoint_tolerance{0.000001};
    double max_retrace_ratio{1.0};
    std::vector<std::string> retrace_segment_types{"glyph"};
    std::vector<CircularKeepOut> keep_outs;
};

struct PathOptimizationReport final {
    std::size_t retrace_merges{};
    Millimetres retrace_distance{};
};

// Reorders only within contiguous semantic groups.  The returned strokes retain
// their source fields; a safe retrace combines the provenance of its inputs.
[[nodiscard]] PathDocument optimize_paths(
    const PathDocument& document, const PathOptimizerOptions& options = {},
    PathOptimizationReport* report = nullptr);

}  // namespace plotter::doc
