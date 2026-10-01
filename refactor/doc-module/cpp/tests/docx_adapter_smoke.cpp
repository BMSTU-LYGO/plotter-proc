#include "plotter/doc/docx_adapter.hpp"

#include <algorithm>
#include <cassert>
#include <filesystem>
#include <variant>

int main() {
    using namespace plotter::doc;
    const auto result = read_docx_document("tests/fixtures/layout/paragraph_formatting_demo.docx");
    assert(std::holds_alternative<Document>(result));
    const auto& document = std::get<Document>(result);
    assert(document.metadata.source_format == "docx");
    assert(document.pages.size() == 1);
    const auto& page = document.pages.front();
    assert(page.width && page.height && page.width->value > 0.0 && page.height->value > 0.0);
    assert(page.content_bounds && page.content_bounds->has_positive_area());
    assert(!page.elements.empty());
    const auto& text = std::get<TextElement>(page.elements.front());
    assert(!text.paragraphs.empty());
    const auto styled = std::find_if(text.paragraphs.begin(), text.paragraphs.end(), [](const Paragraph& paragraph) { return !paragraph.runs.empty() && (paragraph.alignment || paragraph.left_indent || paragraph.space_after || !paragraph.tab_stops.empty()); });
    assert(styled != text.paragraphs.end());
    const auto run = std::find_if(styled->runs.begin(), styled->runs.end(), [](const TextRun& value) { return !value.text.empty(); });
    assert(run != styled->runs.end());

    const auto merged = read_docx_document("tests/fixtures/update_7/lines_tables/merged_cells.docx");
    assert(std::holds_alternative<Document>(merged));
    const auto& merged_page = std::get<Document>(merged).pages.front();
    const auto table = std::find_if(merged_page.elements.begin(), merged_page.elements.end(), [](const SourceElement& value) { return std::holds_alternative<TableElement>(value); });
    assert(table != merged_page.elements.end());
    const auto& structured_table = std::get<TableElement>(*table);
    assert(structured_table.rows > 0 && structured_table.columns > 0);
    assert(std::any_of(structured_table.cells.begin(), structured_table.cells.end(), [](const TableCell& cell) { return cell.column_span > 1 || cell.row_span > 1; }));

    const auto arrows = read_docx_document("tests/fixtures/update_7/lines_tables/arrows.docx");
    assert(std::holds_alternative<Document>(arrows));
    const auto& arrow_elements = std::get<Document>(arrows).pages.front().elements;
    assert(std::any_of(arrow_elements.begin(), arrow_elements.end(), [](const SourceElement& value) { return std::holds_alternative<ArrowElement>(value); }));

    const auto formulae = read_docx_document("tests/fixtures/update_7/latex/omml_basic.docx");
    assert(std::holds_alternative<Document>(formulae));
    const auto& formula_elements = std::get<Document>(formulae).pages.front().elements;
    assert(std::any_of(formula_elements.begin(), formula_elements.end(), [](const SourceElement& value) {
        return std::holds_alternative<MathElement>(value) && !std::get<MathElement>(value).expression.empty();
    }));

    const auto temporary = std::filesystem::temp_directory_path() / "plotter-docx-image-smoke.docx";
    std::filesystem::copy_file("tests/fixtures/update_7/images/image_left_wrap.docx", temporary, std::filesystem::copy_options::overwrite_existing);
    const auto images = read_docx_document(temporary);
    assert(std::holds_alternative<Document>(images));
    const auto& image_elements = std::get<Document>(images).pages.front().elements;
    const auto image = std::find_if(image_elements.begin(), image_elements.end(), [](const SourceElement& value) { return std::holds_alternative<RasterImageElement>(value); });
    assert(image != image_elements.end());
    const auto& raster = std::get<RasterImageElement>(*image);
    assert(raster.anchor_type == "anchored" && raster.wrap_mode == "square" && raster.bounds);
    assert(std::filesystem::exists(raster.image_path));
    std::filesystem::remove_all(temporary.parent_path() / "plotter-docx-image-smoke.assets");
    std::filesystem::remove(temporary);
}
