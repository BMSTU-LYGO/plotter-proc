#include "fontc/font_face.hpp"

#include <limits>
#include <string>
#include <utility>

namespace fontc {
namespace {

[[nodiscard]] int checked_int(FT_Pos value, const char* field) {
    if (value < std::numeric_limits<int>::min() || value > std::numeric_limits<int>::max()) {
        throw FreeTypeError(std::string("Font metric is outside int range: ") + field);
    }
    return static_cast<int>(value);
}

}  // namespace

FontFace::FontFace(const std::filesystem::path& path) {
    if (FT_Init_FreeType(&library_) != 0) {
        throw FreeTypeError("Cannot initialize FreeType");
    }

    const std::string native_path = path.string();
    if (FT_New_Face(library_, native_path.c_str(), 0, &face_) != 0) {
        reset();
        throw FreeTypeError("Cannot open font: " + native_path);
    }
    if (face_->units_per_EM == 0) {
        reset();
        throw FreeTypeError("Font units_per_em must be positive: " + native_path);
    }
    if (FT_Select_Charmap(face_, FT_ENCODING_UNICODE) != 0) {
        reset();
        throw FreeTypeError("Font has no Unicode charmap: " + native_path);
    }

    const int ascender = checked_int(face_->ascender, "ascender");
    const int descender = checked_int(face_->descender, "descender");
    metrics_ = {
        static_cast<int>(face_->units_per_EM),
        ascender,
        descender,
        checked_int(face_->height, "height") - (ascender - descender),
    };
}

FontFace::~FontFace() {
    reset();
}

FontFace::FontFace(FontFace&& other) noexcept
    : library_(std::exchange(other.library_, nullptr)),
      face_(std::exchange(other.face_, nullptr)),
      metrics_(other.metrics_) {}

FontFace& FontFace::operator=(FontFace&& other) noexcept {
    if (this != &other) {
        reset();
        library_ = std::exchange(other.library_, nullptr);
        face_ = std::exchange(other.face_, nullptr);
        metrics_ = other.metrics_;
    }
    return *this;
}

std::optional<GlyphMetrics> FontFace::glyph_metrics(std::uint32_t codepoint) {
    const FT_UInt glyph_index = FT_Get_Char_Index(face_, static_cast<FT_ULong>(codepoint));
    if (glyph_index == 0) return std::nullopt;
    if (FT_Load_Glyph(face_, glyph_index, FT_LOAD_NO_SCALE | FT_LOAD_NO_HINTING) != 0) {
        throw FreeTypeError("Cannot load glyph for codepoint U+" + std::to_string(codepoint));
    }
    return GlyphMetrics{
        codepoint,
        static_cast<std::uint32_t>(glyph_index),
        checked_int(face_->glyph->advance.x, "glyph advance"),
    };
}

void FontFace::reset() noexcept {
    if (face_ != nullptr) {
        FT_Done_Face(face_);
        face_ = nullptr;
    }
    if (library_ != nullptr) {
        FT_Done_FreeType(library_);
        library_ = nullptr;
    }
}

}  // namespace fontc
