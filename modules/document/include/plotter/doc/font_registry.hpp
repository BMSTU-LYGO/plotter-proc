#pragma once

#include "plotter/doc/units.hpp"

#include <cstdint>
#include <filesystem>
#include <functional>
#include <map>
#include <memory>
#include <string>
#include <string_view>
#include <vector>

namespace fontc { class RuntimeFont; struct CompiledGlyph; struct FontMetrics; }

namespace plotter::doc {

struct FreeTypeHandle;

// PFC provides centerlines; TTF/OTF supplies metrics for outline layout.
struct FontRegistration final {
    std::string id;
    std::string sha256;
    std::filesystem::path pfc_path;
};

struct FontPoint final { FontUnits x{}, y{}; };
struct FontStroke final { std::vector<FontPoint> points; };
struct GlyphGeometry final { std::uint32_t glyph_codepoint{}; std::vector<FontStroke> strokes; };

struct ResolvedGlyph final {
    std::string font_id;
    std::string font_sha256;
    std::uint32_t requested_codepoint{};
    std::uint32_t glyph_codepoint{};
    FontUnits advance{};
    std::int32_t units_per_em{};
    std::int32_t ascender{};
    std::int32_t descender{};
    std::int32_t line_gap{};
    bool used_fallback{};
};

class FontRegistry final {
public:
    void register_pfc(FontRegistration registration);
    void register_outline_font(FontRegistration registration);
    void set_fallback_font(std::string id);

    [[nodiscard]] bool contains(std::string_view id) const noexcept;
    [[nodiscard]] const FontRegistration& font(std::string_view id) const;
    [[nodiscard]] const std::filesystem::path& outline_font_path(std::string_view id) const;
    // Selects the requested font when it contains the glyph, then the registry
    // fallback, then the requested font's required '?' glyph.
    [[nodiscard]] ResolvedGlyph resolve(std::string_view requested_font_id,
                                        std::uint32_t codepoint) const;
    [[nodiscard]] GlyphGeometry glyph_geometry(std::string_view font_id, std::uint32_t codepoint) const;

private:
    struct Entry final {
        FontRegistration registration;
        std::shared_ptr<fontc::RuntimeFont> runtime;
        std::shared_ptr<FreeTypeHandle> outline;
    };
    [[nodiscard]] const Entry& entry(std::string_view id) const;
    std::map<std::string, Entry, std::less<>> entries_;
    std::string fallback_font_id_;
};

[[nodiscard]] constexpr Millimetres font_units_to_millimetres(FontUnits value,
                                                                Millimetres font_size,
                                                                std::int32_t units_per_em) {
    return {units_per_em == 0 ? 0.0 : value.value * font_size.value / static_cast<double>(units_per_em)};
}

}  // namespace plotter::doc
