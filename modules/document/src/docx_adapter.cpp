#include "plotter/doc/docx_adapter.hpp"

#include "plotter/doc/zip_archive.hpp"

#include <algorithm>
#include <charconv>
#include <cctype>
#include <cmath>
#include <fstream>
#include <map>
#include <optional>
#include <set>
#include <stdexcept>
#include <string_view>
#include <utility>
#include <vector>

namespace plotter::doc {
namespace {

constexpr double kTwipToMm = 25.4 / 1440.0;
constexpr double kEmuToMm = 1.0 / 36000.0;
constexpr double kDefaultPageWidthMm = 210.0;
constexpr double kDefaultPageHeightMm = 297.0;
constexpr double kDefaultMarginMm = 25.4;
constexpr double kPointToMm = 25.4 / 72.0;

[[nodiscard]] std::string padded_order(std::uint32_t order) {
    const auto digits = std::to_string(order + 1);
    return std::string(3 - std::min<std::size_t>(3, digits.size()), '0') + digits;
}

struct XmlNode final {
    std::string name;
    std::map<std::string, std::string> attributes;
    std::vector<XmlNode> children;
    std::string text;
};

[[nodiscard]] std::string local_name(std::string_view value) {
    const auto separator = value.find(':');
    return std::string{separator == std::string_view::npos ? value : value.substr(separator + 1)};
}

[[nodiscard]] std::string xml_unescape(std::string_view text) {
    std::string output;
    output.reserve(text.size());
    for (std::size_t i{}; i < text.size();) {
        if (text[i] != '&') { output += text[i++]; continue; }
        const auto end = text.find(';', i + 1);
        if (end == std::string_view::npos) throw std::runtime_error("unterminated XML entity");
        const auto entity = text.substr(i + 1, end - i - 1);
        if (entity == "amp") output += '&';
        else if (entity == "lt") output += '<';
        else if (entity == "gt") output += '>';
        else if (entity == "quot") output += '"';
        else if (entity == "apos") output += '\'';
        else if (entity.starts_with("#x") || entity.starts_with("#X") || entity.starts_with("#")) {
            unsigned int codepoint{};
            const auto digits = entity.substr(entity[0] == '#' && entity.size() > 1 && (entity[1] == 'x' || entity[1] == 'X') ? 2 : 1);
            const int base = entity.size() > 1 && (entity[1] == 'x' || entity[1] == 'X') ? 16 : 10;
            const auto [ptr, error] = std::from_chars(digits.data(), digits.data() + digits.size(), codepoint, base);
            if (error != std::errc{} || ptr != digits.data() + digits.size() || codepoint > 0x10ffffU) throw std::runtime_error("invalid XML entity");
            if (codepoint <= 0x7fU) output += static_cast<char>(codepoint);
            else if (codepoint <= 0x7ffU) { output += static_cast<char>(0xc0U | (codepoint >> 6U)); output += static_cast<char>(0x80U | (codepoint & 0x3fU)); }
            else if (codepoint <= 0xffffU) { output += static_cast<char>(0xe0U | (codepoint >> 12U)); output += static_cast<char>(0x80U | ((codepoint >> 6U) & 0x3fU)); output += static_cast<char>(0x80U | (codepoint & 0x3fU)); }
            else { output += static_cast<char>(0xf0U | (codepoint >> 18U)); output += static_cast<char>(0x80U | ((codepoint >> 12U) & 0x3fU)); output += static_cast<char>(0x80U | ((codepoint >> 6U) & 0x3fU)); output += static_cast<char>(0x80U | (codepoint & 0x3fU)); }
        } else throw std::runtime_error("unsupported XML entity");
        i = end + 1;
    }
    return output;
}

class XmlParser final {
public:
    explicit XmlParser(std::string_view xml) : xml_(xml) {}
    [[nodiscard]] XmlNode parse() {
        skip_misc();
        XmlNode root = node();
        skip_misc();
        if (pos_ != xml_.size()) throw std::runtime_error("trailing XML content");
        return root;
    }
private:
    void whitespace() { while (pos_ < xml_.size() && std::isspace(static_cast<unsigned char>(xml_[pos_]))) ++pos_; }
    [[nodiscard]] bool starts(std::string_view token) const { return xml_.substr(pos_, token.size()) == token; }
    void skip_until(std::string_view end) { const auto found = xml_.find(end, pos_); if (found == std::string_view::npos) throw std::runtime_error("unterminated XML construct"); pos_ = found + end.size(); }
    void skip_misc() { for (;;) { whitespace(); if (starts("<?")) { pos_ += 2; skip_until("?>"); } else if (starts("<!--")) { pos_ += 4; skip_until("-->"); } else break; } }
    [[nodiscard]] std::string name() {
        const auto start = pos_;
        while (pos_ < xml_.size() && (std::isalnum(static_cast<unsigned char>(xml_[pos_])) || xml_[pos_] == '_' || xml_[pos_] == ':' || xml_[pos_] == '-' || xml_[pos_] == '.')) ++pos_;
        if (start == pos_) throw std::runtime_error("invalid XML name");
        return std::string{xml_.substr(start, pos_ - start)};
    }
    [[nodiscard]] XmlNode node() {
        if (pos_ >= xml_.size() || xml_[pos_++] != '<') throw std::runtime_error("expected XML element");
        if (starts("!DOCTYPE") || starts("![CDATA[")) throw std::runtime_error("DOCTYPE and CDATA are unsupported");
        XmlNode out; out.name = local_name(name());
        for (;;) {
            whitespace();
            if (starts("/>")) { pos_ += 2; return out; }
            if (pos_ < xml_.size() && xml_[pos_] == '>') { ++pos_; break; }
            const auto key = local_name(name()); whitespace();
            if (pos_ >= xml_.size() || xml_[pos_++] != '=') throw std::runtime_error("invalid XML attribute");
            whitespace(); if (pos_ >= xml_.size() || (xml_[pos_] != '\'' && xml_[pos_] != '"')) throw std::runtime_error("invalid XML attribute quote");
            const char quote = xml_[pos_++]; const auto begin = pos_; while (pos_ < xml_.size() && xml_[pos_] != quote) ++pos_;
            if (pos_ == xml_.size()) throw std::runtime_error("unterminated XML attribute");
            out.attributes.emplace(key, xml_unescape(xml_.substr(begin, pos_++ - begin)));
        }
        for (;;) {
            if (pos_ == xml_.size()) throw std::runtime_error("unterminated XML element");
            if (starts("</")) { pos_ += 2; const auto closing = local_name(name()); whitespace(); if (pos_ >= xml_.size() || xml_[pos_++] != '>' || closing != out.name) throw std::runtime_error("mismatched XML element"); return out; }
            if (starts("<!--")) { pos_ += 4; skip_until("-->"); continue; }
            if (starts("<?")) { pos_ += 2; skip_until("?>"); continue; }
            if (xml_[pos_] == '<') out.children.push_back(node());
            else { const auto begin = pos_; while (pos_ < xml_.size() && xml_[pos_] != '<') ++pos_; out.text += xml_unescape(xml_.substr(begin, pos_ - begin)); }
        }
    }
    std::string_view xml_; std::size_t pos_{};
};

[[nodiscard]] const XmlNode* child(const XmlNode& node, std::string_view name) { for (const auto& candidate : node.children) if (candidate.name == name) return &candidate; return nullptr; }
[[nodiscard]] std::vector<const XmlNode*> children(const XmlNode& node, std::string_view name) { std::vector<const XmlNode*> out; for (const auto& candidate : node.children) if (candidate.name == name) out.push_back(&candidate); return out; }
[[nodiscard]] std::optional<std::string> attribute(const XmlNode& node, std::string_view name) { const auto found = node.attributes.find(std::string{name}); return found == node.attributes.end() ? std::nullopt : std::optional<std::string>{found->second}; }
[[nodiscard]] std::optional<double> decimal(const std::optional<std::string>& value) { if (!value) return std::nullopt; double result{}; const auto [ptr, error] = std::from_chars(value->data(), value->data() + value->size(), result); if (error != std::errc{} || ptr != value->data() + value->size()) return std::nullopt; return result; }
[[nodiscard]] std::optional<Millimetres> twips(const XmlNode* node, std::initializer_list<std::string_view> keys) { if (!node) return std::nullopt; for (const auto key : keys) if (const auto value = decimal(attribute(*node, key))) return Millimetres{*value * kTwipToMm}; return std::nullopt; }

struct ParagraphProperties final {
    std::optional<std::string> alignment;
    std::optional<Millimetres> first_line_indent, hanging_indent, left_indent, right_indent, space_before, space_after;
    std::optional<double> line_spacing;
    std::optional<std::vector<TabStop>> tab_stops;
};

[[nodiscard]] ParagraphProperties properties(const XmlNode& ppr, std::vector<std::string>& warnings) {
    ParagraphProperties out;
    if (const auto* jc = child(ppr, "jc")) { const auto raw = attribute(*jc, "val").value_or("left"); const std::map<std::string, std::string> map{{"left","left"},{"start","left"},{"right","right"},{"end","right"},{"center","center"},{"both","justify"},{"distribute","justify"}}; const auto found = map.find(raw); out.alignment = found == map.end() ? "left" : found->second; if (found == map.end()) warnings.push_back("docx_paragraph_alignment_approximated:" + raw); }
    const auto* indent = child(ppr, "ind"); out.first_line_indent = twips(indent, {"firstLine"}); out.hanging_indent = twips(indent, {"hanging"}); out.left_indent = twips(indent, {"left", "start"}); out.right_indent = twips(indent, {"right", "end"});
    const auto* spacing = child(ppr, "spacing"); out.space_before = twips(spacing, {"before"}); out.space_after = twips(spacing, {"after"});
    if (spacing) if (const auto line = decimal(attribute(*spacing, "line"))) { const auto rule = attribute(*spacing, "lineRule").value_or("auto"); out.line_spacing = *line / 240.0; if (rule != "auto") warnings.push_back("docx_line_spacing_approximated:" + rule); }
    if (const auto* tabs = child(ppr, "tabs")) { std::map<double, TabStop> stops; for (const auto* tab : children(*tabs, "tab")) { const auto position = decimal(attribute(*tab, "pos")); if (!position) continue; const auto kind = attribute(*tab, "val").value_or("left"); if (kind == "clear") { stops.erase(*position * kTwipToMm); continue; } if (kind == "bar") continue; std::string alignment = kind; if (kind != "left" && kind != "center" && kind != "right" && kind != "decimal") { alignment = "left"; warnings.push_back("docx_tab_stop_approximated:" + kind); } stops[*position * kTwipToMm] = TabStop{{*position * kTwipToMm}, alignment}; } std::vector<TabStop> values; for (auto& [_, stop] : stops) values.push_back(std::move(stop)); out.tab_stops = std::move(values); }
    return out;
}

void merge(ParagraphProperties& base, const ParagraphProperties& over) {
    if (over.alignment) base.alignment = over.alignment;
    if (over.first_line_indent) base.first_line_indent = over.first_line_indent;
    if (over.hanging_indent) base.hanging_indent = over.hanging_indent;
    if (over.left_indent) base.left_indent = over.left_indent;
    if (over.right_indent) base.right_indent = over.right_indent;
    if (over.space_before) base.space_before = over.space_before;
    if (over.space_after) base.space_after = over.space_after;
    if (over.line_spacing) base.line_spacing = over.line_spacing;
    if (over.tab_stops) base.tab_stops = over.tab_stops;
}

struct Style final { std::string id, name, based_on; ParagraphProperties ppr; };
struct StyleBook final { ParagraphProperties defaults; std::map<std::string, Style> styles; };

[[nodiscard]] StyleBook load_styles(const XmlNode* root, std::vector<std::string>& warnings) {
    StyleBook book; if (!root) return book;
    if (const auto* defaults = child(*root, "docDefaults")) if (const auto* ppr_default = child(*defaults, "pPrDefault")) if (const auto* ppr = child(*ppr_default, "pPr")) book.defaults = properties(*ppr, warnings);
    for (const auto* node : children(*root, "style")) { if (attribute(*node, "type").value_or("") != "paragraph") continue; Style style; style.id = attribute(*node, "styleId").value_or(""); if (style.id.empty()) continue; if (const auto* name = child(*node, "name")) style.name = attribute(*name, "val").value_or(""); if (const auto* based = child(*node, "basedOn")) style.based_on = attribute(*based, "val").value_or(""); if (const auto* ppr = child(*node, "pPr")) style.ppr = properties(*ppr, warnings); book.styles.emplace(style.id, std::move(style)); }
    return book;
}

[[nodiscard]] std::string semantic_role(std::string_view id, std::string_view name) { std::string value{id}; value += ' '; value += name; std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); }); if (value.find("title") != std::string::npos) return "title"; for (int level = 1; level <= 3; ++level) if (value.find("heading " + std::to_string(level)) != std::string::npos || value.find("heading" + std::to_string(level)) != std::string::npos) return "heading_" + std::to_string(level); return "body"; }

