cmake_minimum_required(VERSION 3.20)

project(plotter_document_pipeline VERSION 1.0.0 LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

include(CTest)
option(PLOTTER_DOC_BUILD_TESTS "Build document module tests" ON)

add_subdirectory(modules/fontc)
add_subdirectory(modules/document)
