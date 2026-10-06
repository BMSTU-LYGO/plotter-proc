#pragma once

#include "plotter/doc/font_registry.hpp"
#include "plotter/doc/layout.hpp"
#include "plotter/doc/path.hpp"

namespace plotter::doc {

// Materializes PFC centerlines at the positions already computed by layout.
// A LayoutPage may contain page-number glyphs; those are retained as a
// separate provenance role when PositionedGlyph::text_role is "page-number".
// With join_words enabled, only safe neighboring main strokes are joined.
// Secondary contours and unsafe gaps remain separate pen-down paths.
class CenterlinePathBuilder final {
public:
    explicit CenterlinePathBuilder(const FontRegistry& fonts) : fonts_(fonts) {}
    [[nodiscard]] PathDocument build(const LayoutPage& page, Millimetres page_width,
                                     Millimetres page_height, bool join_words = false) const;
private:
    const FontRegistry& fonts_;
};

}  // namespace plotter::doc
