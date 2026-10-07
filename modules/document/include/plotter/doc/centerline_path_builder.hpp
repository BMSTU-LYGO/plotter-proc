#pragma once

#include "plotter/doc/font_registry.hpp"
#include "plotter/doc/layout.hpp"
#include "plotter/doc/path.hpp"

namespace plotter::doc {

enum class WordMoveKind { draw, travel };
struct WordRouteMove final { WordMoveKind kind; Stroke stroke; };
struct WordRoute final { std::vector<WordRouteMove> moves; };

// Orders strokes already placed in page coordinates. Travel moves separate
// disconnected pen-down groups; the returned route does not alter glyph ink.
[[nodiscard]] WordRoute build_word_route(const std::vector<Stroke>& strokes,
                                         double max_word_join_distance_mm = 2.0);

// Materializes PFC centerlines at the positions already computed by layout.
// A LayoutPage may contain page-number glyphs; those are retained as a
// separate provenance role when PositionedGlyph::text_role is "page-number".
// With join_words enabled, only safe neighboring main strokes are joined.
// Secondary contours and unsafe gaps remain separate pen-down paths.
class CenterlinePathBuilder final {
public:
    explicit CenterlinePathBuilder(const FontRegistry& fonts) : fonts_(fonts) {}
    [[nodiscard]] PathDocument build(const LayoutPage& page, Millimetres page_width,
                                     Millimetres page_height, bool join_words = false,
                                     double max_word_join_distance_mm = 2.0) const;
private:
    const FontRegistry& fonts_;
};

}  // namespace plotter::doc
