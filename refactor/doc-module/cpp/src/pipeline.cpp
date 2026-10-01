#include "plotter/doc/pipeline.hpp"

#include "plotter/doc/centerline_path_builder.hpp"
#include "plotter/doc/docx_adapter.hpp"
#include "plotter/doc/gcode_exporter.hpp"
#include "plotter/doc/gcode_analyzer.hpp"
#include "plotter/doc/multipage_gcode_exporter.hpp"
#include "plotter/doc/path_optimizer.hpp"
#include "plotter/doc/pdf_adapter.hpp"
#include "plotter/doc/svg_adapter.hpp"
#include "plotter/doc/text_adapter.hpp"
#include "plotter/doc/text_layout.hpp"

#include <algorithm>
#include <cctype>
#include <stdexcept>
#include <type_traits>
#include <variant>

namespace plotter::doc {
namespace {
Document import_document(const std::filesystem::path& source, const std::filesystem::path& assets) {
    auto extension = source.extension().string();
    std::transform(extension.begin(), extension.end(), extension.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); });
    ImportResult result;
    if (extension == ".txt" || extension == ".md" || extension == ".markdown") result = read_text_document(source);
    else if (extension == ".docx") result = read_docx_document(source, assets);
    else if (extension == ".pdf") result = read_pdf_document(source);
    else if (extension == ".svg") {
        auto svg = read_svg_document(source);
        if (const auto* error = std::get_if<SvgAdapterError>(&svg)) throw std::runtime_error(error->message);
        result = std::move(std::get<Document>(svg));
    } else throw std::invalid_argument("unsupported input format: " + extension);
    if (const auto* error = std::get_if<ImportError>(&result)) throw std::runtime_error(error->message);
    return std::move(std::get<Document>(result));
}

TextAlignment alignment(const std::optional<std::string>& value) {
    if (value == "center") return TextAlignment::center;
    if (value == "right") return TextAlignment::right;
    if (value == "justify") return TextAlignment::justify;
    return TextAlignment::left;
}

std::vector<LayoutParagraph> collect_text(const Document& document, const PipelineOptions& options, ImportStats& stats, bool& needs_font) {
    std::vector<LayoutParagraph> paragraphs;
    for (const SourcePage& page : document.pages) {
        for (const SourceElement& source : page.elements) {
            if (const auto* text = std::get_if<TextElement>(&source)) {
                ++stats.text_elements;
                needs_font = true;
                for (const Paragraph& item : text->paragraphs) {
                    LayoutParagraph paragraph;
                    paragraph.source_element_id = text->id;
                    paragraph.alignment = alignment(item.alignment);
                    paragraph.space_before = item.space_before.value_or(Millimetres{});
                    paragraph.space_after = item.space_after.value_or(Millimetres{});
                    for (const TextRun& run : item.runs) {
                        paragraph.runs.push_back({run.text, {options.font_id, run.style.font_size.value_or(options.font_size), {}, {}}});
                    }
                    if (!paragraph.runs.empty()) paragraphs.push_back(std::move(paragraph));
                }
            } else if (std::holds_alternative<RasterImageElement>(source)) {
                ++stats.raster_images;
                throw std::runtime_error("raster image path building is not implemented");
            } else if (std::holds_alternative<MathElement>(source)) {
                ++stats.math_elements;
                throw std::runtime_error("math path building is not implemented");
            } else if (std::holds_alternative<TableElement>(source)) {
                ++stats.tables;
                throw std::runtime_error("table layout is not implemented");
            } else if (std::holds_alternative<VectorElement>(source)) ++stats.vector_elements;
        }
    }
    return paragraphs;
}

void append_graphics(PathDocument& paths, const SourcePage& source_page) {
    for (const SourceElement& source : source_page.elements) {
        std::visit([&](const auto& element) {
            using Type = std::decay_t<decltype(element)>;
            if constexpr (std::is_same_v<Type, VectorElement>) {
                for (const VectorPath& vector : element.paths) {
                    if (vector.points.size() < 2) continue;
                    Stroke stroke;
                    stroke.id = paths.strokes.size();
                    stroke.points = vector.points;
                    stroke.closed = vector.closed;
                    stroke.element_id = element.id;
                    stroke.element_type = "vector";
                    stroke.source_page_index = element.source_page;
                    stroke.source_path = vector.source_path;
                    stroke.semantic_role = vector.semantic_role;
                    stroke.preserve_order = vector.preserve_order;
                    stroke.z_order = vector.z_order;
                    paths.strokes.push_back(std::move(stroke));
                }
            } else if constexpr (std::is_same_v<Type, LineElement>) {
                Stroke stroke;
                stroke.id = paths.strokes.size(); stroke.points = {element.start, element.end};
                stroke.element_id = element.id; stroke.element_type = "line";
                stroke.source_page_index = element.source_page;
                stroke.semantic_role = element.semantic_role;
                paths.strokes.push_back(std::move(stroke));
            } else if constexpr (std::is_same_v<Type, ArrowElement>) {
                if (element.points.size() < 2) return;
                Stroke stroke;
                stroke.id = paths.strokes.size(); stroke.points = element.points;
                stroke.element_id = element.id; stroke.element_type = "arrow";
                stroke.source_page_index = element.source_page;
                paths.strokes.push_back(std::move(stroke));
            }
        }, source);
    }
}
}  // namespace

