#pragma once

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <string_view>
#include <vector>

namespace plotter::doc {

struct ZipLimits final {
    std::size_t max_archive_bytes{256'000'000};
    std::size_t max_entries{50'000};
    std::size_t max_entry_bytes{64'000'000};
    std::size_t max_total_uncompressed_bytes{256'000'000};
};

struct ZipEntry final {
    std::string name;
    std::uint16_t method{};
    std::uint32_t crc32{};
    std::uint32_t compressed_size{};
    std::uint32_t uncompressed_size{};
    std::uint32_t local_offset{};
};

class ZipArchive final {
public:
    [[nodiscard]] static ZipArchive open(const std::filesystem::path& path,
                                         ZipLimits limits = {});
    [[nodiscard]] bool contains(std::string_view name) const;
    [[nodiscard]] std::string read_text(std::string_view name) const;
    [[nodiscard]] const std::vector<ZipEntry>& entries() const noexcept { return entries_; }

private:
    std::vector<std::uint8_t> data_;
    std::vector<ZipEntry> entries_;
    ZipLimits limits_{};
};

}  // namespace plotter::doc
