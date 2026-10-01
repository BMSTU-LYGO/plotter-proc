#include "plotter/doc/pipeline.hpp"

#include <iostream>
#include <string_view>

int main(int argc, char** argv) {
    using namespace plotter::doc;
    PipelineOptions options;
    options.config.page = {"A5", {148.0}, {210.0}, {{15.0}, {15.0}, {15.0}, {15.0}}};
    options.config.machine.workspace = {{0.0}, {320.0}, {0.0}, {320.0}};
    for (int i = 1; i < argc; ++i) {
        const std::string_view argument{argv[i]};
        const auto next = [&]() -> std::string_view { return ++i < argc ? std::string_view{argv[i]} : std::string_view{}; };
        if (argument == "--input") options.input_path = next();
        else if (argument == "--output") options.output_directory = next();
        else if (argument == "--font") options.pfc_path = next();
        else if (argument == "--page") {
            const auto page = next();
            if (page == "A4") options.config.page = {"A4", {210.0}, {297.0}, {{15.0}, {15.0}, {15.0}, {15.0}}};
            else if (page != "A5") { std::cerr << "unsupported page: " << page << '\n'; return 2; }
        } else if (argument == "--size") {
            const auto size = next();
            if (size == "small") options.font_size = {9.0};
            else if (size == "normal") options.font_size = {12.0};
            else if (size == "large") options.font_size = {16.0};
            else { std::cerr << "unsupported size: " << size << '\n'; return 2; }
        } else if (argument == "--artifact-level") {
            const auto level = next();
            if (level == "minimal") options.artifact_level = ArtifactLevel::minimal;
            else if (level == "normal") options.artifact_level = ArtifactLevel::normal;
            else if (level == "debug") options.artifact_level = ArtifactLevel::debug;
            else if (level == "audit") options.artifact_level = ArtifactLevel::audit;
            else { std::cerr << "unsupported artifact level: " << level << '\n'; return 2; }
        } else if (argument == "--optimize") options.optimize_geometry = true;
        else if (argument == "--help") {
            std::cout << "usage: plotter-doc --input <file> --output <directory> [--font <font.pfc>] [--page A5|A4] [--size small|normal|large] [--artifact-level minimal|normal|debug|audit] [--optimize]\n";
            return 0;
        } else { std::cerr << "unknown option: " << argument << '\n'; return 2; }
    }
    if (options.input_path.empty() || options.output_directory.empty()) {
        std::cerr << "--input and --output are required\n";
        return 2;
    }
    const PipelineResult result = run_pipeline(options);
    if (!result.ok) { std::cerr << result.error << '\n'; return 1; }
    std::cout << result.gcode_path << '\n';
    return 0;
}
