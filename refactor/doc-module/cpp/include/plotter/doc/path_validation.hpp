#pragma once

#include "plotter/doc/path.hpp"

#include <cstddef>
#include <string>
#include <vector>

namespace plotter::doc {

struct CircularKeepOut final {
    Point center{};
    Millimetres radius{};
    Millimetres clearance{};
};

struct PathValidationOptions final {
    std::size_t max_points_per_stroke{1'000'000};
    bool require_nonempty{true};
    bool require_page_bounds{true};
    std::vector<CircularKeepOut> keep_outs;
};

struct PathValidationIssue final {
    std::size_t stroke_index{};
    std::string code;
    std::string message;
};

[[nodiscard]] std::vector<PathValidationIssue> validate_path_document(
    const PathDocument& document, const PathValidationOptions& options = {});

}  // namespace plotter::doc
