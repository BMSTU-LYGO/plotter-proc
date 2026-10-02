#include "plotter/doc/zip_archive.hpp"

#include <cassert>

int main() {
    using namespace plotter::doc;
    const auto archive = ZipArchive::open("tests/fixtures/layout/paragraph_formatting_demo.docx");
    assert(archive.contains("word/document.xml"));
    const auto xml = archive.read_text("word/document.xml");
    assert(xml.find("<w:document") != std::string::npos);
    assert(!archive.entries().empty());
}
