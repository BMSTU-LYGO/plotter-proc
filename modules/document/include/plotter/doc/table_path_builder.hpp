#pragma once

#include "plotter/doc/font_registry.hpp"
#include "plotter/doc/model.hpp"
#include "plotter/doc/path.hpp"

#include <string>

namespace plotter::doc {

// Materializes the visible borders of an already-positioned table.  The table
// bounds establish the coordinate frame; its column and row dimensions are
// resolved within that frame.  A cell with a span contributes only its outer
// edges, so merged-cell interiors are never drawn.
//
// With a FontRegistry, simple cell text is materialized directly from PFC
// centerlines and clipped to its cell.  The default builder remains useful for
// empty-cell grids and reports nonempty text as unsupported.
class TablePathBuilder final {
public:
    TablePathBuilder() = default;
    TablePathBuilder(const FontRegistry& fonts, std::string font_id,
                     Points font_size = {10.0}, Millimetres cell_padding = {1.5});
    [[nodiscard]] PathDocument build(const TableElement& table, Millimetres page_width,
                                     Millimetres page_height) const;
private:
    const FontRegistry* fonts_{};
    std::string font_id_;
    Points font_size_{10.0};
    Millimetres cell_padding_{1.5};
};

}  // namespace plotter::doc
