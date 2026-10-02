#pragma once

#include "plotter/doc/layout.hpp"

#include <cstdint>
#include <string>
#include <string_view>
#include <variant>

namespace plotter::doc {

inline constexpr std::uint32_t kStageIrSchemaVersion = 1;

enum class StageKind { document, layout, paths };

struct StageIrEnvelope final { StageKind stage{}; std::uint32_t version{}; std::string value_json; };
struct IrParseError final { std::string message; };
using ParsedStageIr = std::variant<StageIrEnvelope, IrParseError>;

[[nodiscard]] std::string_view stage_name(StageKind stage) noexcept;
[[nodiscard]] std::string_view stage_schema_name(StageKind stage) noexcept;
[[nodiscard]] ParsedStageIr deserialize_stage_ir(std::string_view json);
[[nodiscard]] std::string serialize_stage_ir(const Document& document);
[[nodiscard]] std::string serialize_stage_ir(const LayoutDocument& layout);
[[nodiscard]] std::string serialize_stage_ir(const PathDocument& paths);

// Short aliases for adapter code. Output is canonical JSON: no whitespace,
// fixed object member order, UTF-8 strings and finite decimal numbers only.
[[nodiscard]] inline std::string to_json(const Document& value) { return serialize_stage_ir(value); }
[[nodiscard]] inline std::string to_json(const LayoutDocument& value) { return serialize_stage_ir(value); }
[[nodiscard]] inline std::string to_json(const PathDocument& value) { return serialize_stage_ir(value); }

}  // namespace plotter::doc
