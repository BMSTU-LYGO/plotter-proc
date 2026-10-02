#pragma once

#include "plotter/doc/model.hpp"
#include "plotter/doc/stage_cache.hpp"

#include <optional>

namespace plotter::doc {

// Stable binary codec for the normalized import-stage Document model. Every
// model member is encoded explicitly; decoding rejects truncation, unknown
// variants, trailing bytes, and over-large container declarations.
struct DocumentCodec final {
    static constexpr std::uint32_t schema_version = 1;

    [[nodiscard]] static bool cacheable(const Document& value) noexcept;
    [[nodiscard]] static StageBytes encode(const Document& value);
    [[nodiscard]] static std::optional<Document> decode(std::span<const std::uint8_t> bytes);
};

}  // namespace plotter::doc
