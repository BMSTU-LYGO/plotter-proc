#include "fontc/cli.hpp"
#include "fontc/compiler.hpp"

#include <iostream>

int main(int argc, char** argv) {
    const fontc::ParseResult parsed = fontc::parse_command_line(argc, argv);
    if (!parsed.message.empty()) {
        std::ostream& stream = parsed.exit_code == 0 ? std::cout : std::cerr;
        stream << parsed.message;
        if (parsed.message.back() != '\n') stream << '\n';
    }
    if (!parsed.options.has_value()) return parsed.exit_code;

    try {
        const auto print_merge = [](const fontc::PfcMergeStats& stats) {
            std::cout << "pfc_merge: user_glyphs=" << stats.user_glyphs
                      << " special_glyphs_added=" << stats.special_glyphs_added
                      << " duplicate_special_glyphs_skipped=" << stats.duplicate_special_glyphs_skipped
                      << " missing_codepoints=" << stats.missing_codepoints << '\n';
        };
        if (parsed.options->merge_only) {
            const auto& options = *parsed.options;
            if (std::filesystem::exists(options.output_path) && !options.force)
                throw std::runtime_error("output already exists (pass --force to replace it)");
            const auto required = options.chars_file.empty() ? std::vector<std::uint32_t>{}
                : fontc::read_codepoints_file(options.chars_file);
            if (!options.output_path.parent_path().empty())
                std::filesystem::create_directories(options.output_path.parent_path());
            print_merge(fontc::merge_pfc(options.font_path, options.special_pfc_paths,
                                        options.output_path, required));
            return 0;
        }
        const fontc::CompilationReport report = fontc::compile_font(*parsed.options);
        print_merge(report.merge_stats);
        std::cout << "fontc: wrote " << parsed.options->output_path << " ("
                  << report.compiled_glyphs << " glyphs";
        if (report.skipped_missing_glyphs != 0) {
            std::cout << ", " << report.skipped_missing_glyphs << " missing codepoints skipped";
        }
        std::cout << ")\n";
        std::cout << "centerline: raw_points=" << report.raw_centerline_points
                  << " clean_points=" << report.clean_centerline_points
                  << " final_points=" << report.final_path_points
                  << " strokes=" << report.stroke_count
                  << " bezier_segments=" << report.bezier_segment_count
                  << " removed_spurs=" << report.removed_spurs
                  << " removed_spur_length_mm=" << report.removed_spur_length_mm
                  << " graph_nodes_before=" << report.graph_nodes_before
                  << " graph_nodes_after=" << report.graph_nodes_after
                  << " removed_point_count=" << (report.raw_centerline_points > report.final_path_points
                      ? report.raw_centerline_points - report.final_path_points : 0)
                  << " removed_point_ratio=" << (report.raw_centerline_points
                      ? 1.0 - static_cast<double>(report.final_path_points) / report.raw_centerline_points : 0.0)
                  << '\n';
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "fontc: " << error.what() << std::endl;
        return 1;
    }
}
