#include "plotter/doc/gcode_analyzer.hpp"
#include "plotter/doc/multipage_gcode_exporter.hpp"

#include <cassert>
#include <stdexcept>

int main() {
    using namespace plotter::doc;
    MachineConfig machine;
    machine.workspace = {{0.0}, {300.0}, {0.0}, {300.0}};
    machine.page_change.enabled = true;
    machine.page_change.pause_seconds = 2.0;
    machine.page_change.park_inset = {5.0};

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

    const auto report = analyze_gcode(generate_job_gcode(job, machine), machine);
    assert(report.page_count == 2);
    assert(report.page_change_count == 1);
    assert(report.gcode_command_count > 10);
    assert(report.motion_command_count > 0);
    assert(report.dwell_count == 3);
    assert(report.ideal_total_time_seconds > report.dwell_time_seconds);

    bool rejected = false;
    try { static_cast<void>(analyze_gcode("G21\nG90\nG1 X999 F100\nM84\n", machine)); }
    catch (const std::invalid_argument&) { rejected = true; }
    assert(rejected);
}
