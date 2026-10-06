#include "plotter/doc/gcode_exporter.hpp"

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
    assert(gcode.find("G0 X10.000 Y10.000 F3000.000") != std::string::npos);
    assert(gcode.find("G1 X20.000 Y10.000 F1000.000") != std::string::npos);
    assert(gcode.find("G1 X20.000 Y10.000\n") == std::string::npos);

    machine.keep_out.push_back({{{15.0}, {10.0}}, {1.0}, {0.0}});
    bool rejected = false;
    try { static_cast<void>(generate_gcode(document, machine)); }
    catch (const std::invalid_argument&) { rejected = true; }
    assert(rejected);
}
