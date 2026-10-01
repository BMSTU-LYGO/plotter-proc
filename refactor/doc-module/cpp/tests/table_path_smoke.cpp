#include "plotter/doc/table_path_builder.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <utility>

namespace {

void require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }

bool has_segment(const plotter::doc::PathDocument& paths, double x1, double y1, double x2, double y2) {
    return std::any_of(paths.strokes.begin(), paths.strokes.end(), [&](const plotter::doc::Stroke& stroke) {
        if (stroke.points.size() != 2) return false;
        const auto close = [](double left, double right) { return std::abs(left - right) < 1e-9; };
        return (close(stroke.points[0].x.value, x1) && close(stroke.points[0].y.value, y1) &&
                close(stroke.points[1].x.value, x2) && close(stroke.points[1].y.value, y2)) ||
               (close(stroke.points[0].x.value, x2) && close(stroke.points[0].y.value, y2) &&
                close(stroke.points[1].x.value, x1) && close(stroke.points[1].y.value, y1));
    });
}

}  // namespace

int main() {
    using namespace plotter::doc;
    TableElement table;
    table.id = "source-table";
    table.source_order = 11;
    table.source_page = 3;
    table.rows = 2;
    table.columns = 2;
    table.bounds = Rect{{10}, {20}, {60}, {30}};
    table.column_widths = {{20}, {40}};
    table.row_heights = {Millimetres{10}, Millimetres{20}};

    TableCell merged;
    merged.row = 0; merged.column = 0; merged.column_span = 2;
    TableCell bottom_left;
    bottom_left.row = 1; bottom_left.column = 0;
    TableCell bottom_right;
    bottom_right.row = 1; bottom_right.column = 1;
    bottom_right.borders.left = false;
    table.cells = {merged, bottom_left, bottom_right};

    const auto paths = TablePathBuilder{}.build(table, {210}, {297});
    require(paths.strokes.size() == 6, "shared cell borders must be emitted once");
    require(has_segment(paths, 10, 20, 70, 20), "merged cell must use its complete top span");
    require(has_segment(paths, 10, 30, 70, 30), "merged cell must use its complete bottom span");
    require(has_segment(paths, 30, 30, 30, 50), "column widths and row heights must locate cell borders");
    require(!has_segment(paths, 30, 20, 30, 30), "merged cell must not draw an interior border");
    for (const Stroke& stroke : paths.strokes) {
        require(stroke.element_id == "source-table" && stroke.element_type == "table", "table element provenance must be retained");
        require(stroke.source_page_index == 3 && stroke.semantic_role == "table-border", "page and border provenance must be retained");
    }

    Paragraph text;
    text.runs.push_back(TextRun{});
    text.runs.back().text = "A";
    table.cells.front().paragraphs = {std::move(text)};
    bool text_error{};
    try { static_cast<void>(TablePathBuilder{}.build(table, {210}, {297})); }
    catch (const std::runtime_error&) { text_error = true; }
    require(text_error, "nonempty cell text must report unsupported path building");

    TableElement unpositioned;
    unpositioned.id = "unpositioned";
    unpositioned.rows = 1; unpositioned.columns = 1;
    require(!TablePathBuilder{}.build(unpositioned, {210}, {297}).warnings.empty(), "a table without bounds must report why it cannot render");
}
