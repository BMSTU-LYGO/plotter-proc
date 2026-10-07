#include "plotter/doc/report.hpp"

#include <cmath>
#include <iomanip>
#include <locale>
#include <map>
#include <sstream>
#include <stdexcept>

namespace plotter::doc {
namespace {
class Json final {
public:
    void raw(std::string_view value) { output += value; }
    void string(std::string_view value) {
        output += '"';
        for (unsigned char c : value) {
            switch (c) { case '"': output += "\\\""; break; case '\\': output += "\\\\"; break; case '\n': output += "\\n"; break; case '\r': output += "\\r"; break; case '\t': output += "\\t"; break; default: if (c < 0x20U) { static constexpr char hex[] = "0123456789abcdef"; output += "\\u00"; output += hex[c >> 4U]; output += hex[c & 15U]; } else output += static_cast<char>(c); }
        }
        output += '"';
    }
    void key(std::string_view name) { string(name); output += ':'; }
    void number(double value) {
        if (!std::isfinite(value)) throw std::invalid_argument("report cannot encode non-finite number");
        std::ostringstream stream; stream.imbue(std::locale::classic()); stream << std::setprecision(15) << (value == 0.0 ? 0.0 : value); output += stream.str();
    }
    void integer(std::uint64_t value) { output += std::to_string(value); }
    [[nodiscard]] std::string take() && { return std::move(output); }
private: std::string output;
};
double distance(Point a, Point b) { const double x = a.x.value - b.x.value, y = a.y.value - b.y.value; return std::sqrt(x * x + y * y); }
GeometryStats geometry(const PathDocument& paths) {
    GeometryStats result; result.strokes = paths.strokes.size();
    for (const auto& stroke : paths.strokes) { result.points += stroke.points.size(); for (std::size_t i = 1; i < stroke.points.size(); ++i) result.ink_length_mm += distance(stroke.points[i - 1], stroke.points[i]); if (stroke.closed && stroke.points.size() > 1) result.ink_length_mm += distance(stroke.points.back(), stroke.points.front()); }
    return result;
}
MotionStats motion(const PathDocument& paths) {
    MotionStats result;
    Point previous{};
    bool has_previous = false;
    std::map<std::int64_t, std::uint64_t> word_groups;
    for (const auto& stroke : paths.strokes) {
        if (stroke.points.size() < 2) continue;
        if (has_previous) result.travel_length_mm += distance(previous, stroke.points.front());
        ++result.pen_lifts;
        ++result.pen_down_count;
        if (stroke.word_index && *stroke.word_index >= 0) ++word_groups[*stroke.word_index];
        for (std::size_t i = 1; i < stroke.points.size(); ++i)
            result.draw_length_mm += distance(stroke.points[i - 1], stroke.points[i]);
        if (stroke.closed) result.draw_length_mm += distance(stroke.points.back(), stroke.points.front());
        previous = stroke.closed ? stroke.points.front() : stroke.points.back();
        has_previous = true;
    }
    result.word_count = word_groups.size();
    std::uint64_t word_lifts = 0;
    for (const auto& [word, groups] : word_groups) {
        static_cast<void>(word);
        word_lifts += groups;
        if (groups == 1) ++result.words_with_1_pen_down;
        else if (groups == 2) ++result.words_with_2_pen_down;
        else ++result.words_with_3plus_pen_down;
    }
    if (result.word_count) result.pen_lifts_per_word_avg = static_cast<double>(word_lifts) / result.word_count;
    return result;
}
void strings(Json& json, const std::vector<std::string>& values) { json.raw("["); for (std::size_t i = 0; i < values.size(); ++i) { if (i) json.raw(","); json.string(values[i]); } json.raw("]"); }
void geometry_json(Json& json, const GeometryStats& value) { json.raw("{"); json.key("ink_length_mm"); json.number(value.ink_length_mm); json.raw(","); json.key("points"); json.integer(value.points); json.raw(","); json.key("strokes"); json.integer(value.strokes); json.raw("}"); }
void motion_json(Json& json, const MotionStats& value) {
    json.raw("{");
    const auto count = [&](std::string_view key, std::uint64_t number) { json.key(key); json.integer(number); json.raw(","); };
    const auto measurement = [&](std::string_view key, double number) { json.key(key); json.number(number); json.raw(","); };
    count("word_count", value.word_count);
    count("pen_down_count", value.pen_down_count);
    count("pen_lift_count", value.pen_lifts);
    count("pen_lifts", value.pen_lifts);
    count("words_with_1_pen_down", value.words_with_1_pen_down);
    count("words_with_2_pen_down", value.words_with_2_pen_down);
    count("words_with_3plus_pen_down", value.words_with_3plus_pen_down);
    measurement("pen_lifts_per_word_avg", value.pen_lifts_per_word_avg);
    measurement("draw_length_mm", value.draw_length_mm);
    measurement("pen_up_travel_mm", value.travel_length_mm);
    json.key("travel_length_mm"); json.number(value.travel_length_mm);
    json.raw("}");
}
void gcode_json(Json& json, const GcodeAnalysis& value) {
    json.raw("{");
    const auto count = [&](std::string_view key, std::size_t number) { json.key(key); json.integer(number); json.raw(","); };
    const auto measurement = [&](std::string_view key, double number) { json.key(key); json.number(number); json.raw(","); };
    count("draw_segment_count", value.draw_segment_count);
    count("gcode_draw_segments", value.draw_segment_count);
    count("travel_segment_count", value.travel_segment_count);
    count("gcode_travel_segments", value.travel_segment_count);
    count("pen_down_count", value.pen_down_count);
    count("pen_lift_count", value.pen_lift_count);
    count("page_count", value.page_count);
    count("page_change_count", value.page_change_count);
    count("draw_moves", value.draw_segment_count);
    count("travel_moves", value.travel_segment_count);
    count("feedrate_change_count", value.feedrate_change_count);
    measurement("pen_up_travel_mm", value.pen_up_travel_mm);
    count("feedrate_changes", value.feedrate_changes);
    count("segments_below_0_05mm", value.segments_below_0_05mm);
    count("segments_below_0_10mm", value.segments_below_0_10mm);
    count("segments_lt_0_1mm", value.segments_lt_0_1mm);
    count("segments_lt_0_25mm", value.segments_lt_0_25mm);
    count("segments_lt_0_5mm", value.segments_lt_0_5mm);
    count("segments_lt_1mm", value.segments_lt_1mm);
    measurement("draw_length_mm", value.draw_length_mm);
    measurement("min_segment_mm", value.min_segment_mm);
    measurement("median_segment_mm", value.median_segment_mm);
    measurement("p25_segment_mm", value.p25_segment_mm);
    measurement("p75_segment_mm", value.p75_segment_mm);
    measurement("mean_segment_mm", value.mean_segment_mm);
    measurement("max_segment_mm", value.max_segment_mm);
    measurement("draw_distance_mm", value.draw_length_mm);
    measurement("travel_distance_mm", value.pen_up_travel_mm);
    measurement("z_distance_mm", value.z_motion_distance_mm);
    measurement("estimated_draw_time_seconds", value.estimated_draw_time_seconds);
    measurement("estimated_travel_time_seconds", value.estimated_travel_time_seconds);
    measurement("estimated_z_time_seconds", value.estimated_z_time_seconds);
    measurement("estimated_total_time_seconds", value.estimated_total_time_seconds);
    measurement("dwell_time_seconds", value.dwell_time_seconds);
    measurement("requested_draw_speed_mm_s", value.requested_draw_speed_mm_s);
    measurement("estimated_average_draw_speed_mm_s", value.estimated_average_draw_speed_mm_s);
    measurement("segments_reaching_cruise_speed_ratio", value.segments_reaching_cruise_speed_ratio);
    json.key("draw_feedrates_mm_min"); json.raw("[");
    for (std::size_t i = 0; i < value.draw_feedrates_mm_min.size(); ++i) {
        if (i) json.raw(",");
        json.number(value.draw_feedrates_mm_min[i]);
    }
    json.raw("],");
    json.key("ideal_total_time_seconds"); json.number(value.ideal_total_time_seconds);
    json.raw("}");
}
}

PageReport make_page_report(const PageJob& page) { return {page.page_index, page.page_number, geometry(page.paths), motion(page.paths), page.warnings}; }
PipelineReport make_pipeline_report(const PlotterJob& job, std::string artifact_level) {
    PipelineReport report; report.artifact_level = std::move(artifact_level); report.layout.pages = static_cast<std::uint32_t>(job.pages.size()); report.warnings = job.warnings;
    for (const auto& page : job.pages) { auto one = make_page_report(page); report.geometry.strokes += one.geometry.strokes; report.geometry.points += one.geometry.points; report.geometry.ink_length_mm += one.geometry.ink_length_mm; report.motion.draw_length_mm += one.motion.draw_length_mm; report.motion.travel_length_mm += one.motion.travel_length_mm; report.motion.pen_lifts += one.motion.pen_lifts; report.motion.pen_down_count += one.motion.pen_down_count;
        report.motion.pen_lifts_per_word_avg += one.motion.pen_lifts_per_word_avg * one.motion.word_count;
        report.motion.word_count += one.motion.word_count;
        report.motion.words_with_1_pen_down += one.motion.words_with_1_pen_down;
        report.motion.words_with_2_pen_down += one.motion.words_with_2_pen_down;
        report.motion.words_with_3plus_pen_down += one.motion.words_with_3plus_pen_down; report.pages.push_back(std::move(one)); }
    if (report.motion.word_count) report.motion.pen_lifts_per_word_avg /= report.motion.word_count;
    return report;
}
std::string serialize_report_json(const PipelineReport& report) {
    Json json; json.raw("{\"report\":{"); json.key("artifact_level"); json.string(report.artifact_level); json.raw(","); json.key("cache"); json.raw("{"); json.key("hits"); json.integer(report.cache.hits); json.raw(","); json.key("misses"); json.integer(report.cache.misses); json.raw("},"); json.key("errors"); strings(json, report.errors); json.raw(","); json.key("geometry"); geometry_json(json, report.geometry); json.raw(","); json.key("gcode"); gcode_json(json, report.gcode); json.raw(","); json.key("import"); json.raw("{"); json.key("math_elements"); json.integer(report.import.math_elements); json.raw(","); json.key("raster_images"); json.integer(report.import.raster_images); json.raw(","); json.key("source_pages"); json.integer(report.import.source_pages); json.raw(","); json.key("tables"); json.integer(report.import.tables); json.raw(","); json.key("text_elements"); json.integer(report.import.text_elements); json.raw(","); json.key("vector_elements"); json.integer(report.import.vector_elements); json.raw("},"); json.key("layout"); json.raw("{"); json.key("glyphs"); json.integer(report.layout.glyphs); json.raw(","); json.key("lines"); json.integer(report.layout.lines); json.raw(","); json.key("pages"); json.integer(report.layout.pages); json.raw(","); json.key("placements"); json.integer(report.layout.placements); json.raw(","); json.key("table_fragments"); json.integer(report.layout.table_fragments); json.raw("},"); json.key("motion"); motion_json(json, report.motion); json.raw(","); json.key("pages"); json.raw("["); for (std::size_t i = 0; i < report.pages.size(); ++i) { if (i) json.raw(","); const auto& page = report.pages[i]; json.raw("{"); json.key("geometry"); geometry_json(json, page.geometry); json.raw(","); json.key("motion"); motion_json(json, page.motion); json.raw(","); json.key("page_index"); json.integer(page.page_index); json.raw(","); json.key("page_number"); json.integer(page.page_number); json.raw(","); json.key("warnings"); strings(json, page.warnings); json.raw("}"); } json.raw("],"); json.key("status"); json.string(report.status); json.raw(","); json.key("timings"); json.raw("{"); json.key("gcode_ms"); json.number(report.timings.gcode_ms); json.raw(","); json.key("import_ms"); json.number(report.timings.import_ms); json.raw(","); json.key("layout_ms"); json.number(report.timings.layout_ms); json.raw(","); json.key("path_and_geometry_ms"); json.number(report.timings.path_and_geometry_ms); json.raw(","); json.key("peak_rss_kib"); json.integer(report.timings.peak_rss_kib); json.raw("}"); json.raw(","); json.key("warnings"); strings(json, report.warnings); json.raw("},\"stage\":\"report\"}"); return std::move(json).take();
}
}  // namespace plotter::doc
