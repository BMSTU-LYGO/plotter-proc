#include "plotter/doc/pipeline.hpp"

#include "plotter/doc/centerline_path_builder.hpp"
#include "plotter/doc/outline_path_builder.hpp"
#include "plotter/doc/docx_adapter.hpp"
#include "plotter/doc/gcode_exporter.hpp"
#include "plotter/doc/gcode_analyzer.hpp"
#include "plotter/doc/multipage_gcode_exporter.hpp"
#include "plotter/doc/path_optimizer.hpp"
#include "plotter/doc/pdf_adapter.hpp"
#include "plotter/doc/raster_path_builder.hpp"
#include "plotter/doc/table_path_builder.hpp"
#include "plotter/doc/math_path_builder.hpp"
#include "plotter/doc/svg_adapter.hpp"
#include "plotter/doc/text_adapter.hpp"
#include "plotter/doc/text_layout.hpp"

#include <algorithm>
#include <cctype>
#include <stdexcept>
#include <optional>
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
        bool first_paragraph_on_page = true;
        for (const SourceElement& source : page.elements) {
            if (const auto* text = std::get_if<TextElement>(&source)) {
                ++stats.text_elements;
                needs_font = true;
                for (const Paragraph& item : text->paragraphs) {
                    LayoutParagraph paragraph;
                    paragraph.source_element_id = text->id;
                    paragraph.page_break_before = page.source_page > 0 && first_paragraph_on_page;
                    first_paragraph_on_page = false;
                    paragraph.alignment = alignment(item.alignment);
                    paragraph.space_before = item.space_before.value_or(Millimetres{});
                    paragraph.space_after = item.space_after.value_or(Millimetres{2.5});
                    paragraph.first_line_indent = item.first_line_indent.value_or(Millimetres{});
                    paragraph.hanging_indent = item.hanging_indent.value_or(Millimetres{});
                    paragraph.left_indent = item.left_indent.value_or(Millimetres{});
                    paragraph.right_indent = item.right_indent.value_or(Millimetres{});
                    paragraph.line_spacing = item.line_spacing.value_or(1.25);
                    paragraph.tab_stops = item.tab_stops;
                    for (const TextRun& run : item.runs) {
                        if (run.style.bold || run.style.italic || run.style.baseline_shift)
                            throw std::runtime_error("bold, italic, and baseline shift are not implemented");
                        LayoutTextStyle style;
                        style.font_id = options.font_id;
                        style.font_size = run.style.font_size.value_or(options.font_size);
                        style.underline = run.style.underline;
                        style.strike = run.style.strike;
                        paragraph.runs.push_back({run.text, std::move(style)});
                    }
                    if (!paragraph.runs.empty()) paragraphs.push_back(std::move(paragraph));
                }
            } else if (std::holds_alternative<RasterImageElement>(source)) ++stats.raster_images;
            else if (const auto* math = std::get_if<MathElement>(&source)) {
                ++stats.math_elements;
                if (!math->visual_image_path) needs_font = true;
            } else if (const auto* table = std::get_if<TableElement>(&source)) {
                ++stats.tables;
                for (const auto& cell : table->cells)
                    for (const auto& paragraph : cell.paragraphs)
                        for (const auto& run : paragraph.runs)
                            if (!run.text.empty()) needs_font = true;
            }
            else if (std::holds_alternative<VectorElement>(source)) ++stats.vector_elements;
        }
    }
    return paragraphs;
}

