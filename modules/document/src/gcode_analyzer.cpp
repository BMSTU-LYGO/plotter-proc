#include "plotter/doc/gcode_analyzer.hpp"

#include <algorithm>
#include <cmath>
#include <optional>
#include <sstream>
#include <stdexcept>
#include <string_view>
#include <unordered_map>
#include <utility>
#include <vector>

namespace plotter::doc {
namespace {

enum class PagePhase { normal, park, sync, wait_comment, dwell, next_page };

[[noreturn]] void invalid(std::size_t line, std::string_view message) {
    throw std::invalid_argument("Invalid generated G-code at line " +
                                std::to_string(line) + ": " + std::string(message));
}

std::string trim(std::string text) {
    const auto first = text.find_first_not_of(" \t\r");
    if (first == std::string::npos) return {};
    const auto last = text.find_last_not_of(" \t\r");
    return text.substr(first, last - first + 1);
}

double number(const std::string& text, std::size_t line) {
    std::size_t used = 0;
    double value{};
    try {
        value = std::stod(text, &used);
    } catch (const std::exception&) {
        invalid(line, "parameter is not a number");
    }
    if (used != text.size() || !std::isfinite(value)) invalid(line, "parameter is not finite");
    return value;
}

bool has_xy(const std::unordered_map<char, double>& values) {
    return values.contains('X') || values.contains('Y');
}

bool only(const std::unordered_map<char, double>& values, std::string_view allowed) {
    for (const auto& [key, ignored] : values) {
        static_cast<void>(ignored);
        if (allowed.find(key) == std::string_view::npos) return false;
    }
    return true;
}

double round6(double value) {
    return std::nearbyint(value * 1'000'000.0) / 1'000'000.0;
}

struct PageLabel final { std::size_t number{}, total{}; };

std::optional<PageLabel> page_start(const std::string& comment) {
    constexpr std::string_view prefix{"===== PAGE "};
    constexpr std::string_view suffix{" START ====="};
    if (!comment.starts_with(prefix) || !comment.ends_with(suffix)) return std::nullopt;
    const std::string body = comment.substr(prefix.size(), comment.size() - prefix.size() - suffix.size());
    const auto slash = body.find('/');
    if (slash == std::string::npos) return std::nullopt;
    try {
        std::size_t left{}, right{};
        const auto page = std::stoull(body.substr(0, slash), &left);
        const auto total = std::stoull(body.substr(slash + 1), &right);
        if (left != slash || right != body.size() - slash - 1 || page == 0 || total == 0) return std::nullopt;
        return PageLabel{static_cast<std::size_t>(page), static_cast<std::size_t>(total)};
    } catch (const std::exception&) { return std::nullopt; }
}

std::optional<PageLabel> page_complete(const std::string& comment) {
    constexpr std::string_view prefix{"PAGE "};
    constexpr std::string_view suffix{" COMPLETE"};
    if (!comment.starts_with(prefix) || !comment.ends_with(suffix)) return std::nullopt;
    const std::string body = comment.substr(prefix.size(), comment.size() - prefix.size() - suffix.size());
    const auto slash = body.find('/');
    if (slash == std::string::npos) return std::nullopt;
    try {
        std::size_t left{}, right{};
        const auto page = std::stoull(body.substr(0, slash), &left);
        const auto total = std::stoull(body.substr(slash + 1), &right);
        if (left != slash || right != body.size() - slash - 1 || page == 0 || total == 0) return std::nullopt;
        return PageLabel{static_cast<std::size_t>(page), static_cast<std::size_t>(total)};
    } catch (const std::exception&) { return std::nullopt; }
}

}  // namespace

GcodeAnalysis analyze_gcode(const std::string& gcode, const MachineConfig& machine,
                            std::size_t max_commands) {
    if (max_commands == 0) throw std::invalid_argument("max_commands must be positive");
    GcodeAnalysis result;
    bool saw_g21 = false;
    bool saw_g90 = false;
    bool motion_started = false;
    bool pen_up = false;
    bool pen_down = false;
    bool program_ended = false;
    double x = 0.0, y = 0.0, z = 0.0;
    std::optional<double> feed;
    std::optional<double> previous_draw_feed;
    std::vector<double> draw_segments;
    PagePhase page_phase = PagePhase::normal;
    std::size_t expected_page = 1;
    std::size_t marker_total = 0;
    bool saw_page_marker = false;

    std::istringstream input(gcode);
    std::string raw;
    std::size_t line_number = 0;
    while (std::getline(input, raw)) {
        ++line_number;
        const auto semicolon = raw.find(';');
        const std::string code = trim(raw.substr(0, semicolon));
        const std::string comment = semicolon == std::string::npos ? std::string{} : trim(raw.substr(semicolon + 1));

        if (!comment.empty()) {
            if (const auto start = page_start(comment)) {
                if (page_phase != PagePhase::normal && page_phase != PagePhase::next_page)
                    invalid(line_number, "page start has an incomplete page-change sequence");
                if (start->number != expected_page || (marker_total != 0 && start->total != marker_total) ||
                    start->number > start->total)
                    invalid(line_number, "page markers are not sequential");
                marker_total = start->total;
                saw_page_marker = true;
                page_phase = PagePhase::normal;
                ++expected_page;
            } else if (const auto complete = page_complete(comment)) {
                if (!saw_page_marker || page_phase != PagePhase::normal || complete->total != marker_total ||
                    complete->number + 1 != expected_page || complete->number >= marker_total)
                    invalid(line_number, "page completion marker is invalid");
                page_phase = PagePhase::park;
            } else if (comment.starts_with("CHANGE PAPER - WAIT ")) {
                if (page_phase != PagePhase::wait_comment)
                    invalid(line_number, "paper-change comment is out of sequence");
                page_phase = PagePhase::dwell;
            }
        }
        if (code.empty()) continue;
        if (program_ended) invalid(line_number, "command appears after M84");

        std::istringstream words(code);
        std::string command;
        words >> command;
        if (command != "G0" && command != "G1" && command != "G4" && command != "G21" &&
            command != "G90" && command != "G28" && command != "M400" && command != "M84")
            invalid(line_number, "unsupported command");
        std::unordered_map<char, double> values;
        std::string token;
        while (words >> token) {
            if (token.size() < 2 || values.contains(token.front())) invalid(line_number, "invalid or duplicate parameter");
            values.emplace(token.front(), number(token.substr(1), line_number));
        }
        ++result.gcode_command_count;
        if (result.gcode_command_count > max_commands)
            throw std::length_error("G-code command limit exceeded");

        if (page_phase == PagePhase::park) {
            if (command != "G0" || !has_xy(values)) invalid(line_number, "page change must park the pen");
            page_phase = PagePhase::sync;
        } else if (page_phase == PagePhase::sync) {
            if (command != "M400") invalid(line_number, "page change must synchronize before waiting");
            page_phase = PagePhase::wait_comment;
        } else if (page_phase == PagePhase::dwell) {
            if (command != "G4") invalid(line_number, "page change must dwell after wait comment");
            page_phase = PagePhase::next_page;
        } else if (page_phase == PagePhase::next_page) {
            invalid(line_number, "page start marker is missing after page-change dwell");
        }

        if (command == "G21" || command == "G90") {
            if (!values.empty() || motion_started) invalid(line_number, "modal command must precede motion and have no parameters");
            bool& seen = command == "G21" ? saw_g21 : saw_g90;
            if (seen) invalid(line_number, "duplicate modal command");
            seen = true;
            continue;
        }
        if (command == "G28") {
            if (!machine.gcode.home || !values.empty() || motion_started)
                invalid(line_number, "homing is disabled or out of sequence");
            x = y = z = 0.0;
            pen_up = pen_down = false;
            continue;
        }
        if (machine.gcode.units_mm && !saw_g21) invalid(line_number, "G21 must precede executable motion");
        if (!machine.gcode.units_mm && saw_g21) invalid(line_number, "G21 contradicts machine configuration");
        if (machine.gcode.absolute_positioning && !saw_g90) invalid(line_number, "G90 must precede executable motion");
        if (!machine.gcode.absolute_positioning && saw_g90) invalid(line_number, "G90 contradicts machine configuration");

        if (command == "M400") {
            if (!values.empty()) invalid(line_number, "M400 takes no parameters");
            continue;
        }
        if (command == "M84") {
            if (!values.empty() || !pen_up) invalid(line_number, "M84 requires a raised pen and no parameters");
            program_ended = true;
            continue;
        }
        if (command == "G4") {
            if (!only(values, "P") || !values.contains('P') || values.at('P') < 0.0)
                invalid(line_number, "G4 requires a non-negative P parameter");
            ++result.dwell_count;
            result.dwell_time_seconds += values.at('P') / 1000.0;
            continue;
        }

        if (!only(values, "XYZF") || values.empty()) invalid(line_number, "motion has unsupported parameters");
        if (values.contains('F')) {
            if (values.at('F') <= 0.0) invalid(line_number, "feedrate must be positive");
            if (feed && *feed != values.at('F')) ++result.feedrate_change_count;
            feed = values.at('F');
        }
        const bool moves_xy = has_xy(values);
        const bool moves_z = values.contains('Z');
        if (moves_z && moves_xy) invalid(line_number, "pen transition cannot move XY");
        if (moves_z) {
            const double target_z = values.at('Z');
            if (command == "G0" && target_z == machine.pen.up_z.value) {
                if (pen_down) ++result.pen_lift_count;
                pen_up = true; pen_down = false;
            }
            else if (command == "G1" && target_z == machine.pen.down_z.value) {
                if (!pen_down) ++result.pen_down_count;
                pen_up = false; pen_down = true;
            }
            else invalid(line_number, "unexpected pen Z transition");
        }
        if (moves_xy) {
            if ((command == "G0" && !pen_up) || (command == "G1" && !pen_down))
                invalid(line_number, "XY motion has an unsafe pen state");
        }
        const double next_x = values.contains('X') ? values.at('X') : x;
        const double next_y = values.contains('Y') ? values.at('Y') : y;
        const double next_z = values.contains('Z') ? values.at('Z') : z;
        if (moves_xy && (next_x < machine.workspace.min_x.value || next_x > machine.workspace.max_x.value ||
                         next_y < machine.workspace.min_y.value || next_y > machine.workspace.max_y.value))
            invalid(line_number, "XY target is outside workspace");
        const double dx = next_x - x, dy = next_y - y, dz = next_z - z;
        const double distance = std::sqrt(dx * dx + dy * dy + dz * dz);
        if (command == "G0" && moves_xy && distance > 0) {
            ++result.travel_segment_count;
            result.pen_up_travel_mm += std::hypot(dx, dy);
        }
        if (command == "G1" && moves_xy && distance > 0) {
            const double segment = std::hypot(dx, dy);
            draw_segments.push_back(segment);
            result.draw_length_mm += segment;
            if (segment < 0.05) ++result.segments_below_0_05mm;
            if (segment < 0.10) ++result.segments_below_0_10mm;
            if (feed && previous_draw_feed && *feed != *previous_draw_feed)
                ++result.feedrate_changes;
            previous_draw_feed = feed;
        }
        if (distance > 0.0 && feed) {
            result.ideal_motion_time_seconds += distance / *feed * 60.0;
            ++result.motion_command_count;
            if (moves_z) ++result.z_command_count;
        }
        if (moves_xy) result.xy_motion_distance_mm += std::hypot(dx, dy);
        if (moves_z) result.z_motion_distance_mm += std::abs(dz);
        x = next_x; y = next_y; z = next_z;
        motion_started = true;
    }
    if (machine.gcode.units_mm != saw_g21) throw std::invalid_argument("G21 does not match machine configuration");
    if (machine.gcode.absolute_positioning != saw_g90) throw std::invalid_argument("G90 does not match machine configuration");
    if (!program_ended) throw std::invalid_argument("Generated G-code does not terminate with M84");
    if (page_phase != PagePhase::normal) throw std::invalid_argument("Incomplete page-change sequence");
    if (saw_page_marker) {
        if (expected_page != marker_total + 1) throw std::invalid_argument("Missing page start marker");
        result.page_count = marker_total;
        result.page_change_count = marker_total - 1;
    }
    result.dwell_time_seconds = round6(result.dwell_time_seconds);
    result.ideal_motion_time_seconds = round6(result.ideal_motion_time_seconds);
    result.ideal_total_time_seconds = round6(result.ideal_motion_time_seconds + result.dwell_time_seconds);
    result.xy_motion_distance_mm = round6(result.xy_motion_distance_mm);
    result.z_motion_distance_mm = round6(result.z_motion_distance_mm);
    result.pen_up_travel_mm = round6(result.pen_up_travel_mm);
    result.draw_segment_count = draw_segments.size();
    if (!draw_segments.empty()) {
        std::sort(draw_segments.begin(), draw_segments.end());
        result.min_segment_mm = round6(draw_segments.front());
        result.max_segment_mm = round6(draw_segments.back());
        result.median_segment_mm = round6(draw_segments[draw_segments.size()/2]);
        result.mean_segment_mm = round6(result.draw_length_mm/draw_segments.size());
        result.draw_length_mm = round6(result.draw_length_mm);
    }
    return result;
}

}  // namespace plotter::doc
