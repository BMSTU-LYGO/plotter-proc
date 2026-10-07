#include "plotter/doc/gcode_exporter.hpp"
#include "plotter/doc/gcode_analyzer.hpp"

#include <cassert>
#include <stdexcept>

int main() {
    using namespace plotter::doc;
    PathDocument document;
    document.page_width = {148.0};
    document.page_height = {210.0};
    Stroke stroke;
    stroke.points = {{{10.0}, {10.0}}, {{20.0}, {10.0}}, {{20.0}, {10.0}}};
    document.strokes.push_back(stroke);
    MachineConfig machine;
    machine.workspace = {{0.0}, {300.0}, {0.0}, {300.0}};
    machine.pen.down_settle_ms = 0;
    const auto gcode = generate_gcode(document, machine);
    assert(gcode.find("G21\nG90\n") != std::string::npos);
    assert(gcode.find("M203 X120.000 Y120.000\nM204 P1500.000 T2000.000\n") != std::string::npos);
    assert(gcode.find("G0 X10.000 Y10.000 F6000.000") != std::string::npos);
    assert(gcode.find("G1 F6000.000\nG1 X20.000 Y10.000\n") != std::string::npos);

    machine.keep_out.push_back({{{15.0}, {10.0}}, {1.0}, {0.0}});
    bool rejected = false;
    try { static_cast<void>(generate_gcode(document, machine)); }
    catch (const std::invalid_argument&) { rejected = true; }
    assert(rejected);

    machine.keep_out.clear();
    machine.feedrate.draw_mm_min = 4321;
    document.strokes.front().points = {{{10.0},{10.0}},{{20.0},{10.0}},
        {{30.0},{10.0}},{{30.0},{20.0}},{{30.0},{30.0}}};
    const auto uniform = generate_gcode(document, machine);
    assert(uniform.find("G1 F4321.000\n") != std::string::npos);
    assert(uniform.find("G1 F4321.000\n") == uniform.rfind("G1 F4321.000\n"));
    assert(uniform.find("G1 X30.000 Y10.000\nG1 X30.000 Y20.000\n") != std::string::npos);
    const auto analysis = analyze_gcode(uniform, machine);
    assert(analysis.draw_segment_count == 4);
    assert(analysis.segments_below_0_05mm == 0);
    assert(analysis.draw_feedrates_mm_min.size() == 1 && analysis.draw_feedrates_mm_min.front() == 4321);
    assert(analysis.estimated_total_time_seconds > analysis.ideal_total_time_seconds);

    machine.motion.junction_mode = "classic_jerk";
    machine.motion.xy_jerk_mm_s = 12;
    machine.motion.max_xy_feedrate_mm_s = 130;
    const auto tuned = generate_gcode(document, machine);
    assert(tuned.find("M203 X130.000 Y130.000") != std::string::npos);
    assert(tuned.find("M205 X12.000 Y12.000") != std::string::npos);
    assert(analyze_gcode(tuned, machine).draw_feedrates_mm_min.front() == 4321);

    machine.motion.junction_mode = "none";
    document.strokes.front().points = {{{10.0},{10.0}},{{110.0},{10.0}}};
    double previous = 1e100;
    for (double speed : {2000.0, 4000.0, 6000.0}) {
        machine.feedrate.draw_mm_min = speed;
        const auto value = analyze_gcode(generate_gcode(document, machine), machine);
        assert(value.estimated_draw_time_seconds < previous);
        previous = value.estimated_draw_time_seconds;
    }
    document.strokes.front().points = {{{10.0},{10.0}},{{10.1},{10.0}}};
    const auto short_segment = analyze_gcode(generate_gcode(document, machine), machine);
    assert(short_segment.segments_reaching_cruise_speed_ratio == 0);
    assert(short_segment.estimated_draw_time_seconds > 0.1 / 100.0);
}
