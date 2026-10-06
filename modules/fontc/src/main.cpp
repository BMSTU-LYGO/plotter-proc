#include "fontc/cli.hpp"
#include "fontc/compiler.hpp"

#include <iostream>

int main(int argc, char** argv) {
    const fontc::ParseResult parsed = fontc::parse_command_line(argc, argv);
    if (!parsed.message.empty()) {
        std::ostream& stream = parsed.exit_code == 0 ? std::cout : std::cerr;
        stream << parsed.message;
        if (parsed.message.back() != '\n') stream << '\n';
    }
    if (!parsed.options.has_value()) return parsed.exit_code;

    try {
        const fontc::CompilationReport report = fontc::compile_font(*parsed.options);
        std::cout << "fontc: wrote " << parsed.options->output_path << " ("
                  << report.compiled_glyphs << " glyphs";
        if (report.skipped_missing_glyphs != 0) {
            std::cout << ", " << report.skipped_missing_glyphs << " missing codepoints skipped";
        }
        std::cout << ")\n";
        return 0;
    } catch (const std::exception& error) {
        std::cerr << "fontc: " << error.what() << std::endl;
        return 1;
    }
}

