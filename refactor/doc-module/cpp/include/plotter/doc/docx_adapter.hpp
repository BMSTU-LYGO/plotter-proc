#pragma once

#include "plotter/doc/import.hpp"

#include <filesystem>

namespace plotter::doc {

// Reads a DOCX OOXML package directly. Text, tables, embedded images, OMML
// equations and the useful subset of VML line drawings are normalized into the
// document model. Embedded media are copied beside the source package into a
// deterministic asset directory so later pipeline stages never need a ZIP
// reader.
[[nodiscard]] ImportResult read_docx_document(const std::filesystem::path& source_path,
                                              const std::filesystem::path& assets_dir = {});

}  // namespace plotter::doc
