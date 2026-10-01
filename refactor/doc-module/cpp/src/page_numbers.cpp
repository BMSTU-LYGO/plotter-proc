#include "plotter/doc/page_numbers.hpp"

#include <stdexcept>

namespace plotter::doc {
void append_page_numbers(LayoutDocument& layout, const FontRegistry& fonts,
                         const PageNumberOptions& options) {
    if (!options.enabled) return;
    if (options.font_id.empty() || !fonts.contains(options.font_id))
        throw std::invalid_argument("page numbers require a registered font");
    if (options.size.value <= 0.0 || options.baseline_from_bottom.value <= 0.0 ||
        options.baseline_from_bottom.value >= options.page_height.value)
        throw std::invalid_argument("invalid page number geometry");
    std::uint32_t next_glyph_index{};
    for (const auto& page : layout.pages) {
        for (const auto& glyph : page.glyphs)
            if (glyph.glyph_index >= next_glyph_index) next_glyph_index = glyph.glyph_index + 1;
    }
    for (std::size_t page_index = 0; page_index < layout.pages.size(); ++page_index) {
        auto& page = layout.pages[page_index];
        const std::string number = std::to_string(page_index + 1);
        const auto size_mm = to_millimetres(options.size);
        std::vector<ResolvedGlyph> glyphs;
        glyphs.reserve(number.size());
        double width = 0.0;
        for (unsigned char character : number) {
            auto glyph = fonts.resolve(options.font_id, character);
            width += font_units_to_millimetres(glyph.advance, size_mm, glyph.units_per_em).value;
            glyphs.push_back(std::move(glyph));
        }
        double x = (options.page_width.value - width) / 2.0;
        const double baseline = options.page_height.value - options.baseline_from_bottom.value;
        for (std::size_t index = 0; index < number.size(); ++index) {
            const auto& resolved = glyphs[index];
            PositionedGlyph placed;
            placed.character = number.substr(index, 1);
            placed.codepoint = static_cast<unsigned char>(number[index]);
            placed.glyph_name = "U+" + std::to_string(placed.codepoint);
            placed.x = {x}; placed.baseline_y = {baseline};
            placed.advance = font_units_to_millimetres(resolved.advance, size_mm, resolved.units_per_em);
            placed.scale_mm_per_font_unit = size_mm.value / static_cast<double>(resolved.units_per_em);
            placed.line_index = page.line_count;
            placed.glyph_index = next_glyph_index++;
            placed.word_index = -1;
            placed.cluster_index = static_cast<std::int32_t>(index);
            placed.font_id = resolved.font_id;
            placed.font_sha256 = resolved.font_sha256;
            placed.text_role = "page-number";
            page.glyphs.push_back(std::move(placed));
            x += page.glyphs.back().advance.value;
        }
    }
}
}  // namespace plotter::doc
