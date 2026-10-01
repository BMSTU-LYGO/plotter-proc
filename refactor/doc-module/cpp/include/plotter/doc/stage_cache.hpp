#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
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

class StageCache final {
public:
    explicit StageCache(StageCacheOptions options);

    // Produces a stable SHA-256 hex digest over length-delimited declared
    // inputs. Callers must provide already-canonical settings bytes.
    [[nodiscard]] static std::string fingerprint(std::string_view stage,
                                                 std::string_view input_fingerprint,
                                                 std::string_view algorithm_version,
                                                 std::string_view canonical_settings);
    [[nodiscard]] StageCacheLookup load(std::string_view stage,
                                        std::string_view fingerprint) const;
    void store(std::string_view stage, std::string_view fingerprint,
               std::span<const std::uint8_t> payload) const;
    [[nodiscard]] std::filesystem::path entry_path(std::string_view stage,
                                                   std::string_view fingerprint) const;

private:
    StageCacheOptions options_;
};

}  // namespace plotter::doc
