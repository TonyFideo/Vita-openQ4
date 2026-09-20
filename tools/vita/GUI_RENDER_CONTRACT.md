# Vita GUI texture and frame contract

## Candidate changes (2026-09-20)

Restore the transparency of images whose coverage is packed into green, and
initialize each Vita display frame before translucent/additive GUI composition.
These are engine changes: no replacement fonts, materials, menu art, brightness
limits, disabled blend stages, larger memory pools or changed compression policy.
They target the reported rectangular glyphs in Settings and accumulating light
at the sides of the new-game menu. The final game image still needs validation
on Vita and Vita3K; these tests are not a claim that both screenshots are fixed.

### Packed image coverage

`idImage::DeriveOpts()` specifies BC1/DXT1 plus `CFM_GREEN_ALPHA` for `TD_FONT`.
This is not ordinary RGBA: sampling must produce `(1, 1, 1, green)`.
`idImage::SetTexParameters()` in OpenQ4 (including emileb/openQ4) implements that
mapping with native texture swizzle. The Vita branch excludes that API, and the
GLES_D3 material shader previously had no equivalent operation.

The material program now receives `uTextureGreenAlpha`. On Vita the engine
selects it from the bound image's format metadata, after lazy loading, and sets
it for every stage, including the next ordinary image. Cinematic scratch images
remain RGBA. Non-Vita paths keep the value zero because their sampler already
performs the mapping. Decoding occurs before vertex colour, stage tint, alpha
test and blending. Both base and alpha-test shader variants share the change.
The compressed atlas data and its mip chain are unchanged. The depth prepass
uses the same material programs, so both perforated stages and solid white
fills also set the format flag before drawing instead of inheriting GUI state.

### Frame ownership

The authored menu has an opaque 640-unit background and translucent/additive
layers extending beyond it. `RB_SetBuffer()` previously did not initialize
colour unless a debug-clear option was active. Retained swap-buffer contents
can therefore become the destination of the next frame's additive operations.

On Vita, `RC_SET_BUFFER` now clears colour once for the new frame. It preserves
existing diagnostic clear colours, otherwise initializes black, temporarily
removes scissor clipping, enables all colour writes, and invalidates the legacy
state delta after the direct mask change. No depth or stencil clear is added.
No clear is added to individual 2D views: HUDs and in-game dialogs must remain
composited over the current scene. Other platforms retain their old policy.

Doom3-ReArmed's `neo/renderer/tr_backend.cpp` was used to cross-check the
set-buffer / draw-view / swap command boundary, not as a source of per-menu
rendering exceptions. Its image pipeline is not assumed to share OpenQ4's
`CFM_GREEN_ALPHA` storage contract.

## Reproducible validation

Run from the repository root:

```sh
VOQ_REQUIRE_GPU_TESTS=1 LIBGL_ALWAYS_SOFTWARE=1 \
  python3 -m unittest discover -s tools/vita/tests -p 'test_vita_gui*.py' -v
mkdir -p .tmp
c++ -std=c++17 -Wall -Wextra -Werror -Isrc/renderer/GLES \
  tools/vita/tests/vita_shader_compat_test.cpp \
  src/renderer/GLES/vita_glesd3_shader_compat.cpp -o .tmp/vita_shader_compat_test
.tmp/vita_shader_compat_test
```

The pixel tests compile the production material vertex/fragment GLSL, render
synthetic samples into an RGBA8 EGL surface, and read back pixels. They compare
the shader mapping against native sampler swizzle, test alpha discard, colour
and vertex-alpha modulation, blending, and switching back to ordinary RGBA.
The samples model already-decoded texture channels; they do not exercise Vita's
BC decoder or GXM. The GUI CI job requires the EGL tests; environments without
EGL may skip them only when `VOQ_REQUIRE_GPU_TESTS` is not set.

The C++ contract tests extract and execute the real `RB_SetBuffer()` and image
format selector with mocked GL calls, for both Vita and desktop preprocessor
branches. They test 120 frame starts, dirty masks/scissor, debug clear colours,
null images and format selection. Additional source checks keep selection after
image loading, verify that the stage binder returns the actual cinematic or
fallback image, protect both depth-prepass draw paths from stale GUI state,
and forbid a per-2D-view colour clear.

Local results: all 17 GUI tests passed, including four pixel tests on Mesa
llvmpipe / OpenGL ES 3.2, plus the existing Vita shader-normalization test.
Negative controls against the source before this change: three of four pixel
tests failed with the old fragment shader; the frame contract test failed with
the old `RB_SetBuffer()`. This establishes test sensitivity, not a Vita result.
The complete local Python regression suite also passed: 69 tests, no skips,
with the pinned VitaGL patch applied to a fresh source copy.
VitaGL dependency reviewed: `eccee6d767ad5f632812414a6b8251031fe62f0b`.

## Device/emulator acceptance still required

Install a build containing these source changes. Enter Settings and visit its
tabs; check readable glyphs and correct background transparency. Enter New Game,
leave it idle for at least 60 seconds, and navigate away/back several times;
compare the side graphics near entry and after the wait. In gameplay, verify
that the HUD/pause UI does not erase the scene. Do not change brightness, remove
art, or disable material stages to obtain a passing result.

The supplied session also ends in an out-of-memory fatal error while loading.
This change does not fix or validate that separate failure. Shader link success
alone, including the log's 20/20 programs, is not visual/gameplay validation.
