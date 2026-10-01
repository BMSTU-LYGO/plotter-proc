#pragma once

#include "plotter/doc/path.hpp"

#include <cstddef>

namespace plotter::doc {

struct PathSimplificationOptions final {
    Millimetres duplicate_epsilon{};
    // Kept separate from duplicate_epsilon so callers can use different
    // centerline and outline policies.  RDP remains the error-budget owner.
    Millimetres min_segment_length{};
    Millimetres max_deviation{};
};

struct PathSimplificationReport final {
    std::size_t points_before{};
    std::size_t points_after{};
    Millimetres max_observed_deviation{};
};

// Preserves every Stroke field except its reduced points.  Open paths retain
// endpoints; closed paths retain closed=true and at least three vertices.
[[nodiscard]] PathDocument simplify_path_document(
    const PathDocument& document, const PathSimplificationOptions& options,
    PathSimplificationReport* report = nullptr);

}  // namespace plotter::doc