[[nodiscard]] ParagraphProperties resolved_properties(const XmlNode& paragraph, const StyleBook& styles, std::vector<std::string>& warnings, std::optional<std::string>& id, std::optional<std::string>& name) {
    ParagraphProperties out = styles.defaults; const auto* ppr = child(paragraph, "pPr"); if (ppr) if (const auto* style = child(*ppr, "pStyle")) id = attribute(*style, "val");
    std::vector<const Style*> chain; std::set<std::string> seen; auto current = id.value_or(""); while (!current.empty()) { const auto found = styles.styles.find(current); if (found == styles.styles.end()) break; if (!seen.insert(current).second) { warnings.push_back("docx_paragraph_style_cycle:" + current); break; } chain.push_back(&found->second); current = found->second.based_on; }
    for (auto it = chain.rbegin(); it != chain.rend(); ++it) { merge(out, (*it)->ppr); name = (*it)->name; }
    if (ppr) merge(out, properties(*ppr, warnings));
    return out;
}

[[nodiscard]] TextStyle run_style(const XmlNode& run, std::vector<std::string>& warnings) {
    TextStyle style; const auto* rpr = child(run, "rPr"); if (!rpr) return style;
    if (const auto* underline = child(*rpr, "u")) { const auto raw = attribute(*underline, "val").value_or("single"); if (raw != "none" && raw != "false" && raw != "0") { style.underline = (raw == "single" || raw == "double" || raw == "words") ? raw : "single"; if (*style.underline != raw) warnings.push_back("docx_underline_style_approximated:" + raw); } }
    style.strike = child(*rpr, "strike") != nullptr; style.bold = child(*rpr, "b") != nullptr; style.italic = child(*rpr, "i") != nullptr;
    if (const auto* size = child(*rpr, "sz")) if (const auto half_points = decimal(attribute(*size, "val"))) style.font_size = Points{*half_points / 2.0};
    if (const auto* vertical = child(*rpr, "vertAlign")) style.baseline_shift = attribute(*vertical, "val");
    return style;
}

