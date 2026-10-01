#include "plotter/doc/path_optimizer.hpp"
#include "plotter/doc/path_simplifier.hpp"

#include <cassert>
#include <cmath>

int main() {
    using namespace plotter::doc;
    PathDocument document;
    document.page_width = {100.0};
    document.page_height = {100.0};
    Stroke far; far.id = 8; far.glyph_index = 1; far.element_id = "text";
    far.points = {{{20.0}, {0.0}}, {{21.0}, {0.0}}};
    Stroke near = far; near.id = 9; near.points = {{{3.0}, {0.0}}, {{2.0}, {0.0}}};
    Stroke anchor = far; anchor.id = 7; anchor.points = {{{0.0}, {0.0}}, {{1.0}, {0.0}}};
    document.strokes = {anchor, far, near};
    PathOptimizerOptions routing_options;
    routing_options.enable_safe_retrace = false;
    const auto routed = optimize_paths(document, routing_options);
    assert(routed.strokes.size() == 3);
    assert(routed.strokes[1].points.front().x.value == 2.0);
    assert(routed.strokes[1].glyph_index == 1 && routed.strokes[1].element_id == "text");

    Stroke curve; curve.closed = false; curve.glyph_index = 7; curve.element_id = "curve";
    for (int index = 0; index <= 100; ++index) curve.points.push_back({{static_cast<double>(index)}, {std::sin(static_cast<double>(index) / 10.0) * 0.01}});
    document.strokes = {curve};
    PathSimplificationReport report;
    const auto simplified = simplify_path_document(document, {{0.001}, {0.04}, {0.05}}, &report);
    assert(simplified.strokes.front().points.size() < curve.points.size());
    assert(simplified.strokes.front().points.front().x == curve.points.front().x);
    assert(simplified.strokes.front().points.front().y == curve.points.front().y);
    assert(simplified.strokes.front().points.back().x == curve.points.back().x);
    assert(simplified.strokes.front().points.back().y == curve.points.back().y);
    assert(report.max_observed_deviation.value <= 0.05);
}
