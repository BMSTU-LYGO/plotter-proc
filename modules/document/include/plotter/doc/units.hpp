#pragma once

#include <compare>
#include <cstdint>

namespace plotter::doc {

template <typename Tag>
struct Quantity final {
    double value{};
    constexpr auto operator<=>(const Quantity&) const = default;
};

struct MillimetresTag {};
struct PointsTag {};
struct PixelsTag {};
struct DegreesTag {};
struct FontUnitsTag {};

using Millimetres = Quantity<MillimetresTag>;
using Points = Quantity<PointsTag>;
using Pixels = Quantity<PixelsTag>;
using Degrees = Quantity<DegreesTag>;
struct Emu final {
    std::int64_t value{};
    constexpr auto operator<=>(const Emu&) const = default;
};
using FontUnits = Quantity<FontUnitsTag>;

inline constexpr double kMillimetresPerPoint = 25.4 / 72.0;
inline constexpr double kEmuPerMillimetre = 914400.0 / 25.4;

[[nodiscard]] constexpr Millimetres to_millimetres(Points value) { return {value.value * kMillimetresPerPoint}; }
[[nodiscard]] constexpr Points to_points(Millimetres value) { return {value.value / kMillimetresPerPoint}; }
[[nodiscard]] constexpr Millimetres to_millimetres(Emu value) { return {static_cast<double>(value.value) / kEmuPerMillimetre}; }
[[nodiscard]] constexpr Emu to_emu(Millimetres value) { const double scaled = value.value * kEmuPerMillimetre;
    return {static_cast<std::int64_t>(scaled + (scaled >= 0.0 ? 0.5 : -0.5))}; }

constexpr Millimetres operator+(Millimetres lhs, Millimetres rhs) { return {lhs.value + rhs.value}; }
constexpr Millimetres operator-(Millimetres lhs, Millimetres rhs) { return {lhs.value - rhs.value}; }
constexpr Millimetres operator*(Millimetres value, double scale) { return {value.value * scale}; }
constexpr Millimetres operator*(double scale, Millimetres value) { return value * scale; }

}  // namespace plotter::doc
