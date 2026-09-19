cmake_minimum_required(VERSION 3.16)

if(NOT DEFINED CMAKE_TOOLCHAIN_FILE)
  if(DEFINED ENV{VITASDK})
    set(CMAKE_TOOLCHAIN_FILE "$ENV{VITASDK}/share/vita.toolchain.cmake" CACHE PATH "VitaSDK toolchain")
  else()
    message(FATAL_ERROR "VITASDK is not set")
  endif()
endif()

project(vita_openq4_engine_package LANGUAGES C CXX)

include("$ENV{VITASDK}/share/vita.cmake" REQUIRED)

if(NOT DEFINED OPENQ4_ENGINE_ELF OR NOT EXISTS "${OPENQ4_ENGINE_ELF}")
  message(FATAL_ERROR "OPENQ4_ENGINE_ELF must point to the Meson-built openQ4-client_armv7 ELF")
endif()

if(NOT DEFINED OPENQ4_RUNTIME_MOD_JSON OR NOT EXISTS "${OPENQ4_RUNTIME_MOD_JSON}")
  message(FATAL_ERROR "OPENQ4_RUNTIME_MOD_JSON must point to the generated baseoq4/mod.json")
endif()

if(NOT DEFINED OPENQ4_RUNTIME_PAK0 OR NOT EXISTS "${OPENQ4_RUNTIME_PAK0}")
  message(FATAL_ERROR "OPENQ4_RUNTIME_PAK0 must point to the generated baseoq4/pak0.pk4")
endif()

if(NOT DEFINED OPENQ4_BUILD_STAMP OR NOT EXISTS "${OPENQ4_BUILD_STAMP}")
  message(FATAL_ERROR "OPENQ4_BUILD_STAMP must point to the Vita CI build stamp")
endif()

# Quake 4 needs the Vita extended-memory application profile. This mirrors the
# established Vita idTech 4 ports while keeping the SELF itself safe-signed.
set(VITA_MKSFOEX_FLAGS "-d ATTRIBUTE2=12")

vita_create_self(eboot.bin "${OPENQ4_ENGINE_ELF}")

# VitaSDK requires APP_VER in ##.## form; 00.10 represents project version 0.1.
vita_create_vpk(Vita-OpenQ4-engine.vpk VOQ000004 eboot.bin
  VERSION 00.10
  NAME "Vita-OpenQ4"
  FILE "${OPENQ4_RUNTIME_MOD_JSON}" baseoq4/mod.json
  FILE "${OPENQ4_RUNTIME_PAK0}" baseoq4/pak0.pk4
  FILE "${OPENQ4_BUILD_STAMP}" build.txt
)
