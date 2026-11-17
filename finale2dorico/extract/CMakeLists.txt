# f2d-extract: reads a Finale file (.mus via finale-mus-reader, or EnigmaXML via musxdom)
# and prints finale2dorico's Score IR as JSON. See ../docs/DESIGN.md.
#
#   cmake -S extract -B extract/build -G Ninja -DCMAKE_BUILD_TYPE=Release
#   cmake --build extract/build
#
# Dependencies are fetched at the revisions pinned below (all MIT / zlib licensed).
# For development against local checkouts, pass e.g.
#   -DFETCHCONTENT_SOURCE_DIR_MUSXDOM=/path/to/musxdom
cmake_minimum_required(VERSION 3.20)
project(f2d_extract LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)
set(CMAKE_CXX_SCAN_FOR_MODULES OFF)  # no modules used; zig has no clang-scan-deps
if(MSVC)
    add_compile_options(/bigobj /utf-8)
endif()

include(FetchContent)

# musxdom: the revision finale-mus-reader pins (cmake/ReaderDependencies.cmake).
FetchContent_Declare(musxdom
    GIT_REPOSITORY https://github.com/openmusx/musxdom.git
    GIT_TAG 4f29939c68e2855e0494b059efa15761899374da
    GIT_SHALLOW FALSE)
FetchContent_Declare(finale_mus_reader
    GIT_REPOSITORY https://github.com/openmusx/finale-mus-reader.git
    GIT_TAG f4b1a33
    GIT_SHALLOW FALSE)
# smufl-mapping: legacy music-font characters (Maestro, Engraver, Petrucci, Jazz ...) -> SMuFL
# glyph names, so markings are recognised by name in any font.
FetchContent_Declare(smufl_mapping
    GIT_REPOSITORY https://github.com/openmusx/smufl-mapping.git
    GIT_TAG 1b8fbe43d82328f56111c76dd515a3c4a0032971
    GIT_SHALLOW FALSE)
FetchContent_Declare(pugixml
    URL https://github.com/zeux/pugixml/releases/download/v1.15/pugixml-1.15.tar.gz
    URL_HASH SHA256=655ade57fa703fb421c2eb9a0113b5064bddb145d415dd1f88c79353d90d511a
    DOWNLOAD_EXTRACT_TIMESTAMP TRUE)

set(musx_BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(FINALE_MUS_READER_BUILD_TESTING OFF CACHE BOOL "" FORCE)
set(FINALE_MUS_READER_BUILD_REPORTING_TESTING OFF CACHE BOOL "" FORCE)
set(FINALE_MUS_READER_INSTRUMENTATION OFF CACHE STRING "" FORCE)
set(PUGIXML_BUILD_TESTS OFF CACHE BOOL "" FORCE)

FetchContent_MakeAvailable(pugixml musxdom)
FetchContent_MakeAvailable(finale_mus_reader)
if(NOT TARGET smufl_mapping)
    FetchContent_MakeAvailable(smufl_mapping)
endif()

add_executable(f2d-extract src/main.cpp)
target_link_libraries(f2d-extract PRIVATE musx finale_mus_reader::finale_mus_reader pugixml smufl_mapping)
target_compile_definitions(f2d-extract PRIVATE MUSX_USE_PUGIXML)
if(NOT MSVC)
    target_compile_options(f2d-extract PRIVATE -Wall -Wextra)
endif()
