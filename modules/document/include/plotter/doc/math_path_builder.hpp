#pragma once

#include "plotter/doc/font_registry.hpp"
#include "plotter/doc/model.hpp"
#include "plotter/doc/path.hpp"

#include <string>
#include <variant>

namespace plotter::doc {

// Builds PFC centerlines for the subset of MathElement expressions that are
// already linear text. Structural math needs a layout engine and is reported
// explicitly instead of being drawn as misleading plain text.
struct MathPathBuildError final {
    std::string code;
    std::string message;
};

struct MathPathBuildOptions final {
    std::string font_id;
    Points font_size{12.0};
    Millimetres page_width{}, page_height{};
};

using MathPathBuildResult = std::variant<PathDocument, MathPathBuildError>;

class MathPathBuilder final {
public:
    explicit MathPathBuilder(const FontRegistry& fonts) : fonts_(fonts) {}

    [[nodiscard]] MathPathBuildResult build(const MathElement& element,
                                            const MathPathBuildOptions& options) const;

private:
    const FontRegistry& fonts_;
};

}  // namespace plotter::doc
