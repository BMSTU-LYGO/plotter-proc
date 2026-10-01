#include "plotter/doc/pdf_adapter.hpp"

#include <algorithm>
#include <array>
#include <cerrno>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstring>
#include <filesystem>
#include <fstream>
#include <optional>
#include <regex>
#include <string>
#include <string_view>
#include <sys/types.h>
#include <sys/wait.h>
#include <unistd.h>
#include <utility>
#include <vector>
#include <limits>

namespace plotter::doc {
namespace {

struct Word final {
    double x_min{};
    double y_min{};
    double x_max{};
    double y_max{};
    std::string text;
};

struct PdfPage final {
    double width{};
    double height{};
    std::vector<Word> words;
};

using CommandResult = std::variant<std::string, ImportError>;

[[nodiscard]] CommandResult run_pdftotext_bbox(const std::filesystem::path& source_path) {
    int output_pipe[2]{};
    if (::pipe(output_pipe) != 0) {
        return ImportError{"Cannot create pipe for PDF reader: " + std::string{std::strerror(errno)}};
    }
    const pid_t child = ::fork();
    if (child < 0) {
        const auto message = std::string{std::strerror(errno)};
        ::close(output_pipe[0]);
        ::close(output_pipe[1]);
        return ImportError{"Cannot start PDF reader: " + message};
    }
    if (child == 0) {
        ::close(output_pipe[0]);
        if (::dup2(output_pipe[1], STDOUT_FILENO) < 0) { _exit(126); }
        ::close(output_pipe[1]);
        const std::string input = source_path.string();
        const char* const arguments[] = {"pdftotext", "-bbox", "-enc", "UTF-8", input.c_str(), "-", nullptr};
        ::execv("/usr/bin/pdftotext", const_cast<char* const*>(arguments));
        _exit(127);
    }
    ::close(output_pipe[1]);
    std::string output;
    std::array<char, 8192> buffer{};
    for (;;) {
        const ssize_t count = ::read(output_pipe[0], buffer.data(), buffer.size());
        if (count > 0) { output.append(buffer.data(), static_cast<std::size_t>(count)); continue; }
        if (count == 0) { break; }
        if (errno == EINTR) { continue; }
        const auto message = std::string{std::strerror(errno)};
        ::close(output_pipe[0]);
        int ignored{};
        (void)::waitpid(child, &ignored, 0);
        return ImportError{"Cannot read PDF text layer: " + message};
    }
    ::close(output_pipe[0]);
    int status{};
    while (::waitpid(child, &status, 0) < 0) {
        if (errno != EINTR) { return ImportError{"Cannot wait for PDF reader: " + std::string{std::strerror(errno)}}; }
    }
    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) {
        return ImportError{"Cannot read PDF document with pdftotext: " + source_path.string()};
    }
    return output;
}

[[nodiscard]] std::optional<double> number_attribute(const std::string& attributes, const char* name) {
    const std::regex expression{std::string{"\\b"} + name + R"re(="([^"]+)")re"};
    std::smatch match;
    if (!std::regex_search(attributes, match, expression)) { return std::nullopt; }
    try {
        std::size_t consumed{};
        const double value = std::stod(match[1].str(), &consumed);
        if (consumed != static_cast<std::size_t>(match[1].length()) || !std::isfinite(value)) { return std::nullopt; }
        return value;
    } catch (const std::exception&) { return std::nullopt; }
}

[[nodiscard]] std::string xml_unescape(std::string value) {
    const std::array<std::pair<std::string_view, std::string_view>, 5> named{{
        {"&amp;", "&"}, {"&lt;", "<"}, {"&gt;", ">"}, {"&quot;", "\""}, {"&apos;", "'"},
    }};
    for (const auto& [encoded, decoded] : named) {
        std::size_t position{};
        while ((position = value.find(encoded, position)) != std::string::npos) {
            value.replace(position, encoded.size(), decoded);
            position += decoded.size();
        }
    }
    static const std::regex numeric{R"(&#(x[0-9A-Fa-f]+|[0-9]+);)"};
    std::string result;
    std::size_t cursor{};
    for (std::sregex_iterator it{value.begin(), value.end(), numeric}, end; it != end; ++it) {
        const auto& match = *it;
        result.append(value, cursor, static_cast<std::size_t>(match.position()) - cursor);
        const std::string token = match[1].str();
        try {
            const auto codepoint = static_cast<std::uint32_t>(std::stoul(token, nullptr, token.front() == 'x' ? 16 : 10));
            if (codepoint <= 0x7FU) { result.push_back(static_cast<char>(codepoint)); }
            else if (codepoint <= 0x7FFU) { result.append({static_cast<char>(0xC0U | (codepoint >> 6U)), static_cast<char>(0x80U | (codepoint & 0x3FU))}); }
            else if (codepoint <= 0xFFFFU && !(codepoint >= 0xD800U && codepoint <= 0xDFFFU)) { result.append({static_cast<char>(0xE0U | (codepoint >> 12U)), static_cast<char>(0x80U | ((codepoint >> 6U) & 0x3FU)), static_cast<char>(0x80U | (codepoint & 0x3FU))}); }
            else if (codepoint <= 0x10FFFFU) { result.append({static_cast<char>(0xF0U | (codepoint >> 18U)), static_cast<char>(0x80U | ((codepoint >> 12U) & 0x3FU)), static_cast<char>(0x80U | ((codepoint >> 6U) & 0x3FU)), static_cast<char>(0x80U | (codepoint & 0x3FU))}); }
            else { result.append(match.str()); }
        } catch (const std::exception&) { result.append(match.str()); }
        cursor = static_cast<std::size_t>(match.position() + match.length());
    }
    result.append(value, cursor, std::string::npos);
    return result;
}

[[nodiscard]] std::vector<PdfPage> parse_bbox_xhtml(const std::string& xhtml) {
    std::vector<PdfPage> pages;
    std::size_t page_pos = 0;
    while ((page_pos = xhtml.find("<page ", page_pos)) != std::string::npos) {
        const auto opening_end = xhtml.find('>', page_pos);
        if (opening_end == std::string::npos) break;
        const auto closing = xhtml.find("</page>", opening_end + 1);
        if (closing == std::string::npos) break;
        const std::string attributes = xhtml.substr(page_pos + 5, opening_end - page_pos - 5);
        page_pos = closing + 7;
        const auto width = number_attribute(attributes, "width");
        const auto height = number_attribute(attributes, "height");
        if (!width || !height || *width <= 0.0 || *height <= 0.0) continue;
        PdfPage page{*width, *height, {}};
        std::size_t word_pos = opening_end + 1;
        while ((word_pos = xhtml.find("<word ", word_pos)) != std::string::npos && word_pos < closing) {
            const auto word_open_end = xhtml.find('>', word_pos);
            if (word_open_end == std::string::npos || word_open_end >= closing) break;
            const auto word_close = xhtml.find("</word>", word_open_end + 1);
            if (word_close == std::string::npos || word_close > closing) break;
            const std::string word_attributes = xhtml.substr(word_pos + 5, word_open_end - word_pos - 5);
            word_pos = word_close + 7;
            const auto x_min = number_attribute(word_attributes, "xMin");
            const auto y_min = number_attribute(word_attributes, "yMin");
            const auto x_max = number_attribute(word_attributes, "xMax");
            const auto y_max = number_attribute(word_attributes, "yMax");
            if (!x_min || !y_min || !x_max || !y_max || *x_max < *x_min || *y_max < *y_min) continue;
            const auto text = xml_unescape(xhtml.substr(word_open_end + 1, word_close - word_open_end - 1));
            if (!text.empty()) page.words.push_back({*x_min, *y_min, *x_max, *y_max, text});
        }
        pages.push_back(std::move(page));
    }
    return pages;
}

[[nodiscard]] Rect rect_mm(const double x_min, const double y_min, const double x_max, const double y_max) {
    return {{x_min * kMillimetresPerPoint}, {y_min * kMillimetresPerPoint},
            {(x_max - x_min) * kMillimetresPerPoint}, {(y_max - y_min) * kMillimetresPerPoint}};
}

[[nodiscard]] bool line_is_math(const std::vector<Word>& line) {
    for (const Word& word : line) if (word.text.find_first_of("=+−×÷*/^<>") != std::string::npos) return true;
    return false;
}

void append_page_text(SourcePage& output, std::vector<Word> words) {
    std::sort(words.begin(), words.end(), [](const Word& left, const Word& right) {
        if (std::abs(left.y_min - right.y_min) > 0.5) return left.y_min < right.y_min;
        return left.x_min < right.x_min;
    });
    std::vector<std::vector<Word>> lines;
    for (Word& word : words) {
        if (lines.empty() || std::abs(lines.back().front().y_min - word.y_min) > 0.5) lines.emplace_back();
        lines.back().push_back(std::move(word));
    }
    std::uint32_t order{};
    TextElement block;
    double block_xmin{}, block_ymin{}, block_xmax{}, block_ymax{}, previous_ymax{};
    const auto flush = [&]() {
        if (block.paragraphs.empty()) return;
        block.bounds = rect_mm(block_xmin, block_ymin, block_xmax, block_ymax);
        output.elements.emplace_back(std::move(block));
        block = TextElement{};
    };
    for (auto& line : lines) {
        std::sort(line.begin(), line.end(), [](const Word& left, const Word& right) { return left.x_min < right.x_min; });
        if (line_is_math(line)) { flush(); continue; }
        double xmin = line.front().x_min, ymin = line.front().y_min, xmax = line.front().x_max, ymax = line.front().y_max;
        Paragraph paragraph; paragraph.semantic_role = "body";
        for (std::size_t index = 0; index < line.size(); ++index) {
            const Word& word = line[index]; xmin = std::min(xmin, word.x_min); ymin = std::min(ymin, word.y_min); xmax = std::max(xmax, word.x_max); ymax = std::max(ymax, word.y_max);
            TextRun run; run.text = (index == 0 ? std::string{} : std::string{" "}) + word.text; run.bounds = rect_mm(word.x_min, word.y_min, word.x_max, word.y_max); paragraph.runs.push_back(std::move(run));
        }
        paragraph.bounds = rect_mm(xmin, ymin, xmax, ymax);
        const bool contiguous = !block.paragraphs.empty() && ymin - previous_ymax <= (previous_ymax - block.paragraphs.back().bounds->y.value / kMillimetresPerPoint) * 0.8;
        if (!contiguous) {
            flush();
            block.id = "page-" + std::to_string(output.source_page + 1) + "-text-" + std::to_string(order + 1);
            block.source_order = order++; block.source_page = output.source_page;
            block_xmin = xmin; block_ymin = ymin; block_xmax = xmax; block_ymax = ymax;
        } else { block_xmin = std::min(block_xmin, xmin); block_ymin = std::min(block_ymin, ymin); block_xmax = std::max(block_xmax, xmax); block_ymax = std::max(block_ymax, ymax); }
        previous_ymax = ymax;
        block.paragraphs.push_back(std::move(paragraph));
    }
    flush();
}
}  // namespace

[[nodiscard]] CommandResult run_pdftocairo_svg(const std::filesystem::path&, std::uint32_t);
[[nodiscard]] std::filesystem::path render_pdf_page(const std::filesystem::path&, std::uint32_t);
void append_vectors(SourcePage&, const std::string&, std::uint32_t&);
void append_math(SourcePage&, const std::vector<Word>&, std::uint32_t&);
void append_grid_table(SourcePage&, std::uint32_t&);

ImportResult read_pdf_document(const std::filesystem::path& source_path) {
    if (!std::filesystem::is_regular_file(source_path)) {
        return ImportError{"Input PDF document does not exist: " + source_path.string()};
    }
    if (source_path.extension() != ".pdf" && source_path.extension() != ".PDF") {
        return ImportError{"Unsupported PDF format: " + source_path.string()};
    }
    auto output = run_pdftotext_bbox(source_path);
    if (const auto* error = std::get_if<ImportError>(&output)) { return *error; }
    const auto pages = parse_bbox_xhtml(std::get<std::string>(output));
    if (pages.empty()) { return ImportError{"PDF reader returned no page geometry: " + source_path.string()}; }
    Document document;
    document.source_path = source_path.string();
    document.metadata.source_format = "pdf";
    document.warnings = {};
    document.pages.reserve(pages.size());
    for (std::size_t page_index = 0; page_index < pages.size(); ++page_index) {
        const PdfPage& input_page = pages[page_index];
        SourcePage page;
        page.source_page = static_cast<std::uint32_t>(page_index);
        page.width = Millimetres{input_page.width * kMillimetresPerPoint};
        page.height = Millimetres{input_page.height * kMillimetresPerPoint};
        append_page_text(page, input_page.words);
        std::uint32_t visual_order = static_cast<std::uint32_t>(page.elements.size());
        if (auto svg = run_pdftocairo_svg(source_path, static_cast<std::uint32_t>(page_index + 1)); std::holds_alternative<std::string>(svg)) {
            append_vectors(page, std::get<std::string>(svg), visual_order);
        } else {
            document.warnings.push_back("pdf_vector_not_imported: pdftocairo SVG conversion failed on page " + std::to_string(page_index + 1));
        }
        append_grid_table(page, visual_order);
        const std::filesystem::path rendered = render_pdf_page(source_path, static_cast<std::uint32_t>(page_index + 1));
        if (!rendered.empty()) {
            RasterImageElement image; image.id = "page-" + std::to_string(page_index + 1) + "-raster-1"; image.source_order = visual_order++; image.source_page = static_cast<std::uint32_t>(page_index); image.image_path = rendered.string(); image.width = Pixels{static_cast<double>(std::llround(input_page.width * 150.0 / 72.0))}; image.height = Pixels{static_cast<double>(std::llround(input_page.height * 150.0 / 72.0))}; image.displayed_width = page.width; image.displayed_height = page.height; image.bounds = Rect{{0.0}, {0.0}, *page.width, *page.height}; image.anchor_type = "absolute"; image.behind_text = true; page.elements.emplace_back(std::move(image));
        } else { document.warnings.push_back("pdf_image_page_raster_not_imported: pdftocairo PNG conversion failed on page " + std::to_string(page_index + 1)); }
        append_math(page, input_page.words, visual_order);
        std::uint32_t source_order = 0;
        const auto renumber = [&](SourceElement& element) {
            std::visit([&](auto& value) {
                const std::string category = [&]() -> std::string {
                    using Type = std::decay_t<decltype(value)>;
                    if constexpr (std::is_same_v<Type, TextElement>) return "text";
                    if constexpr (std::is_same_v<Type, RasterImageElement>) return "image";
                    if constexpr (std::is_same_v<Type, VectorElement>) return "vector";
                    if constexpr (std::is_same_v<Type, MathElement>) return "math";
                    if constexpr (std::is_same_v<Type, TableElement>) return "table";
                    if constexpr (std::is_same_v<Type, LineElement>) return "line";
                    return "arrow";
                }();
                value.source_order = source_order++;
                const auto padded = [](std::size_t number) {
                    const auto digits = std::to_string(number);
                    return std::string(3 - std::min<std::size_t>(3, digits.size()), '0') + digits;
                };
                value.id = "page-" + padded(page_index + 1) + "-" + category + "-" + padded(value.source_order + 1);
            }, element);
        };
        for (auto& element : page.elements) if (std::holds_alternative<MathElement>(element)) renumber(element);
        for (auto& element : page.elements) if (!std::holds_alternative<MathElement>(element)) renumber(element);
        if (!page.elements.empty()) {
            std::optional<Rect> first;
            for (const auto& element : page.elements) {
                first = std::visit([](const auto& value) { return value.bounds; }, element);
                if (first) break;
            }
            if (!first) { document.pages.push_back(std::move(page)); continue; }
            Rect bounds = *first;
            for (const SourceElement& element : page.elements) {
                const std::optional<Rect>* maybe = std::visit([](const auto& value) { return &value.bounds; }, element);
                if (!*maybe) continue;
                const Rect& rect = **maybe;
                const double right = std::max(bounds.right().value, rect.right().value);
                const double bottom = std::max(bounds.bottom().value, rect.bottom().value);
                bounds.x.value = std::min(bounds.x.value, rect.x.value);
                bounds.y.value = std::min(bounds.y.value, rect.y.value);
                bounds.width.value = right - bounds.x.value;
                bounds.height.value = bottom - bounds.y.value;
            }
            page.content_bounds = bounds;
        }
        document.pages.push_back(std::move(page));
    }
    return document;
}


// Poppler writes SVG in page coordinates (points). We only take stroked paths:
// glyph outlines are deliberately skipped so they remain text, not fake vectors.
[[nodiscard]] CommandResult run_pdftocairo_svg(const std::filesystem::path& source_path, std::uint32_t page) {
    int output_pipe[2]{};
    if (::pipe(output_pipe) != 0) return ImportError{"Cannot create pipe for PDF SVG reader"};
    const pid_t child = ::fork();
    if (child < 0) { ::close(output_pipe[0]); ::close(output_pipe[1]); return ImportError{"Cannot start PDF SVG reader"}; }
    if (child == 0) {
        ::close(output_pipe[0]); if (::dup2(output_pipe[1], STDOUT_FILENO) < 0) _exit(126); ::close(output_pipe[1]);
        const std::string input = source_path.string(), first = std::to_string(page), last = first;
        const char* const args[] = {"pdftocairo", "-svg", "-f", first.c_str(), "-l", last.c_str(), input.c_str(), "-", nullptr};
        ::execv("/usr/bin/pdftocairo", const_cast<char* const*>(args)); _exit(127);
    }
    ::close(output_pipe[1]); std::string output; std::array<char, 8192> buffer{};
    for (;;) { const ssize_t count = ::read(output_pipe[0], buffer.data(), buffer.size()); if (count > 0) { output.append(buffer.data(), static_cast<std::size_t>(count)); continue; } if (count == 0) break; if (errno != EINTR) { ::close(output_pipe[0]); return ImportError{"Cannot read PDF SVG"}; } }
    ::close(output_pipe[0]); int status{}; while (::waitpid(child, &status, 0) < 0 && errno == EINTR) {};
    if (!WIFEXITED(status) || WEXITSTATUS(status) != 0) return ImportError{"Cannot convert PDF page to SVG"};
    return output;
}

[[nodiscard]] std::filesystem::path render_pdf_page(const std::filesystem::path& source_path, std::uint32_t page) {
    std::error_code error;
    const auto directory = std::filesystem::temp_directory_path(error) / "plotter-pdf-renders";
    if (error) return {};
    if (!std::filesystem::create_directories(directory, error) && error) return {};
    const auto prefix = directory / ("page-" + std::to_string(::getpid()) + "-" + std::to_string(page));
    const std::string input = source_path.string(), page_text = std::to_string(page), output = prefix.string();
    const pid_t child = ::fork(); if (child < 0) return {};
    if (child == 0) { const char* const args[] = {"pdftocairo", "-png", "-singlefile", "-r", "150", "-f", page_text.c_str(), "-l", page_text.c_str(), input.c_str(), output.c_str(), nullptr}; ::execv("/usr/bin/pdftocairo", const_cast<char* const*>(args)); _exit(127); }
    int status{}; while (::waitpid(child, &status, 0) < 0 && errno == EINTR) {}
    const auto file = prefix.string() + ".png";
    return WIFEXITED(status) && WEXITSTATUS(status) == 0 && std::filesystem::is_regular_file(file) ? std::filesystem::path{file} : std::filesystem::path{};
}

[[nodiscard]] std::vector<Point> svg_line_points(const std::string& d, const std::string& transform) {
    static const std::regex number{R"([-+]?(?:[0-9]*\.)?[0-9]+(?:[eE][-+]?[0-9]+)?)"};
    std::vector<double> v, m;
    for (std::sregex_iterator it{d.begin(), d.end(), number}, end; it != end; ++it) v.push_back(std::stod((*it).str()));
    for (std::sregex_iterator it{transform.begin(), transform.end(), number}, end; it != end; ++it) m.push_back(std::stod((*it).str()));
    if (v.size() < 4) return {};
    const double a = m.size() == 6 ? m[0] : 1.0, b = m.size() == 6 ? m[1] : 0.0, c = m.size() == 6 ? m[2] : 0.0, dm = m.size() == 6 ? m[3] : 1.0, e = m.size() == 6 ? m[4] : 0.0, f = m.size() == 6 ? m[5] : 0.0;
    std::vector<Point> result;
    for (std::size_t i = 0; i + 1 < v.size(); i += 2) result.push_back({Millimetres{(a * v[i] + c * v[i + 1] + e) * kMillimetresPerPoint}, Millimetres{(b * v[i] + dm * v[i + 1] + f) * kMillimetresPerPoint}});
    return result;
}

void append_vectors(SourcePage& page, const std::string& svg, std::uint32_t& order) {
    static const std::regex path{R"re(<path\b([^>]*)/>)re"}, d_attr{R"re(\bd="([^"]+)")re"}, transform_attr{R"re(\btransform="matrix\(([^)]*)\)")re"};
    for (std::sregex_iterator it{svg.begin(), svg.end(), path}, end; it != end; ++it) {
        const std::string attributes = (*it)[1].str(); if (attributes.find("stroke=") == std::string::npos) continue;
        std::smatch dm, tm; if (!std::regex_search(attributes, dm, d_attr)) continue;
        const std::string transform = std::regex_search(attributes, tm, transform_attr) ? tm[1].str() : std::string{};
        auto points = svg_line_points(dm[1].str(), transform); if (points.size() < 2) continue;
        double xmin = points[0].x.value, xmax = xmin, ymin = points[0].y.value, ymax = ymin;
        for (const Point& point : points) { xmin = std::min(xmin, point.x.value); xmax = std::max(xmax, point.x.value); ymin = std::min(ymin, point.y.value); ymax = std::max(ymax, point.y.value); }
        VectorPath shape; shape.points = std::move(points); shape.source_path = "pdf:pdftocairo-svg"; shape.source_page = page.source_page;
        VectorElement element; element.id = "page-" + std::to_string(page.source_page + 1) + "-vector-" + std::to_string(order + 1); element.source_order = order++; element.source_page = page.source_page; element.bounds = Rect{{xmin}, {ymin}, {xmax - xmin}, {ymax - ymin}}; element.paths.push_back(std::move(shape)); page.elements.emplace_back(std::move(element));
    }
}

void append_math(SourcePage& page, const std::vector<Word>& words, std::uint32_t& order) {
    std::vector<Word> sorted = words; std::sort(sorted.begin(), sorted.end(), [](const Word& a, const Word& b) { return a.y_min == b.y_min ? a.x_min < b.x_min : a.y_min < b.y_min; });
    std::vector<std::vector<Word>> lines;
    for (Word& word : sorted) { if (lines.empty() || std::abs(lines.back()[0].y_min - word.y_min) > 1.0) lines.emplace_back(); lines.back().push_back(std::move(word)); }
    for (const auto& line : lines) {
        std::string expression; double xmin = line[0].x_min, ymin = line[0].y_min, xmax = line[0].x_max, ymax = line[0].y_max;
        for (const Word& word : line) { if (!expression.empty()) expression += ' '; expression += word.text; xmin = std::min(xmin, word.x_min); ymin = std::min(ymin, word.y_min); xmax = std::max(xmax, word.x_max); ymax = std::max(ymax, word.y_max); }
        if (!line_is_math(line)) continue;
        MathElement math; math.id = "page-" + std::to_string(page.source_page + 1) + "-math-" + std::to_string(order + 1); math.source_order = order++; math.source_page = page.source_page; math.expression = std::move(expression); math.source_syntax = "pdf-text-layer-heuristic"; math.display_mode = true; math.bounds = rect_mm(xmin, ymin, xmax, ymax); math.detection_confidence = 0.75; page.elements.emplace_back(std::move(math));
    }
}

void append_grid_table(SourcePage& page, std::uint32_t& order) {
    std::vector<double> xs, ys;
    for (const SourceElement& source : page.elements) { const auto* vector = std::get_if<VectorElement>(&source); if (!vector || vector->paths.empty()) continue; const auto& p = vector->paths[0].points; if (p.size() != 2) continue; if (std::abs(p[0].y.value - p[1].y.value) < 0.2) ys.push_back(p[0].y.value); if (std::abs(p[0].x.value - p[1].x.value) < 0.2) xs.push_back(p[0].x.value); }
    const auto normalize = [](std::vector<double>& values) { std::sort(values.begin(), values.end()); values.erase(std::unique(values.begin(), values.end(), [](double a, double b) { return std::abs(a - b) < 0.2; }), values.end()); };
    normalize(xs); normalize(ys); if (xs.size() < 2 || ys.size() < 2) return;
    TableElement table; table.id = "page-" + std::to_string(page.source_page + 1) + "-table-" + std::to_string(order + 1); table.source_order = order++; table.source_page = page.source_page; table.columns = static_cast<std::uint32_t>(xs.size() - 1); table.rows = static_cast<std::uint32_t>(ys.size() - 1); table.source_kind = "pdf-vector-grid"; table.bounds = Rect{{xs.front()}, {ys.front()}, {xs.back() - xs.front()}, {ys.back() - ys.front()}};
    for (std::size_t col = 0; col + 1 < xs.size(); ++col) table.column_widths.push_back(Millimetres{xs[col + 1] - xs[col]});
    for (std::size_t row = 0; row + 1 < ys.size(); ++row) for (std::size_t col = 0; col + 1 < xs.size(); ++col) { TableCell cell; cell.row = static_cast<std::uint32_t>(row); cell.column = static_cast<std::uint32_t>(col); cell.width = Millimetres{xs[col + 1] - xs[col]}; cell.height = Millimetres{ys[row + 1] - ys[row]}; table.cells.push_back(std::move(cell)); }
    page.elements.emplace_back(std::move(table));
}

}  // namespace
