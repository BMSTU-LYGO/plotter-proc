#pragma once

#include "plotter/doc/path_validation.hpp"

#include <cstdint>
#include <string>
#include <variant>
#include <vector>

namespace plotter::doc {

// A deliberately bounded, deterministic handwriting pass for PFC body text.
// It has no language-specific joining graph or outline rerouter; when a
// transformed result would violate a protected region it restores the source
// body geometry and reports the safety decision in metadata.
struct HandwritingOptions final {
    bool enabled{};
    std::uint64_t seed{};
    Millimetres baseline_jitter{0.12};
    Degrees rotation{1.0};
    double glyph_scale_percent{3.0};
    double glyph_slant{0.04};
    double word_width_percent{3.0};
    std::vector<CircularKeepOut> keep_outs;
};

struct HandwritingError final {
    std::string code;
    std::string message;
};

using HandwritingResult = std::variant<PathDocument, HandwritingError>;

[[nodiscard]] HandwritingResult apply_handwriting(const PathDocument& document,
                                                   const HandwritingOptions& options = {});

}  // namespace plotter::doc
