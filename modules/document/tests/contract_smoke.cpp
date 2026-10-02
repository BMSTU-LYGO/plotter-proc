#include "plotter/doc/gcode.hpp"
#include "plotter/doc/pipeline.hpp"
#include "plotter/doc/units.hpp"

#include <cassert>
#include <variant>

int main() {
    using namespace plotter::doc;
    Document document;
    document.source_path = "fixture.docx";
    SourcePage page;
    page.source_page = 0;
    page.width = Millimetres{210.0};
    page.height = Millimetres{297.0};
    TextElement title;
    title.id = "title";
    title.source_order = 0;
    title.source_page = 0;
    Paragraph paragraph;
    TextRun run;
    run.text = "Hello";
    paragraph.runs.push_back(std::move(run));
    title.paragraphs.push_back(std::move(paragraph));
    page.elements.emplace_back(std::move(title));
    document.pages.push_back(std::move(page));
    static_assert(std::variant_size_v<SourceElement> == 7);
    static_assert(to_emu(Millimetres{25.4}).value == 914400.0);
    static_assert(to_millimetres(Points{72.0}).value == 25.4);
    assert(std::get<TextElement>(document.pages.front().elements.front()).id == "title");
    Stroke stroke;
    stroke.glyph_index = 3;
    stroke.font_role = "primary";
    stroke.source_page_index = 0;
    stroke.layout_group = "body";
    stroke.preserve_order = true;
    LayoutPage rich_page;
    PositionedGlyph glyph;
    glyph.character = "A";
    glyph.glyph_name = "A";
    glyph.codepoint = 65;
    glyph.x = {10.0};
    glyph.baseline_y = {20.0};
    glyph.advance = {3.0};
    rich_page.glyphs.push_back(std::move(glyph));
    rich_page.graphic_strokes.push_back(stroke);
    rich_page.placements.push_back(SourcePlacement{0, std::nullopt, Rect{{}, {}, {1.0}, {1.0}}, "flow", "inline"});
    rich_page.line_boxes.push_back(Rect{{}, {}, {10.0}, {2.0}});
    rich_page.table_fragments.push_back(TableFragment{"table-1", 0, 1, Rect{{}, {}, {10.0}, {5.0}}});
    assert(rich_page.graphic_strokes.front().preserve_order);
    LayoutDocument layout;
    layout.pages.push_back(std::move(rich_page));
    assert(layout.pages.front().glyphs.front().character == "A");
    PlotterJob job;
    job.page_width = {210.0};
    job.page_height = {297.0};
    assert(job.page_width.value == 210.0);
}
