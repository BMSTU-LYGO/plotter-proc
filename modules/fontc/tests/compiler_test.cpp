#include "fontc/compiler.hpp"

#include <cassert>
#include <filesystem>
#include <fstream>
#include <stdexcept>

int main() {
    const auto path = std::filesystem::temp_directory_path() / "fontc-compiler-corpus.txt";
    {
        std::ofstream stream(path, std::ios::binary);
        stream << "B?A\xD0\x90\xF0\x9F\x98\x80" "A";
    }
    const auto codepoints = fontc::read_codepoints_file(path);
    std::filesystem::remove(path);
    assert((codepoints == std::vector<std::uint32_t>{
        static_cast<std::uint32_t>('?'), static_cast<std::uint32_t>('A'),
        static_cast<std::uint32_t>('B'), 0x410U, 0x1F600U}));

    const auto invalid = std::filesystem::temp_directory_path() / "fontc-compiler-invalid.txt";
    {
        std::ofstream stream(invalid, std::ios::binary);
        stream << "\xC0\xAF";
    }
    bool rejected = false;
    try {
        (void)fontc::read_codepoints_file(invalid);
    } catch (const std::runtime_error&) {
        rejected = true;
    }
    std::filesystem::remove(invalid);
    assert(rejected);
}
