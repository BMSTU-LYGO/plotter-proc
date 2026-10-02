#pragma once

#include "fontc/cli.hpp"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace fontc {

struct CompilationReport {
    std::size_t requested_codepoints = 0;
    std::size_t compiled_glyphs = 0;
    std::size_t skipped_missing_glyphs = 0;
};

// Decodes a UTF-8 corpus, sorts the result, and always includes the fallback '?'.
// Invalid UTF-8 is rejected rather than silently producing a different font cache.
[[nodiscard]] std::vector<std::uint32_t> read_codepoints_file(const std::filesystem::path& path);

// Runs the complete offline pipeline and atomically writes the requested PFC.
// The output order is independent of worker scheduling.
[[nodiscard]] CompilationReport compile_font(const CompilerOptions& options);

}  // namespace fontc
