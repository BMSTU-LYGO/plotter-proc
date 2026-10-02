#include "plotter/doc/document_codec.hpp"
#include "plotter/doc/stage_cache.hpp"

#include <filesystem>
#include <fstream>
#include <optional>
#include <stdexcept>

namespace {
void require(bool value, const char* message) { if (!value) throw std::runtime_error(message); }
struct NumberCodec final {
    static constexpr std::uint32_t schema_version = 7;
    static plotter::doc::StageBytes encode(const std::uint32_t value) {
        return {static_cast<std::uint8_t>(value), static_cast<std::uint8_t>(value >> 8U),
                static_cast<std::uint8_t>(value >> 16U), static_cast<std::uint8_t>(value >> 24U)};
    }
    static std::optional<std::uint32_t> decode(std::span<const std::uint8_t> bytes) {
        if (bytes.size() != 4U) return std::nullopt;
        return static_cast<std::uint32_t>(bytes[0]) | (static_cast<std::uint32_t>(bytes[1]) << 8U) |
            (static_cast<std::uint32_t>(bytes[2]) << 16U) | (static_cast<std::uint32_t>(bytes[3]) << 24U);
    }
};
}

int main() {
    const auto root = std::filesystem::temp_directory_path() / "plotter-stage-cache-smoke";
    std::error_code ignored;
    std::filesystem::remove_all(root, ignored);
    plotter::doc::StageCache cache({root, 3, 1024 * 1024});
    const std::string fingerprint = plotter::doc::StageCache::fingerprint("layout", "input-sha", "layout-v2", "{\"font\":\"abc\"}");
    const std::vector<std::uint8_t> payload{0, 1, 2, 255};
    cache.store("layout", fingerprint, payload);
    const auto hit = cache.load("layout", fingerprint);
    require(hit.hit && !hit.corrupt && hit.payload == payload, "versioned opaque payload must round-trip");
    cache.store_typed<std::uint32_t, NumberCodec>("read_document", fingerprint, 0x12345678U);
    const auto typed = cache.load_typed<std::uint32_t, NumberCodec>("read_document", fingerprint);
    require(typed.hit && !typed.corrupt && typed.value == 0x12345678U, "typed binary payload must round-trip");
    require(fingerprint == plotter::doc::StageCache::fingerprint("layout", "input-sha", "layout-v2", "{\"font\":\"abc\"}"), "fingerprint must be deterministic");
    require(fingerprint != plotter::doc::StageCache::fingerprint("layout", "input-sha", "layout-v3", "{\"font\":\"abc\"}"), "fingerprint must bind declared stage inputs");
    const auto source = root / "source.txt";
    { std::ofstream output(source, std::ios::binary); output << "source bytes"; }
    const auto import_key = plotter::doc::StageCache::import_fingerprint(source, "import-v1", "{\"pdf_math\":false}");
    require(import_key == plotter::doc::StageCache::import_fingerprint(source, "import-v1", "{\"pdf_math\":false}"), "import key must derive from source and config");
    require(import_key != plotter::doc::StageCache::import_fingerprint(source, "import-v2", "{\"pdf_math\":false}"), "import key must bind importer version");

    plotter::doc::Document document;
    document.source_path = "input.txt";
    document.metadata = {"fixture", std::string{"Title"}, {{"creator", "test"}}};
    document.warnings = {"warning"};
    plotter::doc::SourcePage page; page.source_page = 4; page.width = plotter::doc::Millimetres{210.0}; page.height = plotter::doc::Millimetres{297.0};
    plotter::doc::TextElement text; text.id = "text"; text.source_order = 1; text.source_page = 4;
    plotter::doc::Paragraph paragraph; paragraph.alignment = "center"; paragraph.line_spacing = 1.5; paragraph.tab_stops = {{plotter::doc::Millimetres{12.0}, "right"}};
    paragraph.runs.push_back({"hello", {std::string{"single"}, true, true, true, plotter::doc::Points{11.0}, std::string{"sup"}}, std::nullopt}); text.paragraphs.push_back(paragraph); page.elements.push_back(text);
    plotter::doc::RasterImageElement image; image.id = "image"; image.source_page = 4; image.width = plotter::doc::Pixels{640}; image.height = plotter::doc::Pixels{480}; image.anchor_type = "absolute"; image.rotation = plotter::doc::Degrees{15}; page.elements.push_back(image);
    plotter::doc::VectorElement vector; vector.id = "vector"; vector.paths.push_back({{{plotter::doc::Millimetres{1}, plotter::doc::Millimetres{2}}}, true, std::string{"vector"}, std::string{"path"}, std::string{"source"}, std::string{"role"}, std::string{"group"}, 4, true, 9}); page.elements.push_back(vector);
    plotter::doc::MathElement math; math.id = "math"; math.expression = "x^2"; math.source_syntax = "latex"; math.display_mode = true; math.absorbed_element_ids = {"text"}; math.detection_confidence = 0.8; page.elements.push_back(math);
    plotter::doc::LineElement line; line.id = "line"; line.start = {{1}, {2}}; line.end = {{3}, {4}}; line.line_width = plotter::doc::Millimetres{0.2}; line.dash_style = "dash"; line.semantic_role = "border"; page.elements.push_back(line);
    plotter::doc::ArrowElement arrow; arrow.id = "arrow"; arrow.points = {{{1}, {2}}, {{3}, {4}}}; arrow.head_at_start = true; arrow.head_style = "filled"; arrow.stroke_color = "#000"; page.elements.push_back(arrow);
    plotter::doc::TableElement table; table.id = "table"; table.rows = 1; table.columns = 1; table.column_widths = {{20}}; table.row_heights = {plotter::doc::Millimetres{8}}; table.cells.push_back({0, 0, 1, 1, {paragraph}, plotter::doc::Millimetres{20}, plotter::doc::Millimetres{8}, {true, false, true, false}, std::string{"middle"}}); page.elements.push_back(table);
    document.pages.push_back(page);
    cache.store_typed<plotter::doc::Document, plotter::doc::DocumentCodec>("read_document", fingerprint, document);
    const auto restored = cache.load_typed<plotter::doc::Document, plotter::doc::DocumentCodec>("read_document", fingerprint);
    require(restored.hit && restored.value.pages.size() == 1U && restored.value.pages[0].elements.size() == 7U, "document codec must round-trip every source element variant");
    require(std::get<plotter::doc::TextElement>(restored.value.pages[0].elements[0]).paragraphs[0].runs[0].style.bold, "document codec must retain text provenance");
    require(std::get<plotter::doc::TableElement>(restored.value.pages[0].elements[6]).cells[0].borders.right == false, "document codec must retain table provenance");
    std::get<plotter::doc::RasterImageElement>(document.pages[0].elements[1]).image_path = "/tmp/stale.png";
    bool rejected_external_asset = false;
    try { (void)plotter::doc::DocumentCodec::encode(document); } catch (const std::invalid_argument&) { rejected_external_asset = true; }
    require(rejected_external_asset, "document codec must reject nonpersistent external assets");
    { std::ofstream broken(cache.entry_path("layout", fingerprint), std::ios::binary | std::ios::trunc); broken << "broken"; }
    const auto corrupt = cache.load("layout", fingerprint);
    require(!corrupt.hit && corrupt.corrupt, "corrupted cache envelopes must become misses");
    plotter::doc::StageCache incompatible({root, 4, 1024 * 1024});
    cache.store("layout", fingerprint, payload);
    const auto version_miss = incompatible.load("layout", fingerprint);
    require(!version_miss.hit && version_miss.corrupt, "unsupported cache versions must become misses");
    std::filesystem::remove_all(root, ignored);
}
