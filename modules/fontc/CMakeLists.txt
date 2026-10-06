cmake_minimum_required(VERSION 3.20)

project(fontc VERSION 0.1.0 LANGUAGES CXX)

find_package(Freetype QUIET)
if(NOT Freetype_FOUND)
    find_library(FONTC_FREETYPE_LIBRARY NAMES freetype libfreetype.so.6 REQUIRED)
    add_library(fontc_freetype INTERFACE)
    target_include_directories(fontc_freetype INTERFACE ${CMAKE_CURRENT_SOURCE_DIR}/../../third_party/freetype2)
    target_link_libraries(fontc_freetype INTERFACE ${FONTC_FREETYPE_LIBRARY})
    add_library(Freetype::Freetype ALIAS fontc_freetype)
endif()

add_library(fontc_core
    src/cli.cpp
    src/compiler.cpp
    src/compiled_font.cpp
    src/font_face.cpp
    src/binary_image.cpp
    src/graph_cleanup.cpp
    src/pfc.cpp
    src/geometry.cpp
    src/pruning.cpp
    src/rasterizer.cpp
    src/routing.cpp
    src/runtime_font.cpp
    src/skeleton_graph.cpp
    src/thinning.cpp
)
target_compile_features(fontc_core PUBLIC cxx_std_20)
target_include_directories(fontc_core PUBLIC include)
target_link_libraries(fontc_core PUBLIC Freetype::Freetype)

if(MSVC)
    target_compile_options(fontc_core PRIVATE /W4 /permissive-)
else()
    target_compile_options(fontc_core PRIVATE -Wall -Wextra -Wpedantic -Wconversion)
endif()

add_executable(fontc src/main.cpp)
target_link_libraries(fontc PRIVATE fontc_core)

add_executable(fontc_benchmark tools/benchmark.cpp)
target_link_libraries(fontc_benchmark PRIVATE fontc_core)

include(CTest)
if(BUILD_TESTING)
    add_test(NAME fontc_help COMMAND fontc --help)

    add_executable(fontc_font_face_test tests/font_face_test.cpp)
    target_link_libraries(fontc_font_face_test PRIVATE fontc_core)
    if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/../../assets/1.ttf")
        add_test(
            NAME fontc_font_face
            COMMAND fontc_font_face_test "${CMAKE_CURRENT_SOURCE_DIR}/../../assets/1.ttf"
        )
    endif()

    add_executable(fontc_rasterizer_test tests/rasterizer_test.cpp)
    target_link_libraries(fontc_rasterizer_test PRIVATE fontc_core)
    if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/../../assets/1.ttf")
        add_test(
            NAME fontc_rasterizer
            COMMAND fontc_rasterizer_test "${CMAKE_CURRENT_SOURCE_DIR}/../../assets/1.ttf"
        )
    endif()

    add_executable(fontc_binary_image_test tests/binary_image_test.cpp)
    target_link_libraries(fontc_binary_image_test PRIVATE fontc_core)
    add_test(NAME fontc_binary_image COMMAND fontc_binary_image_test)

    add_executable(fontc_thinning_test tests/thinning_test.cpp)
    target_link_libraries(fontc_thinning_test PRIVATE fontc_core)
    if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/../../assets/1.ttf")
        add_test(
            NAME fontc_thinning
            COMMAND fontc_thinning_test "${CMAKE_CURRENT_SOURCE_DIR}/../../assets/1.ttf"
        )
    endif()

    add_executable(fontc_pruning_test tests/pruning_test.cpp)
    target_link_libraries(fontc_pruning_test PRIVATE fontc_core)
    add_test(NAME fontc_pruning COMMAND fontc_pruning_test)

    add_executable(fontc_skeleton_graph_test tests/skeleton_graph_test.cpp)
    target_link_libraries(fontc_skeleton_graph_test PRIVATE fontc_core)
    add_test(NAME fontc_skeleton_graph COMMAND fontc_skeleton_graph_test)

    add_executable(fontc_graph_cleanup_test tests/graph_cleanup_test.cpp)
    target_link_libraries(fontc_graph_cleanup_test PRIVATE fontc_core)
    add_test(NAME fontc_graph_cleanup COMMAND fontc_graph_cleanup_test)

    add_executable(fontc_routing_test tests/routing_test.cpp)
    target_link_libraries(fontc_routing_test PRIVATE fontc_core)
    add_test(NAME fontc_routing COMMAND fontc_routing_test)

    add_executable(fontc_geometry_test tests/geometry_test.cpp)
    target_link_libraries(fontc_geometry_test PRIVATE fontc_core)
    add_test(NAME fontc_geometry COMMAND fontc_geometry_test)

    add_executable(fontc_compiled_font_test tests/compiled_font_test.cpp)
    target_link_libraries(fontc_compiled_font_test PRIVATE fontc_core)
    add_test(NAME fontc_compiled_font COMMAND fontc_compiled_font_test)

    add_executable(fontc_compiler_test tests/compiler_test.cpp)
    target_link_libraries(fontc_compiler_test PRIVATE fontc_core)
    add_test(NAME fontc_compiler COMMAND fontc_compiler_test)

    add_executable(fontc_pfc_test tests/pfc_test.cpp)
    target_link_libraries(fontc_pfc_test PRIVATE fontc_core)
    add_test(NAME fontc_pfc COMMAND fontc_pfc_test)

    add_executable(fontc_runtime_font_test tests/runtime_font_test.cpp)
    target_link_libraries(fontc_runtime_font_test PRIVATE fontc_core)
    add_test(NAME fontc_runtime_font COMMAND fontc_runtime_font_test)

    add_executable(fontc_pipeline_regression_test tests/pipeline_regression_test.cpp)
    target_link_libraries(fontc_pipeline_regression_test PRIVATE fontc_core)
    if(EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/../../assets/1.ttf")
        add_test(
            NAME fontc_pipeline_regression
            COMMAND fontc_pipeline_regression_test "${CMAKE_CURRENT_SOURCE_DIR}/../../assets/1.ttf"
                    "${CMAKE_CURRENT_SOURCE_DIR}/../../assets/font-cache-corpus.txt"
        )
    endif()
endif()

