#pragma once

#include <cstddef>
#include <filesystem>
#include <optional>
#include <string>

namespace fontc {

struct CompilerOptions {
    std::filesystem::path font_path;
    std::filesystem::path chars_file;
    std::filesystem::path output_path;
    int resolution = 1024;
    std::size_t threads = 0;  // 0 means hardware_concurrency.
    bool force = false;
    std::optional<std::filesystem::path> debug_dir;
};

struct ParseResult {
    std::optional<CompilerOptions> options;
    std::string message;
    int exit_code = 0;
};

[[nodiscard]] ParseResult parse_command_line(int argc, char** argv);
[[nodiscard]] std::string usage();

}  // namespace fontc

