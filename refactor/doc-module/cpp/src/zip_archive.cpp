#include "plotter/doc/zip_archive.hpp"

#include <algorithm>
#include <fstream>
#include <iterator>
#include <stdexcept>

#include <zlib.h>

namespace plotter::doc {
namespace {

void require_range(std::size_t offset, std::size_t length, std::size_t size) {
    if (offset > size || length > size - offset)
        throw std::runtime_error("ZIP structure exceeds archive bounds");
}

std::uint16_t u16(const std::vector<std::uint8_t>& bytes, std::size_t offset) {
    require_range(offset, 2, bytes.size());
    return static_cast<std::uint16_t>(bytes[offset] | (bytes[offset + 1] << 8U));
}

std::uint32_t u32(const std::vector<std::uint8_t>& bytes, std::size_t offset) {
    require_range(offset, 4, bytes.size());
    return static_cast<std::uint32_t>(bytes[offset]) |
           (static_cast<std::uint32_t>(bytes[offset + 1]) << 8U) |
           (static_cast<std::uint32_t>(bytes[offset + 2]) << 16U) |
           (static_cast<std::uint32_t>(bytes[offset + 3]) << 24U);
}

bool safe_name(std::string_view name) {
    if (name.empty() || name.front() == '/' || name.find('\\') != name.npos ||
        name.find('\0') != name.npos) return false;
    std::size_t start = 0;
    while (start < name.size()) {
        const auto end = name.find('/', start);
        if (name.substr(start, end == name.npos ? name.npos : end - start) == "..") return false;
        if (end == name.npos) break;
        start = end + 1;
    }
    return true;
}

}  // namespace

ZipArchive ZipArchive::open(const std::filesystem::path& path, ZipLimits limits) {
    std::ifstream file(path, std::ios::binary);
    if (!file) throw std::runtime_error("Cannot open ZIP archive: " + path.string());
    file.seekg(0, std::ios::end);
    const auto length = file.tellg();
    if (length < 0 || static_cast<std::uint64_t>(length) > limits.max_archive_bytes)
        throw std::runtime_error("ZIP archive exceeds size limit");
    file.seekg(0);
    ZipArchive result;
    result.limits_ = limits;
    result.data_.assign(std::istreambuf_iterator<char>(file), std::istreambuf_iterator<char>());
    const auto& bytes = result.data_;
    if (bytes.size() < 22) throw std::runtime_error("ZIP end record is missing");
    const std::size_t first = bytes.size() > 65'557 ? bytes.size() - 65'557 : 0;
    std::size_t eocd = bytes.size();
    for (std::size_t offset = bytes.size() - 22;; --offset) {
        if (u32(bytes, offset) == 0x06054b50U &&
            offset + 22U + u16(bytes, offset + 20) == bytes.size()) {
            eocd = offset;
            break;
        }
        if (offset == first) break;
    }
    if (eocd == bytes.size()) throw std::runtime_error("ZIP end record is missing");
    if (u16(bytes, eocd + 4) != 0 || u16(bytes, eocd + 6) != 0 ||
        u16(bytes, eocd + 8) != u16(bytes, eocd + 10))
        throw std::runtime_error("Multi-disk ZIP is unsupported");
    const auto count = u16(bytes, eocd + 10);
    const auto central_size = u32(bytes, eocd + 12);
    const auto central_offset = u32(bytes, eocd + 16);
    if (count == 0xffffU || central_size == 0xffffffffU || central_offset == 0xffffffffU)
        throw std::runtime_error("ZIP64 is unsupported");
    if (count > limits.max_entries) throw std::runtime_error("ZIP entry limit exceeded");
    require_range(central_offset, central_size, bytes.size());
    std::size_t cursor = central_offset;
    std::size_t total_uncompressed = 0;
    result.entries_.reserve(count);
    for (std::size_t index = 0; index < count; ++index) {
        require_range(cursor, 46, bytes.size());
        if (u32(bytes, cursor) != 0x02014b50U)
            throw std::runtime_error("Invalid ZIP central directory entry");
        const auto flags = u16(bytes, cursor + 8);
        if ((flags & 1U) != 0) throw std::runtime_error("Encrypted ZIP entry is unsupported");
        const auto method = u16(bytes, cursor + 10);
        const auto crc = u32(bytes, cursor + 16);
        const auto compressed = u32(bytes, cursor + 20);
        const auto uncompressed = u32(bytes, cursor + 24);
        const auto name_length = u16(bytes, cursor + 28);
        const auto extra_length = u16(bytes, cursor + 30);
        const auto comment_length = u16(bytes, cursor + 32);
        const auto local_offset = u32(bytes, cursor + 42);
        const std::size_t record_length = 46U + name_length + extra_length + comment_length;
        require_range(cursor, record_length, bytes.size());
        std::string name(reinterpret_cast<const char*>(bytes.data() + cursor + 46), name_length);
        if (!safe_name(name)) throw std::runtime_error("Unsafe ZIP entry name");
        if (uncompressed > limits.max_entry_bytes ||
            uncompressed > limits.max_total_uncompressed_bytes - total_uncompressed)
            throw std::runtime_error("ZIP uncompressed size limit exceeded");
        total_uncompressed += uncompressed;
        result.entries_.push_back({std::move(name), method, crc, compressed,
                                   uncompressed, local_offset});
        cursor += record_length;
    }
    if (cursor != static_cast<std::size_t>(central_offset) + central_size)
        throw std::runtime_error("ZIP central directory size mismatch");
    return result;
}

bool ZipArchive::contains(std::string_view name) const {
    return std::any_of(entries_.begin(), entries_.end(), [name](const ZipEntry& entry) {
        return entry.name == name;
    });
}

std::string ZipArchive::read_text(std::string_view name) const {
    const auto found = std::find_if(entries_.begin(), entries_.end(), [name](const ZipEntry& entry) {
        return entry.name == name;
    });
    if (found == entries_.end()) throw std::runtime_error("ZIP entry is missing: " + std::string(name));
    const auto& entry = *found;
    const auto offset = static_cast<std::size_t>(entry.local_offset);
    require_range(offset, 30, data_.size());
    if (u32(data_, offset) != 0x04034b50U) throw std::runtime_error("Invalid ZIP local header");
    if (u16(data_, offset + 8) != entry.method) throw std::runtime_error("ZIP compression method mismatch");
    const std::size_t start = offset + 30U + u16(data_, offset + 26) + u16(data_, offset + 28);
    require_range(start, entry.compressed_size, data_.size());
    std::string output(entry.uncompressed_size, '\0');
    if (entry.method == 0) {
        if (entry.compressed_size != entry.uncompressed_size)
            throw std::runtime_error("Stored ZIP entry length mismatch");
        std::copy_n(data_.begin() + static_cast<std::ptrdiff_t>(start),
                    entry.uncompressed_size, output.begin());
    } else if (entry.method == 8) {
        z_stream stream{};
        stream.next_in = const_cast<Bytef*>(reinterpret_cast<const Bytef*>(data_.data() + start));
        stream.avail_in = entry.compressed_size;
        stream.next_out = reinterpret_cast<Bytef*>(output.data());
        stream.avail_out = entry.uncompressed_size;
        if (inflateInit2(&stream, -MAX_WBITS) != Z_OK)
            throw std::runtime_error("Cannot initialize ZIP inflater");
        const int status = inflate(&stream, Z_FINISH);
        inflateEnd(&stream);
        if (status != Z_STREAM_END || stream.total_out != entry.uncompressed_size)
            throw std::runtime_error("Invalid compressed ZIP entry");
    } else {
        throw std::runtime_error("Unsupported ZIP compression method");
    }
    const auto checksum = crc32(0L, reinterpret_cast<const Bytef*>(output.data()),
                                static_cast<uInt>(output.size()));
    if (checksum != entry.crc32) throw std::runtime_error("ZIP entry CRC mismatch");
    return output;
}

}  // namespace plotter::doc
