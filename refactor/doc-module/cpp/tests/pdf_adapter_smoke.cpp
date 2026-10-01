#include "plotter/doc/pdf_adapter.hpp"

#include <cassert>
#include <cmath>
#include <filesystem>
#include <variant>
#include <string>
#include <vector>

namespace {
using namespace plotter::doc;

const Document& load(const std::filesystem::path& fixture, Document& storage) {
    const auto result = read_pdf_document(fixture);
    assert(std::holds_alternative<Document>(result));
    storage = std::get<Document>(result);
    return storage;
}

template <class T>
bool has_element(const Document& document) {
    for (const SourcePage& page : document.pages) for (const SourceElement& element : page.elements) if (std::holds_alternative<T>(element)) return true;
    return false;
}
}  // namespace

int main() {
    Document math_document;
    load("tests/fixtures/update_18/mixed_math_diagram.pdf", math_document);
    const Document& math = math_document;
    assert(math.metadata.source_format == "pdf" && math.pages.size() == 1);
    const SourcePage& page = math.pages.front();
    assert(page.width && page.height && std::abs(page.width->value - 209.903) < 0.01 && std::abs(page.height->value - 297.039) < 0.01);
    assert(has_element<TextElement>(math) && has_element<MathElement>(math) && has_element<VectorElement>(math));
    assert(math.warnings.empty());

    Document image_document;
    load("tests/fixtures/update_7/images/image_preserve_position.pdf", image_document);
    const Document& image = image_document;
    assert(has_element<RasterImageElement>(image));
    for (const SourceElement& element : image.pages.front().elements) if (const auto* raster = std::get_if<RasterImageElement>(&element)) { assert(raster->bounds && raster->width.value > 0 && raster->height.value > 0 && std::filesystem::is_regular_file(raster->image_path)); }

    Document table_document;
    load("tests/fixtures/update_7/lines_tables/simple_table.pdf", table_document);
    const Document& table = table_document;
    assert(has_element<TableElement>(table));
    for (const SourceElement& element : table.pages.front().elements) if (const auto* grid = std::get_if<TableElement>(&element)) { assert(grid->source_kind == "pdf-vector-grid" && grid->rows >= 2 && grid->columns >= 2 && !grid->cells.empty()); }

    Document parity_document;
    load("tests/fixtures/layout/mixed_layout_demo.pdf", parity_document);
    std::size_t text_count{}, image_count{}, math_count{};
    for (const SourcePage& parity_page : parity_document.pages) for (const SourceElement& element : parity_page.elements) {
        text_count += std::holds_alternative<TextElement>(element) ? 1U : 0U;
        image_count += std::holds_alternative<RasterImageElement>(element) ? 1U : 0U;
        math_count += std::holds_alternative<MathElement>(element) ? 1U : 0U;
    }
    assert(parity_document.pages.size() == 2);
    assert(text_count == 5 && image_count == 2 && math_count == 4);
    assert(parity_document.warnings.empty());
    const auto ordered_types = [](const SourcePage& source_page) {
        std::string result;
        for (const SourceElement& element : source_page.elements) {
            if (const auto* text = std::get_if<TextElement>(&element)) { assert(text->source_order == result.size()); result += "t"; }
            else if (const auto* image = std::get_if<RasterImageElement>(&element)) { assert(image->source_order == result.size()); result += "i"; }
            else if (const auto* math = std::get_if<MathElement>(&element)) { assert(math->source_order == result.size()); result += "m"; }
        }
        return result;
    };
    assert(ordered_types(parity_document.pages[0]) == "ttimm");
    assert(ordered_types(parity_document.pages[1]) == "tttimm");
}