[[nodiscard]] bool contains_descendant(const XmlNode& node, std::string_view name) { for (const auto& candidate : node.children) if (candidate.name == name || contains_descendant(candidate, name)) return true; return false; }

void descendants(const XmlNode& node, std::string_view name, std::vector<const XmlNode*>& out) {
    for (const auto& candidate : node.children) {
        if (candidate.name == name) out.push_back(&candidate);
        descendants(candidate, name, out);
    }
}

[[nodiscard]] std::string descendant_text(const XmlNode& node) {
    std::string output = node.text;
    for (const auto& candidate : node.children) output += descendant_text(candidate);
    return output;
}

[[nodiscard]] std::optional<double> number_prefix(std::string_view value) {
    std::size_t length{};
    while (length < value.size() && (std::isdigit(static_cast<unsigned char>(value[length])) || value[length] == '.' || value[length] == '-' || value[length] == '+')) ++length;
    return decimal(length == 0 ? std::nullopt : std::optional<std::string>{std::string{value.substr(0, length)}});
}

[[nodiscard]] std::optional<Millimetres> vml_length(std::string_view value) {
    const auto number = number_prefix(value);
    if (!number) return std::nullopt;
    const auto unit_start = value.find_first_not_of("+-0123456789.");
    const auto unit = unit_start == std::string_view::npos ? std::string_view{} : value.substr(unit_start);
    if (unit == "pt" || unit.empty()) return Millimetres{*number * kPointToMm};
    if (unit == "in") return Millimetres{*number * 25.4};
    if (unit == "cm") return Millimetres{*number * 10.0};
    if (unit == "mm") return Millimetres{*number};
    return std::nullopt;
}

