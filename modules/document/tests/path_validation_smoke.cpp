#include "plotter/doc/path_validation.hpp"

#include <cassert>

int main() {
    using namespace plotter::doc;
    PathDocument document;
    document.page_width = {148.0};
    document.page_height = {210.0};
    Stroke stroke;
    stroke.points = {{{10.0}, {10.0}}, {{30.0}, {10.0}}};
    document.strokes.push_back(stroke);
    assert(validate_path_document(document).empty());

    PathValidationOptions options;
    options.keep_outs.push_back({{{20.0}, {10.0}}, {2.0}, {1.0}});
    const auto issues = validate_path_document(document, options);
    assert(issues.size() == 1 && issues.front().code == "keep_out");

    document.strokes.front().points.back().x = {150.0};
    const auto bounds = validate_path_document(document);
    assert(bounds.size() == 1 && bounds.front().code == "outside_page");
}
