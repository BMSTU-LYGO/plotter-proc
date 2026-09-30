cmake_minimum_required(VERSION 3.20)

project(fontc VERSION 0.1.0 LANGUAGES CXX)

find_package(Freetype REQUIRED)

add_library(fontc_core
    src/cli.cpp
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

include(CTest)
if(BUILD_TESTING)
    add_test(NAME fontc_help COMMAND fontc --help)
endif()