[[nodiscard]] Paragraph parse_paragraph(const XmlNode& node, const StyleBook& styles, std::vector<std::string>& warnings) {
    Paragraph out; std::optional<std::string> id, name; const auto format = resolved_properties(node, styles, warnings, id, name);
    out.alignment = format.alignment; out.first_line_indent = format.first_line_indent; out.hanging_indent = format.hanging_indent; out.left_indent = format.left_indent; out.right_indent = format.right_indent; out.space_before = format.space_before; out.space_after = format.space_after; out.line_spacing = format.line_spacing; if (format.tab_stops) out.tab_stops = *format.tab_stops; out.style_id = id; out.style_name = name; out.semantic_role = semantic_role(id.value_or(""), name.value_or(""));
    for (const auto& member : node.children) { if (member.name != "r") continue; std::string text; for (const auto& part : member.children) { if (part.name == "t") text += part.text; else if (part.name == "tab") text += '\t'; else if (part.name == "br" || part.name == "cr") text += '\n'; else if (part.name == "drawing" || part.name == "pict") { } } if (!text.empty()) out.runs.push_back(TextRun{std::move(text), run_style(member, warnings), std::nullopt}); }
    return out;
}


[[nodiscard]] std::string relationship_target(const ZipArchive& archive, std::string_view id, std::vector<std::string>& warnings) {
    constexpr std::string_view kRelationships = "word/_rels/document.xml.rels";
    if (!archive.contains(kRelationships)) { warnings.push_back("docx_relationships_missing"); return {}; }
    const auto root = XmlParser{archive.read_text(kRelationships)}.parse();
    for (const auto* relation : children(root, "Relationship")) {
        if (attribute(*relation, "Id").value_or("") != id) continue;
        if (attribute(*relation, "TargetMode").value_or("") == "External") { warnings.push_back("docx_external_image_relationship:" + std::string{id}); return {}; }
        auto target = attribute(*relation, "Target").value_or("");
        if (target.empty() || target.starts_with("/") || target.find("..") != std::string::npos) { warnings.push_back("docx_image_target_invalid:" + std::string{id}); return {}; }
        return "word/" + target;
    }
    warnings.push_back("docx_image_relationship_missing:" + std::string{id});
    return {};
}

