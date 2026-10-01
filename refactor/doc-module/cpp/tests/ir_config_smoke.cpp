#include "plotter/doc/config.hpp"
#include "plotter/doc/ir.hpp"

#include <cassert>

using namespace plotter::doc;

int main() {
    Document document{"<input>", {}, {}, {"txt", std::nullopt, {}}, 1};
    const auto json = to_json(document);
    assert(json == to_json(document));
    assert(json.find("\"ir_version\":1") != std::string::npos);
    Document styled = document;
    TextRun run;
    run.text = "optional";
    run.style.bold = true;
    run.style.font_size = {12.0};
    Paragraph paragraph;
    paragraph.runs = {run};
    paragraph.alignment = "center";
    TextElement text{"text-1", 0, 0, {paragraph}, std::nullopt};
    styled.pages = {{0, std::nullopt, std::nullopt, {text}, std::nullopt}};
    const auto styled_json = to_json(styled);
    auto& changed_text = std::get<TextElement>(styled.pages.front().elements.front());
    changed_text.paragraphs.front().runs.front().style.bold = false;
    assert(styled_json != to_json(styled));
    const auto parsed = deserialize_stage_ir(json);
    assert(std::holds_alternative<StageIrEnvelope>(parsed));
    assert(std::get<StageIrEnvelope>(parsed).stage == StageKind::document);

    Stroke stroke;
    stroke.id = 0;
    stroke.points = {{{10.0}, {10.0}}, {{20.0}, {20.0}}};
    PathDocument paths;
    paths.page_width = {148.0};
    paths.page_height = {210.0};
    paths.strokes = {stroke};
    PipelineConfig config;
    config.page = {"A5", {148.0}, {210.0}, {}};
    config.machine.workspace = {{0.0}, {220.0}, {0.0}, {220.0}};
    config.machine.page_origin = {{10.0}, {10.0}};
    assert(validate_config(config).ok());
    assert(preflight(paths, config).ok());
    config.machine.keep_out.push_back({{{15.0}, {15.0}}, {1.0}, {0.0}});
    assert(!preflight(paths, config).ok());
    config.machine.keep_out.clear();
    config.machine.invert_x = true;
    assert(preflight(paths, config).ok());
    paths.strokes.front().points.front().x = {-1.0};
    assert(!preflight(paths, config).ok());
}
