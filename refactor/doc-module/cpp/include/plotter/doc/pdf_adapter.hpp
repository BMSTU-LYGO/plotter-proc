#pragma once

#include "plotter/doc/import.hpp"

#include <filesystem>

namespace plotter::doc {

// Reads a local PDF through Poppler command-line readers. Text positions, stroked
// vector paths, embedded rasters, grid tables, and text-layer maths are imported
// when Poppler exposes enough information to do so safely.
// The adapter never invokes a shell: source_path is passed as one exec argument.
// Coordinates from the PDF text layer (points) are normalized to millimetres.
[[nodiscard]] ImportResult read_pdf_document(const std::filesystem::path& source_path);

}  // namespace plotter::doc
