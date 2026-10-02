#include "fontc/font_face.hpp"

#include <cstdlib>
#include <iostream>

namespace {

void require(bool condition, const char* message) {
    if (!condition) {
        std::cerr << message << '\n';
        std::exit(1);
    }
}

}  // namespace

int main(int argc, char** argv) {
    require(argc == 2, "expected path to test font");
    fontc::FontFace font(argv[1]);
    const fontc::FontMetrics metrics = font.metrics();
    require(metrics.units_per_em > 0, "units_per_em must be positive");
    require(metrics.ascender > metrics.descender, "invalid vertical metrics");

    const auto question = font.glyph_metrics(U'?');
    require(question.has_value(), "test font must contain fallback glyph");
    require(question->glyph_index != 0, "mapped glyph index must be non-zero");
    require(question->advance_font_units > 0, "advance must be positive");
    require(!font.glyph_metrics(0x10FFFFU).has_value(), "missing codepoint must be explicit");

    bool invalid_rejected = false;
    try {
        fontc::FontFace missing("/fontc/does-not-exist.ttf");
    } catch (const fontc::FreeTypeError&) {
        invalid_rejected = true;
    }
    require(invalid_rejected, "invalid font path must be rejected");
}
