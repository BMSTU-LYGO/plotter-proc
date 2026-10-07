#pragma once

#include "plotter/doc/job.hpp"
#include "plotter/doc/gcode_analyzer.hpp"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace plotter::doc {

struct ImportStats final {
    std::uint32_t source_pages{};
    std::uint32_t text_elements{}, raster_images{}, vector_elements{}, math_elements{}, tables{};
};

struct LayoutStats final {
    std::uint32_t pages{}, lines{}, glyphs{}, placements{}, table_fragments{};
};

struct GeometryStats final {
    std::uint64_t strokes{}, points{};
    double ink_length_mm{};
};

struct MotionStats final {
    double draw_length_mm{}, travel_length_mm{};
    std::uint64_t pen_lifts{};
};

struct CacheStats final { std::uint64_t hits{}, misses{}; };

struct StageTimings final {
    double import_ms{}, layout_ms{}, path_and_geometry_ms{}, gcode_ms{};
    std::uint64_t peak_rss_kib{};
};

struct PageReport final {
    std::uint32_t page_index{}, page_number{};
    GeometryStats geometry{};
    MotionStats motion{};
    std::vector<std::string> warnings;
};

struct PipelineReport final {
    std::string status{"ok"};
    std::string artifact_level{"normal"};
    ImportStats import{};
    LayoutStats layout{};
    GeometryStats geometry{};
    MotionStats motion{};
    CacheStats cache{};
    StageTimings timings{};
    GcodeAnalysis gcode{};
    std::vector<PageReport> pages;
    std::vector<std::string> warnings;
    std::vector<std::string> errors;
};

[[nodiscard]] PageReport make_page_report(const PageJob& page);
[[nodiscard]] PipelineReport make_pipeline_report(const PlotterJob& job,
                                                  std::string artifact_level = "normal");
[[nodiscard]] std::string serialize_report_json(const PipelineReport& report);

}  // namespace plotter::doc
