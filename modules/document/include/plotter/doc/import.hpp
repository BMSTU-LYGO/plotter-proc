#pragma once

#include "plotter/doc/model.hpp"

#include <string>
#include <variant>

namespace plotter::doc {

struct ImportError final { std::string message; };
using ImportResult = std::variant<Document, ImportError>;

}  // namespace plotter::doc
