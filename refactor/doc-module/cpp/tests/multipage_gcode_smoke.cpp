#include "plotter/doc/multipage_gcode_exporter.hpp"

#include <cassert>

int main() {
    using namespace plotter::doc;
    PathDocument paths;
    paths.page_width = {148.0};
    paths.page_height = {210.0};
    Stroke stroke;
    stroke.points = {{{10.0}, {10.0}}, {{20.0}, {10.0}}};
    paths.strokes.push_back(stroke);
    PlotterJob job;
    job.page_width = paths.page_width;
    job.page_height = paths.page_height;
    job.pages.push_back({0, 1, paths, {}, {}, {}});
    job.pages.push_back({1, 2, paths, {}, {}, {}});
    MachineConfig machine;
    machine.workspace = {{0.0}, {300.0}, {0.0}, {300.0}};
    machine.page_change.enabled = true;
    machine.page_change.pause_seconds = 2.0;
    machine.page_change.park_inset = {5.0};
    const auto gcode = generate_job_gcode(job, machine);
    assert(gcode.find("PAGE 1/2 START") != std::string::npos);
    assert(gcode.find("PAGE 2/2 START") != std::string::npos);
    assert(gcode.find("G4 P2000") != std::string::npos);
    assert(gcode.find("G0 X143.000 Y5.000") != std::string::npos);
}
