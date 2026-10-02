#include "plotter/doc/text_adapter.hpp"

#include <cassert>
#include <filesystem>
#include <fstream>
#include <variant>

int main() {
    using namespace plotter::doc;
    const auto root = std::filesystem::temp_directory_path() / "plotter-doc-text-adapter-smoke";
    std::filesystem::create_directories(root);
    const auto txt_path = root / "input.txt";
    const auto markdown_path = root / "input.md";
    { std::ofstream file(txt_path, std::ios::binary); file << "\xEF\xBB\xBFone\n\ntwo\n"; }
    { std::ofstream file(markdown_path, std::ios::binary); file << "# Title\n\n- first **item**\n```cpp\n<keep `this`>\n```\n[site](https://example.invalid) &amp; <b>text</b>\n"; }

    const auto txt = read_txt_document(txt_path);
    assert(std::holds_alternative<Document>(txt));
    const auto& txt_element = std::get<TextElement>(std::get<Document>(txt).pages[0].elements[0]);
    assert(txt_element.paragraphs.size() == 3 && txt_element.paragraphs[1].runs[0].text.empty());
    assert(*txt_element.paragraphs[0].semantic_role == "body");

    const auto markdown = read_markdown_document(markdown_path);
    assert(std::holds_alternative<Document>(markdown));
    const auto& element = std::get<TextElement>(std::get<Document>(markdown).pages[0].elements[0]);
    assert(element.paragraphs.size() == 5);
    assert(element.paragraphs[0].runs[0].text == "Title" && *element.paragraphs[0].semantic_role == "heading");
    assert(element.paragraphs[2].runs[0].text == "first item" && *element.paragraphs[2].semantic_role == "list");
    assert(element.paragraphs[3].runs[0].text == "<keep `this`>" && *element.paragraphs[3].semantic_role == "code");
    assert(element.paragraphs[4].runs[0].text == "site & text");
    const auto golden_txt_path = root / "golden.txt";
    const auto golden_markdown_path = root / "golden.md";
    { std::ofstream file(golden_txt_path, std::ios::binary); file << "\xEF\xBB\xBFМама мыла раму. Мир, шрифт, линия."; }
    { std::ofstream file(golden_markdown_path, std::ios::binary); file << "Мама мыла раму."; }
    const auto golden_txt = read_txt_document(golden_txt_path);
    const auto golden_markdown = read_markdown_document(golden_markdown_path);
    assert(std::holds_alternative<Document>(golden_txt));
    assert(std::holds_alternative<Document>(golden_markdown));
    const auto& golden_txt_element = std::get<TextElement>(std::get<Document>(golden_txt).pages[0].elements[0]);
    const auto& golden_markdown_element = std::get<TextElement>(std::get<Document>(golden_markdown).pages[0].elements[0]);
    assert(golden_txt_element.paragraphs[0].runs[0].text == "Мама мыла раму. Мир, шрифт, линия.");
    assert(*golden_txt_element.paragraphs[0].semantic_role == "body");
    assert(golden_markdown_element.paragraphs[0].runs[0].text == "Мама мыла раму.");
    assert(*golden_markdown_element.paragraphs[0].semantic_role == "body");
    std::filesystem::remove_all(root);
}
