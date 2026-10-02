#include "plotter/doc/pipeline.hpp"

#include "plotter/doc/centerline_path_builder.hpp"
#include "plotter/doc/outline_path_builder.hpp"
#include "plotter/doc/docx_adapter.hpp"
#include "plotter/doc/document_codec.hpp"
#include "plotter/doc/stage_cache.hpp"
#include "plotter/doc/gcode_exporter.hpp"
#include "plotter/doc/gcode_analyzer.hpp"
#include "plotter/doc/multipage_gcode_exporter.hpp"
#include "plotter/doc/path_optimizer.hpp"
#include "plotter/doc/raster_path_builder.hpp"
#include "plotter/doc/table_path_builder.hpp"
#include "plotter/doc/math_path_builder.hpp"
#include "plotter/doc/svg_adapter.hpp"
#include "plotter/doc/text_adapter.hpp"
#include "plotter/doc/text_layout.hpp"
#include "plotter/doc/thread_pool.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <sys/resource.h>
#include <cctype>
#include <stdexcept>
#include <optional>
#include <unordered_set>
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
                    double semantic_scale = 1.0;
                    if (item.semantic_role == "title") semantic_scale = 1.35;
                    else if (item.semantic_role == "heading_1") semantic_scale = 1.25;
                    else if (item.semantic_role == "heading_2") semantic_scale = 1.15;
                    else if (item.semantic_role == "heading_3") semantic_scale = 1.08;
                    double source_size_total = 0.0;
                    std::size_t source_size_count = 0;
                    if (document.metadata.source_format == "docx") {
                        for (const TextRun& run : item.runs) {
                            if (run.style.font_size && run.text.find_first_not_of(" \t\r\n") != std::string::npos) {
                                source_size_total += run.style.font_size->value;
                                ++source_size_count;
                            }
                        }
                        if (source_size_count)
                            semantic_scale = source_size_total / static_cast<double>(source_size_count) / 12.0;
                        semantic_scale = std::clamp(semantic_scale, 0.8, 1.6);
                    }
                    for (const TextRun& run : item.runs) {
                        if (options.font_mode == FontMode::centerline && (run.style.bold || run.style.italic))
                            throw std::runtime_error("bold and italic need outline font mode");
                        LayoutTextStyle style;
                        style.font_id = options.font_id;
                        style.font_size = document.metadata.source_format == "docx"
                            ? Points{options.font_size.value * semantic_scale}
                            : run.style.font_size.value_or(options.font_size);
                        style.underline = run.style.underline;
                        style.strike = run.style.strike;
                        style.bold = run.style.bold;
                        style.italic = run.style.italic;
                        style.baseline_shift = run.style.baseline_shift;
                        paragraph.runs.push_back({run.text, std::move(style)});
                    }
                    if (paragraph.runs.size() == 1U) {
                        const std::string& raw = paragraph.runs.front().utf8;
                        if (raw.size() >= 4U && raw.starts_with("$$") && raw.ends_with("$$")) {
                            paragraph.display_math = true;
                            const LayoutTextStyle base = paragraph.runs.front().style;
                            const std::string expression = raw.substr(2U, raw.size() - 4U);
                            paragraph.runs.clear();
                            std::string normal;
                            const auto flush = [&]() {
                                if (!normal.empty()) { paragraph.runs.push_back({std::move(normal), base}); normal.clear(); }
                            };
                            for (std::size_t offset = 0; offset < expression.size();) {
                                const char character = expression[offset];
                                if (character == '\\') throw std::runtime_error("display math command needs a structural renderer");
                                if (character == '^' || character == '_') {
                                    flush();
                                    const bool superscript = character == '^';
                                    ++offset;
                                    if (offset == expression.size()) throw std::runtime_error("display math shift has no operand");
                                    std::string operand;
                                    if (expression[offset] == '{') {
                                        const auto end = expression.find('}', offset + 1U);
                                        if (end == std::string::npos || expression.find('{', offset + 1U) < end)
                                            throw std::runtime_error("nested display math grouping is unsupported");
                                        operand = expression.substr(offset + 1U, end - offset - 1U);
                                        offset = end + 1U;
                                    } else operand = expression.substr(offset++, 1U);
                                    LayoutTextStyle shifted = base;
                                    shifted.font_size.value *= 0.65;
                                    shifted.baseline_shift = superscript ? "superscript" : "subscript";
                                    paragraph.runs.push_back({std::move(operand), std::move(shifted)});
                                } else { normal += character; ++offset; }
                            }
                            flush();
                        }
                    }
                    if (!paragraph.runs.empty()) paragraphs.push_back(std::move(paragraph));
                }
            } else if (const auto* image = std::get_if<RasterImageElement>(&source)) {
                ++stats.raster_images;
                if (document.metadata.source_format == "docx" && image->anchor_type == "flow" && !image->bounds) {
                    const auto& paper = options.config.page;
                    const Rect content = page.content_bounds.value_or(Rect{{0.0}, {0.0},
                        page.width.value_or(paper.width), page.height.value_or(paper.height)});
                    const double target_width = paper.width.value - paper.margins.left.value - paper.margins.right.value;
                    const double target_height = paper.height.value - paper.margins.top.value - paper.margins.bottom.value - (options.page_numbers ? 8.0 : 0.0);
                    const double scale = std::min({target_width / content.width.value,
                        target_height / content.height.value, options.preserve_max_upscale});
                    const double width = image->displayed_width.value_or(Millimetres{image->width.value * 25.4 / 96.0}).value * scale;
                    const double height = image->displayed_height.value_or(Millimetres{image->height.value * 25.4 / 96.0}).value * scale;
                    LayoutParagraph marker;
                    marker.flow_image = FlowImage{image->id, {width}, {height}};
                    paragraphs.push_back(std::move(marker));
                }
            }
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
                     const FontRegistry& fonts, const PipelineOptions& options,
                     const std::unordered_set<std::string>& placed_flow_images) {
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
                if (placed_flow_images.contains(element.id)) return;
                RasterPathOptions raster_options; raster_options.mode = RasterTraceMode::outline;
                raster_options.maximum_strokes = 10000U;
                append_built(RasterPathBuilder{raster_options}.build(element, paths.page_width, paths.page_height));
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
                    RasterPathOptions raster_options; raster_options.mode = RasterTraceMode::outline;
                    raster_options.maximum_strokes = 10000U;
                    auto raster = RasterPathBuilder{raster_options}.build(visual, paths.page_width, paths.page_height);
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
void position_hybrid_vectors(PathDocument& mapped, const PathDocument& original,
                             const SourcePage& source_page, const PageTransform& transform,
                             const Rect& target_content) {
    for (const SourceElement& element : source_page.elements) {
        const auto* vector = std::get_if<VectorElement>(&element);
        if (!vector || vector->paths.empty()) continue;
        double min_x = std::numeric_limits<double>::infinity(), min_y = min_x;
        double max_x = -min_x, max_y = -min_x;
        for (const auto& path : vector->paths) for (const auto point : path.points) {
            min_x = std::min(min_x, point.x.value); min_y = std::min(min_y, point.y.value);
            max_x = std::max(max_x, point.x.value); max_y = std::max(max_y, point.y.value);
        }
        if (!std::isfinite(min_x) || max_x <= min_x || max_y <= min_y) continue;
        const double width = (max_x - min_x) * transform.scale;
        const double height = (max_y - min_y) * transform.scale;
        const Rect bounds = vector->bounds.value_or(Rect{{min_x}, {min_y}, {max_x - min_x}, {max_y - min_y}});
        const double desired_x = transform.offset_x.value + bounds.x.value * transform.scale;
        const double desired_y = transform.offset_y.value + bounds.y.value * transform.scale;
        const double left = std::clamp(desired_x, target_content.x.value, target_content.right().value - width);
        const double top = std::clamp(desired_y, target_content.y.value, target_content.bottom().value - height);
        for (std::size_t index = 0; index < mapped.strokes.size(); ++index) {
            Stroke& stroke = mapped.strokes[index];
            if (stroke.element_type != "vector" || stroke.element_id != vector->id) continue;
            const Stroke& input = original.strokes[index];
            for (std::size_t point = 0; point < stroke.points.size(); ++point) {
                stroke.points[point].x = {left + (input.points[point].x.value - min_x) * transform.scale};
                stroke.points[point].y = {top + (input.points[point].y.value - min_y) * transform.scale};
            }
        }
    }
}

}  // namespace