[[nodiscard]] std::pair<Pixels, Pixels> image_size(std::string_view bytes) {
    const auto byte = [&bytes](std::size_t index) -> unsigned char { return static_cast<unsigned char>(bytes[index]); };
    if (bytes.size() >= 24 && bytes.substr(1, 3) == "PNG") return {{static_cast<double>((byte(16) << 24U) | (byte(17) << 16U) | (byte(18) << 8U) | byte(19))}, {static_cast<double>((byte(20) << 24U) | (byte(21) << 16U) | (byte(22) << 8U) | byte(23))}};
    if (bytes.size() >= 10 && byte(0) == 0xffU && byte(1) == 0xd8U) {
        for (std::size_t pos = 2; pos + 9 < bytes.size();) {
            if (byte(pos++) != 0xffU) continue;
            const auto type = byte(pos++); if (type == 0xd8U || type == 0xd9U) continue;
            const auto length = static_cast<std::size_t>((byte(pos) << 8U) | byte(pos + 1));
            if (length < 2 || pos + length > bytes.size()) break;
            if ((type >= 0xc0U && type <= 0xc3U) || (type >= 0xc5U && type <= 0xc7U) || (type >= 0xc9U && type <= 0xcbU) || (type >= 0xcdU && type <= 0xcfU)) return {{static_cast<double>((byte(pos + 5) << 8U) | byte(pos + 6))}, {static_cast<double>((byte(pos + 3) << 8U) | byte(pos + 4))}};
            pos += length;
        }
    }
    return {{}, {}};
}

[[nodiscard]] std::filesystem::path extract_asset(const ZipArchive& archive, const std::filesystem::path& source, std::string_view target, std::map<std::string, std::filesystem::path>& cache, std::vector<std::string>& warnings) {
    const auto cached = cache.find(std::string{target}); if (cached != cache.end()) return cached->second;
    if (!archive.contains(target)) { warnings.push_back("docx_image_part_missing:" + std::string{target}); return {}; }
    const auto extension = std::filesystem::path{std::string{target}}.extension().string();
    const auto& directory = source;
    const auto output = directory / ("image-" + std::to_string(cache.size() + 1) + extension);
    std::error_code error; std::filesystem::create_directories(directory, error);
    if (error) { warnings.push_back("docx_asset_directory_failed:" + error.message()); return {}; }
    std::ofstream file(output, std::ios::binary | std::ios::trunc);
    const auto bytes = archive.read_text(target);
    file.write(bytes.data(), static_cast<std::streamsize>(bytes.size()));
    if (!file) { warnings.push_back("docx_asset_write_failed:" + output.string()); return {}; }
    cache.emplace(std::string{target}, output); return output;
}

[[nodiscard]] std::string wrap_mode(const XmlNode& anchor, std::string& side) {
    side = "both";
    for (const auto& value : anchor.children) {
        if (value.name == "wrapSquare") { side = attribute(value, "wrapText").value_or("bothSides"); if (side == "left") side = "left"; else if (side == "right") side = "right"; else side = "both"; return "square"; }
        if (value.name == "wrapTopAndBottom") return "top_bottom";
        if (value.name == "wrapNone") return "none";
        if (value.name == "wrapTight" || value.name == "wrapThrough") return "tight";
    }
    return "none";
}

[[nodiscard]] std::optional<Rect> anchor_bounds(const XmlNode& anchor, double page_width, double page_height, double left, double top, Millimetres width, Millimetres height) {
    const auto* horizontal = child(anchor, "positionH"); const auto* vertical = child(anchor, "positionV");
    const auto offset = [](const XmlNode* position) { const auto* value = position ? child(*position, "posOffset") : nullptr; return value ? decimal(value->text).value_or(0.0) * kEmuToMm : 0.0; };
    double x = offset(horizontal), y = offset(vertical);
    const auto h_align = horizontal && child(*horizontal, "align") ? child(*horizontal, "align")->text : "";
    const auto v_align = vertical && child(*vertical, "align") ? child(*vertical, "align")->text : "";
    if (h_align == "center") x = (page_width - width.value) / 2.0; else if (h_align == "right") x = page_width - left - width.value; else if (h_align == "left") x = left;
    if (v_align == "center") y = (page_height - height.value) / 2.0; else if (v_align == "bottom") y = page_height - top - height.value; else if (v_align == "top") y = top;
    return Rect{{x}, {y}, width, height};
}

