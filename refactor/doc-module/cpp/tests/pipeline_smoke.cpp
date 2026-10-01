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
    plotter::doc::Document direct;
    direct.source_path = "<in-memory>";
    plotter::doc::SourcePage source_page;
    source_page.source_page = 0;
    plotter::doc::TableElement table;
    table.id = "table-1"; table.rows = 1; table.columns = 1;
    table.bounds = plotter::doc::Rect{{30}, {60}, {20}, {10}};
    plotter::doc::TableCell cell;
    plotter::doc::Paragraph table_paragraph;
    plotter::doc::TextRun table_run; table_run.text = "A";
    table_paragraph.runs.push_back(table_run);
    cell.paragraphs.push_back(table_paragraph);
    table.cells.push_back(cell);
    source_page.elements.push_back(table);
    plotter::doc::MathElement math;
    math.id = "math-1"; math.expression = "A";
    math.source_syntax = "pdf-text-layer-heuristic";
    math.bounds = plotter::doc::Rect{{70}, {60}, {10}, {10}};
    source_page.elements.push_back(math);
    direct.pages.push_back(source_page);
    options.page_numbers = false;
    options.output_directory = root / "out-direct";
    const auto direct_result = plotter::doc::run_pipeline(direct, options);
    require(direct_result.ok, "typed Document pipeline failed");
    bool has_table = false, has_table_text = false, has_math = false;
    for (const auto& stroke : direct_result.job.pages.front().paths.strokes) {
        has_table |= stroke.element_type == "table";
        has_table_text |= stroke.element_type == "table-cell-text";
        has_math |= stroke.element_type == "math";
    }
    require(has_table && has_table_text && has_math, "table cell text and math paths were not assembled");
    std::filesystem::remove_all(root);
}
