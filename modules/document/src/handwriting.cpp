#include "plotter/doc/handwriting.hpp"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <map>
#include <numbers>
#include <sstream>
#include <utility>

namespace plotter::doc {
namespace {

struct Bounds final { double left{}, top{}, right{}, bottom{}; };

[[nodiscard]] HandwritingError error(std::string code, std::string message) {
    return {std::move(code), std::move(message)};
}

[[nodiscard]] bool is_body_glyph(const Stroke& stroke) {
    return stroke.element_type && *stroke.element_type == "text" &&
           stroke.font_role && *stroke.font_role == "body" &&
           stroke.glyph_index && stroke.word_index && stroke.points.size() >= 2U;
}

[[nodiscard]] std::uint64_t hash_identity(std::uint64_t seed, const Stroke& stroke) {
    std::uint64_t state = 1469598103934665603ULL ^ seed;
    const auto mix = [&state](std::uint64_t value) { state ^= value; state *= 1099511628211ULL; };
    mix(stroke.id);
    mix(static_cast<std::uint64_t>(*stroke.glyph_index));
    mix(static_cast<std::uint64_t>(*stroke.word_index));
    for (unsigned char value : stroke.source_characters) mix(value);
    return state;
}

[[nodiscard]] double random_signed(std::uint64_t state, std::uint64_t salt) {
    state += 0x9e3779b97f4a7c15ULL + salt;
    state = (state ^ (state >> 30U)) * 0xbf58476d1ce4e5b9ULL;
    state = (state ^ (state >> 27U)) * 0x94d049bb133111ebULL;
    state ^= state >> 31U;
    return static_cast<double>(state >> 11U) * (1.0 / 9007199254740991.0) * 2.0 - 1.0;
}

[[nodiscard]] Bounds bounds_of(const std::vector<Point>& points) {
    Bounds result{points.front().x.value, points.front().y.value, points.front().x.value, points.front().y.value};
    for (const Point point : points) {
        result.left = std::min(result.left, point.x.value); result.right = std::max(result.right, point.x.value);
        result.top = std::min(result.top, point.y.value); result.bottom = std::max(result.bottom, point.y.value);
    }
    return result;
}

[[nodiscard]] Bounds bounds_of(const std::vector<Stroke*>& strokes) {
    Bounds result = bounds_of(strokes.front()->points);
    for (std::size_t index = 1; index < strokes.size(); ++index) {
        const Bounds value = bounds_of(strokes[index]->points);
        result.left = std::min(result.left, value.left); result.right = std::max(result.right, value.right);
        result.top = std::min(result.top, value.top); result.bottom = std::max(result.bottom, value.bottom);
    }
    return result;
}

[[nodiscard]] bool valid_options(const HandwritingOptions& options) {
    return std::isfinite(options.baseline_jitter.value) && options.baseline_jitter.value >= 0.0 &&
           std::isfinite(options.rotation.value) && options.rotation.value >= 0.0 &&
           std::isfinite(options.glyph_scale_percent) && options.glyph_scale_percent >= 0.0 &&
           std::isfinite(options.glyph_slant) && options.glyph_slant >= 0.0 &&
           std::isfinite(options.word_width_percent) && options.word_width_percent >= 0.0 &&
           options.rotation.value <= 5.0 && options.glyph_scale_percent <= 10.0 &&
           options.glyph_slant <= 0.15 && options.word_width_percent <= 10.0;
}

[[nodiscard]] std::string issue_message(const PathValidationIssue& issue) {
    std::ostringstream output;
    output << "handwriting output failed path validation: " << issue.code << " (" << issue.message << ")";
    return output.str();
}

}  // namespace

HandwritingResult apply_handwriting(const PathDocument& document, const HandwritingOptions& options) {
    if (!options.enabled) return document;
    if (!valid_options(options))
        return error("invalid_handwriting_options", "handwriting variation values must be finite and within safe limits");
    PathValidationOptions validation;
    validation.keep_outs = options.keep_outs;
    if (const auto issues = validate_path_document(document, validation); !issues.empty())
        return error("invalid_handwriting_input", issue_message(issues.front()));

    PathDocument varied = document;
    std::map<std::int64_t, std::vector<Stroke*>> words;
    std::size_t transformed_strokes = 0U;
    for (Stroke& stroke : varied.strokes) {
        if (!is_body_glyph(stroke)) continue;
        const Bounds original = bounds_of(stroke.points);
        const double center_x = (original.left + original.right) / 2.0;
        const double center_y = (original.top + original.bottom) / 2.0;
        const std::uint64_t identity = hash_identity(options.seed, stroke);
        const double scale_x = 1.0 + random_signed(identity, 1U) * options.glyph_scale_percent / 100.0;
        const double scale_y = 1.0 + random_signed(identity, 2U) * options.glyph_scale_percent / 100.0;
        const double slant = random_signed(identity, 3U) * options.glyph_slant;
        const double radians = random_signed(identity, 4U) * options.rotation.value * std::numbers::pi / 180.0;
        const double cosine = std::cos(radians);
        const double sine = std::sin(radians);
        const double shift_y = random_signed(identity, 5U) * options.baseline_jitter.value;
        const double shift_x = random_signed(identity, 6U) * options.baseline_jitter.value * 0.5;
        for (Point& point : stroke.points) {
            const double x = (point.x.value - center_x) * scale_x;
            const double y = (point.y.value - center_y) * scale_y;
            const double slanted_x = x + slant * y;
            point = {{center_x + slanted_x * cosine - y * sine + shift_x},
                     {center_y + slanted_x * sine + y * cosine + shift_y}};
        }
        words[*stroke.word_index].push_back(&stroke);
        ++transformed_strokes;
    }
    for (const auto& [word, strokes] : words) {
        const Bounds current = bounds_of(strokes);
        const std::uint64_t identity = options.seed ^ (static_cast<std::uint64_t>(word) * 0x9e3779b97f4a7c15ULL);
        const double width_scale = 1.0 + random_signed(identity, 7U) * options.word_width_percent / 100.0;
        const double center_x = (current.left + current.right) / 2.0;
        for (Stroke* stroke : strokes) for (Point& point : stroke->points)
            point.x.value = center_x + (point.x.value - center_x) * width_scale;
    }

    // Clamp each transformed word to page bounds while retaining contour order,
    // then validate protected geometry.  This is the safe rerouting boundary:
    // a failed candidate falls back to the original centerline paths.
    for (const auto& [word, strokes] : words) {
        static_cast<void>(word);
        const Bounds current = bounds_of(strokes);
        const double dx = current.left < 0.0 ? -current.left : (current.right > varied.page_width.value ? varied.page_width.value - current.right : 0.0);
        const double dy = current.top < 0.0 ? -current.top : (current.bottom > varied.page_height.value ? varied.page_height.value - current.bottom : 0.0);
        for (Stroke* stroke : strokes) for (Point& point : stroke->points) {
            point.x.value += dx;
            point.y.value += dy;
        }
    }
    validation.keep_outs = options.keep_outs;
    bool restored = false;
    if (const auto issues = validate_path_document(varied, validation); !issues.empty()) {
        varied = document;
        restored = true;
        if (const auto source_issues = validate_path_document(varied, validation); !source_issues.empty())
            return error("handwriting_keep_out_violation", issue_message(source_issues.front()));
    }
    varied.metadata.emplace_back("handwriting", "deterministic-body-variation");
    varied.metadata.emplace_back("handwriting_seed", std::to_string(options.seed));
    varied.metadata.emplace_back("handwriting_transformed_strokes", std::to_string(transformed_strokes));
    varied.metadata.emplace_back("handwriting_reroute", restored ? "reference-restored" : "safe");
    return varied;
}

}  // namespace plotter::doc
