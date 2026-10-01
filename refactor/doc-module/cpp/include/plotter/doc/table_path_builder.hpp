#pragma once

#include "plotter/doc/model.hpp"
#include "plotter/doc/path.hpp"

namespace plotter::doc {

// Materializes the visible borders of an already-positioned table.  The table
// bounds establish the coordinate frame; its column and row dimensions are
// resolved within that frame.  A cell with a span contributes only its outer
// edges, so merged-cell interiors are never drawn.
//
// Cell text is intentionally not materialized here: TableCell holds source
// paragraphs, but it has no positioned glyph layout.  Text layout belongs to
// the layout stage before centerline path construction.
class TablePathBuilder final {
public:
    [[nodiscard]] PathDocument build(const TableElement& table, Millimetres page_width,
                                     Millimetres page_height) const;
};

}  // namespace plotter::doc
