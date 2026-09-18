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

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

add_executable(vita_sdk_smoke
  main.cpp
)

target_compile_options(vita_sdk_smoke PRIVATE
  -Wall
  -Wextra
)

target_link_libraries(vita_sdk_smoke PRIVATE
  SceLibKernel_stub
  stdc++
  pthread
)

vita_create_self(vita_sdk_smoke.self vita_sdk_smoke)
