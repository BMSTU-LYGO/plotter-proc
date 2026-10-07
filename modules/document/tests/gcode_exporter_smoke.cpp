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
    assert(gcode.find("G0 X10.000 Y10.000 F6000.000") != std::string::npos);
    assert(gcode.find("G1 X20.000 Y10.000 F2000.000") != std::string::npos);
    assert(gcode.find("G1 X20.000 Y10.000\n") == std::string::npos);

    machine.keep_out.push_back({{{15.0}, {10.0}}, {1.0}, {0.0}});
    bool rejected = false;
    try { static_cast<void>(generate_gcode(document, machine)); }
    catch (const std::invalid_argument&) { rejected = true; }
    assert(rejected);

    machine.keep_out.clear();
    machine.feedrate.draw_fast_mm_min = 2700;
    machine.feedrate.curve_mm_min = 2000;
    machine.feedrate.tight_mm_min = 1200;
    document.strokes.front().points = {{{10.0},{10.0}},{{20.0},{10.0}},
        {{30.0},{10.0}},{{30.0},{20.0}},{{30.0},{30.0}}};
    const auto zoned = generate_gcode(document, machine);
    assert(zoned.find("F2700.000") != std::string::npos);
    assert(zoned.find("F1200.000") != std::string::npos);
    const auto analysis = analyze_gcode(zoned, machine);
    assert(analysis.feedrate_changes >= 2 && analysis.feedrate_changes < analysis.draw_segment_count);
    assert(analysis.segments_below_0_05mm == 0);
}
