#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <optional>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace plotter::doc {

// This cache only persists opaque binary stage payloads. Typed document,
// layout, and geometry codecs remain separate versioned contracts; this file
// deliberately does not serialize C++ objects or Python pickle data.
using StageBytes = std::vector<std::uint8_t>;

struct StageCacheOptions final {
    std::filesystem::path root;
    std::uint32_t schema_version{1};
    std::uint64_t max_payload_bytes{512ULL * 1024ULL * 1024ULL};
};

struct StageCacheLookup final {
    bool hit{};
    bool corrupt{};
    StageBytes payload;
};

template <typename Value>
struct TypedStageCacheLookup final {
    bool hit{};
    bool corrupt{};
    Value value{};
};

// A codec owns the model-specific binary layout. It must provide:
// static constexpr std::uint32_t schema_version;
// static StageBytes encode(const Value&);
// static std::optional<Value> decode(std::span<const std::uint8_t>);
// Decode failure is converted into a cache miss.

class StageCache final {
public:
    explicit StageCache(StageCacheOptions options);

    // Produces a stable SHA-256 hex digest over length-delimited declared
    // inputs. Callers must provide already-canonical settings bytes.
    [[nodiscard]] static std::string fingerprint(std::string_view stage,
                                                 std::string_view input_fingerprint,
                                                 std::string_view algorithm_version,
                                                 std::string_view canonical_settings);
    // SHA-256 of exact source bytes. Paths, timestamps, and other local
    // metadata are excluded so a copied source retains the same key.
    [[nodiscard]] static std::string source_fingerprint(const std::filesystem::path& source);
    [[nodiscard]] static std::string import_fingerprint(const std::filesystem::path& source,
                                                         std::string_view algorithm_version,
                                                         std::string_view canonical_settings);
    [[nodiscard]] StageCacheLookup load(std::string_view stage,
                                        std::string_view fingerprint) const;
    void store(std::string_view stage, std::string_view fingerprint,
               std::span<const std::uint8_t> payload) const;

    template <typename Value, typename Codec>
    [[nodiscard]] TypedStageCacheLookup<Value> load_typed(
        std::string_view stage, std::string_view fingerprint) const {
        const auto raw = load(stage, fingerprint);
        if (!raw.hit) return {false, raw.corrupt, {}};
        if (raw.payload.size() < 8U || raw.payload[0] != 'P' || raw.payload[1] != 'T' ||
            raw.payload[2] != 'Y' || raw.payload[3] != 'P') return {false, true, {}};
        const auto version = static_cast<std::uint32_t>(raw.payload[4]) |
            (static_cast<std::uint32_t>(raw.payload[5]) << 8U) |
            (static_cast<std::uint32_t>(raw.payload[6]) << 16U) |
            (static_cast<std::uint32_t>(raw.payload[7]) << 24U);
        if (version != Codec::schema_version) return {false, true, {}};
        const auto value = Codec::decode(std::span<const std::uint8_t>{raw.payload}.subspan(8U));
        if (!value) return {false, true, {}};
        return {true, false, *value};
    }

    template <typename Value, typename Codec>
    void store_typed(std::string_view stage, std::string_view fingerprint,
                     const Value& value) const {
        auto payload = Codec::encode(value);
        payload.insert(payload.begin(), {'P', 'T', 'Y', 'P',
            static_cast<std::uint8_t>(Codec::schema_version),
            static_cast<std::uint8_t>(Codec::schema_version >> 8U),
            static_cast<std::uint8_t>(Codec::schema_version >> 16U),
            static_cast<std::uint8_t>(Codec::schema_version >> 24U)});
        store(stage, fingerprint, payload);
    }
    [[nodiscard]] std::filesystem::path entry_path(std::string_view stage,
                                                   std::string_view fingerprint) const;

private:
    StageCacheOptions options_;
};

}  // namespace plotter::doc