PipelineResult run_pipeline(const PipelineOptions& options) {
    PipelineResult result;
    try {
        if (options.input_path.empty() || options.output_directory.empty()) throw std::invalid_argument("input and output paths are required");
        const auto config_report = validate_config(options.config);
        if (!config_report.ok()) throw std::invalid_argument("invalid page or machine configuration: " + config_report.issues.front().code);
        const Document source = import_document(options.input_path, options.output_directory / "assets");
        result.report.import.source_pages = static_cast<std::uint32_t>(source.pages.size());
        bool needs_font = false;
        auto paragraphs = collect_text(source, options, result.report.import, needs_font);
        FontRegistry registry;
        if (needs_font) {
            if (options.pfc_path.empty()) throw std::invalid_argument("text input requires a compiled .pfc font");
            registry.register_pfc({options.font_id, options.font_sha256, options.pfc_path});
        }
        LayoutDocument layout;
        if (needs_font) {
            const auto& page = options.config.page;
            TextLayoutOptions text_options;
            text_options.page_width = page.width; text_options.page_height = page.height;
            text_options.margin_left = page.margins.left; text_options.margin_right = page.margins.right;
            text_options.margin_top = page.margins.top; text_options.margin_bottom = page.margins.bottom;
            layout = TextLayoutEngine{registry}.layout(paragraphs, text_options);
        }
        const std::size_t page_count = std::max(source.pages.size(), layout.pages.size());
        result.job.page_width = options.config.page.width;
        result.job.page_height = options.config.page.height;
        result.job.pages.reserve(page_count);
        for (std::size_t index = 0; index < page_count; ++index) {
            PathDocument paths;
            paths.page_width = options.config.page.width;
            paths.page_height = options.config.page.height;
            if (index < layout.pages.size()) paths = CenterlinePathBuilder{registry}.build(layout.pages[index], paths.page_width, paths.page_height);
            if (index < source.pages.size()) append_graphics(paths, source.pages[index]);
            if (options.optimize_geometry) paths = optimize_paths(paths);
            const auto checks = preflight(paths, options.config);
            if (!checks.ok()) throw std::runtime_error("path preflight failed on page " + std::to_string(index + 1) + ": " + checks.issues.front().code);
            PageJob page;
            page.page_index = static_cast<std::uint32_t>(index);
            page.page_number = static_cast<std::uint32_t>(index + 1);
            page.paths = std::move(paths);
            if (index < layout.pages.size()) page.source_element_ids = layout.pages[index].source_element_ids;
            result.job.pages.push_back(std::move(page));
        }
        const ImportStats import_stats = result.report.import;
        result.report = make_pipeline_report(result.job, std::string(artifact_level_name(options.artifact_level)));
        result.report.import = import_stats;
        result.report.layout.pages = static_cast<std::uint32_t>(layout.pages.size());
        for (const auto& page : layout.pages) {
            result.report.layout.lines += page.line_count;
            result.report.layout.glyphs += static_cast<std::uint32_t>(page.glyphs.size());
        }
        const auto gcode = generate_job_gcode(result.job, options.config.machine);
        static_cast<void>(analyze_gcode(gcode, options.config.machine));
        result.gcode_path = options.output_directory / "output.gcode";
        write_gcode_atomic(gcode, result.gcode_path);
        result.artifacts = write_artifacts(result.job, result.report, {options.output_directory, options.artifact_level, true});
        result.ok = true;
    } catch (const std::exception& error) {
        result.error = error.what();
        try { if (!options.output_directory.empty()) write_error_artifacts(options.output_directory, result.error, options.artifact_level); }
        catch (const std::exception&) { }
    }
    return result;
}
}  // namespace plotter::doc
