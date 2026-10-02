#include "plotter/doc/document_codec.hpp"

#include <bit>
#include <limits>
#include <stdexcept>
#include <utility>

namespace plotter::doc {
namespace {
constexpr std::uint64_t kMaxItems = 16ULL * 1024ULL * 1024ULL;

struct W final {
    StageBytes b;
    void u8(std::uint8_t v) { b.push_back(v); }
    void u32(std::uint32_t v) { for (unsigned i = 0; i != 4U; ++i) u8(static_cast<std::uint8_t>(v >> (i * 8U))); }
    void i32(std::int32_t v) { u32(std::bit_cast<std::uint32_t>(v)); }
    void u64(std::uint64_t v) { for (unsigned i = 0; i != 8U; ++i) u8(static_cast<std::uint8_t>(v >> (i * 8U))); }
    void i64(std::int64_t v) { u64(std::bit_cast<std::uint64_t>(v)); }
    void d(double v) { u64(std::bit_cast<std::uint64_t>(v)); }
    void s(std::string_view v) { u64(v.size()); b.insert(b.end(), v.begin(), v.end()); }
    void flag(bool v) { u8(v ? 1U : 0U); }
    template <typename T, typename F> void opt(const std::optional<T>& v, F f) { flag(v.has_value()); if (v) f(*v); }
    template <typename T, typename F> void vec(const std::vector<T>& v, F f) { u64(v.size()); for (const auto& x : v) f(x); }
};
struct R final {
    std::span<const std::uint8_t> b; std::size_t p{};
    [[nodiscard]] std::uint8_t u8() { if (p == b.size()) throw std::runtime_error("truncated document cache"); return b[p++]; }
    [[nodiscard]] bool flag() { const auto v=u8(); if (v > 1U) throw std::runtime_error("invalid document cache boolean"); return v != 0U; }
    [[nodiscard]] std::uint32_t u32() { std::uint32_t v{}; for(unsigned i=0;i!=4U;++i) v|=static_cast<std::uint32_t>(u8())<<(i*8U); return v; }
    [[nodiscard]] std::int32_t i32() { return std::bit_cast<std::int32_t>(u32()); }
    [[nodiscard]] std::uint64_t u64() { std::uint64_t v{}; for(unsigned i=0;i!=8U;++i) v|=static_cast<std::uint64_t>(u8())<<(i*8U); return v; }
    [[nodiscard]] std::int64_t i64() { return std::bit_cast<std::int64_t>(u64()); }
    [[nodiscard]] double d() { return std::bit_cast<double>(u64()); }
    [[nodiscard]] std::string s() { const auto n=u64(); if(n > kMaxItems || n > b.size()-p) throw std::runtime_error("invalid document cache string"); std::string v(reinterpret_cast<const char*>(b.data()+p), static_cast<std::size_t>(n)); p += static_cast<std::size_t>(n); return v; }
    template <typename T, typename F> [[nodiscard]] std::optional<T> opt(F f) { if(!flag()) return std::nullopt; return f(); }
    template <typename T, typename F> [[nodiscard]] std::vector<T> vec(F f) { const auto n=u64(); if(n>kMaxItems) throw std::runtime_error("invalid document cache count"); std::vector<T> v; v.reserve(static_cast<std::size_t>(n)); for(std::uint64_t i=0;i<n;++i) v.push_back(f()); return v; }
};
void point(W& w,const Point& x){w.d(x.x.value);w.d(x.y.value);} Point point(R&r){return {{r.d()},{r.d()}};}
void rect(W&w,const Rect&x){w.d(x.x.value);w.d(x.y.value);w.d(x.width.value);w.d(x.height.value);} Rect rect(R&r){return {{r.d()},{r.d()},{r.d()},{r.d()}};}
void mmopt(W&w,const std::optional<Millimetres>&x){w.opt(x,[&](auto v){w.d(v.value);});} std::optional<Millimetres> mmopt(R&r){return r.opt<Millimetres>([&]{return Millimetres{r.d()};});}
void stropt(W&w,const std::optional<std::string>&x){w.opt(x,[&](const auto&v){w.s(v);});} std::optional<std::string> stropt(R&r){return r.opt<std::string>([&]{return r.s();});}
void rectopt(W&w,const std::optional<Rect>&x){w.opt(x,[&](const auto&v){rect(w,v);});} std::optional<Rect> rectopt(R&r){return r.opt<Rect>([&]{return rect(r);});}
void style(W&w,const TextStyle&x){stropt(w,x.underline);w.flag(x.strike);w.flag(x.bold);w.flag(x.italic);w.opt(x.font_size,[&](Points v){w.d(v.value);});stropt(w,x.baseline_shift);} TextStyle style(R&r){TextStyle x; x.underline=stropt(r);x.strike=r.flag();x.bold=r.flag();x.italic=r.flag();x.font_size=r.opt<Points>([&]{return Points{r.d()};});x.baseline_shift=stropt(r);return x;}
void run(W&w,const TextRun&x){w.s(x.text);style(w,x.style);rectopt(w,x.bounds);} TextRun run(R&r){TextRun x;x.text=r.s();x.style=style(r);x.bounds=rectopt(r);return x;}
void paragraph(W&w,const Paragraph&x){w.vec(x.runs,[&](const auto&v){run(w,v);});stropt(w,x.alignment);mmopt(w,x.first_line_indent);mmopt(w,x.hanging_indent);mmopt(w,x.left_indent);mmopt(w,x.right_indent);mmopt(w,x.space_before);mmopt(w,x.space_after);w.opt(x.line_spacing,[&](double v){w.d(v);});w.vec(x.tab_stops,[&](const TabStop&v){w.d(v.position.value);w.s(v.alignment);});stropt(w,x.style_id);stropt(w,x.style_name);stropt(w,x.semantic_role);rectopt(w,x.bounds);} Paragraph paragraph(R&r){Paragraph x;x.runs=r.vec<TextRun>([&]{return run(r);});x.alignment=stropt(r);x.first_line_indent=mmopt(r);x.hanging_indent=mmopt(r);x.left_indent=mmopt(r);x.right_indent=mmopt(r);x.space_before=mmopt(r);x.space_after=mmopt(r);x.line_spacing=r.opt<double>([&]{return r.d();});x.tab_stops=r.vec<TabStop>([&]{return TabStop{{r.d()},r.s()};});x.style_id=stropt(r);x.style_name=stropt(r);x.semantic_role=stropt(r);x.bounds=rectopt(r);return x;}
void common(W&w,const std::string&id,std::uint32_t o,std::uint32_t p){w.s(id);w.u32(o);w.u32(p);} void common(R&r,std::string&id,std::uint32_t&o,std::uint32_t&p){id=r.s();o=r.u32();p=r.u32();}
void vector_path(W&w,const VectorPath&x){w.vec(x.points,[&](const auto&v){point(w,v);});w.flag(x.closed);stropt(w,x.element_id);stropt(w,x.element_type);stropt(w,x.source_path);stropt(w,x.semantic_role);stropt(w,x.layout_group);w.opt(x.source_page,[&](std::uint32_t v){w.u32(v);});w.flag(x.preserve_order);w.i32(x.z_order);} VectorPath vector_path(R&r){VectorPath x;x.points=r.vec<Point>([&]{return point(r);});x.closed=r.flag();x.element_id=stropt(r);x.element_type=stropt(r);x.source_path=stropt(r);x.semantic_role=stropt(r);x.layout_group=stropt(r);x.source_page=r.opt<std::uint32_t>([&]{return r.u32();});x.preserve_order=r.flag();x.z_order=r.i32();return x;}
void text(W&w,const TextElement&x){common(w,x.id,x.source_order,x.source_page);w.vec(x.paragraphs,[&](const auto&v){paragraph(w,v);});rectopt(w,x.bounds);} TextElement text(R&r){TextElement x;common(r,x.id,x.source_order,x.source_page);x.paragraphs=r.vec<Paragraph>([&]{return paragraph(r);});x.bounds=rectopt(r);return x;}
void image(W&w,const RasterImageElement&x){common(w,x.id,x.source_order,x.source_page);w.s(x.image_path);w.d(x.width.value);w.d(x.height.value);mmopt(w,x.displayed_width);mmopt(w,x.displayed_height);rectopt(w,x.bounds);w.s(x.anchor_type);w.s(x.wrap_mode);w.s(x.wrap_side);w.d(x.distance_left.value);w.d(x.distance_right.value);w.d(x.distance_top.value);w.d(x.distance_bottom.value);stropt(w,x.relative_to_h);stropt(w,x.relative_to_v);w.flag(x.behind_text);w.i32(x.z_order);w.d(x.rotation.value);w.d(x.anchor_offset_x.value);w.d(x.anchor_offset_y.value);} RasterImageElement image(R&r){RasterImageElement x;common(r,x.id,x.source_order,x.source_page);x.image_path=r.s();x.width={r.d()};x.height={r.d()};x.displayed_width=mmopt(r);x.displayed_height=mmopt(r);x.bounds=rectopt(r);x.anchor_type=r.s();x.wrap_mode=r.s();x.wrap_side=r.s();x.distance_left={r.d()};x.distance_right={r.d()};x.distance_top={r.d()};x.distance_bottom={r.d()};x.relative_to_h=stropt(r);x.relative_to_v=stropt(r);x.behind_text=r.flag();x.z_order=r.i32();x.rotation={r.d()};x.anchor_offset_x={r.d()};x.anchor_offset_y={r.d()};return x;}
void vector(W&w,const VectorElement&x){common(w,x.id,x.source_order,x.source_page);w.vec(x.paths,[&](const auto&v){vector_path(w,v);});rectopt(w,x.bounds);w.s(x.anchor_type);w.s(x.wrap_mode);w.s(x.wrap_side);w.i32(x.z_order);} VectorElement vector(R&r){VectorElement x;common(r,x.id,x.source_order,x.source_page);x.paths=r.vec<VectorPath>([&]{return vector_path(r);});x.bounds=rectopt(r);x.anchor_type=r.s();x.wrap_mode=r.s();x.wrap_side=r.s();x.z_order=r.i32();return x;}
void math(W&w,const MathElement&x){common(w,x.id,x.source_order,x.source_page);w.s(x.expression);w.s(x.source_syntax);w.flag(x.display_mode);rectopt(w,x.bounds);stropt(w,x.visual_image_path);w.opt(x.visual_pixels_per_mm,[&](double v){w.d(v);});w.vec(x.absorbed_element_ids,[&](const auto&v){w.s(v);});w.opt(x.detection_confidence,[&](double v){w.d(v);});} MathElement math(R&r){MathElement x;common(r,x.id,x.source_order,x.source_page);x.expression=r.s();x.source_syntax=r.s();x.display_mode=r.flag();x.bounds=rectopt(r);x.visual_image_path=stropt(r);x.visual_pixels_per_mm=r.opt<double>([&]{return r.d();});x.absorbed_element_ids=r.vec<std::string>([&]{return r.s();});x.detection_confidence=r.opt<double>([&]{return r.d();});return x;}
void line(W&w,const LineElement&x){common(w,x.id,x.source_order,x.source_page);point(w,x.start);point(w,x.end);mmopt(w,x.line_width);stropt(w,x.dash_style);rectopt(w,x.bounds);w.s(x.semantic_role);w.opt(x.confidence,[&](double v){w.d(v);});} LineElement line(R&r){LineElement x;common(r,x.id,x.source_order,x.source_page);x.start=point(r);x.end=point(r);x.line_width=mmopt(r);x.dash_style=stropt(r);x.bounds=rectopt(r);x.semantic_role=r.s();x.confidence=r.opt<double>([&]{return r.d();});return x;}
void arrow(W&w,const ArrowElement&x){common(w,x.id,x.source_order,x.source_page);w.vec(x.points,[&](const auto&v){point(w,v);});w.flag(x.head_at_start);w.flag(x.head_at_end);w.s(x.head_style);rectopt(w,x.bounds);w.opt(x.confidence,[&](double v){w.d(v);});w.s(x.start_head_style);w.s(x.end_head_style);stropt(w,x.stroke_color);stropt(w,x.source_identity);mmopt(w,x.line_width);} ArrowElement arrow(R&r){ArrowElement x;common(r,x.id,x.source_order,x.source_page);x.points=r.vec<Point>([&]{return point(r);});x.head_at_start=r.flag();x.head_at_end=r.flag();x.head_style=r.s();x.bounds=rectopt(r);x.confidence=r.opt<double>([&]{return r.d();});x.start_head_style=r.s();x.end_head_style=r.s();x.stroke_color=stropt(r);x.source_identity=stropt(r);x.line_width=mmopt(r);return x;}
void table_cell(W&w,const TableCell&x){w.u32(x.row);w.u32(x.column);w.u32(x.row_span);w.u32(x.column_span);w.vec(x.paragraphs,[&](const auto&v){paragraph(w,v);});mmopt(w,x.width);mmopt(w,x.height);w.flag(x.borders.top);w.flag(x.borders.right);w.flag(x.borders.bottom);w.flag(x.borders.left);stropt(w,x.vertical_alignment);} TableCell table_cell(R&r){TableCell x;x.row=r.u32();x.column=r.u32();x.row_span=r.u32();x.column_span=r.u32();x.paragraphs=r.vec<Paragraph>([&]{return paragraph(r);});x.width=mmopt(r);x.height=mmopt(r);x.borders.top=r.flag();x.borders.right=r.flag();x.borders.bottom=r.flag();x.borders.left=r.flag();x.vertical_alignment=stropt(r);return x;}
void table(W&w,const TableElement&x){common(w,x.id,x.source_order,x.source_page);w.u32(x.rows);w.u32(x.columns);w.vec(x.cells,[&](const auto&v){table_cell(w,v);});w.vec(x.column_widths,[&](const auto&v){w.d(v.value);});rectopt(w,x.bounds);w.u32(x.repeat_header_rows);w.s(x.source_kind);stropt(w,x.alignment);mmopt(w,x.left_indent);mmopt(w,x.preferred_width);w.vec(x.row_heights,[&](const auto&v){mmopt(w,v);});} TableElement table(R&r){TableElement x;common(r,x.id,x.source_order,x.source_page);x.rows=r.u32();x.columns=r.u32();x.cells=r.vec<TableCell>([&]{return table_cell(r);});x.column_widths=r.vec<Millimetres>([&]{return Millimetres{r.d()};});x.bounds=rectopt(r);x.repeat_header_rows=r.u32();x.source_kind=r.s();x.alignment=stropt(r);x.left_indent=mmopt(r);x.preferred_width=mmopt(r);x.row_heights=r.vec<std::optional<Millimetres>>([&]{return mmopt(r);});return x;}
void element(W&w,const SourceElement&x){w.u8(static_cast<std::uint8_t>(x.index()));std::visit([&](const auto&v){using T=std::decay_t<decltype(v)>;if constexpr(std::is_same_v<T,TextElement>)text(w,v);else if constexpr(std::is_same_v<T,RasterImageElement>)image(w,v);else if constexpr(std::is_same_v<T,VectorElement>)vector(w,v);else if constexpr(std::is_same_v<T,MathElement>)math(w,v);else if constexpr(std::is_same_v<T,LineElement>)line(w,v);else if constexpr(std::is_same_v<T,ArrowElement>)arrow(w,v);else table(w,v);},x);} SourceElement element(R&r){switch(r.u8()){case 0:return text(r);case 1:return image(r);case 2:return vector(r);case 3:return math(r);case 4:return line(r);case 5:return arrow(r);case 6:return table(r);default:throw std::runtime_error("unknown document cache element");}}
void page(W&w,const SourcePage&x){w.u32(x.source_page);mmopt(w,x.width);mmopt(w,x.height);w.vec(x.elements,[&](const auto&v){element(w,v);});rectopt(w,x.content_bounds);} SourcePage page(R&r){SourcePage x;x.source_page=r.u32();x.width=mmopt(r);x.height=mmopt(r);x.elements=r.vec<SourceElement>([&]{return element(r);});x.content_bounds=rectopt(r);return x;}
}

bool DocumentCodec::cacheable(const Document& value) noexcept {
    for (const auto& source_page : value.pages) for (const auto& source : source_page.elements) {
        if (const auto* image = std::get_if<RasterImageElement>(&source); image && !image->image_path.empty()) return false;
        if (const auto* math_element = std::get_if<MathElement>(&source);
            math_element && math_element->visual_image_path && !math_element->visual_image_path->empty()) return false;
    }
    return true;
}

StageBytes DocumentCodec::encode(const Document& value) {
    if (!cacheable(value)) throw std::invalid_argument("document cache cannot persist external raster or math asset paths");
    W w; w.s(value.source_path);w.vec(value.pages,[&](const auto&v){page(w,v);});w.vec(value.warnings,[&](const auto&v){w.s(v);});w.s(value.metadata.source_format);stropt(w,value.metadata.title);w.vec(value.metadata.properties,[&](const auto&v){w.s(v.first);w.s(v.second);});w.u32(value.schema_version);return std::move(w.b); }
std::optional<Document> DocumentCodec::decode(std::span<const std::uint8_t> bytes) { try { R r{bytes};Document v;v.source_path=r.s();v.pages=r.vec<SourcePage>([&]{return page(r);});v.warnings=r.vec<std::string>([&]{return r.s();});v.metadata.source_format=r.s();v.metadata.title=stropt(r);v.metadata.properties=r.vec<std::pair<std::string,std::string>>([&]{return std::pair{r.s(),r.s()};});v.schema_version=r.u32();if(r.p!=bytes.size())return std::nullopt;return v;}catch(const std::exception&){return std::nullopt;} }

}  // namespace plotter::doc
