#include "plotter/doc/math_path_builder.hpp"

#include "fontc/pfc.hpp"

#include <filesystem>
#include <stdexcept>

namespace { void require(bool value, const char* message) { if (!value) throw std::runtime_error(message); } }

int main() {
    const auto path = std::filesystem::temp_directory_path() / "plotter-math-path-smoke.pfc";
    fontc::CompiledFont font;
    font.metrics = {1000, 800, -200, 0};
    font.glyphs = {
        {'?', 500, {}},
        {'x', 500, {fontc::CompiledStroke{{{0, 0}, {100, 100}}}}},
        {'+', 500, {fontc::CompiledStroke{{{0, 50}, {100, 50}}}}},
        {'1', 500, {fontc::CompiledStroke{{{10, 0}, {10, 100}}}}},
    };
    fontc::write_pfc(path, font);
    plotter::doc::FontRegistry fonts;
    fonts.register_pfc({"math", "math-hash", path});
    plotter::doc::MathElement element;
    element.id = "page-2-math-3"; element.source_page = 1; element.expression = "x+1";
    element.source_syntax = "plain"; element.bounds = {{20}, {30}, {30}, {10}};
    const auto result = plotter::doc::MathPathBuilder(fonts).build(element, {"math", {12}, {210}, {297}});
    require(std::holds_alternative<plotter::doc::PathDocument>(result), "linear math must produce paths");
    const auto& paths = std::get<plotter::doc::PathDocument>(result);
    require(paths.strokes.size() == 3, "each linear glyph contour must be materialized");
    for (const auto& stroke : paths.strokes) {
        require(stroke.element_id == "page-2-math-3" && stroke.element_type == "math" &&
                stroke.source_page_index == 1 && stroke.font_role == "math" && stroke.font_sha256 == "math-hash",
                "math provenance must be preserved");
        for (const auto& point : stroke.points)
            require(point.x.value >= 20 && point.x.value <= 50 && point.y.value >= 30 && point.y.value <= 40,
                    "math paths must remain within source bounds");
    }
    plotter::doc::MathElement visual = element;
    visual.visual_image_path = "formula.png";
    const auto visual_result = plotter::doc::MathPathBuilder(fonts).build(visual, {"math", {12}, {210}, {297}});
    require(std::holds_alternative<plotter::doc::MathPathBuildError>(visual_result) &&
            std::get<plotter::doc::MathPathBuildError>(visual_result).code == "unsupported_visual_math",
            "visual math must fail explicitly until raster vectorization exists");
    plotter::doc::MathElement structured = element;
    structured.source_syntax = "omml"; structured.expression = "x^2";
    const auto structured_result = plotter::doc::MathPathBuilder(fonts).build(structured, {"math", {12}, {210}, {297}});
    require(std::holds_alternative<plotter::doc::MathPathBuildError>(structured_result) &&
            std::get<plotter::doc::MathPathBuildError>(structured_result).code == "unsupported_math_syntax",
            "structural OMML must fail explicitly");
    std::filesystem::remove(path);
}
