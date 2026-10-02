#pragma once

#include "fontc/compiled_font.hpp"

#include <array>
#include <cstdint>
#include <filesystem>
#include <stdexcept>
#include <vector>

namespace fontc {

inline constexpr std::uint32_t kPfcFormatVersion = 1;
inline constexpr std::uint32_t kPfcAlgorithmVersion = 1;

class PfcError final : public std::runtime_error {
public:
    using std::runtime_error::runtime_error;
};

// Deterministic 256-bit fingerprints of the source font and compiler configuration.
using PfcHash = std::array<std::uint8_t, 32>;

struct PfcMetadata {
    std::uint32_t algorithm_version = kPfcAlgorithmVersion;
    PfcHash font_hash{};
    PfcHash config_hash{};
};

// Writes a deterministic PFC1 file. The replacement is committed atomically.
void write_pfc(const std::filesystem::path& path, const CompiledFont& font,
               const PfcMetadata& metadata = {});

class PfcFont final {
public:
    [[nodiscard]] static PfcFont load(const std::filesystem::path& path);

    [[nodiscard]] const FontMetrics& metrics() const noexcept { return metrics_; }
    [[nodiscard]] const PfcMetadata& metadata() const noexcept { return metadata_; }
    [[nodiscard]] const CompiledGlyph* find(std::uint32_t codepoint) const noexcept;
    // Looks up codepoint, falling back to ASCII '?' when it is present.
    [[nodiscard]] const CompiledGlyph* lookup(std::uint32_t codepoint) const noexcept;
    [[nodiscard]] const std::vector<CompiledGlyph>& glyphs() const noexcept { return glyphs_; }

private:
    FontMetrics metrics_{};
    PfcMetadata metadata_{};
    std::vector<CompiledGlyph> glyphs_;  // sorted by codepoint
};

// Explicit runtime name for consumers that only need the compiled cache.
using PfcReader = PfcFont;

}  // namespace fontc
