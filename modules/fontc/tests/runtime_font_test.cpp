#include "fontc/runtime_font.hpp"

#include <cstdlib>
#include <filesystem>
#include <iostream>

namespace {
void require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}
}

int main() {
    const auto path = std::filesystem::temp_directory_path() / "fontc-runtime-test.pfc";
    fontc::CompiledFont compiled{{1000, 800, -200, 0}, {
        {static_cast<std::uint32_t>('?'), 500, {{{{0, 0}, {1, 1}}}}},
        {static_cast<std::uint32_t>('A'), 600, {{{{0, 0}, {2, 3}}}}},
    }};
    fontc::write_pfc(path, compiled);
    const fontc::RuntimeFont runtime(path);
    require(runtime.metrics().units_per_em == 1000, "runtime metrics mismatch");
    require(runtime.contains(static_cast<std::uint32_t>('A')), "runtime glyph missing");
    require(runtime.lookup(static_cast<std::uint32_t>('A')).advance_font_units == 600, "lookup mismatch");
    require(runtime.lookup(0x10FFFFU).codepoint == static_cast<std::uint32_t>('?'), "fallback mismatch");
    for (int index = 0; index < 1000; ++index) {
        require(runtime.lookup(static_cast<std::uint32_t>('A')).codepoint == static_cast<std::uint32_t>('A'),
                "repeated lookup mismatch");
    }
    const fontc::RuntimeWord word = runtime.build_word(U"A?");
    require(word.advance_font_units == 1100, "word advance mismatch");
    require(word.strokes.size() == 2, "word stroke count mismatch");
    require(word.strokes[1].points[0].x == 600, "word glyph translation mismatch");
    std::error_code error;
    std::filesystem::remove(path, error);
}
