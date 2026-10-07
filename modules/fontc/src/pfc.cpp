#include "fontc/pfc.hpp"

#include <algorithm>
#include <cerrno>
#include <cstring>
#include <fcntl.h>
#include <fstream>
#include <limits>
#include <map>
#include <set>
#include <span>
#include <string>
#include <system_error>
#include <unistd.h>

namespace fontc {
namespace {

constexpr std::size_t kHeaderSize = 96;
constexpr std::size_t kIndexSize = 16;
constexpr std::uint32_t kMaxGlyphs = 1'000'000;
constexpr std::uint32_t kMaxStrokes = 1'000'000;
constexpr std::uint32_t kMaxPoints = 10'000'000;

[[noreturn]] void fail(const char* message) { throw PfcError(message); }

void append_u32(std::vector<std::uint8_t>& output, std::uint32_t value) {
    for (int shift = 0; shift != 32; shift += 8) output.push_back(static_cast<std::uint8_t>(value >> shift));
}

void append_i32(std::vector<std::uint8_t>& output, std::int32_t value) {
    append_u32(output, static_cast<std::uint32_t>(value));
}

void append_u64(std::vector<std::uint8_t>& output, std::uint64_t value) {
    for (int shift = 0; shift != 64; shift += 8) output.push_back(static_cast<std::uint8_t>(value >> shift));
}

std::uint32_t read_u32(std::span<const std::uint8_t> bytes, std::size_t& position) {
    if (bytes.size() - position < 4) fail("truncated PFC field");
    std::uint32_t value = 0;
    for (int shift = 0; shift != 32; shift += 8) value |= static_cast<std::uint32_t>(bytes[position++]) << shift;
    return value;
}

std::int32_t read_i32(std::span<const std::uint8_t> bytes, std::size_t& position) {
    return static_cast<std::int32_t>(read_u32(bytes, position));
}

std::uint64_t read_u64(std::span<const std::uint8_t> bytes, std::size_t& position) {
    if (bytes.size() - position < 8) fail("truncated PFC field");
    std::uint64_t value = 0;
    for (int shift = 0; shift != 64; shift += 8) value |= static_cast<std::uint64_t>(bytes[position++]) << shift;
    return value;
}

void require_range(std::size_t offset, std::size_t size, std::size_t total) {
    if (offset > total || size > total - offset) fail("PFC offset is out of bounds");
}

std::vector<std::uint8_t> make_payload(const CompiledGlyph& glyph) {
    if (glyph.strokes.size() > kMaxStrokes) fail("too many strokes for PFC");
    std::vector<std::uint8_t> payload;
    append_u32(payload, glyph.codepoint);
    append_i32(payload, glyph.advance_font_units);
    append_u32(payload, static_cast<std::uint32_t>(glyph.strokes.size()));
    for (const CompiledStroke& stroke : glyph.strokes) {
        if (stroke.points.size() > kMaxPoints) fail("too many points for PFC");
        append_u32(payload, static_cast<std::uint32_t>(stroke.points.size()));
        for (const PointFU point : stroke.points) {
            append_i32(payload, point.x);
            append_i32(payload, point.y);
        }
    }
    return payload;
}

CompiledGlyph parse_payload(std::span<const std::uint8_t> payload, std::uint32_t indexed_codepoint) {
    std::size_t position = 0;
    CompiledGlyph glyph;
    glyph.codepoint = read_u32(payload, position);
    if (glyph.codepoint != indexed_codepoint) fail("PFC index/payload codepoint mismatch");
    glyph.advance_font_units = read_i32(payload, position);
    const std::uint32_t stroke_count = read_u32(payload, position);
    if (stroke_count > kMaxStrokes) fail("PFC stroke count is unreasonable");
    glyph.strokes.reserve(stroke_count);
    for (std::uint32_t stroke = 0; stroke < stroke_count; ++stroke) {
        const std::uint32_t point_count = read_u32(payload, position);
        if (point_count > kMaxPoints || point_count > (payload.size() - position) / 8) {
            fail("PFC point count is unreasonable");
        }
        CompiledStroke result;
        result.points.reserve(point_count);
        for (std::uint32_t point = 0; point < point_count; ++point) {
            result.points.push_back({read_i32(payload, position), read_i32(payload, position)});
        }
        glyph.strokes.push_back(std::move(result));
    }
    if (position != payload.size()) fail("PFC glyph payload has trailing data");
    return glyph;
}

std::string temporary_name(const std::filesystem::path& path) {
    return path.string() + ".tmp." + std::to_string(static_cast<long long>(::getpid()));
}

void write_all(int fd, std::span<const std::uint8_t> bytes) {
    std::size_t written = 0;
    while (written != bytes.size()) {
        const ssize_t count = ::write(fd, bytes.data() + written, bytes.size() - written);
        if (count < 0) {
            if (errno == EINTR) continue;
            throw std::system_error(errno, std::generic_category(), "write PFC temporary file");
        }
        if (count == 0) fail("short write to PFC temporary file");
        written += static_cast<std::size_t>(count);
    }
}

}  // namespace

void write_pfc(const std::filesystem::path& path, const CompiledFont& font, const PfcMetadata& metadata) {
    if (font.glyphs.size() > kMaxGlyphs) fail("too many glyphs for PFC");
    std::vector<CompiledGlyph> glyphs = font.glyphs;
    std::sort(glyphs.begin(), glyphs.end(), [](const auto& left, const auto& right) { return left.codepoint < right.codepoint; });
    if (std::adjacent_find(glyphs.begin(), glyphs.end(), [](const auto& left, const auto& right) {
            return left.codepoint == right.codepoint;
        }) != glyphs.end()) fail("duplicate PFC codepoint");

    std::vector<std::vector<std::uint8_t>> payloads;
    payloads.reserve(glyphs.size());
    std::size_t data_size = 0;
    for (const CompiledGlyph& glyph : glyphs) {
        payloads.push_back(make_payload(glyph));
        if (payloads.back().size() > std::numeric_limits<std::uint32_t>::max() ||
            data_size > std::numeric_limits<std::size_t>::max() - payloads.back().size()) fail("PFC is too large");
        data_size += payloads.back().size();
    }
    if (glyphs.size() > (std::numeric_limits<std::size_t>::max() - kHeaderSize) / kIndexSize) fail("PFC index is too large");
    const std::size_t payload_offset = kHeaderSize + glyphs.size() * kIndexSize;
    if (payload_offset > std::numeric_limits<std::size_t>::max() - data_size) fail("PFC is too large");

    std::vector<std::uint8_t> bytes;
    bytes.reserve(payload_offset + data_size);
    bytes.insert(bytes.end(), {'P', 'F', 'C', '1'});
    append_u32(bytes, kPfcFormatVersion);
    append_u32(bytes, metadata.algorithm_version);
    bytes.insert(bytes.end(), metadata.font_hash.begin(), metadata.font_hash.end());
    bytes.insert(bytes.end(), metadata.config_hash.begin(), metadata.config_hash.end());
    append_i32(bytes, font.metrics.units_per_em);
    append_i32(bytes, font.metrics.ascender);
    append_i32(bytes, font.metrics.descender);
    append_i32(bytes, font.metrics.line_gap);
    append_u32(bytes, static_cast<std::uint32_t>(glyphs.size()));
    if (bytes.size() != kHeaderSize) fail("internal PFC header size error");

    std::uint64_t offset = static_cast<std::uint64_t>(payload_offset);
    for (std::size_t index = 0; index < glyphs.size(); ++index) {
        append_u32(bytes, glyphs[index].codepoint);
        append_u64(bytes, offset);
        append_u32(bytes, static_cast<std::uint32_t>(payloads[index].size()));
        offset += payloads[index].size();
    }
    for (const auto& payload : payloads) bytes.insert(bytes.end(), payload.begin(), payload.end());

    const std::string temporary = temporary_name(path);
    int fd = ::open(temporary.c_str(), O_WRONLY | O_CREAT | O_TRUNC, 0644);
    if (fd < 0) throw std::system_error(errno, std::generic_category(), "open PFC temporary file");
    try {
        write_all(fd, bytes);
        if (::fsync(fd) != 0) throw std::system_error(errno, std::generic_category(), "fsync PFC temporary file");
        if (::close(fd) != 0) throw std::system_error(errno, std::generic_category(), "close PFC temporary file");
        fd = -1;
        if (::rename(temporary.c_str(), path.c_str()) != 0) {
            throw std::system_error(errno, std::generic_category(), "rename PFC temporary file");
        }
    } catch (...) {
        if (fd >= 0) ::close(fd);
        ::unlink(temporary.c_str());
        throw;
    }
}

PfcFont PfcFont::load(const std::filesystem::path& path) {
    std::ifstream stream(path, std::ios::binary | std::ios::ate);
    if (!stream) throw PfcError("cannot open PFC file");
    const std::streamsize size = stream.tellg();
    if (size < 0) fail("cannot determine PFC size");
    stream.seekg(0);
    std::vector<std::uint8_t> bytes(static_cast<std::size_t>(size));
    if (!bytes.empty()) stream.read(reinterpret_cast<char*>(bytes.data()), size);
    if (!stream && !bytes.empty()) fail("cannot read PFC file");
    if (bytes.size() < kHeaderSize) fail("PFC header is truncated");
    if (!std::equal(bytes.begin(), bytes.begin() + 4, "PFC1")) fail("invalid PFC magic");

    std::span<const std::uint8_t> input(bytes);
    std::size_t position = 4;
    if (read_u32(input, position) != kPfcFormatVersion) fail("unsupported PFC format version");
    PfcFont font;
    font.metadata_.algorithm_version = read_u32(input, position);
    if (position > input.size() - font.metadata_.font_hash.size()) fail("truncated PFC font hash");
    std::copy_n(input.begin() + static_cast<std::ptrdiff_t>(position), font.metadata_.font_hash.size(), font.metadata_.font_hash.begin());
    position += font.metadata_.font_hash.size();
    if (position > input.size() - font.metadata_.config_hash.size()) fail("truncated PFC config hash");
    std::copy_n(input.begin() + static_cast<std::ptrdiff_t>(position), font.metadata_.config_hash.size(), font.metadata_.config_hash.begin());
    position += font.metadata_.config_hash.size();
    font.metrics_.units_per_em = read_i32(input, position);
    font.metrics_.ascender = read_i32(input, position);
    font.metrics_.descender = read_i32(input, position);
    font.metrics_.line_gap = read_i32(input, position);
    const std::uint32_t count = read_u32(input, position);
    if (count > kMaxGlyphs || position != kHeaderSize || count > (input.size() - position) / kIndexSize) fail("invalid PFC glyph index");

    std::uint32_t previous = 0;
    bool have_previous = false;
    font.glyphs_.reserve(count);
    for (std::uint32_t index = 0; index < count; ++index) {
        const std::uint32_t codepoint = read_u32(input, position);
        const std::uint64_t raw_offset = read_u64(input, position);
        const std::uint32_t raw_size = read_u32(input, position);
        if (have_previous && codepoint <= previous) fail("PFC index is not sorted");
        if (raw_offset > std::numeric_limits<std::size_t>::max()) fail("PFC offset is too large");
        const std::size_t offset = static_cast<std::size_t>(raw_offset);
        require_range(offset, raw_size, input.size());
        font.glyphs_.push_back(parse_payload(input.subspan(offset, raw_size), codepoint));
        previous = codepoint;
        have_previous = true;
    }
    return font;
}

const CompiledGlyph* PfcFont::find(std::uint32_t codepoint) const noexcept {
    const auto it = std::lower_bound(glyphs_.begin(), glyphs_.end(), codepoint,
        [](const CompiledGlyph& glyph, std::uint32_t value) { return glyph.codepoint < value; });
    return it != glyphs_.end() && it->codepoint == codepoint ? &*it : nullptr;
}

const CompiledGlyph* PfcFont::lookup(std::uint32_t codepoint) const noexcept {
    if (const CompiledGlyph* glyph = find(codepoint)) return glyph;
    return codepoint == static_cast<std::uint32_t>('?') ? nullptr : find(static_cast<std::uint32_t>('?'));
}

PfcMergeStats merge_special_glyphs(CompiledFont& user, std::span<const PfcFont> specials,
                                 std::span<const std::uint32_t> required_codepoints) {
    PfcMergeStats stats;
    stats.user_glyphs = user.glyphs.size();
    std::map<std::uint32_t, CompiledGlyph> merged;
    for (const auto& glyph : user.glyphs) {
        if (!merged.emplace(glyph.codepoint, glyph).second) fail("duplicate user PFC codepoint");
    }
    for (const auto& special : specials) {
        for (const auto& glyph : special.glyphs()) {
            if (merged.emplace(glyph.codepoint, glyph).second) ++stats.special_glyphs_added;
            else ++stats.duplicate_special_glyphs_skipped;
        }
    }
    const std::set<std::uint32_t> required(required_codepoints.begin(), required_codepoints.end());
    for (auto codepoint : required) if (!merged.contains(codepoint)) ++stats.missing_codepoints;
    user.glyphs.clear();
    user.glyphs.reserve(merged.size());
    for (auto& [codepoint, glyph] : merged) user.glyphs.push_back(std::move(glyph));
    return stats;
}

PfcMergeStats merge_pfc(const std::filesystem::path& user_path,
                       std::span<const std::filesystem::path> special_paths,
                       const std::filesystem::path& output_path,
                       std::span<const std::uint32_t> required_codepoints) {
    const auto source = PfcFont::load(user_path);
    CompiledFont merged{source.metrics(), source.glyphs()};
    std::vector<PfcFont> specials;
    specials.reserve(special_paths.size());
    for (const auto& path : special_paths) specials.push_back(PfcFont::load(path));
    const auto stats = merge_special_glyphs(merged, specials, required_codepoints);
    write_pfc(output_path, merged, source.metadata());
    return stats;
}

}  // namespace fontc