[[nodiscard]] std::optional<RasterImageElement> parse_image(const XmlNode& drawing, const ZipArchive& archive, const std::filesystem::path& source, std::map<std::string, std::filesystem::path>& cache, std::vector<std::string>& warnings, std::uint32_t order, double page_width, double page_height, double left, double top) {
    std::vector<const XmlNode*> blips; descendants(drawing, "blip", blips); if (blips.empty()) { warnings.push_back("docx_drawing_without_image"); return std::nullopt; }
    const auto relation = attribute(*blips.front(), "embed"); if (!relation) { warnings.push_back("docx_image_relationship_missing"); return std::nullopt; }
    const auto target = relationship_target(archive, *relation, warnings); if (target.empty()) return std::nullopt;
    const auto asset = extract_asset(archive, source, target, cache, warnings); if (asset.empty()) return std::nullopt;
    const auto pixels = image_size(archive.read_text(target));
    std::vector<const XmlNode*> inline_nodes, anchor_nodes, extents, transforms; descendants(drawing, "inline", inline_nodes); descendants(drawing, "anchor", anchor_nodes); descendants(drawing, "extent", extents); descendants(drawing, "xfrm", transforms);
    const auto* container = !anchor_nodes.empty() ? anchor_nodes.front() : (!inline_nodes.empty() ? inline_nodes.front() : nullptr);
    const auto* extent = !extents.empty() ? extents.front() : nullptr;
    const Millimetres displayed_width{extent ? decimal(attribute(*extent, "cx")).value_or(0.0) * kEmuToMm : 0.0};
    const Millimetres displayed_height{extent ? decimal(attribute(*extent, "cy")).value_or(0.0) * kEmuToMm : 0.0};
    RasterImageElement image; image.id = "page-001-image-" + padded_order(order); image.source_order = order; image.source_page = 0; image.image_path = asset.string(); image.width = pixels.first; image.height = pixels.second;
    if (displayed_width.value > 0.0) image.displayed_width = displayed_width;
    if (displayed_height.value > 0.0) image.displayed_height = displayed_height;
    if (container && !anchor_nodes.empty()) {
        image.anchor_type = "anchored"; image.bounds = anchor_bounds(*container, page_width, page_height, left, top, displayed_width, displayed_height);
        image.wrap_mode = wrap_mode(*container, image.wrap_side); image.behind_text = attribute(*container, "behindDoc").value_or("0") == "1";
        image.z_order = static_cast<std::int32_t>(decimal(attribute(*container, "relativeHeight")).value_or(0.0));
        image.distance_left = Millimetres{decimal(attribute(*container, "distL")).value_or(0.0) * kEmuToMm}; image.distance_right = Millimetres{decimal(attribute(*container, "distR")).value_or(0.0) * kEmuToMm}; image.distance_top = Millimetres{decimal(attribute(*container, "distT")).value_or(0.0) * kEmuToMm}; image.distance_bottom = Millimetres{decimal(attribute(*container, "distB")).value_or(0.0) * kEmuToMm};
        if (const auto* h = child(*container, "positionH")) { image.relative_to_h = attribute(*h, "relativeFrom"); if (const auto* value = child(*h, "posOffset")) image.anchor_offset_x = Millimetres{decimal(value->text).value_or(0.0) * kEmuToMm}; }
        if (const auto* v = child(*container, "positionV")) { image.relative_to_v = attribute(*v, "relativeFrom"); if (const auto* value = child(*v, "posOffset")) image.anchor_offset_y = Millimetres{decimal(value->text).value_or(0.0) * kEmuToMm}; }
    }
    if (!transforms.empty()) image.rotation = Degrees{decimal(attribute(*transforms.front(), "rot")).value_or(0.0) / 60000.0};
    if (pixels.first.value == 0.0 || pixels.second.value == 0.0) warnings.push_back("docx_image_dimensions_unknown:" + target);
    return image;
}


