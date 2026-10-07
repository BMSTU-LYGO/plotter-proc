#pragma once

#include "fontc/compiled_font.hpp"

#include <array>
#include <cstdint>
#include <filesystem>
#include <stdexcept>
#include <span>
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

struct PfcMergeStats {
    std::size_t user_glyphs = 0;
    std::size_t special_glyphs_added = 0;
    std::size_t duplicate_special_glyphs_skipped = 0;
    std::size_t missing_codepoints = 0;
};

// Sources are visited in caller order; glyph coordinates and advances are copied exactly.
// Required codepoints are counted by exact presence, without '?' fallback.
[[nodiscard]] PfcMergeStats merge_special_glyphs(
    CompiledFont& user, std::span<const PfcFont> specials,
    std::span<const std::uint32_t> required_codepoints = {});

// Offline merge: runtime loads only the resulting cache.
[[nodiscard]] PfcMergeStats merge_pfc(
    const std::filesystem::path& user_path,
    std::span<const std::filesystem::path> special_paths,
    const std::filesystem::path& output_path,
    std::span<const std::uint32_t> required_codepoints = {});

}  // namespace fontc
