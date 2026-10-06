#pragma once

#include "plotter/doc/path.hpp"

#include <cstdint>
#include <string>
#include <vector>

namespace plotter::doc {

struct PageJob final { std::uint32_t page_index{}, page_number{}; PathDocument paths; std::vector<std::string> source_element_ids, warnings; std::vector<std::pair<std::string, std::string>> metadata; };
struct PlotterJob final { Millimetres page_width{}, page_height{}; std::vector<PageJob> pages; std::vector<std::string> warnings; std::vector<std::pair<std::string, std::string>> metadata; };

}  // namespace plotter::doc
