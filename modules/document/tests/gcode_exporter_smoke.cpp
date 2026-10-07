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
}
