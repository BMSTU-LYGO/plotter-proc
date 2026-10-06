#include "plotter/doc/config_reader.hpp"

#include <charconv>
#include <cmath>
#include <fstream>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>

namespace plotter::doc {
namespace {
using Values = std::map<std::string, std::string>;
struct YamlFile { Values scalars; std::map<std::string, std::vector<Values>> inline_lists; };
std::string trim(std::string text) {
    const auto left = text.find_first_not_of(" \t\r");
    if (left == std::string::npos) return {};
    const auto right = text.find_last_not_of(" \t\r");
    return text.substr(left, right - left + 1);
}
Values inline_map(const std::string& raw) {
    if (raw.size() < 2 || raw.front() != '{' || raw.back() != '}') throw std::invalid_argument("expected inline YAML mapping");
    Values result;
    const std::string body = raw.substr(1, raw.size() - 2);
    std::size_t cursor = 0;
    while (cursor < body.size()) {
        const auto separator = body.find(',', cursor);
        const auto field = trim(body.substr(cursor, separator == std::string::npos ? separator : separator - cursor));
        const auto colon = field.find(':');
        if (colon == std::string::npos) throw std::invalid_argument("invalid inline YAML mapping");
        result[trim(field.substr(0, colon))] = trim(field.substr(colon + 1));
        if (separator == std::string::npos) break;
        cursor = separator + 1;
    }
    return result;
}
YamlFile read_yaml(const std::filesystem::path& path) {
    std::ifstream input(path);
    if (!input) throw std::runtime_error("cannot read config: " + path.string());
    YamlFile result;
    std::vector<std::pair<std::size_t, std::string>> sections;
    std::string line;
    std::size_t number = 0;
    while (std::getline(input, line)) {
        ++number;
        const auto hash = line.find('#');
        if (hash != std::string::npos) line.erase(hash);
        if (trim(line).empty()) continue;
        const auto indent = line.find_first_not_of(' ');
        if (indent == std::string::npos || indent % 2 != 0) throw std::invalid_argument("invalid YAML indentation at line " + std::to_string(number));
        while (!sections.empty() && sections.back().first >= indent) sections.pop_back();
        std::string key;
        for (const auto& section : sections) { key += section.second; key += '.'; }
        const auto text = trim(line.substr(indent));
        if (text.starts_with("- ")) {
            result.inline_lists[key.substr(0, key.size() - (key.empty() ? 0 : 1))].push_back(inline_map(trim(text.substr(2))));
            continue;
        }
        const auto colon = text.find(':');
        if (colon == std::string::npos) throw std::invalid_argument("invalid YAML scalar at line " + std::to_string(number));
        const auto name = trim(text.substr(0, colon));
        const auto value = trim(text.substr(colon + 1));
        if (name.empty()) throw std::invalid_argument("empty YAML key at line " + std::to_string(number));
        if (value.empty()) sections.emplace_back(indent, name);
        else result.scalars[key + name] = value;
    }
    return result;
}
double number(const std::string& value, std::string_view key) {
    double parsed{};
    const auto* begin = value.data();
    const auto [end, error] = std::from_chars(begin, begin + value.size(), parsed);
    if (error != std::errc{} || end != begin + value.size() || !std::isfinite(parsed)) throw std::invalid_argument("invalid number for config key " + std::string(key));
    return parsed;
}
void assign(const Values& values, const std::string& key, double& destination) {
    if (auto found = values.find(key); found != values.end()) destination = number(found->second, key);
}
void assign(const Values& values, const std::string& key, Millimetres& destination) { assign(values, key, destination.value); }
void assign_bool(const Values& values, const std::string& key, bool& destination) {
    if (auto found = values.find(key); found != values.end()) {
        if (found->second == "true") destination = true;
        else if (found->second == "false") destination = false;
        else throw std::invalid_argument("invalid bool for config key " + key);
    }
}
void assign_uint(const Values& values, const std::string& key, std::uint32_t& destination) {
    if (auto found = values.find(key); found != values.end()) {
        std::uint32_t parsed{};
        const auto* begin = found->second.data();
        const auto [end, error] = std::from_chars(begin, begin + found->second.size(), parsed);
        if (error != std::errc{} || end != begin + found->second.size()) throw std::invalid_argument("invalid unsigned integer for config key " + key);
        destination = parsed;
    }
}
}  // namespace

PipelineConfig load_pipeline_config(const std::filesystem::path& layout_yaml,
                                    const std::filesystem::path& machine_yaml,
                                    std::string_view page_name) {
    if (page_name != "A4" && page_name != "A5") throw std::invalid_argument("unsupported page profile");
    const YamlFile layout = read_yaml(layout_yaml);
    const YamlFile machine = read_yaml(machine_yaml);
    PipelineConfig config;
    config.page.name = std::string(page_name);
    const std::string page = "pages." + config.page.name + ".";
    assign(layout.scalars, page + "width_mm", config.page.width);
    assign(layout.scalars, page + "height_mm", config.page.height);
    assign(layout.scalars, "margins_mm.left", config.page.margins.left);
    assign(layout.scalars, "margins_mm.right", config.page.margins.right);
    assign(layout.scalars, "margins_mm.top", config.page.margins.top);
    assign(layout.scalars, "margins_mm.bottom", config.page.margins.bottom);
    assign(layout.scalars, "line_gap_mm", config.page.line_gap);
    double clearance = 0.0;
    assign(layout.scalars, page + "hole_clearance_mm", clearance);
    if (const auto holes = layout.inline_lists.find(page + "holes"); holes != layout.inline_lists.end()) {
        for (const Values& hole : holes->second) {
            CircularKeepOut region;
            auto required = [&](std::string_view key) {
                const auto found = hole.find(std::string(key));
                if (found == hole.end()) throw std::invalid_argument("hole missing " + std::string(key));
                return number(found->second, key);
            };
            region.center = {{required("x_mm")}, {required("y_mm")}};
            region.radius = {required("radius_mm")};
            region.clearance = {clearance};
            config.machine.keep_out.push_back(region);
        }
    }
    auto& m = config.machine;
    assign(machine.scalars, "workspace_mm.min_x", m.workspace.min_x);
    assign(machine.scalars, "workspace_mm.max_x", m.workspace.max_x);
    assign(machine.scalars, "workspace_mm.min_y", m.workspace.min_y);
    assign(machine.scalars, "workspace_mm.max_y", m.workspace.max_y);
    assign(machine.scalars, "page_origin_mm.x", m.page_origin.x);
    assign(machine.scalars, "page_origin_mm.y", m.page_origin.y);
    const std::string profile = "page_position_profiles." + config.page.name + ".";
    assign(machine.scalars, profile + "origin_x_mm", m.page_origin.x);
    assign(machine.scalars, profile + "origin_y_mm", m.page_origin.y);
    assign_bool(machine.scalars, "axes.invert_x", m.invert_x);
    assign_bool(machine.scalars, "axes.invert_y", m.invert_y);
    assign(machine.scalars, "pen.up_z_mm", m.pen.up_z);
    assign(machine.scalars, "pen.down_z_mm", m.pen.down_z);
    assign_uint(machine.scalars, "pen.settle_ms", m.pen.down_settle_ms);
    assign(machine.scalars, "feedrate_mm_min.draw", m.feedrate.draw_mm_min);
    m.feedrate.draw_fast_mm_min = m.feedrate.draw_mm_min;
    assign(machine.scalars, "feedrate_mm_min.draw_fast", m.feedrate.draw_fast_mm_min);
    assign(machine.scalars, "feedrate_mm_min.travel", m.feedrate.travel_mm_min);
    assign(machine.scalars, "feedrate_mm_min.z", m.feedrate.z_mm_min);
    assign_bool(machine.scalars, "gcode.home", m.gcode.home);
    assign_bool(machine.scalars, "gcode.absolute_positioning", m.gcode.absolute_positioning);
    assign_bool(machine.scalars, "gcode.units_mm", m.gcode.units_mm);
    assign_uint(machine.scalars, "gcode.decimals", m.gcode.decimals);
    assign_bool(machine.scalars, "page_change.enabled", m.page_change.enabled);
    assign(machine.scalars, "page_change.pause_seconds", m.page_change.pause_seconds);
    assign_bool(machine.scalars, "page_change.keep_steppers_enabled", m.page_change.keep_steppers_enabled);
    assign(machine.scalars, "page_change.park.inset_mm", m.page_change.park_inset);
    for (const auto& [key, target] : {std::pair{"page_change.wait_command", &m.page_change.wait_command},
                                      std::pair{"page_change.park.mode", &m.page_change.park_mode},
                                      std::pair{"page_change.park.corner", &m.page_change.park_corner}}) {
        if (auto found = machine.scalars.find(key); found != machine.scalars.end()) *target = found->second;
    }
    const auto report = validate_config(config);
    if (!report.ok()) throw std::invalid_argument("invalid loaded config: " + report.issues.front().code);
    return config;
}
}  // namespace plotter::doc
