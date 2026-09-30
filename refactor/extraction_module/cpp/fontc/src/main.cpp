#include "fontc/cli.hpp"

#include <iostream>

int main(int argc, char** argv) {
    const fontc::ParseResult parsed = fontc::parse_command_line(argc, argv);
    if (!parsed.message.empty()) {
        std::ostream& stream = parsed.exit_code == 0 ? std::cout : std::cerr;
        stream << parsed.message;
        if (parsed.message.back() != '\n') stream << '\n';
    }
    if (!parsed.options.has_value()) return parsed.exit_code;

    std::cerr << "fontc: compiler stages are not available yet\n";
    return 2;
}

