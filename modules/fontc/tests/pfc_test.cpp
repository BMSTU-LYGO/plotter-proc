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

    const auto common_path = path.string() + ".common";
    const auto extra_path = path.string() + ".extra";
    const auto merged_path = path.string() + ".merged";
    fontc::CompiledFont common;
    common.metrics = {2048, 1600, -400, 0};
    common.glyphs = {
        {static_cast<std::uint32_t>('A'), 999, {{{{777, 888}, {900, 1000}}}}},
        {0x0416, 1234, {{{{100, 200}, {300, 400}}}, {{{500, 600}}}}},
    };
    fontc::CompiledFont extra;
    extra.metrics = common.metrics;
    extra.glyphs = {
        {0x0416, 9999, {{{{9999, 9999}}}}},
        {0x0451, 750, {{{{50, 60}}}}},
    };
    fontc::write_pfc(common_path, common);
    fontc::write_pfc(extra_path, extra);
    const std::vector<std::filesystem::path> specials{common_path, extra_path};
    const std::vector<std::uint32_t> required{'A', 0x0416, 0x0451, 0x9999, 0x9999};
    const auto stats = fontc::merge_pfc(path, specials, merged_path, required);
    require(stats.user_glyphs == 2 && stats.special_glyphs_added == 2 &&
            stats.duplicate_special_glyphs_skipped == 2 && stats.missing_codepoints == 1,
            "merge statistics mismatch");
    const auto merged = fontc::PfcFont::load(merged_path);
    require(merged.glyphs().size() == 4 && merged.metrics().units_per_em == 1000,
            "merge changed user metrics or introduced duplicates");
    require(merged.find('A')->strokes[0].points == font.find('A')->strokes[0].points &&
            merged.find('A')->advance_font_units == 600, "special replaced user glyph");
    require(merged.find(0x0416)->advance_font_units == 1234 &&
            merged.find(0x0416)->strokes.size() == 2 &&
            merged.find(0x0416)->strokes[0].points == common.glyphs[1].strokes[0].points &&
            merged.find(0x0416)->strokes[1].points == common.glyphs[1].strokes[1].points,
            "special glyph geometry/advance changed or special ordering ignored");
    require(merged.lookup(0x9999)->codepoint == '?', "merge changed missing glyph fallback");
    const auto read_file = [](const std::filesystem::path& file) {
        std::ifstream stream(file, std::ios::binary);
        return std::string(std::istreambuf_iterator<char>(stream), {});
    };
    const auto first_bytes = read_file(merged_path);
    (void)fontc::merge_pfc(path, specials, merged_path, required);
    require(read_file(merged_path) == first_bytes, "merge output is not deterministic");
    std::filesystem::remove(common_path);
    std::filesystem::remove(extra_path);
    std::filesystem::remove(merged_path);

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
