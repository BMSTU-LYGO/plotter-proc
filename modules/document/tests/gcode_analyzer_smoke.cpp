#include "plotter/doc/gcode_analyzer.hpp"
#include "plotter/doc/multipage_gcode_exporter.hpp"
#include "plotter/doc/report.hpp"

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
    assert(report.pen_down_count == 2);
    assert(report.pen_lift_count == 2);
    assert(report.draw_segment_count == 2);
    assert(report.travel_segment_count >= 2);
    assert(report.pen_up_travel_mm > 0);

    // Initial/repeated UP and repeated F commands are not transitions.
    const std::string prefix = "G21\nG90\nG0 Z" + std::to_string(machine.pen.up_z.value) + " F1200\n";
    const auto transitions = analyze_gcode(prefix +
        "G0 Z" + std::to_string(machine.pen.up_z.value) + " F1200\nG0 X3 Y4 F6000\n" +
        "G1 Z" + std::to_string(machine.pen.down_z.value) + " F1200\nG1 F6000\n" +
        "G1 X6 Y8\nG1 X9 Y12 F6000\n" +
        "G0 Z" + std::to_string(machine.pen.up_z.value) + " F1200\nM84\n", machine);
    assert(transitions.pen_down_count == 1 && transitions.pen_lift_count == 1);
    assert(transitions.feedrate_change_count == 4);
    assert(transitions.feedrate_changes == 0);
    assert(transitions.draw_segment_count == 2 && transitions.travel_segment_count == 1);
    assert(transitions.draw_length_mm == 10 && transitions.pen_up_travel_mm == 5);

    PlotterJob words;
    PathDocument word_paths = paths;
    word_paths.strokes.clear();
    for (int word = 0; word < 3; ++word) {
        for (int group = 0; group <= word; ++group) {
            Stroke part = stroke;
            part.word_index = word;
            word_paths.strokes.push_back(part);
        }
    }
    // Untagged graphics contribute to document lifts, but not the word average.
    word_paths.strokes.push_back(stroke);
    words.pages.push_back({0, 1, word_paths, {}, {}, {}});
    words.pages.push_back({1, 2, word_paths, {}, {}, {}});
    const auto word_report = make_pipeline_report(words);
    assert(word_report.motion.word_count == 6);
    assert(word_report.motion.pen_down_count == 14);
    assert(word_report.motion.pen_lifts_per_word_avg == 2);
    assert(word_report.motion.words_with_1_pen_down == 2);
    assert(word_report.motion.words_with_2_pen_down == 2);
    assert(word_report.motion.words_with_3plus_pen_down == 2);

    bool rejected = false;
    try { static_cast<void>(analyze_gcode("G21\nG90\nG1 X999 F100\nM84\n", machine)); }
    catch (const std::invalid_argument&) { rejected = true; }
    assert(rejected);
}
