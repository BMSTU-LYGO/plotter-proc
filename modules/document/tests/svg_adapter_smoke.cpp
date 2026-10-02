#include "plotter/doc/svg_adapter.hpp"

#include <array>
#include <cassert>
#include <cmath>
#include <filesystem>
#include <fstream>
#include <variant>

int main() {
    using namespace plotter::doc;
    const auto path = std::filesystem::temp_directory_path() / "plotter_svg_adapter_smoke.svg";
    { std::ofstream output(path); output << R"svg(<svg width="10cm" height="2in" viewBox="0 0 100 20"><g transform="translate(10 2)"><line x1="0" y1="0" x2="10" y2="0" stroke="black"/></g><circle cx="50" cy="10" r="3" stroke="black" fill="none"/></svg>)svg"; }
    const auto result = read_svg_document(path); std::filesystem::remove(path);
    assert(std::holds_alternative<Document>(result)); const auto& document = std::get<Document>(result); assert(document.metadata.source_format == "svg"); assert(document.pages.front().width->value == 100.0); assert(document.pages.front().height->value == 50.8);
    const auto& vector = std::get<VectorElement>(document.pages.front().elements.front()); assert(vector.paths.size() == 2); assert(vector.paths.front().points.front().x.value == 10.0); assert(vector.paths.front().points.front().y.value == 17.4); assert(vector.paths.front().source_path == path.string()); assert(vector.paths.back().closed);
    const auto fixture = read_svg_document("tests/fixtures/update_18/vector_diagram.svg");
    assert(std::holds_alternative<Document>(fixture));
    const auto& fixture_document = std::get<Document>(fixture);
    const auto& fixture_vector = std::get<VectorElement>(fixture_document.pages.front().elements.front());
    assert(fixture_document.pages.front().width->value == 120.0);
    assert(fixture_document.pages.front().height->value == 80.0);
    assert(fixture_vector.paths.size() == 9);
    assert(fixture_vector.paths.front().points.size() == 27);
    constexpr std::array golden_cubic{std::pair{5.0, 15.0}, std::pair{6.40625, 14.14856}, std::pair{19.0625, 12.583008}, std::pair{50.0, 15.0}};
    for (const auto& [index, expected] : std::array{std::pair{0U, golden_cubic[0]}, std::pair{1U, golden_cubic[1]}, std::pair{10U, golden_cubic[2]}, std::pair{26U, golden_cubic[3]}}) {
        const auto& point = fixture_vector.paths.front().points[index];
        assert(std::abs(point.x.value - expected.first) < 0.000001);
        assert(std::abs(point.y.value - expected.second) < 0.000001);
    }
    assert(fixture_vector.paths.back().points.size() == 3);
    assert(fixture_vector.paths.back().source_path == "tests/fixtures/update_18/vector_diagram.svg");
}
