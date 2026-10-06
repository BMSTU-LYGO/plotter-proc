#include "plotter/doc/text_adapter.hpp"

#include <algorithm>
#include <cctype>
#include <fstream>
#include <iterator>
#include <string_view>
#include <utility>

namespace plotter::doc {
namespace {

constexpr std::string_view kTextElementId{"page-001-text-001"};

[[nodiscard]] std::string lowercase_ascii(std::string value) {
    std::transform(value.begin(), value.end(), value.begin(), [](const unsigned char character) {
        return static_cast<char>(std::tolower(character));
    });
    return value;
}

[[nodiscard]] bool is_valid_utf8(const std::string_view text) {
    for (std::size_t index = 0; index < text.size();) {
        const auto first = static_cast<unsigned char>(text[index]);
        if (first < 0x80U) { ++index; continue; }
        std::size_t continuation_count = 0;
        std::uint32_t codepoint = 0;
        if (first >= 0xC2U && first <= 0xDFU) { continuation_count = 1; codepoint = first & 0x1FU; }
        else if (first >= 0xE0U && first <= 0xEFU) { continuation_count = 2; codepoint = first & 0x0FU; }
        else if (first >= 0xF0U && first <= 0xF4U) { continuation_count = 3; codepoint = first & 0x07U; }
        else { return false; }
        if (index + continuation_count >= text.size()) { return false; }
        for (std::size_t offset = 1; offset <= continuation_count; ++offset) {
            const auto next = static_cast<unsigned char>(text[index + offset]);
            if ((next & 0xC0U) != 0x80U) { return false; }
            codepoint = (codepoint << 6U) | (next & 0x3FU);
        }
        if ((continuation_count == 2 && codepoint < 0x800U) ||
            (continuation_count == 3 && codepoint < 0x10000U) ||
            (codepoint >= 0xD800U && codepoint <= 0xDFFFU) || codepoint > 0x10FFFFU) { return false; }
        index += continuation_count + 1;
    }
    return true;
}

using TextLoadResult = std::variant<std::string, ImportError>;

[[nodiscard]] TextLoadResult load_utf8(const std::filesystem::path& path, const std::string_view format_name) {
    if (!std::filesystem::is_regular_file(path)) {
        return ImportError{"Input document does not exist: " + path.string()};
    }
    std::ifstream input(path, std::ios::binary);
    if (!input) { return ImportError{"Cannot read " + std::string(format_name) + " document: " + path.string()}; }
    std::string text{std::istreambuf_iterator<char>{input}, std::istreambuf_iterator<char>{}};
    if (text.size() >= 3 && static_cast<unsigned char>(text[0]) == 0xEFU &&
        static_cast<unsigned char>(text[1]) == 0xBBU && static_cast<unsigned char>(text[2]) == 0xBFU) {
        text.erase(0, 3);
    }
    if (!is_valid_utf8(text)) { return ImportError{std::string(format_name) + " document is not valid UTF-8: " + path.string()}; }
    if (std::none_of(text.begin(), text.end(), [](const unsigned char character) { return !std::isspace(character); })) {
        return ImportError{std::string(format_name) + " document contains no usable text: " + path.string()};
    }
    return text;
}

[[nodiscard]] std::vector<std::string> split_lines(const std::string_view text) {
    std::vector<std::string> lines;
    std::size_t start = 0;
    for (std::size_t index = 0; index < text.size(); ++index) {
        if (text[index] != '\n' && text[index] != '\r') { continue; }
        lines.emplace_back(text.substr(start, index - start));
        if (text[index] == '\r' && index + 1 < text.size() && text[index + 1] == '\n') { ++index; }
        start = index + 1;
    }
    if (start < text.size()) { lines.emplace_back(text.substr(start)); }
    return lines;
}

[[nodiscard]] Document make_document(const std::filesystem::path& path, std::vector<std::string> paragraphs,
                                     std::vector<std::string> roles, std::string source_format,
                                     const std::vector<bool>& paragraph_breaks = {}) {
    TextElement element;
    element.id = std::string{kTextElementId};
    element.source_order = 0;
    element.source_page = 0;
    element.paragraphs.reserve(paragraphs.size());
    for (std::size_t index = 0; index < paragraphs.size(); ++index) {
        Paragraph paragraph;
        TextRun run;
        run.text = std::move(paragraphs[index]);
        paragraph.runs.push_back(std::move(run));
        paragraph.semantic_role = std::move(roles[index]);
        if (source_format == "markdown") {
            paragraph.space_after = Millimetres{index < paragraph_breaks.size() && paragraph_breaks[index] ? 2.5 : 0.0};
        }
        element.paragraphs.push_back(std::move(paragraph));
    }
    SourcePage page;
    page.source_page = 0;
    page.elements.emplace_back(std::move(element));
    Document document;
    document.source_path = path.string();
    document.pages.push_back(std::move(page));
    document.metadata.source_format = std::move(source_format);
    return document;
}

[[nodiscard]] bool starts_with_at(const std::string_view text, const std::size_t index, const std::string_view prefix) {
    return index <= text.size() && prefix.size() <= text.size() - index && text.substr(index, prefix.size()) == prefix;
}

[[nodiscard]] std::string replace_links_and_images(std::string text) {
    std::string output;
    for (std::size_t index = 0; index < text.size();) {
        const bool image = text[index] == '!' && index + 1 < text.size() && text[index + 1] == '[';
        const bool link = text[index] == '[' && (index == 0 || text[index - 1] != '!');
        const std::size_t open = image ? index + 1 : index;
        if (!image && !link) { output += text[index++]; continue; }
        const auto close = text.find(']', open + 1);
        if (close == std::string::npos || close + 1 >= text.size() || (text[close + 1] != '(' && text[close + 1] != '[')) {
            output += text[index++]; continue;
        }
        const char end = text[close + 1] == '(' ? ')' : ']';
        const auto target_end = text.find(end, close + 2);
        if (target_end == std::string::npos) { output += text[index++]; continue; }
        output.append(text, open + 1, close - open - 1);
        index = target_end + 1;
    }
    return output;
}

[[nodiscard]] std::string unwrap_inline_code(std::string text) {
    std::string output;
    for (std::size_t index = 0; index < text.size();) {
        if (text[index] != '`') { output += text[index++]; continue; }
        std::size_t length = 1;
        while (index + length < text.size() && text[index + length] == '`') { ++length; }
        const auto close = text.find(std::string(length, '`'), index + length);
        if (close == std::string::npos) { output.append(text, index, length); index += length; continue; }
        output.append(text, index + length, close - index - length);
        index = close + length;
    }
    return output;
}

[[nodiscard]] std::string unwrap_emphasis(std::string text) {
    bool changed = true;
    while (changed) {
        changed = false;
        for (const std::string& delimiter : {std::string{"**"}, std::string{"__"}, std::string{"*"}, std::string{"_"}}) {
            for (std::size_t start = 0; start + delimiter.size() <= text.size(); ++start) {
                if (!starts_with_at(text, start, delimiter) || (start > 0 && text[start - 1] == '\\')) { continue; }
                const auto end = text.find(delimiter, start + delimiter.size());
                if (end == std::string::npos || end == start + delimiter.size() || (end > 0 && text[end - 1] == '\\')) { continue; }
                text.erase(end, delimiter.size());
                text.erase(start, delimiter.size());
                changed = true;
                goto next_pass;
            }
        }
next_pass:;
    }
    return text;
}

[[nodiscard]] std::string html_unescape(std::string text) {
    const std::pair<std::string_view, std::string_view> named[] = {
        {"&quot;", "\""}, {"&apos;", "'"}, {"&amp;", "&"}, {"&lt;", "<"}, {"&gt;", ">"}, {"&nbsp;", "\xC2\xA0"},
    };
    for (const auto& [entity, value] : named) {
        std::size_t index = 0;
        while ((index = text.find(entity, index)) != std::string::npos) { text.replace(index, entity.size(), value); index += value.size(); }
    }
    return text;
}

[[nodiscard]] std::string clean_inline_markdown(std::string line) {
    std::size_t comment_start = 0;
    while ((comment_start = line.find("<!--", comment_start)) != std::string::npos) {
        const auto comment_end = line.find("-->", comment_start + 4);
        if (comment_end == std::string::npos) { break; }
        line.erase(comment_start, comment_end + 3 - comment_start);
    }
    line = replace_links_and_images(std::move(line));
    line = unwrap_inline_code(std::move(line));
    line = unwrap_emphasis(std::move(line));
    for (std::size_t index = 0; index < line.size();) {
        if (line[index] != '<') { ++index; continue; }
        std::size_t name = index + 1;
        if (name < line.size() && line[name] == '/') { ++name; }
        if (name >= line.size() || !std::isalpha(static_cast<unsigned char>(line[name]))) { ++index; continue; }
        const auto end = line.find('>', name + 1);
        if (end == std::string::npos) { ++index; continue; }
        line.erase(index, end + 1 - index);
    }
    line = html_unescape(std::move(line));
    for (const auto& [escaped, plain] : {std::pair<std::string_view, std::string_view>{"\\*", "*"}, {"\\_", "_"}, {"\\`", "`"}}) {
        std::size_t index = 0;
        while ((index = line.find(escaped, index)) != std::string::npos) { line.replace(index, escaped.size(), plain); index += plain.size(); }
    }
    return line;
}

[[nodiscard]] bool fence_marker(const std::string_view line, char& character, std::size_t& length) {
    std::size_t index = 0;
    while (index < line.size() && index < 3 && line[index] == ' ') { ++index; }
    if (index == line.size() || (line[index] != '`' && line[index] != '~')) { return false; }
    character = line[index]; length = 0;
    while (index + length < line.size() && line[index + length] == character) { ++length; }
    return length >= 3;
}

[[nodiscard]] std::string_view ltrim_three_spaces(std::string_view line) {
    std::size_t index = 0;
    while (index < line.size() && index < 3 && line[index] == ' ') { ++index; }
    return line.substr(index);
}

[[nodiscard]] bool strip_heading(std::string& line, std::size_t* level = nullptr) {
    const auto view = ltrim_three_spaces(line);
    std::size_t hashes = 0;
    while (hashes < view.size() && view[hashes] == '#' && hashes < 6) { ++hashes; }
    if (hashes == 0 || hashes == view.size() || (view[hashes] != ' ' && view[hashes] != '\t')) { return false; }
    if (level) *level = hashes;
    std::size_t start = hashes;
    while (start < view.size() && (view[start] == ' ' || view[start] == '\t')) { ++start; }
    line = std::string{view.substr(start)};
    std::size_t end = line.size();
    while (end > 0 && (line[end - 1] == ' ' || line[end - 1] == '\t')) { --end; }
    std::size_t trailing = end;
    while (trailing > 0 && line[trailing - 1] == '#') { --trailing; }
    if (trailing < end && trailing > 0 && (line[trailing - 1] == ' ' || line[trailing - 1] == '\t')) {
        while (trailing > 0 && (line[trailing - 1] == ' ' || line[trailing - 1] == '\t')) { --trailing; }
        line.resize(trailing);
    }
    return true;
}

[[nodiscard]] bool strip_quote(std::string& line) {
    const auto view = ltrim_three_spaces(line);
    if (view.empty() || view.front() != '>') { return false; }
    line = std::string{view.substr(1)};
    if (!line.empty() && (line.front() == ' ' || line.front() == '\t')) { line.erase(0, 1); }
    return true;
}

[[nodiscard]] bool strip_list(std::string& line) {
    const auto view = ltrim_three_spaces(line);
    std::size_t marker_end = 0;
    if (!view.empty() && (view.front() == '-' || view.front() == '+' || view.front() == '*')) { marker_end = 1; }
    else {
        while (marker_end < view.size() && std::isdigit(static_cast<unsigned char>(view[marker_end]))) { ++marker_end; }
        if (marker_end == 0 || marker_end == view.size() || (view[marker_end] != '.' && view[marker_end] != ')')) { return false; }
        ++marker_end;
    }
    if (marker_end >= view.size() || (view[marker_end] != ' ' && view[marker_end] != '\t')) { return false; }
    while (marker_end < view.size() && (view[marker_end] == ' ' || view[marker_end] == '\t')) { ++marker_end; }
    const std::string prefix = std::isdigit(static_cast<unsigned char>(view.front()))
        ? std::string{view.substr(0, marker_end)} : std::string{"- "};
    line = prefix + std::string{view.substr(marker_end)};
    return true;
}

[[nodiscard]] bool thematic_break(std::string_view line) {
    char marker = 0;
    std::size_t count = 0;
    for (char character : line) {
        if (character == ' ' || character == '\t' || character == '\r') continue;
        if (marker == 0) {
            if (character != '-' && character != '*' && character != '_') return false;
            marker = character;
        }
        if (character != marker) return false;
        ++count;
    }
    return count >= 3;
}

[[nodiscard]] std::string trim_cell(std::string_view value) {
    const auto first = value.find_first_not_of(" \t\r");
    if (first == std::string_view::npos) return {};
    const auto last = value.find_last_not_of(" \t\r");
    return std::string{value.substr(first, last - first + 1)};
}

[[nodiscard]] std::vector<std::string> table_cells(std::string_view line) {
    std::vector<std::string> cells;
    std::string cell;
    bool saw_pipe = false;
    for (std::size_t i = 0; i < line.size(); ++i) {
        if (line[i] == '\\' && i + 1 < line.size() && line[i + 1] == '|') { cell += '|'; ++i; continue; }
        if (line[i] == '|') { cells.push_back(trim_cell(cell)); cell.clear(); saw_pipe = true; }
        else cell += line[i];
    }
    if (!saw_pipe) return {};
    cells.push_back(trim_cell(cell));
    if (!cells.empty() && cells.front().empty()) cells.erase(cells.begin());
    if (!cells.empty() && cells.back().empty()) cells.pop_back();
    return cells;
}

[[nodiscard]] bool table_separator(std::string_view line, std::size_t columns) {
    const auto cells = table_cells(line);
    if (cells.size() != columns || columns == 0) return false;
    for (const auto& cell : cells) {
        std::size_t first = !cell.empty() && cell.front() == ':' ? 1 : 0;
        std::size_t last = cell.size() - (!cell.empty() && cell.back() == ':' ? 1 : 0);
        if (last < first + 3) return false;
        for (std::size_t i = first; i < last; ++i) if (cell[i] != '-') return false;
    }
    return true;
}

[[nodiscard]] TableElement markdown_table(const std::vector<std::vector<std::string>>& rows, std::size_t index) {
    TableElement table;
    table.id = "markdown-table-" + std::to_string(index + 1);
    table.source_kind = "markdown-table";
    table.rows = static_cast<std::uint32_t>(rows.size());
    table.columns = static_cast<std::uint32_t>(rows.front().size());
    table.repeat_header_rows = 1;
    for (std::size_t row = 0; row < rows.size(); ++row) {
        for (std::size_t column = 0; column < rows.front().size(); ++column) {
            TableCell cell;
            cell.row = static_cast<std::uint32_t>(row);
            cell.column = static_cast<std::uint32_t>(column);
            Paragraph paragraph;
            paragraph.semantic_role = row == 0 ? "table-header" : "table-cell";
            paragraph.runs.push_back({column < rows[row].size() ? clean_inline_markdown(rows[row][column]) : std::string{}, {}});
            cell.paragraphs.push_back(std::move(paragraph));
            table.cells.push_back(std::move(cell));
        }
    }
    return table;
}

}  // namespace

ImportResult read_txt_document(const std::filesystem::path& source_path) {
    auto loaded = load_utf8(source_path, "TXT");
    if (const auto* error = std::get_if<ImportError>(&loaded)) { return *error; }
    const auto text = std::move(std::get<std::string>(loaded));
    auto paragraphs = split_lines(text);
    return make_document(source_path, std::move(paragraphs), std::vector<std::string>(split_lines(text).size(), "body"), "txt");
}

ImportResult read_markdown_document(const std::filesystem::path& source_path) {
    const auto extension = lowercase_ascii(source_path.extension().string());
    if (extension != ".md" && extension != ".markdown") {
        return ImportError{"Unsupported Markdown format '" + (extension.empty() ? std::string{"(none)"} : extension) + "'. Use .markdown, .md."};
    }
    auto loaded = load_utf8(source_path, "Markdown");
    if (const auto* error = std::get_if<ImportError>(&loaded)) { return *error; }
    const auto lines = split_lines(std::get<std::string>(loaded));
    std::vector<std::string> paragraphs;
    std::vector<std::string> roles;
    std::vector<bool> paragraph_breaks;
    std::vector<std::pair<std::size_t, TableElement>> tables;
    char fence_character{};
    std::size_t fence_length{};
    for (std::size_t i = 0; i < lines.size(); ++i) {
        std::string line = lines[i];
        char marker_character{};
        std::size_t marker_length{};
        const bool marker = fence_marker(line, marker_character, marker_length);
        if (fence_length != 0) {
            if (marker && marker_character == fence_character && marker_length >= fence_length) { fence_length = 0; continue; }
            paragraphs.push_back(std::move(line)); roles.emplace_back("code");
            paragraph_breaks.push_back(false); continue;
        }
        if (marker) { fence_character = marker_character; fence_length = marker_length; continue; }
        if (i + 1 < lines.size()) {
            const auto header = table_cells(line);
            if (!header.empty() && table_separator(lines[i + 1], header.size())) {
                std::vector<std::vector<std::string>> rows{header};
                i += 2;
                while (i < lines.size()) {
                    const auto cells = table_cells(lines[i]);
                    if (cells.empty()) break;
                    rows.push_back(cells);
                    ++i;
                }
                tables.emplace_back(paragraphs.size(), markdown_table(rows, tables.size()));
                if (i < lines.size() && lines[i].find_first_not_of(" \t\r") == std::string::npos) {
                    // The table itself supplies vertical separation.
                } else if (i < lines.size()) --i;
                continue;
            }
        }
        if (line.find_first_not_of(" \t\r") == std::string::npos) {
            if (!paragraph_breaks.empty()) paragraph_breaks.back() = true;
            continue;
        }
        if (thematic_break(line)) {
            paragraphs.emplace_back();
            roles.emplace_back("thematic_break");
            paragraph_breaks.push_back(false);
            continue;
        }
        std::string role{"body"};
        std::size_t heading_level = 0;
        if (strip_heading(line, &heading_level)) { role = "heading_" + std::to_string(heading_level); }
        else {
            if (strip_quote(line)) { role = "blockquote"; }
            if (strip_list(line)) { role = "list"; }
        }
        paragraphs.push_back(clean_inline_markdown(std::move(line)));
        roles.push_back(std::move(role));
        paragraph_breaks.push_back(false);
    }
    Document document = make_document(source_path, std::move(paragraphs), std::move(roles), "markdown", paragraph_breaks);
    if (tables.empty()) return document;
    SourcePage& page = document.pages.front();
    TextElement source = std::move(std::get<TextElement>(page.elements.front()));
    page.elements.clear();
    std::size_t first = 0;
    std::uint32_t order = 0;
    for (auto& [before, table] : tables) {
        if (before > first) {
            TextElement text;
            text.id = "markdown-text-" + std::to_string(order + 1);
            text.source_order = order++;
            for (std::size_t j = first; j < before; ++j) text.paragraphs.push_back(std::move(source.paragraphs[j]));
            page.elements.emplace_back(std::move(text));
        }
        table.source_order = order++;
        page.elements.emplace_back(std::move(table));
        first = before;
    }
    if (first < source.paragraphs.size()) {
        TextElement text;
        text.id = "markdown-text-" + std::to_string(order + 1);
        text.source_order = order;
        for (std::size_t j = first; j < source.paragraphs.size(); ++j) text.paragraphs.push_back(std::move(source.paragraphs[j]));
        page.elements.emplace_back(std::move(text));
    }
    return document;
}

ImportResult read_text_document(const std::filesystem::path& source_path) {
    const auto extension = lowercase_ascii(source_path.extension().string());
    if (extension == ".txt") { return read_txt_document(source_path); }
    if (extension == ".md" || extension == ".markdown") { return read_markdown_document(source_path); }
    return ImportError{"Unsupported input format '" + (extension.empty() ? std::string{"(none)"} : extension) + "'. Use .markdown, .md, .txt."};
}

}  // namespace plotter::doc