void append_graphics(PathDocument& paths, const SourcePage& source_page,
                     const FontRegistry& fonts, const PipelineOptions& options) {
    auto append_built = [&](PathDocument built) {
        for (auto& stroke : built.strokes) {
            stroke.id = paths.strokes.size();
            paths.strokes.push_back(std::move(stroke));
        }
        paths.warnings.insert(paths.warnings.end(), built.warnings.begin(), built.warnings.end());
    };
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
            } else if constexpr (std::is_same_v<Type, RasterImageElement>) {
                append_built(RasterPathBuilder{}.build(element, paths.page_width, paths.page_height));
            } else if constexpr (std::is_same_v<Type, TableElement>) {
                if (fonts.contains(options.font_id))
                    append_built(TablePathBuilder{fonts, options.font_id, options.font_size}.build(element, paths.page_width, paths.page_height));
                else append_built(TablePathBuilder{}.build(element, paths.page_width, paths.page_height));
            } else if constexpr (std::is_same_v<Type, MathElement>) {
                if (element.visual_image_path) {
                    if (!element.bounds) throw std::runtime_error("visual math has no placement bounds");
                    RasterImageElement visual;
                    visual.id = element.id;
                    visual.source_page = element.source_page;
                    visual.image_path = *element.visual_image_path;
                    visual.bounds = element.bounds;
                    auto raster = RasterPathBuilder{}.build(visual, paths.page_width, paths.page_height);
                    for (auto& stroke : raster.strokes) {
                        stroke.element_type = "math";
                        stroke.semantic_role = "math-visual";
                    }
                    append_built(std::move(raster));
                } else {
                    auto built = MathPathBuilder{fonts}.build(element, {options.font_id, options.font_size, paths.page_width, paths.page_height});
                    if (const auto* error = std::get_if<MathPathBuildError>(&built))
                        throw std::runtime_error(error->code + ": " + error->message);
                    append_built(std::move(std::get<PathDocument>(built)));
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

PipelineResult run_pipeline_impl(const PipelineOptions& options, const Document* provided) {
    PipelineResult result;
    try {
        if ((!provided && options.input_path.empty()) || options.output_directory.empty())
            throw std::invalid_argument("input and output paths are required");
        const auto config_report = validate_config(options.config);
        if (!config_report.ok()) throw std::invalid_argument("invalid page or machine configuration: " + config_report.issues.front().code);
        std::optional<Document> imported;
        if (!provided) imported = import_document(options.input_path, options.output_directory / "assets");
        const Document& source = provided ? *provided : *imported;
        result.report.import.source_pages = static_cast<std::uint32_t>(source.pages.size());
        bool needs_font = false;
        auto paragraphs = collect_text(source, options, result.report.import, needs_font);
        if (options.page_numbers && paragraphs.empty())
            throw std::invalid_argument("page numbers require text content and a font");
        FontRegistry registry;
        if (needs_font) {
            if (options.font_mode == FontMode::centerline) {
                if (options.pfc_path.empty() || options.pfc_path.extension() != ".pfc")
                    throw std::invalid_argument("centerline mode requires a compiled .pfc font");
                registry.register_pfc({options.font_id, options.font_sha256, options.pfc_path});
            } else {
                const auto extension = options.pfc_path.extension().string();
                if (extension != ".ttf" && extension != ".otf")
                    throw std::invalid_argument("outline mode requires a .ttf or .otf font");
                registry.register_outline_font({options.font_id, options.font_sha256, options.pfc_path});
            }
        }
        LayoutDocument layout;
        if (!paragraphs.empty()) {
            const auto& page = options.config.page;
            TextLayoutOptions text_options;
            text_options.page_width = page.width; text_options.page_height = page.height;
            text_options.margin_left = page.margins.left; text_options.margin_right = page.margins.right;
            text_options.margin_top = page.margins.top; text_options.margin_bottom = page.margins.bottom;
            if (options.page_numbers) text_options.footer_reserve = {8.0};
            layout = TextLayoutEngine{registry}.layout(paragraphs, text_options);
            append_page_numbers(layout, registry, {options.page_numbers, page.width, page.height, {4.5}, {9.0}, options.font_id});
        }
        const std::size_t page_count = std::max(source.pages.size(), layout.pages.size());
        result.job.page_width = options.config.page.width;
        result.job.page_height = options.config.page.height;
        result.job.pages.reserve(page_count);
        for (std::size_t index = 0; index < page_count; ++index) {
            PathDocument paths;
            paths.page_width = options.config.page.width;
            paths.page_height = options.config.page.height;
            if (index < layout.pages.size()) {
                if (options.font_mode == FontMode::centerline)
                    paths = CenterlinePathBuilder{registry}.build(layout.pages[index], paths.page_width, paths.page_height);
                else paths = OutlinePathBuilder{options.pfc_path}.build(layout.pages[index], paths.page_width, paths.page_height);
                for (auto stroke : layout.pages[index].graphic_strokes) {
                    stroke.id = paths.strokes.size();
                    paths.strokes.push_back(std::move(stroke));
                }
            }
            if (index < source.pages.size()) {
                const auto& input_page = source.pages[index];
                const Millimetres source_width = input_page.width.value_or(options.config.page.width);
                const Millimetres source_height = input_page.height.value_or(options.config.page.height);
                PathDocument graphics;
                graphics.page_width = source_width;
                graphics.page_height = source_height;
                append_graphics(graphics, input_page, registry, options);
                if (!graphics.strokes.empty()) {
                    const auto& paper = options.config.page;
                    const Rect target_content{paper.margins.left, paper.margins.top,
                        {paper.width.value - paper.margins.left.value - paper.margins.right.value},
                        {paper.height.value - paper.margins.top.value - paper.margins.bottom.value}};
                    const SourcePageTransformOptions transform_options{
                        options.document_layout, source_width, source_height,
                        {{0.0}, {0.0}, source_width, source_height}, paper.width, paper.height,
                        target_content, options.preserve_max_upscale, false};
                    auto mapped = transform_source_page_paths(graphics, transform_options);
                    if (const auto* error = std::get_if<SourcePageTransformError>(&mapped))
                        throw std::runtime_error(error->code + ": " + error->message);
                    graphics = std::move(std::get<TransformedSourcePage>(mapped).paths);
                    for (auto& stroke : graphics.strokes) {
                        stroke.id = paths.strokes.size();
                        paths.strokes.push_back(std::move(stroke));
                    }
                }
                paths.warnings.insert(paths.warnings.end(), graphics.warnings.begin(), graphics.warnings.end());
            }
            if (options.optimize_geometry) paths = optimize_paths(paths);
            if (options.handwriting.enabled) {
                auto settings = options.handwriting;
                settings.keep_outs = options.config.machine.keep_out;
                auto transformed = apply_handwriting(paths, settings);
                if (const auto* error = std::get_if<HandwritingError>(&transformed))
                    throw std::runtime_error(error->code + ": " + error->message);
                paths = std::move(std::get<PathDocument>(transformed));
            }
            if (options.simplify_geometry) {
                const PathSimplificationOptions settings{{0.001}, {0.04},
                    {options.font_mode == FontMode::outline ? 0.05 : 0.06}};
                paths = simplify_path_document(paths, settings);
            }
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
PipelineResult run_pipeline(const PipelineOptions& options) { return run_pipeline_impl(options, nullptr); }
PipelineResult run_pipeline(const Document& document, const PipelineOptions& options) {
    return run_pipeline_impl(options, &document);
}
}  // namespace plotter::doc
