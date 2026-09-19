cmake_minimum_required(VERSION 3.16)
if(NOT DEFINED CMAKE_TOOLCHAIN_FILE)
  if(NOT DEFINED ENV{VITASDK})
    message(FATAL_ERROR "VITASDK is not set")
  endif()
  set(CMAKE_TOOLCHAIN_FILE "$ENV{VITASDK}/share/vita.toolchain.cmake" CACHE PATH "VitaSDK toolchain")
endif()
project(openq4_vita_render_probe LANGUAGES C CXX)
include("$ENV{VITASDK}/share/vita.cmake" REQUIRED)
get_filename_component(OPENQ4_ROOT "${CMAKE_CURRENT_LIST_DIR}/../../.." ABSOLUTE)
set(PROBE_BUILD_SHA "local" CACHE STRING "Source commit recorded in the runtime log")
add_executable(openq4_vita_render_probe
  main.cpp
  ${OPENQ4_ROOT}/src/renderer/GLES/vita_glesd3_shader_compat.cpp
  ${OPENQ4_ROOT}/src/renderer/GLES_D3/glsl/debugShaderVP.cpp
  ${OPENQ4_ROOT}/src/renderer/GLES_D3/glsl/debugShaderFP.cpp
  ${OPENQ4_ROOT}/src/renderer/GLES_D3/glsl/materialShaderVP.cpp
  ${OPENQ4_ROOT}/src/renderer/GLES_D3/glsl/materialShaderFP.cpp
  ${OPENQ4_ROOT}/src/renderer/GLES_D3/glsl/interactionShaderVP.cpp
  ${OPENQ4_ROOT}/src/renderer/GLES_D3/glsl/interactionShaderFP.cpp
)
target_compile_features(openq4_vita_render_probe PRIVATE cxx_std_17)
target_compile_definitions(openq4_vita_render_probe PRIVATE VITA=1 PROBE_BUILD_SHA="${PROBE_BUILD_SHA}")
target_compile_options(openq4_vita_render_probe PRIVATE -fsigned-char -fno-strict-aliasing -ffp-contract=off -Wall -Wextra)
target_link_libraries(openq4_vita_render_probe PRIVATE
  vitaGL vitashark mathneon SceLibKernel_stub SceIofilemgr_stub
  ScePower_stub SceAppMgr_stub SceAppUtil_stub SceCommonDialog_stub
  SceDisplay_stub SceGxm_stub SceSysmodule_stub SceShaccCgExt
  SceShaccCg_stub SceKernelDmacMgr_stub SceCtrl_stub taihen_stub m c
)
vita_create_self(openq4_vita_render_probe.self openq4_vita_render_probe)
vita_create_vpk(Vita-OpenQ4-render-probe.vpk VOQ000004 openq4_vita_render_probe.self
  VERSION 00.10 NAME "Vita-OpenQ4"
)