[[nodiscard]] TableElement parse_table(const XmlNode& node, const StyleBook& styles, std::vector<std::string>& warnings, std::uint32_t order) {
    TableElement table; table.id = "page-001-table-" + padded_order(order); table.source_order = order; table.source_page = 0;
    if (const auto* properties = child(node, "tblPr")) { if (const auto* justification = child(*properties, "jc")) table.alignment = attribute(*justification, "val"); if (const auto* indent = child(*properties, "tblInd")) table.left_indent = twips(indent, {"w"}); if (const auto* width = child(*properties, "tblW")) table.preferred_width = twips(width, {"w"}); }
    if (const auto* grid = child(node, "tblGrid")) for (const auto* column : children(*grid, "gridCol")) if (const auto width = twips(column, {"w"})) table.column_widths.push_back(*width);
    struct ActiveMerge final { std::size_t cell_index{}; std::uint32_t row{}; };
    std::map<std::uint32_t, ActiveMerge> vertical;
    const auto rows = children(node, "tr"); table.rows = static_cast<std::uint32_t>(rows.size());
    for (std::uint32_t row = 0; row < table.rows; ++row) {
        const auto& source_row = *rows[row]; std::optional<Millimetres> row_height;
        if (const auto* properties = child(source_row, "trPr")) { if (const auto* height = child(*properties, "trHeight")) row_height = twips(height, {"val"}); if (child(*properties, "tblHeader")) ++table.repeat_header_rows; }
        table.row_heights.push_back(row_height); std::uint32_t column{};
        for (const auto* source_cell : children(source_row, "tc")) {
            const auto* properties = child(*source_cell, "tcPr"); const auto span = static_cast<std::uint32_t>(std::max(1.0, properties && child(*properties, "gridSpan") ? decimal(attribute(*child(*properties, "gridSpan"), "val")).value_or(1.0) : 1.0));
            const auto* merge = properties ? child(*properties, "vMerge") : nullptr; const auto merge_value = merge ? attribute(*merge, "val").value_or("continue") : "";
            if (merge && merge_value != "restart") {
                const auto active = vertical.find(column);
                if (active != vertical.end()) { table.cells[active->second.cell_index].row_span = row - active->second.row + 1; column += span; continue; }
                warnings.push_back("docx_table_vmerge_without_restart");
            }
            TableCell cell; cell.row = row; cell.column = column; cell.column_span = span; cell.height = row_height;
            if (properties) { if (const auto* width = child(*properties, "tcW")) cell.width = twips(width, {"w"}); if (const auto* valign = child(*properties, "vAlign")) cell.vertical_alignment = attribute(*valign, "val"); if (const auto* borders = child(*properties, "tcBorders")) { const auto enabled = [borders](std::string_view side) { const auto* border = child(*borders, side); const auto value = border ? attribute(*border, "val").value_or("single") : "single"; return value != "nil" && value != "none"; }; cell.borders = {enabled("top"), enabled("right"), enabled("bottom"), enabled("left")}; } }
            for (const auto& member : source_cell->children) if (member.name == "p") cell.paragraphs.push_back(parse_paragraph(member, styles, warnings));
            const auto index = table.cells.size(); table.cells.push_back(std::move(cell)); if (merge && merge_value == "restart") vertical[column] = {index, row}; column += span;
        }
        table.columns = std::max(table.columns, column);
    }
    if (!table.column_widths.empty() && table.column_widths.size() != table.columns) warnings.push_back("docx_table_grid_columns_mismatch");
    return table;
}

[[nodiscard]] std::optional<Point> vml_point(std::string_view value) {
    const auto comma = value.find(','); if (comma == std::string_view::npos) return std::nullopt;
    const auto x = vml_length(value.substr(0, comma)); const auto y = vml_length(value.substr(comma + 1)); if (!x || !y) return std::nullopt;
    return Point{*x, *y};
}

void parse_vml_lines(const XmlNode& pict, std::vector<SourceElement>& elements, std::uint32_t& order, std::vector<std::string>& warnings) {
    std::vector<const XmlNode*> lines; descendants(pict, "line", lines);
    for (const auto* line : lines) {
        const auto start = vml_point(attribute(*line, "from").value_or("0,0")); const auto end = vml_point(attribute(*line, "to").value_or("0,0"));
        if (!start || !end) { warnings.push_back("docx_vml_line_coordinates_invalid"); continue; }
        const auto* stroke = child(*line, "stroke"); const auto start_style = stroke ? attribute(*stroke, "startarrow").value_or("none") : "none"; const auto end_style = stroke ? attribute(*stroke, "endarrow").value_or("none") : "none";
        const auto bbox = Rect{{std::min(start->x.value, end->x.value)}, {std::min(start->y.value, end->y.value)}, {std::abs(end->x.value - start->x.value)}, {std::abs(end->y.value - start->y.value)}};
        if (start_style != "none" || end_style != "none") { ArrowElement arrow; arrow.id = "page-001-arrow-" + padded_order(order); arrow.source_order = order++; arrow.source_page = 0; arrow.points = {*start, *end}; arrow.head_at_start = start_style != "none"; arrow.head_at_end = end_style != "none"; arrow.head_style = arrow.head_at_end ? end_style : start_style; arrow.start_head_style = start_style; arrow.end_head_style = end_style; arrow.stroke_color = attribute(*line, "strokecolor"); arrow.line_width = vml_length(attribute(*line, "strokeweight").value_or("")); arrow.bounds = bbox; elements.emplace_back(std::move(arrow)); }
        else { LineElement plain; plain.id = "page-001-line-" + padded_order(order); plain.source_order = order++; plain.source_page = 0; plain.start = *start; plain.end = *end; plain.line_width = vml_length(attribute(*line, "strokeweight").value_or("")); plain.bounds = bbox; elements.emplace_back(std::move(plain)); }
    }
}

