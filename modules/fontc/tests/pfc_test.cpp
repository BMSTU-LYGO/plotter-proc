#include "fontc/pfc.hpp"

#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <iostream>

namespace {

void require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

fontc::CompiledFont fixture() {
    fontc::CompiledFont font;
    font.metrics = {1000, 800, -200, 0};
    font.glyphs = {
        {static_cast<std::uint32_t>('?'), 500, {{{{0, 0}, {10, 20}}}}},
        {static_cast<std::uint32_t>('A'), 600, {{{{-123456, 10}, {20, 30}}}}},
    };
    return font;
}

}  // namespace

int main() {
    const std::filesystem::path path = std::filesystem::temp_directory_path() / "fontc_pfc_test.pfc";
    std::error_code error;
    std::filesystem::remove(path, error);

    fontc::PfcMetadata metadata;
    metadata.algorithm_version = 7;
    metadata.font_hash[0] = 0xAB;
    fontc::write_pfc(path, fixture(), metadata);

    const fontc::PfcFont font = fontc::PfcFont::load(path);
    require(font.metrics().units_per_em == 1000, "metrics did not round trip");
    require(font.metadata().algorithm_version == 7 && font.metadata().font_hash[0] == 0xAB,
            "metadata did not round trip");
    const auto* a = font.find(static_cast<std::uint32_t>('A'));
    require(a != nullptr && a->strokes[0].points[0] == fontc::PointFU{-123456, 10}, "glyph did not round trip");
    require(font.lookup(0x0416) != nullptr && font.lookup(0x0416)->codepoint == static_cast<std::uint32_t>('?'),
            "fallback glyph mismatch");
    require(font.find(0x0416) == nullptr, "missing glyph unexpectedly found");

    std::fstream corrupt(path, std::ios::binary | std::ios::in | std::ios::out);
    corrupt.seekp(0);
    corrupt.write("BAD!", 4);
    corrupt.close();
    bool rejected = false;
    try {
        static_cast<void>(fontc::PfcFont::load(path));
    } catch (const fontc::PfcError&) {
        rejected = true;
    }
    require(rejected, "corrupted PFC was accepted");
    std::filesystem::remove(path, error);
}
