#include "plotter/doc/source_page_transform.hpp"

#include <cmath>
#include <stdexcept>

namespace {
void require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
bool close(double left, double right) { return std::abs(left - right) < 1e-9; }
}

int main() {
    using namespace plotter::doc;
    PathDocument source;
    source.page_width = {100}; source.page_height = {200};
    Stroke stroke;
    stroke.id = 4; stroke.points = {{{10}, {10}}, {{90}, {190}}};
    stroke.element_id = "source-vector"; stroke.element_type = "vector"; stroke.source_page_index = 2;
    source.strokes = {stroke};
    SourcePageTransformOptions contain;
    contain.mode = SourcePageTransformMode::contain;
    contain.source_page_width = source.page_width; contain.source_page_height = source.page_height;
    contain.source_content = {{10}, {10}, {80}, {180}};
    contain.target_page_width = {210}; contain.target_page_height = {297};
    contain.target_content = {{10}, {20}, {180}, {250}};
    contain.max_upscale = 1.1;
    const auto contained = transform_source_page_paths(source, contain);
    require(std::holds_alternative<TransformedSourcePage>(contained), "contain transform must succeed");
    const auto& contain_result = std::get<TransformedSourcePage>(contained);
    require(close(contain_result.transform.scale, 1.1), "contain must cap the uniform upscale");
    const auto& contained_stroke = contain_result.paths.strokes.front();
    require(close(contained_stroke.points.front().x.value, 56) && close(contained_stroke.points.front().y.value, 46), "contain must center source content in target content");
    require(contained_stroke.id == 4 && contained_stroke.element_id == "source-vector" && contained_stroke.source_page_index == 2, "contain must preserve stroke provenance");

    SourcePageTransformOptions reflow = contain;
    reflow.mode = SourcePageTransformMode::reflow;
    reflow.target_content = {{20}, {30}, {100}, {200}};
    const auto reflowed = transform_source_page_paths(source, reflow);
    require(std::holds_alternative<TransformedSourcePage>(reflowed), "reflow translation must succeed when source geometry fits");
    const auto& reflow_point = std::get<TransformedSourcePage>(reflowed).paths.strokes.front().points.front();
    require(close(reflow_point.x.value, 20) && close(reflow_point.y.value, 30), "reflow must align source content origin to target content origin");

    SourcePageTransformOptions preserve = contain;
    preserve.mode = SourcePageTransformMode::preserve;
    const auto preserved = transform_source_page_paths(source, preserve);
    require(std::holds_alternative<TransformedSourcePage>(preserved), "preserve transform must succeed on a larger target page");
    const auto& preserve_point = std::get<TransformedSourcePage>(preserved).paths.strokes.front().points.front();
    require(close(preserve_point.x.value, 10) && close(preserve_point.y.value, 10), "preserve must retain source page coordinates");
    contain.target_content = {{10}, {20}, {180}, {250}};
    source.strokes.front().points.front() = {{0}, {0}};
    const auto rejected = transform_source_page_paths(source, contain);
    require(std::holds_alternative<SourcePageTransformError>(rejected) && std::get<SourcePageTransformError>(rejected).code == "source_path_outside_content", "out-of-content geometry must be rejected before placement");
}
