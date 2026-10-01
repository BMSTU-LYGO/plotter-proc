#include "plotter/doc/artifact_writer.hpp"

#include <cassert>
#include <filesystem>
#include <fstream>
#include <utility>

int main() {
    using namespace plotter::doc;
    const auto output = std::filesystem::temp_directory_path() / "plotter-doc-artifact-smoke";
    std::error_code ignored; std::filesystem::remove_all(output, ignored);
    PlotterJob job; job.page_width = {100.0}; job.page_height = {50.0};
    PageJob page; page.page_number = 1; page.warnings = {"tab\tline\n"}; page.paths.page_width = job.page_width; page.paths.page_height = job.page_height;
    Stroke stroke; stroke.id = 1; stroke.points = {{{1.0}, {2.0}}, {{10.0}, {2.0}}}; page.paths.strokes.push_back(std::move(stroke)); job.pages.push_back(page);
    auto report = make_pipeline_report(job, "normal");
    report.cache.hits = 9;
    const auto paths = write_artifacts(job, report, {output, ArtifactLevel::normal});
    assert(std::filesystem::exists(paths.job_json)); assert(std::filesystem::exists(paths.report_json)); assert(std::filesystem::exists(paths.paths_json)); assert(std::filesystem::exists(paths.preview_svg));
    std::ifstream success_report_file(paths.report_json); std::string success_report((std::istreambuf_iterator<char>(success_report_file)), {}); assert(success_report.find("\"hits\":9") != std::string::npos);
    std::ifstream job_file(paths.job_json); std::string job_manifest((std::istreambuf_iterator<char>(job_file)), {}); assert(job_manifest.find("pages/page-001/paths.json") != std::string::npos); assert(job_manifest.find("tab\\tline\\n") != std::string::npos);
    job.warnings = {"job-warning"};
    const auto minimal = write_artifacts(job, report, {output / "minimal", ArtifactLevel::minimal, false});
    assert(minimal.preview_svg.empty());
    std::ifstream minimal_file(minimal.job_json);
    const std::string minimal_job((std::istreambuf_iterator<char>(minimal_file)), {});
    assert(minimal_job.find("\"preview\":null") != std::string::npos);
    assert(minimal_job.find("job-warning") != std::string::npos);
    { std::ofstream stale(output / "stale.gcode"); stale << "old"; }
    write_error_artifacts(output, "expected error");
    assert(!std::filesystem::exists(output / "stale.gcode"));
    std::ifstream report_file(output / "report.json"); std::string report_json((std::istreambuf_iterator<char>(report_file)), {}); assert(report_json.find("\"status\":\"error\"") != std::string::npos);
    std::filesystem::remove_all(output, ignored);
}
