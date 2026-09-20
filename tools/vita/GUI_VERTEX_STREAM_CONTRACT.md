# Vita GUI vertex stream addressing

## Follow-up to build 245 (2026-09-20)

The user's build-245 log identifies commit
`7e6b1fd48a16339cc6cf379146fbf9152c913ff8`. Settings is still solid yellow,
and navigating Settings/Arena draws a complete font atlas over panel geometry.
The earlier green-alpha/frame-initialization changes did not resolve those
screenshots. Do not interpret their passing Mesa tests as a Vita result.

This candidate corrects a separate, reproduced address-truncation defect in the
pinned VitaGL dependency. Visual acceptance on Vita/Vita3K is still pending.

## Source-level defect

OpenQ4's `idVertexCache::Position()` returns an offset into a shared VBO.
`R_GLESD3_BindDrawVertAttributes()` passes that offset plus each `idDrawVert`
field offset to `glVertexAttribPointer()`. The user's log confirms a 4096 KiB
frame-temp stream, so valid offsets are not limited to the first 64 KiB.

VitaSDK declares `SceGxmVertexAttribute::offset` as **uint16_t**. At VitaGL
`eccee6d767ad5f632812414a6b8251031fe62f0b`, the packed-VBO branch of
`source/custom_shaders.c` sets the GXM stream pointer to the VBO allocation's
start and copies the complete GL attribute offset into that narrow field.
Values of 65536 and above wrap; an attribute can cross that boundary even when
the start of its vertex is below it. This is a byte-offset defect, not a limit
on the number of indices and not a reason to split or shrink engine geometry.

For example, with block base 65536 and a UV field offset of 56:

```
Expected: VBO + 65536 + 56 + vertexIndex * stride
Old:      VBO + uint16(65536 + 56) + vertexIndex * stride
Fixed:    (VBO + 65536) + uint16(56) + vertexIndex * stride
```

The wrong address changes position, colour and UV data together. An atlas can
therefore be sampled using another surface's fullscreen geometry, even when
the material's texture binding is correct. This mechanism is consistent with
the captures, but the current log contains no per-draw offsets proving which
individual corrupt surface crossed the boundary.

## Implementation

`patch_vertex_streams()` in `tools/vita/patch_vitagl_vita3k.py` rebases packed
VBO pointers in all three custom-shader paths: indexed draws, array draws, and
multi-array draws. Only relative field offsets enter GXM's uint16 descriptor.
The same patch is valid on hardware; it is not gated on emulator behavior.

Every enabled attribute is checked for a compatible VBO, offset range and
stride. A layout that cannot share the rebased stream uses VitaGL's existing
independent-attribute route. VBO data remains zero-copy in either case; no
per-draw vertex allocations, extra buffer uploads or new draw calls are added.
Existing constant-attribute and client-memory routes are not replaced.

The patch has exact pinned-source checks and rejects duplicate application.
Its implementation remains in the entrypoint hashed by the existing VitaGL
CI cache key, so a build cannot restore the old library under the new key.
With LOG_ERRORS, each draw path reports its first packed base above 64 KiB:

```
[VOQ4][vertex] ...: rebased VBO base=... stride=... attrs=...
```

That line records an actual corrected addressing path, not a passing visual
test. No engine shader, atlas, GUI material, brightness, memory-pool size,
compression policy, SAFE_DRAW flag or draw-speedhack setting is changed.

## Executable regression and limits

`test_vita_gui_vertex_streams.py` extracts the real address-selection blocks,
macros and stream submission from the patched VitaGL source. A native C harness
uses the VitaSDK field widths and captures the descriptors/pointers sent to
GXM. It checks their effective addresses against the original GL offsets.

Four test groups contain 57 cases: low offsets, large offsets through the
4 MiB range, crossing 64 KiB inside a vertex, and mixed layouts. These include
non-contiguous shader attribute locations, separate VBOs, an earlier UV stream,
an out-of-range relative UV offset, disabled colour, and different strides.
The VBO cases also assert no temporary vertex allocation/copy.

Negative control using the unchanged pinned address code: **39 failing cases**.
Corrected code: **57/57 cases pass**. Complete local suite: **73 tests pass,
no skips**, including the previous material-pixel tests. These are executable
address tests with GXM mocked, not a hardware draw or an emulator screenshot.

Run on a fresh pinned VitaGL checkout:

```sh
python3 tools/vita/patch_vitagl_vita3k.py .tmp/vitagl
VOQ_VITAGL_SOURCE="$PWD/.tmp/vitagl" VITAGL_REPO="$PWD/.tmp/vitagl" \
  VOQ_REQUIRE_GPU_TESTS=1 LIBGL_ALWAYS_SOFTWARE=1 \
  python3 -m unittest discover -s tools/vita/tests -p 'test_*.py' -v
```

The existing GUI workflow supplies the patched dependency and runs this test.
Device acceptance: visit all Settings tabs, navigate into Arena Circuit and
back repeatedly, leave New Game idle for 60 seconds, and check for full-atlas
quads, solid-colour glyphs and side accumulation. Gameplay/HUD and the separate
map-loading memory failure remain unvalidated by this change.

## References

- VitaSDK `psp2/gxm.h`, `SceGxmVertexAttribute` and `SceGxmVertexStream`:
  https://docs.vitasdk.org/group__SceGxmUser.html
- Pinned VitaGL custom-shader addressing:
  https://github.com/Rinnegatamante/vitaGL/blob/eccee6d767ad5f632812414a6b8251031fe62f0b/source/custom_shaders.c
- OpenQ4 uses the standard GL buffer-offset contract; the Android/OpenQ4
  reference and Doom 3 ReArmed are not assumed to use this exact modern shared
  upload path. The correction belongs at the GL-to-GXM translation boundary.
