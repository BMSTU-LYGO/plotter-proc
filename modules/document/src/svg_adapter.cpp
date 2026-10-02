#include "plotter/doc/svg_adapter.hpp"

#include <algorithm>
#include <array>
#include <charconv>
#include <cmath>
#include <fstream>
#include <limits>
#include <iterator>
#include <map>
#include <numbers>
#include <regex>
#include <set>
#include <sstream>
#include <string_view>

namespace plotter::doc {
namespace {

constexpr double kPxToMm = 25.4 / 96.0;
using Matrix = std::array<double, 6>;
constexpr Matrix kIdentity{1.0, 0.0, 0.0, 1.0, 0.0, 0.0};

struct Tag final { std::string name; std::map<std::string, std::string> attributes; bool closing{}; bool self_closing{}; };
struct ViewBox final { double x{}, y{}, width{}, height{}; };
struct Context final { Matrix transform{kIdentity}; std::string name; };

[[nodiscard]] SvgAdapterError error(std::string message) { return {std::move(message)}; }

[[nodiscard]] bool finite(double value) { return std::isfinite(value); }

[[nodiscard]] std::optional<double> number(std::string_view value) {
    double out{};
    const auto [ptr, ec] = std::from_chars(value.data(), value.data() + value.size(), out);
    if (ec != std::errc{} || ptr != value.data() + value.size() || !finite(out)) return std::nullopt;
    return out;
}

[[nodiscard]] std::vector<double> numbers(std::string_view input) {
    static const std::regex pattern(R"([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)");
    std::vector<double> values;
    const std::string text(input);
    for (std::sregex_iterator it(text.begin(), text.end(), pattern), end; it != end; ++it) {
        const auto value = number(it->str());
        if (!value) return {};
        values.push_back(*value);
    }
    return values;
}

[[nodiscard]] Matrix multiply(const Matrix& a, const Matrix& b) {
    return {a[0] * b[0] + a[2] * b[1], a[1] * b[0] + a[3] * b[1],
            a[0] * b[2] + a[2] * b[3], a[1] * b[2] + a[3] * b[3],
            a[0] * b[4] + a[2] * b[5] + a[4], a[1] * b[4] + a[3] * b[5] + a[5]};
}

[[nodiscard]] Point apply(const Matrix& matrix, double x, double y) {
    return {{matrix[0] * x + matrix[2] * y + matrix[4]}, {matrix[1] * x + matrix[3] * y + matrix[5]}};
}

[[nodiscard]] std::variant<Matrix, SvgAdapterError> parse_transform(std::string_view text) {
    Matrix result = kIdentity;
    static const std::regex item(R"(([A-Za-z]+)\s*\(([^)]*)\))");
    const std::string value(text);
    std::size_t covered{};
    for (std::sregex_iterator it(value.begin(), value.end(), item), end; it != end; ++it) {
        const auto gap = value.substr(covered, static_cast<std::size_t>(it->position()) - covered);
        if (gap.find_first_not_of(" \t\r\n,") != std::string::npos) return error("invalid SVG transform");
        covered = static_cast<std::size_t>(it->position() + it->length());
        const auto values = numbers((*it)[2].str());
        const auto& name = (*it)[1].str();
        Matrix current{};
        if (name == "translate" && (values.size() == 1 || values.size() == 2)) current = {1, 0, 0, 1, values[0], values.size() == 2 ? values[1] : 0};
        else if (name == "scale" && (values.size() == 1 || values.size() == 2)) current = {values[0], 0, 0, values.size() == 2 ? values[1] : values[0], 0, 0};
        else if (name == "matrix" && values.size() == 6) std::copy(values.begin(), values.end(), current.begin());
        else if (name == "rotate" && values.size() == 1) { const double a = values[0] * std::numbers::pi / 180.0; current = {std::cos(a), std::sin(a), -std::sin(a), std::cos(a), 0, 0}; }
        else return error("unsupported SVG transform: " + name);
        result = multiply(result, current);
    }
    if (value.substr(covered).find_first_not_of(" \t\r\n,") != std::string::npos) return error("invalid SVG transform");
    return result;
}

[[nodiscard]] std::string local_name(std::string name) { const auto pos = name.find(':'); return pos == std::string::npos ? name : name.substr(pos + 1); }

[[nodiscard]] std::variant<std::vector<Tag>, SvgAdapterError> parse_tags(const std::string& xml, const SvgImportOptions& options) {
    std::vector<Tag> tags;
    for (std::size_t cursor{}; ; ) {
        const auto start = xml.find('<', cursor);
        if (start == std::string::npos) break;
        if (xml.compare(start, 4, "<!--") == 0) { const auto end = xml.find("-->", start + 4); if (end == std::string::npos) return error("unterminated SVG comment"); cursor = end + 3; continue; }
        if (xml.compare(start, 2, "<?") == 0) { const auto end = xml.find("?>", start + 2); if (end == std::string::npos) return error("unterminated SVG declaration"); cursor = end + 2; continue; }
        if (xml.compare(start, 2, "<!") == 0) return error("SVG entities and declarations are forbidden");
        const auto end = xml.find('>', start + 1); if (end == std::string::npos) return error("unterminated SVG tag");
        std::string inside = xml.substr(start + 1, end - start - 1); cursor = end + 1;
        Tag tag;
        if (!inside.empty() && inside.front() == '/') { tag.closing = true; inside.erase(inside.begin()); }
        while (!inside.empty() && std::isspace(static_cast<unsigned char>(inside.back()))) inside.pop_back();
        if (!tag.closing && !inside.empty() && inside.back() == '/') { tag.self_closing = true; inside.pop_back(); }
        static const std::regex head(R"(^\s*([A-Za-z_][A-Za-z0-9_.:-]*))"); std::smatch match;
        if (!std::regex_search(inside, match, head)) return error("invalid SVG tag");
        tag.name = local_name(match[1].str());
        if (!tag.closing) {
            const std::string rest = inside.substr(static_cast<std::size_t>(match.position() + match.length()));
            static const std::regex attr(R"(([A-Za-z_:][A-Za-z0-9_.:-]*)\s*=\s*([\"'])(.*?)\2)");
            std::size_t position{};
            for (std::sregex_iterator it(rest.begin(), rest.end(), attr), last; it != last; ++it) {
                if (rest.substr(position, static_cast<std::size_t>(it->position()) - position).find_first_not_of(" \t\r\n") != std::string::npos) return error("invalid SVG attribute");
                position = static_cast<std::size_t>(it->position() + it->length()); tag.attributes.emplace(local_name((*it)[1].str()), (*it)[3].str());
            }
            if (rest.substr(position).find_first_not_of(" \t\r\n") != std::string::npos) return error("invalid SVG attribute");
        }
        tags.push_back(std::move(tag));
        if (tags.size() > options.max_nodes) return error("SVG exceeds safe XML node limit");
    }
    return tags;
}

[[nodiscard]] std::optional<double> length_mm(const std::string& value) {
    static const std::regex unit(R"(^\s*([-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)\s*(px|mm|cm|in|pt|pc)?\s*$)"); std::smatch match;
    if (!std::regex_match(value, match, unit)) return std::nullopt;
    const auto raw = number(match[1].str()); if (!raw) return std::nullopt;
    const std::string suffix = match[2].str();
    const double factor = suffix.empty() || suffix == "px" ? kPxToMm : suffix == "mm" ? 1.0 : suffix == "cm" ? 10.0 : suffix == "in" ? 25.4 : suffix == "pt" ? 25.4 / 72.0 : 25.4 / 6.0;
    return *raw * factor;
}

[[nodiscard]] std::variant<ViewBox, SvgAdapterError> viewbox(const Tag& root) {
    if (const auto found = root.attributes.find("viewBox"); found != root.attributes.end()) { const auto values = numbers(found->second); if (values.size() == 4 && values[2] > 0 && values[3] > 0) return ViewBox{values[0], values[1], values[2], values[3]}; }
    const auto w = root.attributes.find("width"), h = root.attributes.find("height");
    if (w != root.attributes.end() && h != root.attributes.end()) { const auto width = number(w->second), height = number(h->second); if (width && height && *width > 0 && *height > 0) return ViewBox{0, 0, *width, *height}; }
    return error("SVG requires a positive viewBox or numeric width and height");
}

[[nodiscard]] std::variant<SvgIntrinsicSize, SvgAdapterError> intrinsic(const Tag& root) {
    const auto box = viewbox(root); if (const auto* failure = std::get_if<SvgAdapterError>(&box)) return *failure;
    const auto& b = std::get<ViewBox>(box); const auto w = root.attributes.find("width"), h = root.attributes.find("height");
    const auto width = w == root.attributes.end() ? std::optional<double>{} : length_mm(w->second);
    const auto height = h == root.attributes.end() ? std::optional<double>{} : length_mm(h->second);
    const double out_w = width.value_or(b.width * kPxToMm), out_h = height.value_or(b.height * kPxToMm);
    if (!(out_w > 0.0 && out_h > 0.0 && finite(out_w) && finite(out_h))) return error("SVG intrinsic dimensions must be positive");
    return SvgIntrinsicSize{{out_w}, {out_h}};
}

[[nodiscard]] std::variant<double, SvgAdapterError> attribute_number(const Tag& tag, const char* key, double fallback = 0.0) {
    const auto found = tag.attributes.find(key); if (found == tag.attributes.end()) return fallback;
    const auto out = number(found->second); if (!out) return error(std::string("invalid SVG attribute: ") + key); return *out;
}

[[nodiscard]] std::variant<std::vector<Point>, SvgAdapterError> shape(const Tag& tag, const Matrix& matrix, const SvgImportOptions& options, bool& closed) {
    auto n = [&](const char* key, double fallback = 0.0) { return attribute_number(tag, key, fallback); };
    auto read = [&](const char* key, double fallback, double& out) -> std::optional<SvgAdapterError> { auto value = n(key, fallback); if (const auto* e = std::get_if<SvgAdapterError>(&value)) return *e; out = std::get<double>(value); return {}; };
    std::vector<Point> points; double a{}, b{}, c{}, d{};
    if (tag.name == "line") { if (auto e = read("x1", 0, a)) return *e; if (auto e = read("y1", 0, b)) return *e; if (auto e = read("x2", 0, c)) return *e; if (auto e = read("y2", 0, d)) return *e; points = {apply(matrix, a, b), apply(matrix, c, d)}; closed = false; }
    else if (tag.name == "polyline" || tag.name == "polygon") { const auto it = tag.attributes.find("points"); if (it == tag.attributes.end()) return error("SVG polyline requires points"); const auto raw = numbers(it->second); if (raw.size() < 4 || raw.size() % 2 != 0) return error("invalid SVG polyline points"); for (std::size_t i{}; i < raw.size(); i += 2) points.push_back(apply(matrix, raw[i], raw[i + 1])); closed = tag.name == "polygon"; }
    else if (tag.name == "rect") { if (auto e = read("x", 0, a)) return *e; if (auto e = read("y", 0, b)) return *e; if (auto e = read("width", 0, c)) return *e; if (auto e = read("height", 0, d)) return *e; if (c <= 0 || d <= 0) return error("SVG rect dimensions must be positive"); points = {apply(matrix, a,b), apply(matrix,a+c,b), apply(matrix,a+c,b+d), apply(matrix,a,b+d)}; closed = true; }
    else { if (auto e = read("cx", 0, a)) return *e; if (auto e = read("cy", 0, b)) return *e; const char* x_radius = tag.name == "circle" ? "r" : "rx"; if (auto e = read(x_radius, 0, c)) return *e; if (tag.name == "circle") d = c; else if (auto e = read("ry", 0, d)) return *e; if (c <= 0 || d <= 0) return error("SVG ellipse radius must be positive"); for (std::size_t i{}; i < options.ellipse_segments; ++i) { const double angle = 2.0 * std::numbers::pi * static_cast<double>(i) / static_cast<double>(options.ellipse_segments); points.push_back(apply(matrix, a + c * std::cos(angle), b + d * std::sin(angle))); } closed = true; }
    return points;
}

struct RawContour final { std::vector<Point> points; bool closed{}; };

[[nodiscard]] double distance_to_chord(const Point& point, const Point& start, const Point& end) {
    const double dx = end.x.value - start.x.value, dy = end.y.value - start.y.value;
    const double length = std::hypot(dx, dy);
    if (length == 0.0) return std::hypot(point.x.value - start.x.value, point.y.value - start.y.value);
    return std::abs(dy * point.x.value - dx * point.y.value + end.x.value * start.y.value - end.y.value * start.x.value) / length;
}

[[nodiscard]] Point midpoint(const Point& left, const Point& right) {
    return {{(left.x.value + right.x.value) / 2.0}, {(left.y.value + right.y.value) / 2.0}};
}

void append_flattened(std::vector<Point>& output, const Point& point, const SvgImportOptions& options) {
    if (!output.empty() && std::hypot(point.x.value - output.back().x.value, point.y.value - output.back().y.value) < options.min_segment_length_mm) return;
    if (output.size() >= options.max_points_per_contour) { output.back() = point; return; }
    output.push_back(point);
}

void flatten_quadratic(std::vector<Point>& output, const Point& p0, const Point& p1, const Point& p2, const SvgImportOptions& options, std::size_t depth = 0) {
    if (depth >= options.max_curve_recursion_depth || distance_to_chord(p1, p0, p2) <= options.curve_tolerance_mm) { append_flattened(output, p2, options); return; }
    const Point p01 = midpoint(p0, p1), p12 = midpoint(p1, p2), middle = midpoint(p01, p12);
    flatten_quadratic(output, p0, p01, middle, options, depth + 1);
    flatten_quadratic(output, middle, p12, p2, options, depth + 1);
}

void flatten_cubic(std::vector<Point>& output, const Point& p0, const Point& p1, const Point& p2, const Point& p3, const SvgImportOptions& options, std::size_t depth = 0) {
    if (depth >= options.max_curve_recursion_depth || std::max(distance_to_chord(p1, p0, p3), distance_to_chord(p2, p0, p3)) <= options.curve_tolerance_mm) { append_flattened(output, p3, options); return; }
    const Point p01 = midpoint(p0, p1), p12 = midpoint(p1, p2), p23 = midpoint(p2, p3);
    const Point p012 = midpoint(p01, p12), p123 = midpoint(p12, p23), middle = midpoint(p012, p123);
    flatten_cubic(output, p0, p01, p012, middle, options, depth + 1);
    flatten_cubic(output, middle, p123, p23, p3, options, depth + 1);
}

[[nodiscard]] std::variant<std::vector<RawContour>, SvgAdapterError> parse_path_data(std::string_view text, const Matrix& matrix, const SvgImportOptions& options) {
    static const std::regex token(R"([MmLlHhVvCcQqZz]|[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][-+]?\d+)?)");
    std::vector<std::string> values;
    const std::string data(text);
    for (std::sregex_iterator it(data.begin(), data.end(), token), end; it != end; ++it) values.push_back(it->str());
    if (values.empty()) return error("SVG path requires path data");
    std::vector<RawContour> contours;
    RawContour current;
    double x{}, y{}, start_x{}, start_y{};
    char command{};
    bool have_current{};
    auto is_command = [](const std::string& value) { return value.size() == 1 && std::isalpha(static_cast<unsigned char>(value.front())); };
    auto take = [&](std::size_t& index, double& value) -> bool {
        if (index >= values.size() || is_command(values[index])) return false;
        const auto parsed = number(values[index++]);
        if (!parsed) return false;
        value = *parsed;
        return true;
    };
    for (std::size_t index{}; index < values.size();) {
        if (is_command(values[index])) command = values[index++].front();
        if (command == '\0') return error("SVG path must begin with a command");
        const bool relative = std::islower(static_cast<unsigned char>(command));
        const char upper = static_cast<char>(std::toupper(static_cast<unsigned char>(command)));
        if (upper == 'Z') {
            if (!have_current) return error("SVG close command has no contour");
            current.closed = true;
            contours.push_back(std::move(current));
            current = {};
            x = start_x; y = start_y; have_current = false; command = '\0';
            continue;
        }
        auto coordinate = [&](double& out_x, double& out_y) -> bool {
            if (!take(index, out_x) || !take(index, out_y)) return false;
            if (relative) { out_x += x; out_y += y; }
            return true;
        };
        if (upper == 'M') {
            double nx{}, ny{};
            if (!coordinate(nx, ny)) return error("invalid SVG move command");
            if (have_current) contours.push_back(std::move(current));
            current = {}; current.points.push_back(apply(matrix, nx, ny)); x = start_x = nx; y = start_y = ny; have_current = true;
            command = relative ? 'l' : 'L';
        } else if (upper == 'L') {
            if (!have_current) return error("SVG line command has no current point");
            double nx{}, ny{}; if (!coordinate(nx, ny)) return error("invalid SVG line command");
            append_flattened(current.points, apply(matrix, nx, ny), options); x = nx; y = ny;
        } else if (upper == 'H') {
            if (!have_current) return error("SVG horizontal command has no current point");
            double nx{}; if (!take(index, nx)) return error("invalid SVG horizontal command"); if (relative) nx += x;
            append_flattened(current.points, apply(matrix, nx, y), options); x = nx;
        } else if (upper == 'V') {
            if (!have_current) return error("SVG vertical command has no current point");
            double ny{}; if (!take(index, ny)) return error("invalid SVG vertical command"); if (relative) ny += y;
            append_flattened(current.points, apply(matrix, x, ny), options); y = ny;
        } else if (upper == 'C') {
            if (!have_current) return error("SVG cubic command has no current point");
            double x1{}, y1{}, x2{}, y2{}, nx{}, ny{};
            if (!coordinate(x1, y1) || !coordinate(x2, y2) || !coordinate(nx, ny)) return error("invalid SVG cubic command");
            flatten_cubic(current.points, current.points.back(), apply(matrix, x1, y1), apply(matrix, x2, y2), apply(matrix, nx, ny), options);
            x = nx; y = ny;
        } else if (upper == 'Q') {
            if (!have_current) return error("SVG quadratic command has no current point");
            double x1{}, y1{}, nx{}, ny{};
            if (!coordinate(x1, y1) || !coordinate(nx, ny)) return error("invalid SVG quadratic command");
            flatten_quadratic(current.points, current.points.back(), apply(matrix, x1, y1), apply(matrix, nx, ny), options);
            x = nx; y = ny;
        } else return error(std::string("unsupported SVG path command: ") + command);
    }
    if (have_current) contours.push_back(std::move(current));
    if (contours.empty()) return error("SVG path contains no contours");
    return contours;
}

[[nodiscard]] std::variant<std::vector<VectorPath>, SvgAdapterError> path_shapes(const Tag& tag, const Matrix& matrix, const SvgImportOptions& options, const std::filesystem::path& source_path, const std::string& element_id) {
    const auto found = tag.attributes.find("d");
    if (found == tag.attributes.end() || found->second.size() > 1'000'000) return error("SVG path data is missing or exceeds safe limit");
    const auto parsed = parse_path_data(found->second, matrix, options);
    if (const auto* failure = std::get_if<SvgAdapterError>(&parsed)) return *failure;
    std::vector<VectorPath> paths;
    for (const auto& contour : std::get<std::vector<RawContour>>(parsed)) {
        if (contour.points.size() < (contour.closed ? 3U : 2U)) continue;
        VectorPath item;
        item.closed = contour.closed;
        item.points = contour.points;
        item.element_id = element_id; item.element_type = "svg-vector"; item.source_path = source_path.string(); item.semantic_role = "svg-vector"; item.source_page = 0;
        paths.push_back(std::move(item));
    }
    if (paths.empty()) return error("SVG path contains no drawable contours");
    return paths;
}
[[nodiscard]] std::optional<Rect> bounds(const std::vector<VectorPath>& paths) {
    double left = std::numeric_limits<double>::infinity(), top = left, right = -left, bottom = -left;
    for (const auto& path : paths) for (const auto& point : path.points) { left = std::min(left, point.x.value); top = std::min(top, point.y.value); right = std::max(right, point.x.value); bottom = std::max(bottom, point.y.value); }
    if (!finite(left)) return std::nullopt;
    return Rect{{left}, {top}, {right - left}, {bottom - top}};
}

[[nodiscard]] std::variant<std::string, SvgAdapterError> read_file(const std::filesystem::path& path, const SvgImportOptions& options) {
    std::error_code ec; const auto size = std::filesystem::file_size(path, ec); if (ec) return error("cannot read SVG: " + path.string()); if (size > options.max_file_bytes) return error("SVG exceeds safe file size limit");
    std::ifstream input(path, std::ios::binary); std::ostringstream output; output << input.rdbuf(); const auto data = output.str();
    const auto lower = [&] { std::string s = data; std::transform(s.begin(), s.end(), s.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); }); return s; }();
    if (lower.find("<!doctype") != std::string::npos || lower.find("<!entity") != std::string::npos) return error("SVG entities and DOCTYPE are forbidden");
    return data;
}

}  // namespace

