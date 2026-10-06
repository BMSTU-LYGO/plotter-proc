#pragma once

#include "plotter/doc/geometry.hpp"

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace plotter::doc {

struct Stroke final {
    std::uint64_t id{};
    std::vector<Point> points;
    bool closed{};
    std::optional<std::int64_t> glyph_index, contour_index, word_index, source_page_index;
    std::optional<std::string> character, element_id, element_type, font_role, font_sha256, source_path, semantic_role, layout_group;
    std::vector<std::int64_t> source_glyph_indices, connection_ids;
    std::string source_characters;
    std::vector<std::string> segment_types;
    bool preserve_order{};
    std::int32_t z_order{};
};

struct PathDocument final {
    Millimetres page_width{}, page_height{};
    std::vector<Stroke> strokes;
    std::vector<std::string> warnings;
    std::vector<std::pair<std::string, std::string>> metadata;
};

}  // namespace plotter::doc
