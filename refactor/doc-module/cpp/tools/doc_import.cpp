#include "plotter/doc/docx_adapter.hpp"
#include "plotter/doc/ir.hpp"
#include "plotter/doc/svg_adapter.hpp"
#include "plotter/doc/text_adapter.hpp"

#include <algorithm>
#include <cctype>
#include <filesystem>
#include <iostream>
#include <string>
#include <variant>

int main(int argc, char** argv) {
    using namespace plotter::doc;
    if (argc != 2) {
        std::cerr << "usage: plotter-doc-import <input>\n";
        return 2;
    }
    const std::filesystem::path input{argv[1]};
    std::string extension = input.extension().string();
    std::transform(extension.begin(), extension.end(), extension.begin(), [](unsigned char c) {
        return static_cast<char>(std::tolower(c));
    });
    try {
        ImportResult result;
        if (extension == ".txt" || extension == ".md" || extension == ".markdown")
            result = read_text_document(input);
        else if (extension == ".docx")
            result = read_docx_document(input);
        else if (extension == ".svg") {
            auto svg = read_svg_document(input);
            if (const auto* error = std::get_if<SvgAdapterError>(&svg)) {
                std::cerr << error->message << '\n';
                return 1;
            }
            result = std::move(std::get<Document>(svg));
        } else {
            std::cerr << "Unsupported source format: " << extension << '\n';
            return 2;
        }
        if (const auto* error = std::get_if<ImportError>(&result)) {
            std::cerr << error->message << '\n';
            return 1;
        }
        std::cout << serialize_stage_ir(std::get<Document>(result)) << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << error.what() << '\n';
        return 1;
    }
}
