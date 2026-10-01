#include "plotter/doc/pipeline.hpp"
#include "fontc/pfc.hpp"

#include <filesystem>
#include <fstream>
#include <stdexcept>
#include <string>

namespace {
void require(bool condition, const char* message) { if (!condition) throw std::runtime_error(message); }
}

int main() {
    const auto root = std::filesystem::temp_directory_path() / "plotter-doc-pipeline-smoke-data";
    std::filesystem::create_directories(root);
    const auto input = root / "a.txt";
    const auto pfc = root / "font.pfc";
    { std::ofstream stream(input); stream << "AAA"; }
    fontc::CompiledFont font;
    font.metrics = {1000, 800, -200, 0};
    font.glyphs = {{'?', 500, {}}, {'A', 600, {fontc::CompiledStroke{{{0, 0}, {100, 100}}}}}, {'1', 500, {fontc::CompiledStroke{{{0, 0}, {0, 100}}}}}};
    fontc::write_pfc(pfc, font);
    plotter::doc::PipelineOptions options;
    options.input_path = input;
    options.output_directory = root / "out";
    options.pfc_path = pfc;
    options.page_numbers = true;
    options.config.page = {"A5", {148.0}, {210.0}, {{15.0}, {15.0}, {15.0}, {15.0}}};
    options.config.machine.workspace = {{0.0}, {220.0}, {0.0}, {220.0}};
    const auto result = plotter::doc::run_pipeline(options);
    require(result.ok, "text pipeline failed");
    require(result.job.pages.size() == 1, "text pipeline page count");
    require(result.job.pages.front().paths.strokes.size() == 4, "text centerline strokes missing");
    require(result.job.pages.front().paths.strokes.back().element_type == "page-number", "page-number stroke role missing");
    require(std::filesystem::is_regular_file(result.gcode_path), "G-code missing");
    require(std::filesystem::is_regular_file(result.artifacts.report_json), "report missing");
    std::filesystem::remove_all(root);
}
