#include "plotter/doc/text_layout.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <utility>

namespace plotter::doc {
namespace {
struct Character final { std::uint32_t codepoint{}; std::string utf8; LayoutTextStyle style; bool whitespace{}; bool newline{}; };
struct MeasuredCharacter final { Character character; ResolvedGlyph glyph; Millimetres advance, natural_height, ascender; };
struct Word final { std::vector<MeasuredCharacter> characters; Millimetres width{}; };
struct Token final { Word word; Millimetres preceding_space{}; bool forced_break{}; bool tab_before{}; };
struct Line final { std::vector<Word> words; std::vector<Millimetres> gaps; Millimetres width{}, height{}, ascender{}; bool forced_break{}; };

std::vector<Character> decode(const LayoutTextRun& run) {
    std::vector<Character> result;
    for (std::size_t i = 0; i < run.utf8.size();) {
        const unsigned char first = static_cast<unsigned char>(run.utf8[i]);
        std::uint32_t cp = 0xFFFDU; std::size_t n = 1;
        if (first < 0x80U) cp = first;
        else if ((first & 0xE0U) == 0xC0U && i + 1 < run.utf8.size() && (static_cast<unsigned char>(run.utf8[i + 1]) & 0xC0U) == 0x80U) { cp = (static_cast<std::uint32_t>(first & 0x1FU) << 6U) | (static_cast<unsigned char>(run.utf8[i + 1]) & 0x3FU); n = cp >= 0x80U ? 2 : 1; }
        else if ((first & 0xF0U) == 0xE0U && i + 2 < run.utf8.size() && (static_cast<unsigned char>(run.utf8[i + 1]) & 0xC0U) == 0x80U && (static_cast<unsigned char>(run.utf8[i + 2]) & 0xC0U) == 0x80U) { cp = (static_cast<std::uint32_t>(first & 0x0FU) << 12U) | (static_cast<std::uint32_t>(static_cast<unsigned char>(run.utf8[i + 1]) & 0x3FU) << 6U) | (static_cast<unsigned char>(run.utf8[i + 2]) & 0x3FU); n = (cp >= 0x800U && !(cp >= 0xD800U && cp <= 0xDFFFU)) ? 3 : 1; }
        else if ((first & 0xF8U) == 0xF0U && i + 3 < run.utf8.size() && (static_cast<unsigned char>(run.utf8[i + 1]) & 0xC0U) == 0x80U && (static_cast<unsigned char>(run.utf8[i + 2]) & 0xC0U) == 0x80U && (static_cast<unsigned char>(run.utf8[i + 3]) & 0xC0U) == 0x80U) { cp = (static_cast<std::uint32_t>(first & 0x07U) << 18U) | (static_cast<std::uint32_t>(static_cast<unsigned char>(run.utf8[i + 1]) & 0x3FU) << 12U) | (static_cast<std::uint32_t>(static_cast<unsigned char>(run.utf8[i + 2]) & 0x3FU) << 6U) | (static_cast<unsigned char>(run.utf8[i + 3]) & 0x3FU); n = (cp >= 0x10000U && cp <= 0x10FFFFU) ? 4 : 1; }
        const bool newline = cp == '\n' || cp == '\r';
        result.push_back({cp, newline ? std::string{} : (n == 1 && cp == 0xFFFDU ? "\xEF\xBF\xBD" : run.utf8.substr(i, n)), run.style, cp == ' ' || cp == '\t', newline});
        i += n;
    }
    return result;
}

MeasuredCharacter measure(const Character& character, const FontRegistry& fonts) {
    const ResolvedGlyph glyph = fonts.resolve(character.style.font_id, character.codepoint);
    const Millimetres size = to_millimetres(character.style.font_size);
    Millimetres advance = font_units_to_millimetres(glyph.advance, size, glyph.units_per_em);
    advance = advance + (character.whitespace ? character.style.word_spacing : character.style.letter_spacing);
    const double vertical = static_cast<double>(glyph.ascender) - static_cast<double>(glyph.descender) + static_cast<double>(glyph.line_gap);
    return {character, glyph, advance, {std::max(size.value, size.value * vertical / static_cast<double>(glyph.units_per_em))}, font_units_to_millimetres({static_cast<double>(glyph.ascender)}, size, glyph.units_per_em)};
}

void measure_line(Line& line) {
    line.width = {}; line.height = {}; line.ascender = {};
    for (std::size_t i = 0; i < line.words.size(); ++i) {
        if (i != 0) line.width = line.width + line.gaps[i - 1];
        for (const auto& character : line.words[i].characters) {
            line.width = line.width + character.advance;
            line.height = {std::max(line.height.value, character.natural_height.value)};
            line.ascender = {std::max(line.ascender.value, character.ascender.value)};
        }
    }
}

LayoutPage make_page(std::uint32_t index) { LayoutPage page; page.page_index = index; return page; }
void add_source(LayoutPage& page, const std::optional<std::string>& id) { if (id && std::find(page.source_element_ids.begin(), page.source_element_ids.end(), *id) == page.source_element_ids.end()) page.source_element_ids.push_back(*id); }
constexpr double kDefaultTabInterval = 12.5;
[[nodiscard]] double tab_target(double cursor, double paragraph_left, const std::vector<TabStop>& stops, const Word& following) {
    TabStop stop{}; bool found{};
    for (const TabStop& candidate : stops) if (candidate.position.value > cursor - paragraph_left) { stop = candidate; found = true; break; }
    const double position = found ? paragraph_left + stop.position.value : paragraph_left + (std::floor((cursor - paragraph_left) / kDefaultTabInterval) + 1.0) * kDefaultTabInterval;
    if (!found || stop.alignment == "left") return position;
    if (stop.alignment == "center") return position - following.width.value / 2.0;
    return position - following.width.value;
}

}  // namespace

LayoutDocument TextLayoutEngine::layout(const std::vector<LayoutParagraph>& paragraphs, const TextLayoutOptions& options) const {
    const double right = options.page_width.value - options.margin_right.value;
    const double bottom = options.page_height.value - options.margin_bottom.value - options.footer_reserve.value;
    if (options.margin_left.value >= right || options.margin_top.value >= bottom) throw std::invalid_argument("text layout area is empty");
    LayoutDocument document; document.pages.push_back(make_page(0));
    double cursor_y = options.margin_top.value;
    std::uint32_t next_glyph = 0, next_line = 0; std::int32_t next_word = 0;
    auto new_page = [&]() { document.pages.push_back(make_page(static_cast<std::uint32_t>(document.pages.size()))); cursor_y = options.margin_top.value; };
    auto require_vertical = [&](double height) { if (height <= 0.0 || height > bottom - options.margin_top.value) throw std::invalid_argument("line does not fit in page content area"); if (cursor_y + height > bottom) new_page(); };

    for (const LayoutParagraph& paragraph : paragraphs) {
        if (paragraph.page_break_before && (cursor_y != options.margin_top.value || !document.pages.back().glyphs.empty())) new_page();
        cursor_y += paragraph.space_before.value; if (cursor_y > bottom) new_page();
        std::vector<Token> tokens; Word word; Millimetres pending_space{}; bool pending_tab{};
        auto flush_word = [&]() { if (!word.characters.empty()) { tokens.push_back({std::move(word), pending_space, false, pending_tab}); word = {}; pending_space = {}; pending_tab = false; } };
        for (const auto& run : paragraph.runs) {
            if (run.style.font_id.empty() || run.style.font_size.value <= 0.0) throw std::invalid_argument("text run requires a font id and positive size");
            for (const Character& character : decode(run)) {
                if (character.newline) { flush_word(); tokens.push_back({{}, {}, true, false}); continue; }
                if (character.codepoint == '\t') { flush_word(); pending_space = {}; pending_tab = true; continue; }
                const MeasuredCharacter item = measure(character, fonts_);
                if (character.whitespace) { flush_word(); pending_space = pending_space + item.advance; }
                else { word.characters.push_back(item); word.width = word.width + item.advance; }
            }
        }
        flush_word();
        const double paragraph_left = options.margin_left.value + paragraph.left_indent.value;
        const double first_left = std::max(options.margin_left.value, paragraph_left + paragraph.first_line_indent.value - paragraph.hanging_indent.value);
        const double paragraph_right = right - paragraph.right_indent.value;
        if (paragraph_right <= std::max(paragraph_left, first_left)) throw std::invalid_argument("paragraph indents leave no usable line width");
        std::vector<Line> lines; Line current;
        const auto current_left = [&]() { return lines.empty() ? first_left : paragraph_left; };
        const auto current_available = [&]() { return paragraph_right - current_left(); };
        auto finish = [&]() { measure_line(current); lines.push_back(std::move(current)); current = {}; };
        for (Token& token : tokens) {
            if (token.forced_break) { finish(); continue; }
            const auto gap_for = [&]() {
                if (!token.tab_before) return token.preceding_space;
                const double cursor = current_left() + current.width.value;
                return Millimetres{std::max(0.0, tab_target(cursor, paragraph_left, paragraph.tab_stops, token.word) - cursor)};
            };
            Millimetres gap = current.words.empty() ? Millimetres{} : gap_for();
            double proposed = current.width.value + gap.value + token.word.width.value;
            if (!current.words.empty() && proposed > current_available()) { finish(); gap = current.words.empty() ? Millimetres{} : gap_for(); proposed = current.width.value + gap.value + token.word.width.value; }
            auto append = [&](Word part, Millimetres value) { if (!current.words.empty()) current.gaps.push_back(value); current.words.push_back(std::move(part)); measure_line(current); };
            if (proposed <= current_available() || !current.words.empty()) { append(std::move(token.word), gap); continue; }
            Word part;
            for (auto& item : token.word.characters) {
                if (!part.characters.empty() && part.width.value + item.advance.value > current_available()) { append(std::move(part), {}); finish(); part = {}; }
                part.width = part.width + item.advance; part.characters.push_back(std::move(item));
            }
            if (!part.characters.empty()) append(std::move(part), {});
        }
        if (!current.words.empty() || lines.empty()) finish();
        const double fallback_height = paragraph.runs.empty() ? to_millimetres(Points{12.0}).value * 1.2 : to_millimetres(paragraph.runs.front().style.font_size).value * 1.2;
        for (std::size_t line_number = 0; line_number < lines.size(); ++line_number) {
            const Line& line = lines[line_number];
            const double base_height = paragraph.line_height ? paragraph.line_height->value : std::max(line.height.value, fallback_height);
            if (paragraph.line_spacing && *paragraph.line_spacing <= 0.0) throw std::invalid_argument("paragraph line spacing must be positive");
            const double height = paragraph.line_spacing ? base_height * *paragraph.line_spacing : base_height;
            require_vertical(height);
            const double line_left = line_number == 0 ? first_left : paragraph_left;
            const double line_available = paragraph_right - line_left;
            const bool justify = paragraph.alignment == TextAlignment::justify && line_number + 1 < lines.size() && line.words.size() > 1 && !line.forced_break;
            const double extra = justify ? (line_available - line.width.value) / static_cast<double>(line.words.size() - 1) : 0.0;
            double x = line_left;
            if (paragraph.alignment == TextAlignment::center) x += std::max(0.0, (line_available - line.width.value) / 2.0);
            else if (paragraph.alignment == TextAlignment::right) x += std::max(0.0, line_available - line.width.value);
            const double baseline = cursor_y + std::min(line.ascender.value, height);
            LayoutPage& page = document.pages.back(); add_source(page, paragraph.source_element_id);
            page.line_boxes.push_back({{x}, {cursor_y}, {justify ? line_available : line.width.value}, {height}});
            for (std::size_t word_position = 0; word_position < line.words.size(); ++word_position) {
                if (word_position != 0) x += line.gaps[word_position - 1].value + extra;
                const std::int32_t word_index = next_word++;
                for (const auto& item : line.words[word_position].characters) {
                    PositionedGlyph placed; placed.character = item.character.utf8; placed.glyph_name = "U+" + std::to_string(item.glyph.glyph_codepoint); placed.codepoint = item.character.codepoint;
                    placed.x = {x}; placed.baseline_y = {baseline}; placed.advance = item.advance; placed.scale_mm_per_font_unit = to_millimetres(item.character.style.font_size).value / static_cast<double>(item.glyph.units_per_em);
                    placed.line_index = next_line; placed.glyph_index = next_glyph++; placed.word_index = word_index; placed.cluster_index = static_cast<std::int32_t>(placed.glyph_index);
                    placed.font_id = item.glyph.font_id; placed.font_sha256 = item.glyph.font_sha256; placed.text_role = "letter"; page.glyphs.push_back(std::move(placed)); x += item.advance.value;
                }
            }
            ++next_line; ++page.line_count; cursor_y += height;
        }
        cursor_y += paragraph.space_after.value; if (cursor_y > bottom) new_page();
    }
    return document;
}
}  // namespace plotter::doc
