cmake_minimum_required(VERSION 3.16)

if(NOT DEFINED CMAKE_TOOLCHAIN_FILE)
  if(DEFINED ENV{VITASDK})
    set(CMAKE_TOOLCHAIN_FILE "$ENV{VITASDK}/share/vita.toolchain.cmake" CACHE PATH "VitaSDK toolchain")
  else()
    message(FATAL_ERROR "VITASDK is not set")
  endif()
endif()

project(vita_sdk_smoke LANGUAGES CXX)

include("$ENV{VITASDK}/share/vita.cmake" REQUIRED)

set(OPENQ4_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../..")
execute_process(
  COMMAND python3
    "${OPENQ4_ROOT}/tools/build/openq4_version.py"
    --source-root "${OPENQ4_ROOT}"
    --track dev
    --header-out "${CMAKE_CURRENT_BINARY_DIR}/openq4_version_generated.h"
  RESULT_VARIABLE OPENQ4_VERSION_RESULT
)
if(NOT OPENQ4_VERSION_RESULT EQUAL 0)
  message(FATAL_ERROR "Failed to generate openq4_version_generated.h")
endif()
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_library(openq4_vita_idlib_probe STATIC
  ${CMAKE_CURRENT_LIST_DIR}/../../../src/idlib/CryptoHash.cpp
)

target_include_directories(openq4_vita_idlib_probe PRIVATE
  ${CMAKE_CURRENT_LIST_DIR}/../../../src/idlib
)

target_compile_features(openq4_vita_idlib_probe PRIVATE cxx_std_20)

file(GLOB OPENQ4_VITA_IDLIB_SOURCES CONFIGURE_DEPENDS
  "${OPENQ4_ROOT}/src/idlib/*.cpp"
  "${OPENQ4_ROOT}/src/idlib/bv/*.cpp"
  "${OPENQ4_ROOT}/src/idlib/containers/*.cpp"
  "${OPENQ4_ROOT}/src/idlib/geometry/*.cpp"
  "${OPENQ4_ROOT}/src/idlib/hashing/*.cpp"
  "${OPENQ4_ROOT}/src/idlib/math/*.cpp"
)

add_library(openq4_vita_full_idlib_probe STATIC
  ${OPENQ4_VITA_IDLIB_SOURCES}
)

target_include_directories(openq4_vita_full_idlib_probe PRIVATE
  ${CMAKE_CURRENT_BINARY_DIR}
  ${OPENQ4_ROOT}
  ${OPENQ4_ROOT}/src
  ${OPENQ4_ROOT}/.tmp/gamelibs_stage/src/game
  ${OPENQ4_ROOT}/.tmp/gamelibs_stage/src/mpgame
)

target_compile_options(openq4_vita_full_idlib_probe PRIVATE
  -fsigned-char
  -DVITA=1
  -D__DOOM_DLL__
  -DUSE_OPENAL
  -DGLEW_NO_GLU
  -fno-strict-aliasing
  -ffp-contract=off
  -include
  ${OPENQ4_ROOT}/src/idlib/precompiled.h
)

target_compile_features(openq4_vita_full_idlib_probe PRIVATE cxx_std_20)

add_library(openq4_vita_threads_probe STATIC
  ${OPENQ4_ROOT}/src/sys/vita/vita_threads.cpp
)

target_include_directories(openq4_vita_threads_probe PRIVATE
  ${CMAKE_CURRENT_BINARY_DIR}
  ${OPENQ4_ROOT}
  ${OPENQ4_ROOT}/src
  ${OPENQ4_ROOT}/.tmp/gamelibs_stage/src/game
  ${OPENQ4_ROOT}/.tmp/gamelibs_stage/src/mpgame
)

target_compile_options(openq4_vita_threads_probe PRIVATE
  -fsigned-char
  -DVITA=1
  -D__DOOM_DLL__
  -DUSE_OPENAL
  -DGLEW_NO_GLU
  -DID_GL_HARDLINK
  -fno-strict-aliasing
  -ffp-contract=off
)

target_compile_features(openq4_vita_threads_probe PRIVATE cxx_std_20)

add_library(openq4_vita_system_probe STATIC
  ${OPENQ4_ROOT}/src/sys/vita/vita_system.cpp
)

target_include_directories(openq4_vita_system_probe PRIVATE
  ${CMAKE_CURRENT_BINARY_DIR}
  ${OPENQ4_ROOT}
  ${OPENQ4_ROOT}/src
  ${OPENQ4_ROOT}/.tmp/gamelibs_stage/src/game
  ${OPENQ4_ROOT}/.tmp/gamelibs_stage/src/mpgame
)

target_compile_options(openq4_vita_system_probe PRIVATE
  -fsigned-char
  -DVITA=1
  -D__DOOM_DLL__
  -DUSE_OPENAL
  -DGLEW_NO_GLU
  -DID_GL_HARDLINK
  -fno-strict-aliasing
  -ffp-contract=off
)

target_compile_features(openq4_vita_system_probe PRIVATE cxx_std_20)
add_executable(vita_sdk_smoke
  main.cpp
  platform_probe.cpp
)

target_compile_options(vita_sdk_smoke PRIVATE
  -Wall
  -Wextra
)

target_link_libraries(vita_sdk_smoke PRIVATE
  openq4_vita_idlib_probe
  SceLibKernel_stub
  stdc++
  pthread
)

vita_create_self(vita_sdk_smoke.self vita_sdk_smoke)
