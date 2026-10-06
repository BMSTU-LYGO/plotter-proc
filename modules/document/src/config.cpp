#include "plotter/doc/config.hpp"

#include <cmath>
#include <iterator>

namespace plotter::doc {
namespace {
bool finite(double v) noexcept { return std::isfinite(v); }
void add(PreflightReport& r, PreflightSeverity s, std::string code, std::string message) { r.issues.push_back({s, std::move(code), std::move(message)}); }
void positive(PreflightReport& r, double v, std::string code) { if (!finite(v) || v <= 0.0) add(r, PreflightSeverity::error, std::move(code), "must be finite and greater than zero"); }
bool inside(const WorkspaceConfig& w, Point p) { return p.x.value >= w.min_x.value && p.x.value <= w.max_x.value && p.y.value >= w.min_y.value && p.y.value <= w.max_y.value; }
}

bool PreflightReport::ok() const noexcept { for (const auto& issue : issues) if (issue.severity == PreflightSeverity::error) return false; return true; }

PreflightReport validate_config(const PipelineConfig& c) {
    PreflightReport r; const auto& p = c.page; const auto& m = c.machine;
    positive(r, p.width.value, "page.width"); positive(r, p.height.value, "page.height");
    if (!finite(p.line_gap.value) || p.line_gap.value < 0.0) add(r, PreflightSeverity::error, "page.line_gap", "must be finite and non-negative");
    for (double x : {p.margins.left.value, p.margins.right.value, p.margins.top.value, p.margins.bottom.value}) if (!finite(x) || x < 0.0) add(r, PreflightSeverity::error, "page.margin", "must be finite and non-negative");
    if (p.margins.left.value + p.margins.right.value >= p.width.value || p.margins.top.value + p.margins.bottom.value >= p.height.value) add(r, PreflightSeverity::error, "page.content_area", "margins leave no positive content area");
    const auto& w = m.workspace;
    if (!finite(w.min_x.value) || !finite(w.max_x.value) || !finite(w.min_y.value) || !finite(w.max_y.value) || w.min_x.value >= w.max_x.value || w.min_y.value >= w.max_y.value) add(r, PreflightSeverity::error, "workspace.bounds", "bounds must be finite and ordered");
    if (!finite(m.page_origin.x.value) || !finite(m.page_origin.y.value)) add(r, PreflightSeverity::error, "page_origin", "must be finite");
    else if (!inside(w, m.page_origin)) add(r, PreflightSeverity::error, "page_origin.workspace", "origin is outside workspace");
    if (m.page_origin.x.value + p.width.value > w.max_x.value || m.page_origin.y.value + p.height.value > w.max_y.value) add(r, PreflightSeverity::error, "page.workspace", "configured page extends outside workspace");
    positive(r, m.feedrate.draw_mm_min, "feedrate.draw"); positive(r, m.feedrate.draw_fast_mm_min, "feedrate.draw_fast"); positive(r, m.feedrate.travel_mm_min, "feedrate.travel"); positive(r, m.feedrate.z_mm_min, "feedrate.z");
    if (m.feedrate.draw_fast_mm_min < m.feedrate.draw_mm_min)
        add(r, PreflightSeverity::error, "feedrate.draw_fast", "must be at least draw feedrate");
    if (!finite(m.pen.up_z.value) || !finite(m.pen.down_z.value) || m.pen.up_z.value <= m.pen.down_z.value) add(r, PreflightSeverity::error, "pen.z", "up height must exceed down height");
    if (m.gcode.decimals > 6U) add(r, PreflightSeverity::error, "gcode.decimals", "must be between 0 and 6");
    for (const auto& k : m.keep_out) if (!finite(k.center.x.value) || !finite(k.center.y.value) || !finite(k.radius.value) || !finite(k.clearance.value) || k.radius.value <= 0.0 || k.clearance.value < 0.0) add(r, PreflightSeverity::error, "keep_out", "needs finite center and positive radius");
    return r;
}

PreflightReport preflight(const PathDocument& paths, const PipelineConfig& c) {
    auto r = validate_config(c);
    PathValidationOptions options;
    options.keep_outs = c.machine.keep_out;
    for (const auto& issue : validate_path_document(paths, options)) {
        add(r, PreflightSeverity::error, "path." + issue.code, issue.message);
    }
    if (std::abs(paths.page_width.value-c.page.width.value)>1e-9 || std::abs(paths.page_height.value-c.page.height.value)>1e-9) add(r, PreflightSeverity::warning, "paths.page_mismatch", "dimensions differ from configured page");
    for (const auto& stroke : paths.strokes) for (const auto& local : stroke.points) {
        if (!finite(local.x.value) || !finite(local.y.value)) continue;
        const double page_x = c.machine.invert_x ? paths.page_width.value - local.x.value : local.x.value;
        const double page_y = c.machine.invert_y ? paths.page_height.value - local.y.value : local.y.value;
        const Point machine{{c.machine.page_origin.x.value + page_x}, {c.machine.page_origin.y.value + page_y}};
        if (!inside(c.machine.workspace, machine)) add(r, PreflightSeverity::error, "point.workspace", "transformed point lies outside workspace");
    }
    return r;
}
PreflightReport preflight(const PlotterJob& job, const PipelineConfig& c) { auto r=validate_config(c); if(job.pages.empty()) add(r,PreflightSeverity::warning,"job.empty","job has no pages"); for(const auto& page:job.pages) { auto p=preflight(page.paths,c); r.issues.insert(r.issues.end(),std::make_move_iterator(p.issues.begin()),std::make_move_iterator(p.issues.end())); } return r; }
}  // namespace plotter::doc
