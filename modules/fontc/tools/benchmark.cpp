#include "fontc/compiler.hpp"
#include "fontc/pfc.hpp"

#include <array>
#include <chrono>
#include <cstdint>
#include <filesystem>
#include <iostream>
#include <string>
#include <sys/resource.h>

namespace {

using Clock = std::chrono::steady_clock;

template <typename Duration>
double milliseconds(Duration value) {
    return std::chrono::duration<double, std::milli>(value).count();
}

}  // namespace

int main(int argc, char** argv) {
    if (argc != 4) {
        std::cerr << "Usage: fontc_benchmark <font.ttf> <chars.txt> <output-dir>\n";
        return 2;
    }
    const std::filesystem::path output_dir = argv[3];
    std::filesystem::create_directories(output_dir);
    std::cout << "| resolution | compile_ms | peak_rss_kb | glyphs | strokes | points | pfc_bytes | load_ms | lookup_per_sec |\n"
                 "|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n";
    for (const int resolution : std::array{512, 768, 1024, 1536, 2048}) {
        const auto output = output_dir / ("font-" + std::to_string(resolution) + ".pfc");
        fontc::CompilerOptions options;
        options.font_path = argv[1];
        options.chars_file = argv[2];
        options.output_path = output;
        options.resolution = resolution;
        options.force = true;

        const auto compile_start = Clock::now();
        const fontc::CompilationReport report = fontc::compile_font(options);
        const auto compile_end = Clock::now();
        rusage usage{};
        getrusage(RUSAGE_SELF, &usage);

        const auto load_start = Clock::now();
        const fontc::PfcFont font = fontc::PfcFont::load(output);
        const auto load_end = Clock::now();
        std::size_t strokes = 0;
        std::size_t points = 0;
        for (const fontc::CompiledGlyph& glyph : font.glyphs()) {
            strokes += glyph.strokes.size();
            for (const fontc::CompiledStroke& stroke : glyph.strokes) points += stroke.points.size();
        }
        constexpr std::size_t repetitions = 1000;
        const auto lookup_start = Clock::now();
        std::size_t hits = 0;
        for (std::size_t repetition = 0; repetition < repetitions; ++repetition) {
            for (const fontc::CompiledGlyph& glyph : font.glyphs()) {
                if (font.lookup(glyph.codepoint) != nullptr) ++hits;
            }
        }
        const auto lookup_end = Clock::now();
        const double lookup_seconds = std::chrono::duration<double>(lookup_end - lookup_start).count();
        const double throughput = lookup_seconds == 0.0 ? 0.0 : static_cast<double>(hits) / lookup_seconds;
        std::cout << "| " << resolution
                  << " | " << milliseconds(compile_end - compile_start)
                  << " | " << usage.ru_maxrss
                  << " | " << report.compiled_glyphs
                  << " | " << strokes
                  << " | " << points
                  << " | " << std::filesystem::file_size(output)
                  << " | " << milliseconds(load_end - load_start)
                  << " | " << throughput << " |\n";
    }
}
