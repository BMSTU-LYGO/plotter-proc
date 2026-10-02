#include "fontc/compiler.hpp"
#include "fontc/pfc.hpp"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <iterator>
#include <vector>

namespace {
void require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

std::vector<char> bytes(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary);
    return {std::istreambuf_iterator<char>(stream), std::istreambuf_iterator<char>()};
}
}

int main(int argc, char** argv) {
    require(argc == 3, "expected font and regression corpus paths");
    const auto directory = std::filesystem::temp_directory_path();
    const auto single = directory / "fontc-regression-single.pfc";
    const auto parallel = directory / "fontc-regression-parallel.pfc";
    fontc::CompilerOptions options;
    options.font_path = argv[1];
    options.chars_file = argv[2];
    options.output_path = single;
    options.resolution = 128;
    options.threads = 1;
    options.force = true;
    (void)fontc::compile_font(options);
    options.output_path = parallel;
    options.threads = 2;
    (void)fontc::compile_font(options);
    require(bytes(single) == bytes(parallel), "PFC output depends on worker completion order");

    const fontc::PfcFont font = fontc::PfcFont::load(single);
    require(font.find(static_cast<std::uint32_t>('?')) != nullptr, "fallback glyph missing");
    for (const std::uint32_t codepoint : {0x0410U, 0x0411U, 0x0412U, 0x0416U, 0x0424U,
                                          0x0429U, 0x042FU, 0x0430U, 0x0431U, 0x0432U,
                                          0x0436U, 0x0444U, 0x0030U, 0x004FU, 0x0052U}) {
        const fontc::CompiledGlyph* glyph = font.find(codepoint);
        require(glyph != nullptr, "required regression glyph missing");
        require(glyph->advance_font_units > 0, "regression glyph advance is invalid");
        require(!glyph->strokes.empty(), "visible regression glyph has no strokes");
        for (const fontc::CompiledStroke& stroke : glyph->strokes) {
            require(!stroke.points.empty(), "regression glyph contains an empty stroke");
            for (const fontc::PointFU point : stroke.points) {
                const int limit = font.metrics().units_per_em * 4;
                require(point.x >= -limit && point.x <= limit && point.y >= -limit && point.y <= limit,
                        "regression geometry is outside expected font bounds");
            }
        }
    }
    std::error_code error;
    std::filesystem::remove(single, error);
    std::filesystem::remove(parallel, error);
}
