#include "plotter/doc/stage_cache.hpp"

#include <filesystem>
#include <fstream>
#include <stdexcept>

namespace { void require(bool value, const char* message) { if (!value) throw std::runtime_error(message); } }

int main() {
    const auto root = std::filesystem::temp_directory_path() / "plotter-stage-cache-smoke";
    std::error_code ignored;
    std::filesystem::remove_all(root, ignored);
    plotter::doc::StageCache cache({root, 3, 1024});
    const std::string fingerprint = plotter::doc::StageCache::fingerprint("layout", "input-sha", "layout-v2", "{\"font\":\"abc\"}");
    const std::vector<std::uint8_t> payload{0, 1, 2, 255};
    cache.store("layout", fingerprint, payload);
    const auto hit = cache.load("layout", fingerprint);
    require(hit.hit && !hit.corrupt && hit.payload == payload, "versioned opaque payload must round-trip");
    require(fingerprint == plotter::doc::StageCache::fingerprint("layout", "input-sha", "layout-v2", "{\"font\":\"abc\"}"), "fingerprint must be deterministic");
    require(fingerprint != plotter::doc::StageCache::fingerprint("layout", "input-sha", "layout-v3", "{\"font\":\"abc\"}"), "fingerprint must bind declared stage inputs");
    { std::ofstream broken(cache.entry_path("layout", fingerprint), std::ios::binary | std::ios::trunc); broken << "broken"; }
    const auto corrupt = cache.load("layout", fingerprint);
    require(!corrupt.hit && corrupt.corrupt, "corrupted cache envelopes must become misses");
    plotter::doc::StageCache incompatible({root, 4, 1024});
    cache.store("layout", fingerprint, payload);
    const auto version_miss = incompatible.load("layout", fingerprint);
    require(!version_miss.hit && version_miss.corrupt, "unsupported cache versions must become misses");
    std::filesystem::remove_all(root, ignored);
}
