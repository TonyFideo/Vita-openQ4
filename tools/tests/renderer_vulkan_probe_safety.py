#!/usr/bin/env python3
"""rendererVkProbe must not reload the Vulkan module while it is the active renderer.

The console command loads renderer-vk, calls its GetRenderAPI, runs the
bring-up probe, then calls the module's Shutdown and unloads it. While Vulkan is
the active renderer that load returns the live module instance -- LoadLibrary
and dlopen only raise its reference count -- so the sequence would re-run
idLib::Init under the running renderer, then free its SIMD processor and clear
its dict string pools while the renderer still uses both, and let the probe's
throwaway instance and device repoint volk's function pointers away from the
live device. The loader has to refuse before it loads anything.
"""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(relative_path: str) -> str:
    return (ROOT / relative_path).read_text(encoding="utf-8")


def require(haystack: str, needle: str, context: str) -> None:
    if needle not in haystack:
        raise AssertionError(f"Missing {needle!r} in {context}")


def braced_block(source: str, marker: str) -> str:
    """The marker through the end of the first brace-balanced block after it."""
    start = source.find(marker)
    if start == -1:
        raise AssertionError(f"Missing {marker!r}")

    depth = 0
    for index in range(source.index("{", start), len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : index + 1]

    raise AssertionError(f"Could not find the end of the block after {marker!r}")


def validate_probe_refuses_active_vulkan() -> None:
    loader = read("src/renderer/RendererModule.cpp")
    context = "R_RendererModule_RunVulkanProbe"
    probe = braced_block(loader, "bool R_RendererModule_RunVulkanProbe( bool verbose ) {")

    guard = braced_block(
        probe,
        "if ( rm_state.interfacesPublished && rm_state.status.activeApi == RENDER_MODULE_API_VULKAN ) {",
    )
    require(guard, "rendererVkProbe: the Vulkan renderer is active", f"{context} active-Vulkan refusal")
    require(guard, "return false;", f"{context} active-Vulkan refusal")

    # The load itself hands back the live instance, and GetRenderAPI and
    # Shutdown then run against it, so every one of them has to sit behind
    # the refusal.
    guard_end = probe.index(guard) + len(guard)
    for token in (
        "Sys_DLL_Load( modulePath )",
        "GetRenderAPI( &moduleImport )",
        "moduleExport->Shutdown();",
        "Sys_DLL_Unload( handle );",
    ):
        position = probe.find(token)
        if position == -1:
            raise AssertionError(f"Missing {token!r} in {context}")
        if position < guard_end:
            raise AssertionError(f"{token!r} runs before the active-Vulkan refusal in {context}")


def main() -> None:
    validate_probe_refuses_active_vulkan()
    print("renderer_vulkan_probe_safety: ok")


if __name__ == "__main__":
    main()
