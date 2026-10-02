#pragma once

#include "plotter/doc/font_registry.hpp"
#include "plotter/doc/layout.hpp"
#include "plotter/doc/path.hpp"

namespace plotter::doc {

// Materializes PFC centerlines at the positions already computed by layout.
// A LayoutPage may contain page-number glyphs; those are retained as a
// separate provenance role when PositionedGlyph::text_role is "page-number".
class CenterlinePathBuilder final {
public:
    explicit CenterlinePathBuilder(const FontRegistry& fonts) : fonts_(fonts) {}
    [[nodiscard]] PathDocument build(const LayoutPage& page, Millimetres page_width,
                                     Millimetres page_height) const;
private:
    const FontRegistry& fonts_;
};

}  // namespace plotter::doc
