#include "fontc/cli.hpp"

#include <charconv>
#include <limits>
#include <string_view>

namespace fontc {
namespace {

[[nodiscard]] bool parse_positive_int(std::string_view text, int& value) {
    int parsed = 0;
    const auto result = std::from_chars(text.data(), text.data() + text.size(), parsed);
    if (result.ec != std::errc{} || result.ptr != text.data() + text.size() || parsed <= 0) {
        return false;
    }
    value = parsed;
    return true;
}

[[nodiscard]] bool parse_threads(std::string_view text, std::size_t& value) {
    if (text == "auto") {
        value = 0;
        return true;
    }
    int parsed = 0;
    if (!parse_positive_int(text, parsed)) {
        return false;
    }
    value = static_cast<std::size_t>(parsed);
    return true;
}

[[nodiscard]] ParseResult error(std::string message) {
    return {std::nullopt, std::move(message), 2};
}

}  // namespace

std::string usage() {
    return
        "Usage: fontc <font.ttf> --chars-file <chars.txt> --output <font.pfc> [options]\n"
        "\n"
        "Options:\n"
        "  --resolution <px/em>  Raster resolution (default: 1024)\n"
        "  --threads <n|auto>     Worker count (default: auto)\n"
        "  --force                Replace an existing output file\n"
        "  --debug-dir <path>     Write development artifacts\n"
        "  -h, --help             Show this help\n";
}

ParseResult parse_command_line(int argc, char** argv) {
    if (argc <= 1) {
        return error(usage());
    }
    if (std::string_view(argv[1]) == "--help" || std::string_view(argv[1]) == "-h") {
        return {std::nullopt, usage(), 0};
    }

    CompilerOptions options;
    options.font_path = argv[1];
    for (int index = 2; index < argc; ++index) {
        const std::string_view argument = argv[index];
        const auto next = [&]() -> const char* {
            return ++index < argc ? argv[index] : nullptr;
        };

        if (argument == "--chars-file") {
            const char* value = next();
            if (value == nullptr) return error("--chars-file requires a path\n" + usage());
            options.chars_file = value;
        } else if (argument == "--output") {
            const char* value = next();
            if (value == nullptr) return error("--output requires a path\n" + usage());
            options.output_path = value;
        } else if (argument == "--resolution") {
            const char* value = next();
            if (value == nullptr || !parse_positive_int(value, options.resolution)) {
                return error("--resolution must be a positive integer");
            }
        } else if (argument == "--threads") {
            const char* value = next();
            if (value == nullptr || !parse_threads(value, options.threads)) {
                return error("--threads must be 'auto' or a positive integer");
            }
        } else if (argument == "--force") {
            options.force = true;
        } else if (argument == "--debug-dir") {
            const char* value = next();
            if (value == nullptr) return error("--debug-dir requires a path");
            options.debug_dir = std::filesystem::path(value);
        } else if (argument == "--help" || argument == "-h") {
            return {std::nullopt, usage(), 0};
        } else {
            return error("Unknown option: " + std::string(argument) + "\n" + usage());
        }
    }

    if (options.font_path.empty()) return error("A TTF path is required");
    if (options.chars_file.empty()) return error("--chars-file is required");
    if (options.output_path.empty()) return error("--output is required");
    return {std::move(options), {}, 0};
}

}  // namespace fontc

