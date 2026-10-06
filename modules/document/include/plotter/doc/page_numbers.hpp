#pragma once

#include "plotter/doc/font_registry.hpp"
#include "plotter/doc/layout.hpp"

#include <string>

namespace plotter::doc {

struct PageNumberOptions final {
    bool enabled{};
    Millimetres page_width{210.0}, page_height{297.0};
    Millimetres baseline_from_bottom{4.5};
    Points size{9.0};
    std::string font_id;
};

void append_page_numbers(LayoutDocument& layout, const FontRegistry& fonts,
                         const PageNumberOptions& options);

}  // namespace plotter::doc
