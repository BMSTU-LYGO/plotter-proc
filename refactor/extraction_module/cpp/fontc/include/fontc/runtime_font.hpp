#pragma once

#include "fontc/pfc.hpp"

#include <cstdint>
#include <filesystem>
#include <string_view>
#include <vector>

namespace fontc {

struct RuntimeWord {
    std::int64_t advance_font_units = 0;
    std::vector<CompiledStroke> strokes;
};

// Cache-only runtime facade. It has no TTF or compiler entrypoint.
class RuntimeFont final {
public:
    explicit RuntimeFont(const std::filesystem::path& pfc_path);

    [[nodiscard]] const FontMetrics& metrics() const noexcept { return font_.metrics(); }
    [[nodiscard]] const CompiledGlyph& lookup(std::uint32_t codepoint) const;
    [[nodiscard]] bool contains(std::uint32_t codepoint) const noexcept {
        return font_.find(codepoint) != nullptr;
    }
    [[nodiscard]] RuntimeWord build_word(std::u32string_view text) const;

private:
    PfcFont font_;
};

}  // namespace fontc
