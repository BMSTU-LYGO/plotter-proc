#include "plotter/doc/geometry.hpp"

namespace plotter::doc {
Millimetres Rect::right() const { return x + width; }
Millimetres Rect::bottom() const { return y + height; }
bool Rect::has_positive_area() const { return width.value > 0.0 && height.value > 0.0; }

}  // namespace plotter::doc