PipelineResult run_pipeline_impl(const PipelineOptions& options, const Document* provided) {
    PipelineResult result;
    try {
        const auto pipeline_start = std::chrono::steady_clock::now();
        auto elapsed_ms = [](auto begin, auto end) { return std::chrono::duration<double, std::milli>(end - begin).count(); };
        if ((!provided && options.input_path.empty()) || options.output_directory.empty())
            throw std::invalid_argument("input and output paths are required");
        const auto config_report = validate_config(options.config);
        if (!config_report.ok()) throw std::invalid_argument("invalid page or machine configuration: " + config_report.issues.front().code);
        std::optional<Document> imported;
        CacheStats cache_stats;
        if (!provided) {
            std::optional<StageCache> cache;
            std::string cache_key;
            if (options.use_cache) {
                try {
                    const auto cache_root = options.cache_directory.empty()
                        ? options.output_directory / ".cppdoc-cache" : options.cache_directory;
                    cache.emplace(StageCacheOptions{cache_root});
                    const std::string settings = options.input_path.extension().string();
                    cache_key = StageCache::import_fingerprint(options.input_path, "document-import-v1", settings);
                    auto cached = cache->load_typed<Document, DocumentCodec>("read_document", cache_key);
                    if (cached.hit) {
                        imported = std::move(cached.value);
                        imported->source_path = options.input_path.string();
                        ++cache_stats.hits;
                    } else ++cache_stats.misses;
                } catch (const std::exception&) {
                    cache.reset();
                }
            }
            if (!imported) {
                imported = import_document(options.input_path, options.output_directory / "assets");
                if (cache && DocumentCodec::cacheable(*imported)) {
                    try { cache->store_typed<Document, DocumentCodec>("read_document", cache_key, *imported); }
                    catch (const std::exception&) { /* cache write never invalidates a successful import */ }
                }
            }
        }
        const auto imported_at = std::chrono::steady_clock::now();
        const Document& source = provided ? *provided : *imported;
        result.report.import.source_pages = static_cast<std::uint32_t>(source.pages.size());
        bool needs_font = false;
        auto paragraphs = collect_text(source, options, result.report.import, needs_font);
        if (options.page_numbers) needs_font = true;
        FontRegistry registry;
        if (needs_font) {
            if (options.font_mode == FontMode::centerline) {
                if (options.pfc_path.empty() || options.pfc_path.extension() != ".pfc")
                    throw std::invalid_argument("centerline mode requires a compiled .pfc font");
                registry.register_pfc({options.font_id, options.font_sha256, options.pfc_path});
                if (!options.fallback_font_path.empty()) {
                    if (options.fallback_font_path.extension() != ".pfc")
                        throw std::invalid_argument("centerline fallback font must be .pfc");
                    registry.register_pfc({"fallback", {}, options.fallback_font_path});
                    registry.set_fallback_font("fallback");
                }
            } else {
                const auto extension = options.pfc_path.extension().string();
                if (extension != ".ttf" && extension != ".otf")
                    throw std::invalid_argument("outline mode requires a .ttf or .otf font");
                registry.register_outline_font({options.font_id, options.font_sha256, options.pfc_path});
                if (!options.fallback_font_path.empty()) {
                    const auto fallback_extension = options.fallback_font_path.extension().string();
                    if (fallback_extension != ".ttf" && fallback_extension != ".otf")
                        throw std::invalid_argument("outline fallback font must be .ttf or .otf");
                    registry.register_outline_font({"fallback", {}, options.fallback_font_path});
                    registry.set_fallback_font("fallback");
                }
            }
        }
        LayoutDocument layout;
        if (!paragraphs.empty()) {
            const auto& page = options.config.page;
            TextLayoutOptions text_options;
            text_options.page_width = page.width; text_options.page_height = page.height;
            text_options.margin_left = page.margins.left; text_options.margin_right = page.margins.right;
            text_options.margin_top = page.margins.top; text_options.margin_bottom = page.margins.bottom;
            text_options.line_gap = page.line_gap;
            if (options.page_numbers) text_options.footer_reserve = {8.0};
            layout = TextLayoutEngine{registry}.layout(paragraphs, text_options);
        }
        if (options.page_numbers) {
            const auto old_size = layout.pages.size();
            layout.pages.resize(std::max(layout.pages.size(), source.pages.size()));
            for (std::size_t index = old_size; index < layout.pages.size(); ++index)
                layout.pages[index].page_index = static_cast<std::uint32_t>(index);
            append_page_numbers(layout, registry, {true, options.config.page.width,
                options.config.page.height, {4.5}, {9.0}, options.font_id});
        }
        const auto layout_at = std::chrono::steady_clock::now();
        const SourcePageTransformMode layout_mode = options.document_layout == SourcePageTransformMode::automatic
            ? ((source.metadata.source_format == "txt" || source.metadata.source_format == "markdown")
                ? SourcePageTransformMode::reflow
                : (source.metadata.source_format == "docx" ? SourcePageTransformMode::preserve : SourcePageTransformMode::hybrid))
            : options.document_layout;
        std::unordered_set<std::string> placed_flow_images;
        for (const LayoutPage& page : layout.pages)
            for (const auto& placement : page.flow_images) placed_flow_images.insert(placement.first);
        const std::size_t page_count = std::max(source.pages.size(), layout.pages.size());
        result.job.page_width = options.config.page.width;
        result.job.page_height = options.config.page.height;
        result.job.pages.reserve(page_count);
        const auto build_page = [&](std::size_t index) -> PageJob {
            PathDocument paths;
            paths.page_width = options.config.page.width;
            paths.page_height = options.config.page.height;
            if (index < layout.pages.size()) {
                if (options.font_mode == FontMode::centerline)
                    paths = CenterlinePathBuilder{registry}.build(layout.pages[index], paths.page_width, paths.page_height, options.join_words);
                else paths = OutlinePathBuilder{registry}.build(layout.pages[index], paths.page_width, paths.page_height);
                if (!layout.pages[index].math_glyphs.empty()) {
                    LayoutPage math_page;
                    math_page.page_index = static_cast<std::uint32_t>(index);
                    math_page.glyphs = layout.pages[index].math_glyphs;
                    PathDocument math_paths;
                    if (options.font_mode == FontMode::centerline)
                        math_paths = CenterlinePathBuilder{registry}.build(math_page, paths.page_width, paths.page_height);
                    else math_paths = OutlinePathBuilder{registry}.build(math_page, paths.page_width, paths.page_height);
                    for (auto& stroke : math_paths.strokes) {
                        const auto glyph = std::find_if(math_page.glyphs.begin(), math_page.glyphs.end(),
                            [&](const PositionedGlyph& item) { return static_cast<std::int64_t>(item.glyph_index) == stroke.glyph_index; });
                        if (glyph != math_page.glyphs.end() && glyph->source_element_id)
                            stroke.element_id = *glyph->source_element_id + "-formula-001";
                        stroke.id = paths.strokes.size();
                        stroke.element_type = "latex";
                        stroke.semantic_role = "latex-centerline";
                        stroke.glyph_index.reset();
                        stroke.character.reset();
                        stroke.source_path.reset();
                        stroke.segment_types = {"display-math"};
                        paths.strokes.push_back(std::move(stroke));
                    }
                }
                for (auto stroke : layout.pages[index].graphic_strokes) {
                    stroke.id = paths.strokes.size();
                    paths.strokes.push_back(std::move(stroke));
                }
                for (const auto& [image_id, bounds] : layout.pages[index].flow_images) {
                    for (const SourcePage& source_page : source.pages) {
                        const auto found = std::find_if(source_page.elements.begin(), source_page.elements.end(),
                            [&](const SourceElement& item) {
                                const auto* image = std::get_if<RasterImageElement>(&item);
                                return image && image->id == image_id;
                            });
                        if (found == source_page.elements.end()) continue;
                        RasterImageElement image = std::get<RasterImageElement>(*found);
                        image.bounds = bounds;
                        RasterPathOptions raster_options; raster_options.mode = RasterTraceMode::outline;
                        raster_options.maximum_strokes = 10000U;
                        auto raster = RasterPathBuilder{raster_options}.build(image, paths.page_width, paths.page_height);
                        for (auto& stroke : raster.strokes) {
                            stroke.id = paths.strokes.size();
                            paths.strokes.push_back(std::move(stroke));
                        }
                        break;
                    }
                }
            }
            if (index < source.pages.size()) {
                const auto& input_page = source.pages[index];
                const Millimetres source_width = input_page.width.value_or(options.config.page.width);
                const Millimetres source_height = input_page.height.value_or(options.config.page.height);
                PathDocument graphics;
                graphics.page_width = source_width;
                graphics.page_height = source_height;
                append_graphics(graphics, input_page, registry, options, placed_flow_images);
                if (!graphics.strokes.empty()) {
                    const auto& paper = options.config.page;
                    const Rect target_content{paper.margins.left, paper.margins.top,
                        {paper.width.value - paper.margins.left.value - paper.margins.right.value},
                        {paper.height.value - paper.margins.top.value - paper.margins.bottom.value - (options.page_numbers ? 8.0 : 0.0)}};
                    const Rect source_content = input_page.content_bounds.value_or(Rect{{0.0}, {0.0}, source_width, source_height});
                    const SourcePageTransformOptions transform_options{
                        layout_mode, source_width, source_height, source_content, paper.width, paper.height,
                        target_content, options.preserve_max_upscale, false};
                    auto mapped = transform_source_page_paths(graphics, transform_options);
                    if (const auto* error = std::get_if<SourcePageTransformError>(&mapped))
                        throw std::runtime_error(error->code + ": " + error->message);
                    auto transformed = std::move(std::get<TransformedSourcePage>(mapped));
                    if (layout_mode == SourcePageTransformMode::hybrid)
                        position_hybrid_vectors(transformed.paths, graphics, input_page, transformed.transform, target_content);
                    graphics = std::move(transformed.paths);
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
            return page;
        };
        bool independent_pages = options.font_mode == FontMode::outline;
        if (independent_pages) for (const SourcePage& page : source.pages)
            for (const SourceElement& element : page.elements)
                if (std::holds_alternative<TableElement>(element) || std::holds_alternative<MathElement>(element)) independent_pages = false;
        if (independent_pages && page_count > 1 && ThreadPool::resolve_thread_count(options.thread_count) > 1) {
            ThreadPool pool{{options.thread_count, 1024}};
            result.job.pages = pool.map_indexed(page_count, build_page);
        } else {
            for (std::size_t index = 0; index < page_count; ++index) result.job.pages.push_back(build_page(index));
        }
        const auto paths_at = std::chrono::steady_clock::now();
        const ImportStats import_stats = result.report.import;
        result.report = make_pipeline_report(result.job, std::string(artifact_level_name(options.artifact_level)));
        result.report.import = import_stats;
        result.report.cache = cache_stats;
        result.report.timings.import_ms = elapsed_ms(pipeline_start, imported_at);
        result.report.timings.layout_ms = elapsed_ms(imported_at, layout_at);
        result.report.timings.path_and_geometry_ms = elapsed_ms(layout_at, paths_at);
        result.report.layout.pages = static_cast<std::uint32_t>(layout.pages.size());
        for (const auto& page : layout.pages) {
            result.report.layout.lines += page.line_count;
            result.report.layout.glyphs += static_cast<std::uint32_t>(page.glyphs.size());
        }
        const auto gcode = generate_job_gcode(result.job, options.config.machine);
        static_cast<void>(analyze_gcode(gcode, options.config.machine));
        result.gcode_path = options.output_directory / "output.gcode";
        write_gcode_atomic(gcode, result.gcode_path);
        result.report.timings.gcode_ms = elapsed_ms(paths_at, std::chrono::steady_clock::now());
        struct rusage usage{};
        if (::getrusage(RUSAGE_SELF, &usage) == 0) result.report.timings.peak_rss_kib = static_cast<std::uint64_t>(usage.ru_maxrss);
        result.artifacts = write_artifacts(result.job, result.report, {options.output_directory, options.artifact_level, options.write_preview});
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