void unique_warnings(std::vector<std::string>& warnings) { std::vector<std::string> unique; std::set<std::string> seen; for (auto& warning : warnings) if (seen.insert(warning).second) unique.push_back(std::move(warning)); warnings = std::move(unique); }

}  // namespace

ImportResult read_docx_document(const std::filesystem::path& source_path, const std::filesystem::path& assets_dir) {
    try {
        std::uint64_t asset_key = 1469598103934665603ULL;
        for (unsigned char c : source_path.lexically_normal().string()) { asset_key ^= c; asset_key *= 1099511628211ULL; }
        const auto asset_root = assets_dir.empty()
            ? std::filesystem::temp_directory_path() / "plotter-doc-assets" / (source_path.stem().string() + "-" + std::to_string(asset_key))
            : assets_dir;
        const auto archive = ZipArchive::open(source_path);
        if (!archive.contains("word/document.xml")) return ImportError{"DOCX package has no word/document.xml: " + source_path.string()};
        std::vector<std::string> warnings;
        const auto document_xml = XmlParser{archive.read_text("word/document.xml")}.parse();
        const std::optional<XmlNode> styles_xml = archive.contains("word/styles.xml") ? std::optional<XmlNode>{XmlParser{archive.read_text("word/styles.xml")}.parse()} : std::nullopt;
        const auto styles = load_styles(styles_xml ? &*styles_xml : nullptr, warnings);
        const auto* body = child(document_xml, "body"); if (!body) return ImportError{"DOCX document has no body: " + source_path.string()};
        double width = kDefaultPageWidthMm, height = kDefaultPageHeightMm, left = kDefaultMarginMm, right = kDefaultMarginMm, top = kDefaultMarginMm, bottom = kDefaultMarginMm;
        if (const auto* sect = child(*body, "sectPr")) { if (const auto* page = child(*sect, "pgSz")) { if (const auto value = decimal(attribute(*page, "w"))) width = *value * kTwipToMm; if (const auto value = decimal(attribute(*page, "h"))) height = *value * kTwipToMm; } if (const auto* margins = child(*sect, "pgMar")) { if (const auto value = decimal(attribute(*margins, "left"))) left = *value * kTwipToMm; if (const auto value = decimal(attribute(*margins, "right"))) right = *value * kTwipToMm; if (const auto value = decimal(attribute(*margins, "top"))) top = *value * kTwipToMm; if (const auto value = decimal(attribute(*margins, "bottom"))) bottom = *value * kTwipToMm; } }
        SourcePage page; page.source_page = 0; page.width = Millimetres{width}; page.height = Millimetres{height}; page.content_bounds = Rect{{left}, {top}, {std::max(0.0, width - left - right)}, {std::max(0.0, height - top - bottom)}};
        std::map<std::string, std::filesystem::path> assets; std::uint32_t order{};
        for (const auto& item : body->children) {
            if (item.name == "p") {
                const auto paragraph = parse_paragraph(item, styles, warnings);
                if (!paragraph.runs.empty()) { TextElement text; text.id = "page-001-text-" + padded_order(order); text.source_order = order++; text.source_page = 0; text.paragraphs.push_back(paragraph); page.elements.emplace_back(std::move(text)); }
                std::vector<const XmlNode*> drawings; descendants(item, "drawing", drawings);
                for (const auto* drawing : drawings) if (const auto image = parse_image(*drawing, archive, asset_root, assets, warnings, order, width, height, left, top)) { auto placed = *image; placed.source_order = order++; page.elements.emplace_back(std::move(placed)); }
                std::vector<const XmlNode*> maths; descendants(item, "oMath", maths);
                for (const auto* math : maths) { MathElement equation; equation.id = "page-001-math-" + padded_order(order); equation.source_order = order++; equation.source_page = 0; equation.expression = descendant_text(*math); equation.source_syntax = "omml"; equation.display_mode = false; if (equation.expression.empty()) warnings.push_back("docx_omml_empty_equation"); page.elements.emplace_back(std::move(equation)); }
                std::vector<const XmlNode*> picts; descendants(item, "pict", picts); for (const auto* pict : picts) parse_vml_lines(*pict, page.elements, order, warnings);
            } else if (item.name == "tbl") page.elements.emplace_back(parse_table(item, styles, warnings, order++));
            else if (item.name != "sectPr") warnings.push_back("docx_body_element_not_supported:" + item.name);
        }
        unique_warnings(warnings); Document result; result.source_path = source_path.string(); result.pages.push_back(std::move(page)); result.warnings = std::move(warnings); result.metadata.source_format = "docx"; return result;
    } catch (const std::exception& error) { return ImportError{"Cannot read DOCX document " + source_path.string() + ": " + error.what()}; }
}

}  // namespace plotter::doc
