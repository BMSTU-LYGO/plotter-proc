#include "plotter/doc/stage_cache.hpp"

#include <array>
#include <cctype>
#include <atomic>
#include <chrono>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <limits>
#include <sstream>
#include <stdexcept>
#include <system_error>

namespace plotter::doc {
namespace {

constexpr std::array<std::uint8_t, 8> kMagic{{'P', 'L', 'T', 'C', 'A', 'C', 'H', '1'}};
constexpr std::size_t kDigestSize = 32U;
constexpr std::size_t kFixedHeaderSize = kMagic.size() + 4U + 2U + kDigestSize + 8U + kDigestSize;

class Sha256 final {
public:
    void update(std::span<const std::uint8_t> bytes) {
        for (const std::uint8_t byte : bytes) {
            block_[used++] = byte;
            if (used == block_.size()) { transform(); bit_length += 512U; used = 0U; }
        }
    }
    [[nodiscard]] std::array<std::uint8_t, kDigestSize> final() {
        bit_length += static_cast<std::uint64_t>(used) * 8U;
        block_[used++] = 0x80U;
        if (used > 56U) { while (used < 64U) block_[used++] = 0U; transform(); used = 0U; }
        while (used < 56U) block_[used++] = 0U;
        for (int index = 7; index >= 0; --index) block_[used++] = static_cast<std::uint8_t>(bit_length >> (index * 8));
        transform();
        std::array<std::uint8_t, kDigestSize> result{};
        for (std::size_t index = 0; index < state_.size(); ++index) for (std::size_t byte = 0; byte < 4U; ++byte)
            result[index * 4U + byte] = static_cast<std::uint8_t>(state_[index] >> (24U - static_cast<unsigned>(byte) * 8U));
        return result;
    }
private:
    static constexpr std::array<std::uint32_t, 64> kConstants{{
        0x428a2f98U,0x71374491U,0xb5c0fbcfU,0xe9b5dba5U,0x3956c25bU,0x59f111f1U,0x923f82a4U,0xab1c5ed5U,
        0xd807aa98U,0x12835b01U,0x243185beU,0x550c7dc3U,0x72be5d74U,0x80deb1feU,0x9bdc06a7U,0xc19bf174U,
        0xe49b69c1U,0xefbe4786U,0x0fc19dc6U,0x240ca1ccU,0x2de92c6fU,0x4a7484aaU,0x5cb0a9dcU,0x76f988daU,
        0x983e5152U,0xa831c66dU,0xb00327c8U,0xbf597fc7U,0xc6e00bf3U,0xd5a79147U,0x06ca6351U,0x14292967U,
        0x27b70a85U,0x2e1b2138U,0x4d2c6dfcU,0x53380d13U,0x650a7354U,0x766a0abbU,0x81c2c92eU,0x92722c85U,
        0xa2bfe8a1U,0xa81a664bU,0xc24b8b70U,0xc76c51a3U,0xd192e819U,0xd6990624U,0xf40e3585U,0x106aa070U,
        0x19a4c116U,0x1e376c08U,0x2748774cU,0x34b0bcb5U,0x391c0cb3U,0x4ed8aa4aU,0x5b9cca4fU,0x682e6ff3U,
        0x748f82eeU,0x78a5636fU,0x84c87814U,0x8cc70208U,0x90befffaU,0xa4506cebU,0xbef9a3f7U,0xc67178f2U}};
    [[nodiscard]] static std::uint32_t rotr(std::uint32_t value, unsigned shift) { return (value >> shift) | (value << (32U - shift)); }
    void transform() {
        std::array<std::uint32_t, 64> words{};
        for (std::size_t index = 0; index < 16U; ++index) words[index] =
            (static_cast<std::uint32_t>(block_[index * 4U]) << 24U) | (static_cast<std::uint32_t>(block_[index * 4U + 1U]) << 16U) |
            (static_cast<std::uint32_t>(block_[index * 4U + 2U]) << 8U) | static_cast<std::uint32_t>(block_[index * 4U + 3U]);
        for (std::size_t index = 16U; index < words.size(); ++index) {
            const std::uint32_t a = rotr(words[index - 15U], 7U) ^ rotr(words[index - 15U], 18U) ^ (words[index - 15U] >> 3U);
            const std::uint32_t b = rotr(words[index - 2U], 17U) ^ rotr(words[index - 2U], 19U) ^ (words[index - 2U] >> 10U);
            words[index] = words[index - 16U] + a + words[index - 7U] + b;
        }
        std::uint32_t a = state_[0], b = state_[1], c = state_[2], d = state_[3], e = state_[4], f = state_[5], g = state_[6], h = state_[7];
        for (std::size_t index = 0; index < words.size(); ++index) {
            const std::uint32_t s1 = rotr(e, 6U) ^ rotr(e, 11U) ^ rotr(e, 25U);
            const std::uint32_t choice = (e & f) ^ (~e & g);
            const std::uint32_t temp1 = h + s1 + choice + kConstants[index] + words[index];
            const std::uint32_t s0 = rotr(a, 2U) ^ rotr(a, 13U) ^ rotr(a, 22U);
            const std::uint32_t majority = (a & b) ^ (a & c) ^ (b & c);
            const std::uint32_t temp2 = s0 + majority;
            h = g; g = f; f = e; e = d + temp1; d = c; c = b; b = a; a = temp1 + temp2;
        }
        state_[0] += a; state_[1] += b; state_[2] += c; state_[3] += d; state_[4] += e; state_[5] += f; state_[6] += g; state_[7] += h;
    }
    std::array<std::uint8_t, 64> block_{};
    std::array<std::uint32_t, 8> state_{{0x6a09e667U,0xbb67ae85U,0x3c6ef372U,0xa54ff53aU,0x510e527fU,0x9b05688cU,0x1f83d9abU,0x5be0cd19U}};
    std::size_t used{};
    std::uint64_t bit_length{};
};

[[nodiscard]] std::array<std::uint8_t, kDigestSize> digest(std::span<const std::uint8_t> bytes) { Sha256 hash; hash.update(bytes); return hash.final(); }
[[nodiscard]] std::string hex(const std::array<std::uint8_t, kDigestSize>& value) { std::ostringstream output; output << std::hex << std::setfill('0'); for (const auto byte : value) output << std::setw(2) << static_cast<unsigned>(byte); return output.str(); }
[[nodiscard]] bool valid_stage(std::string_view value) { if (value.empty() || value.size() > 128U) return false; for (const unsigned char character : value) if (!(std::isalnum(character) || character == '-' || character == '_')) return false; return true; }
[[nodiscard]] bool valid_fingerprint(std::string_view value) { if (value.size() != 64U) return false; for (const unsigned char character : value) if (!std::isxdigit(character)) return false; return true; }
void write_u16(std::ofstream& out, std::uint16_t value) { for (unsigned shift = 0; shift < 16U; shift += 8U) out.put(static_cast<char>(value >> shift)); }
void write_u32(std::ofstream& out, std::uint32_t value) { for (unsigned shift = 0; shift < 32U; shift += 8U) out.put(static_cast<char>(value >> shift)); }
void write_u64(std::ofstream& out, std::uint64_t value) { for (unsigned shift = 0; shift < 64U; shift += 8U) out.put(static_cast<char>(value >> shift)); }
[[nodiscard]] bool read_u16(std::ifstream& in, std::uint16_t& value) { std::array<std::uint8_t, 2> bytes{}; if (!in.read(reinterpret_cast<char*>(bytes.data()), 2)) return false; value = static_cast<std::uint16_t>(bytes[0]) | (static_cast<std::uint16_t>(bytes[1]) << 8U); return true; }
[[nodiscard]] bool read_u32(std::ifstream& in, std::uint32_t& value) { std::array<std::uint8_t, 4> bytes{}; if (!in.read(reinterpret_cast<char*>(bytes.data()), 4)) return false; value = 0; for (unsigned index = 0; index < 4U; ++index) value |= static_cast<std::uint32_t>(bytes[index]) << (index * 8U); return true; }
[[nodiscard]] bool read_u64(std::ifstream& in, std::uint64_t& value) { std::array<std::uint8_t, 8> bytes{}; if (!in.read(reinterpret_cast<char*>(bytes.data()), 8)) return false; value = 0; for (unsigned index = 0; index < 8U; ++index) value |= static_cast<std::uint64_t>(bytes[index]) << (index * 8U); return true; }
void append_field(Sha256& hash, std::string_view value) { const auto size = static_cast<std::uint64_t>(value.size()); std::array<std::uint8_t, 8> bytes{}; for (unsigned index = 0; index < 8U; ++index) bytes[index] = static_cast<std::uint8_t>(size >> (index * 8U)); hash.update(bytes); hash.update({reinterpret_cast<const std::uint8_t*>(value.data()), value.size()}); }

}  // namespace

StageCache::StageCache(StageCacheOptions options) : options_(std::move(options)) {
    if (options_.root.empty() || options_.schema_version == 0U || options_.max_payload_bytes == 0U)
        throw std::invalid_argument("stage cache requires a root, nonzero schema version, and payload limit");
}

std::string StageCache::fingerprint(std::string_view stage, std::string_view input_fingerprint,
                                    std::string_view algorithm_version, std::string_view canonical_settings) {
    if (!valid_stage(stage)) throw std::invalid_argument("invalid stage name for fingerprint");
    Sha256 hash;
    append_field(hash, stage); append_field(hash, input_fingerprint); append_field(hash, algorithm_version); append_field(hash, canonical_settings);
    return hex(hash.final());
}

std::string StageCache::source_fingerprint(const std::filesystem::path& source) {
    std::ifstream input(source, std::ios::binary);
    if (!input) throw std::runtime_error("cannot open cache source: " + source.string());
    Sha256 hash;
    std::array<std::uint8_t, 64U * 1024U> buffer{};
    while (input.read(reinterpret_cast<char*>(buffer.data()), static_cast<std::streamsize>(buffer.size())) || input.gcount() > 0) {
        hash.update(std::span<const std::uint8_t>{buffer.data(), static_cast<std::size_t>(input.gcount())});
    }
    if (!input.eof()) throw std::runtime_error("cannot read cache source: " + source.string());
    return hex(hash.final());
}

std::string StageCache::import_fingerprint(const std::filesystem::path& source,
                                           std::string_view algorithm_version,
                                           std::string_view canonical_settings) {
    return fingerprint("read_document", source_fingerprint(source), algorithm_version, canonical_settings);
}

std::filesystem::path StageCache::entry_path(std::string_view stage, std::string_view fingerprint) const {
    if (!valid_stage(stage) || !valid_fingerprint(fingerprint)) throw std::invalid_argument("invalid stage cache key");
    return options_.root / std::string(stage) / std::string(fingerprint) / "entry.bin";
}

StageCacheLookup StageCache::load(std::string_view stage, std::string_view fingerprint) const {
    const auto path = entry_path(stage, fingerprint);
    std::error_code error;
    if (!std::filesystem::is_regular_file(path, error) || error) return {};
    try {
        std::ifstream input(path, std::ios::binary);
        std::array<std::uint8_t, kMagic.size()> magic{};
        std::uint32_t version{}; std::uint16_t stage_size{}; std::uint64_t payload_size{};
        std::array<std::uint8_t, kDigestSize> stored_fingerprint{}, stored_payload{};
        if (!input.read(reinterpret_cast<char*>(magic.data()), static_cast<std::streamsize>(magic.size())) || magic != kMagic ||
            !read_u32(input, version) || !read_u16(input, stage_size) || version != options_.schema_version || stage_size == 0U || stage_size > 128U)
            return {false, true, {}};
        std::string stored_stage(stage_size, '\0');
        if (!input.read(stored_stage.data(), stage_size) || !input.read(reinterpret_cast<char*>(stored_fingerprint.data()), static_cast<std::streamsize>(stored_fingerprint.size())) ||
            !read_u64(input, payload_size) || payload_size > options_.max_payload_bytes || !input.read(reinterpret_cast<char*>(stored_payload.data()), static_cast<std::streamsize>(stored_payload.size())) ||
            stored_stage != stage)
            return {false, true, {}};
        const auto expected_fingerprint = digest({reinterpret_cast<const std::uint8_t*>(fingerprint.data()), fingerprint.size()});
        if (stored_fingerprint != expected_fingerprint) return {false, true, {}};
        StageBytes payload(static_cast<std::size_t>(payload_size));
        if (payload_size != 0U && !input.read(reinterpret_cast<char*>(payload.data()), static_cast<std::streamsize>(payload.size()))) return {false, true, {}};
        if (input.peek() != std::char_traits<char>::eof() || digest(payload) != stored_payload) return {false, true, {}};
        return {true, false, std::move(payload)};
    } catch (const std::exception&) { return {false, true, {}}; }
}

void StageCache::store(std::string_view stage, std::string_view fingerprint, std::span<const std::uint8_t> payload) const {
    if (payload.size() > options_.max_payload_bytes) throw std::invalid_argument("stage cache payload exceeds configured limit");
    const auto path = entry_path(stage, fingerprint);
    std::error_code error;
    std::filesystem::create_directories(path.parent_path(), error);
    if (error) throw std::runtime_error("cannot create stage cache directory: " + error.message());
    static std::atomic<std::uint64_t> sequence{};
    const auto temporary = path.string() + "." + std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()) + "." + std::to_string(sequence.fetch_add(1U)) + ".tmp";
    try {
        std::ofstream output(temporary, std::ios::binary | std::ios::trunc);
        if (!output) throw std::runtime_error("cannot create stage cache temporary entry");
        output.write(reinterpret_cast<const char*>(kMagic.data()), static_cast<std::streamsize>(kMagic.size()));
        write_u32(output, options_.schema_version); write_u16(output, static_cast<std::uint16_t>(stage.size()));
        output.write(stage.data(), static_cast<std::streamsize>(stage.size()));
        const auto fingerprint_digest = digest({reinterpret_cast<const std::uint8_t*>(fingerprint.data()), fingerprint.size()});
        const auto payload_digest = digest(payload);
        output.write(reinterpret_cast<const char*>(fingerprint_digest.data()), static_cast<std::streamsize>(fingerprint_digest.size()));
        write_u64(output, static_cast<std::uint64_t>(payload.size()));
        output.write(reinterpret_cast<const char*>(payload_digest.data()), static_cast<std::streamsize>(payload_digest.size()));
        if (!payload.empty()) output.write(reinterpret_cast<const char*>(payload.data()), static_cast<std::streamsize>(payload.size()));
        output.close();
        if (!output) throw std::runtime_error("cannot write stage cache entry");
        std::filesystem::rename(temporary, path, error);
        if (error) throw std::runtime_error("cannot atomically publish stage cache entry: " + error.message());
    } catch (...) { std::filesystem::remove(temporary, error); throw; }
}

}  // namespace plotter::doc
