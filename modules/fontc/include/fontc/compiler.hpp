#pragma once

#include "fontc/cli.hpp"
#include "fontc/pfc.hpp"

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace fontc {

struct CompilationReport {
    std::size_t requested_codepoints = 0;
    std::size_t compiled_glyphs = 0;
    std::size_t skipped_missing_glyphs = 0;
    std::size_t raw_centerline_points = 0, clean_centerline_points = 0;
    std::size_t removed_spurs = 0, graph_nodes_before = 0, graph_nodes_after = 0;
    double removed_spur_length_mm = 0;
    std::size_t stroke_count = 0, bezier_segment_count = 0, final_path_points = 0;
    PfcMergeStats merge_stats;
};

// Decodes a UTF-8 corpus, sorts the result, and always includes the fallback '?'.
// Invalid UTF-8 is rejected rather than silently producing a different font cache.
[[nodiscard]] std::vector<std::uint32_t> read_codepoints_file(const std::filesystem::path& path);

// Runs the complete offline pipeline and atomically writes the requested PFC.
// The output order is independent of worker scheduling.
[[nodiscard]] CompilationReport compile_font(const CompilerOptions& options);

}  // namespace fontc
