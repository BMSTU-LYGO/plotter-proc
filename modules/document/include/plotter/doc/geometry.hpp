#pragma once

#include "plotter/doc/units.hpp"

namespace plotter::doc {

struct Point final {
    Millimetres x{};
    Millimetres y{};
};

struct Rect final {
    Millimetres x{};
    Millimetres y{};
    Millimetres width{};
    Millimetres height{};

    [[nodiscard]] Millimetres right() const;
    [[nodiscard]] Millimetres bottom() const;
    [[nodiscard]] bool has_positive_area() const;
};

struct PageTransform final {
    Millimetres source_page_width{};
    Millimetres source_page_height{};
    Rect source_content{};
    Rect target_content{};
    double scale{};
    Millimetres offset_x{};
    Millimetres offset_y{};

};

}  // namespace plotter::doc
