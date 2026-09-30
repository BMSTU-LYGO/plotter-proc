#pragma once

#include <cstdint>
#include <filesystem>
#include <optional>
#include <stdexcept>

#include <ft2build.h>
#include FT_FREETYPE_H

namespace fontc {

class FreeTypeError final : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

struct FontMetrics {
    int units_per_em;
    int ascender;
    int descender;
    int line_gap;
};

struct GlyphMetrics {
    std::uint32_t codepoint;
    std::uint32_t glyph_index;
    int advance_font_units;
};

class FontFace final {
public:
    explicit FontFace(const std::filesystem::path& path);
    ~FontFace();

    FontFace(const FontFace&) = delete;
    FontFace& operator=(const FontFace&) = delete;
    FontFace(FontFace&& other) noexcept;
    FontFace& operator=(FontFace&& other) noexcept;

    [[nodiscard]] const FontMetrics& metrics() const noexcept { return metrics_; }
    [[nodiscard]] std::optional<GlyphMetrics> glyph_metrics(std::uint32_t codepoint);
    [[nodiscard]] FT_Face native_handle() noexcept { return face_; }

private:
    void reset() noexcept;

    FT_Library library_ = nullptr;
    FT_Face face_ = nullptr;
    FontMetrics metrics_{};
};

}  // namespace fontc