SvgIntrinsicSizeResult svg_intrinsic_size_mm(const std::filesystem::path& path, const SvgImportOptions& options) {
    const auto data = read_file(path, options); if (const auto* failure = std::get_if<SvgAdapterError>(&data)) return *failure;
    const auto tags = parse_tags(std::get<std::string>(data), options); if (const auto* failure = std::get_if<SvgAdapterError>(&tags)) return *failure;
    if (std::get<std::vector<Tag>>(tags).empty() || std::get<std::vector<Tag>>(tags).front().name != "svg") return error("SVG root element is required");
    return intrinsic(std::get<std::vector<Tag>>(tags).front());
}

SvgDocumentResult read_svg_document(const std::filesystem::path& path, const SvgImportOptions& options) {
    if (options.ellipse_segments < 3) return error("SVG ellipse_segments must be at least 3");
    if (!(options.curve_tolerance_mm > 0.0) || options.min_segment_length_mm < 0.0 || options.max_points_per_contour < 2 || options.max_curve_recursion_depth > 64) return error("invalid SVG curve flattening options");
    const auto data = read_file(path, options); if (const auto* failure = std::get_if<SvgAdapterError>(&data)) return *failure;
    const auto parsed = parse_tags(std::get<std::string>(data), options); if (const auto* failure = std::get_if<SvgAdapterError>(&parsed)) return *failure;
    const auto& tags = std::get<std::vector<Tag>>(parsed); if (tags.empty() || tags.front().name != "svg" || tags.front().closing) return error("SVG root element is required");
    const auto size = intrinsic(tags.front()); if (const auto* failure = std::get_if<SvgAdapterError>(&size)) return *failure;
    const auto box = viewbox(tags.front()); if (const auto* failure = std::get_if<SvgAdapterError>(&box)) return *failure;
    const auto physical = std::get<SvgIntrinsicSize>(size); const auto vb = std::get<ViewBox>(box); const double scale = std::min(physical.width.value / vb.width, physical.height.value / vb.height);
    const Matrix viewport{scale, 0, 0, scale, (physical.width.value - vb.width * scale) / 2.0 - vb.x * scale, (physical.height.value - vb.height * scale) / 2.0 - vb.y * scale};
    const std::set<std::string> allowed{"svg", "g", "line", "polyline", "polygon", "rect", "circle", "ellipse", "path"};
    std::vector<Context> stack;
    stack.push_back({viewport, "svg"});
    VectorElement vector;
    vector.id = "page-001-svg-001";
    for (std::size_t i{}; i < tags.size(); ++i) { const Tag& tag = tags[i];
        if (!allowed.contains(tag.name)) return error("unsupported SVG element: " + tag.name);
        if (tag.closing) { if (stack.size() <= 1 || stack.back().name != tag.name) return error("mismatched SVG closing tag"); stack.pop_back(); continue; }
        for (const auto& [key, value] : tag.attributes) { std::string lowered = value; std::transform(lowered.begin(), lowered.end(), lowered.begin(), [](unsigned char c) { return static_cast<char>(std::tolower(c)); }); if (key != "xmlns" && ((key.size() >= 2 && key.substr(0, 2) == "on") || lowered.find("javascript:") != std::string::npos || lowered.find("file:") != std::string::npos || lowered.find("http:") != std::string::npos || lowered.find("https:") != std::string::npos)) return error("unsafe SVG attribute: " + key); }
        Matrix transform = stack.back().transform; if (const auto found = tag.attributes.find("transform"); found != tag.attributes.end()) { const auto parsed_transform = parse_transform(found->second); if (const auto* failure = std::get_if<SvgAdapterError>(&parsed_transform)) return *failure; transform = multiply(transform, std::get<Matrix>(parsed_transform)); }
        if (tag.name != "svg" && tag.name != "g") {
            const auto fill = tag.attributes.find("fill");
            const auto stroke = tag.attributes.find("stroke");
            if (fill != tag.attributes.end() && fill->second != "none" && fill->second != "transparent" && stroke == tag.attributes.end()) return error("filled-only SVG objects require explicit outline conversion");
            if (tag.name == "path") {
                const auto paths = path_shapes(tag, transform, options, path, vector.id);
                if (const auto* failure = std::get_if<SvgAdapterError>(&paths)) return *failure;
                auto imported = std::get<std::vector<VectorPath>>(paths);
                vector.paths.insert(vector.paths.end(), std::make_move_iterator(imported.begin()), std::make_move_iterator(imported.end()));
            } else {
                bool closed{};
                const auto points = shape(tag, transform, options, closed);
                if (const auto* failure = std::get_if<SvgAdapterError>(&points)) return *failure;
                VectorPath item;
                item.points = std::get<std::vector<Point>>(points);
                item.closed = closed;
                item.element_id = vector.id;
                item.element_type = "svg-vector";
                item.source_path = path.string();
                item.semantic_role = "svg-vector";
                item.source_page = 0;
                vector.paths.push_back(std::move(item));
            }
        }
        if (!tag.self_closing && (tag.name == "svg" || tag.name == "g")) { if (stack.size() > options.max_group_depth) return error("SVG group nesting exceeds safe limit"); stack.push_back({transform, tag.name}); }
    }
    if (stack.size() != 1) return error("unterminated SVG group");
    if (vector.paths.empty()) return error("SVG contains no supported line-art geometry");
    std::size_t point_count{}; for (const auto& item : vector.paths) point_count += item.points.size(); if (point_count > options.max_points) return error("SVG exceeds safe flattened point limit"); vector.bounds = bounds(vector.paths);
    SourcePage page; page.source_page = 0; page.width = physical.width; page.height = physical.height; page.content_bounds = Rect{{}, {}, physical.width, physical.height}; page.elements.emplace_back(std::move(vector));
    Document document; document.source_path = path.string(); document.metadata.source_format = "svg"; document.pages.push_back(std::move(page)); return document;
}

}  // namespace plotter::doc
