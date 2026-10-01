#pragma once

#include "plotter/doc/import.hpp"

#include <filesystem>

namespace plotter::doc {

// Read a local UTF-8 text file (an optional UTF-8 BOM is ignored).  Every
// source line becomes one body paragraph, including empty lines between text.
[[nodiscard]] ImportResult read_txt_document(const std::filesystem::path& source_path);

// Read the deliberately small Markdown projection used by the Python
// pipeline.  It removes supported markup without rendering or fetching it.
[[nodiscard]] ImportResult read_markdown_document(const std::filesystem::path& source_path);

// Dispatch the text formats supported by this adapter (.txt, .md, .markdown).
[[nodiscard]] ImportResult read_text_document(const std::filesystem::path& source_path);

}  // namespace plotter::doc
