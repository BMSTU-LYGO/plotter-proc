#include "plotter/doc/artifact_writer.hpp"

#include "plotter/doc/ir.hpp"

#include <chrono>
#include <cmath>
#include <fstream>
#include <iomanip>
#include <locale>
#include <sstream>

namespace plotter::doc {
namespace {
void atomic_write(const std::filesystem::path& path, std::string_view content) {
    std::error_code error; std::filesystem::create_directories(path.parent_path(), error);
    if (error) throw ArtifactError("cannot create artifact directory: " + error.message());
    auto temporary = path; temporary += "." + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) + ".tmp";
    try { std::ofstream stream(temporary, std::ios::binary | std::ios::trunc); if (!stream) throw ArtifactError("cannot create artifact: " + temporary.string()); stream.write(content.data(), static_cast<std::streamsize>(content.size())); stream.close(); if (!stream) throw ArtifactError("cannot write artifact: " + path.string()); std::filesystem::rename(temporary, path, error); if (error) throw ArtifactError("cannot publish artifact: " + error.message()); } catch (...) { std::filesystem::remove(temporary, error); throw; }
}
std::string quote(std::string_view value) {
    std::string output{"\""};
    static constexpr char hex[] = "0123456789abcdef";
    for (unsigned char c : value) {
        switch (c) {
        case '"': output += "\\\""; break;
        case '\\': output += "\\\\"; break;
        case '\n': output += "\\n"; break;
        case '\r': output += "\\r"; break;
        case '\t': output += "\\t"; break;
        default:
            if (c < 0x20U) { output += "\\u00"; output += hex[c >> 4U]; output += hex[c & 15U]; }
            else output += static_cast<char>(c);
        }
    }
    return output + '"';
}
std::string number(double value) { if (!std::isfinite(value)) throw ArtifactError("artifact cannot encode non-finite number"); std::ostringstream stream; stream.imbue(std::locale::classic()); stream << std::setprecision(15) << (value == 0.0 ? 0.0 : value); return stream.str(); }
std::string page_directory(const PageJob& page) { std::ostringstream name; name << "pages/page-" << std::setw(3) << std::setfill('0') << page.page_number; return name.str(); }
std::string job_json(const PlotterJob& job, ArtifactLevel level, bool write_preview) { std::string out{"{\"job\":{\"format\":\"plotter-job\",\"metadata\":{\"artifact_level\":" + quote(artifact_level_name(level)) + ",\"page_count\":" + std::to_string(job.pages.size()) + "},\"page\":{\"height_mm\":" + number(job.page_height.value) + ",\"width_mm\":" + number(job.page_width.value) + "},\"page_count\":" + std::to_string(job.pages.size()) + ",\"pages\":["}; for (std::size_t i = 0; i < job.pages.size(); ++i) { if (i) out += ","; const auto& page = job.pages[i]; const auto directory = page_directory(page); out += "{\"directory\":" + quote(directory) + ",\"page_index\":" + std::to_string(page.page_index) + ",\"page_number\":" + std::to_string(page.page_number) + ",\"paths\":" + quote(directory + "/paths.json") + ",\"preview\":" + (write_preview && level != ArtifactLevel::minimal ? quote(directory + "/plotter-preview.svg") : "null") + ",\"report\":" + quote(directory + "/report.json") + ",\"warnings\":["; for (std::size_t w = 0; w < page.warnings.size(); ++w) { if (w) out += ","; out += quote(page.warnings[w]); } out += "]}"; } out += "],\"version\":1,\"warnings\":[";
    for (std::size_t i = 0; i < job.warnings.size(); ++i) { if (i) out += ","; out += quote(job.warnings[i]); }
    return out + "]},\"stage\":\"job\"}"; }
std::string preview_svg(const PathDocument& paths) { std::string out{"<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 " + number(paths.page_width.value) + " " + number(paths.page_height.value) + "\"><g fill=\"none\" stroke=\"black\" stroke-linecap=\"round\" stroke-linejoin=\"round\">"}; for (const auto& stroke : paths.strokes) { if (stroke.points.empty()) continue; out += "<path d=\"M " + number(stroke.points.front().x.value) + " " + number(stroke.points.front().y.value); for (std::size_t i = 1; i < stroke.points.size(); ++i) out += " L " + number(stroke.points[i].x.value) + " " + number(stroke.points[i].y.value); if (stroke.closed) out += " Z"; out += "\"/>"; } return out + "</g></svg>\n"; }
void write_page(const PageJob& page, const std::filesystem::path& directory, ArtifactLevel level, bool preview) { atomic_write(directory / "paths.json", serialize_stage_ir(page.paths)); PipelineReport report; report.artifact_level = std::string(artifact_level_name(level)); report.pages.push_back(make_page_report(page)); report.geometry = report.pages.front().geometry; report.motion = report.pages.front().motion; atomic_write(directory / "report.json", serialize_report_json(report)); if (preview && level != ArtifactLevel::minimal) atomic_write(directory / "plotter-preview.svg", preview_svg(page.paths)); }
}
std::string_view artifact_level_name(ArtifactLevel level) noexcept { switch (level) { case ArtifactLevel::minimal: return "minimal"; case ArtifactLevel::normal: return "normal"; case ArtifactLevel::debug: return "debug"; case ArtifactLevel::audit: return "audit"; } return "normal"; }
ArtifactPaths write_artifacts(const PlotterJob& job, const PipelineReport& report, const ArtifactOptions& options) { if (options.output_directory.empty()) throw ArtifactError("artifact output directory is empty"); ArtifactPaths paths{options.output_directory / "job.json", options.output_directory / "report.json", {}, {}}; if (!job.pages.empty()) { const auto directory = options.output_directory / page_directory(job.pages.front()); paths.paths_json = directory / "paths.json"; if (options.write_preview && options.level != ArtifactLevel::minimal) paths.preview_svg = directory / "plotter-preview.svg"; } try { atomic_write(paths.job_json, job_json(job, options.level, options.write_preview)); atomic_write(paths.report_json, serialize_report_json(report)); for (const auto& page : job.pages) write_page(page, options.output_directory / page_directory(page), options.level, options.write_preview); } catch (const ArtifactError&) { throw; } catch (const std::exception& error) { throw ArtifactError(error.what()); } return paths; }
void write_error_artifacts(const std::filesystem::path& output_directory, std::string message, ArtifactLevel level) {
    if (output_directory.empty()) throw ArtifactError("artifact output directory is empty");
    std::error_code error; if (std::filesystem::exists(output_directory, error)) for (const auto& entry : std::filesystem::recursive_directory_iterator(output_directory, error)) { if (error) break; if (entry.is_regular_file(error) && entry.path().extension() == ".gcode") std::filesystem::remove(entry.path(), error); }
    PipelineReport report; report.status = "error"; report.artifact_level = std::string(artifact_level_name(level)); report.errors.push_back(std::move(message)); atomic_write(output_directory / "report.json", serialize_report_json(report));
}
}  // namespace plotter::doc
