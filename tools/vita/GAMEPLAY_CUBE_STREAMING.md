# Gameplay loading: row-bounded RGBA8 sky cubes after build 252

## Observed boundary

The uploaded 20260920-224722 log identifies build 252 / 12ee94a. It again
completes player creation and begins image finalization. Image 332 completes;
image 333/1337, `gfx/env/act_2/act2`, begins and malloc(3145773) fails.
heapUsed=313355432, heapFree=1069912, heapArena=314425344. The requested
size is not overflowing. A second 369664-byte failure occurs while handling
the fatal error. The first return address is an allocator boundary, not a
complete allocation stack. Kernel CDRAM and unavailable GPU pool statistics
must not be interpreted as capacity available to a newlib malloc.

The source path is a camera cube. The old general loader reads the complete
TGA source, allocates RGBA faces, retains six of them, then creates another
mip pyramid before uploading. Build 252's DDS-level streaming did not cover
this raw six-face path. This candidate addresses that actual boundary without
changing the named asset, entity population, heap sizes or texture resolution.

## Source-authoritative decoding

`idCubeImageStream` preflights six square power-of-two TGA faces, retaining
file ownership explicitly. User DDS replacements retain their established
priority: if one is selected, the existing general path handles it. Retail
progimg replacements remain suppressed for camera faces because they are
already oriented. Generated caches, image programs, alternative source types,
compressed cube formats and intentional build-time cache generation keep the
existing general path; they are not silently ignored or converted.

`idTgaStreamDecoder` reads bounded blocks, handling 24/32-bit BGR(A), grayscale,
raw and RLE packets, partial reads, image IDs and both origin bits. Invalid
headers, truncated data and packets extending beyond the image are rejected.
The six camera-to-native transforms follow R_LoadCubeImages. Each decoded row
feeds a row pyramid and is uploaded as a row or column in native orientation.
Gamma and linear reductions preserve the existing arithmetic, including its
ordering after rotation and the separate downsize and mip gamma decisions.
Every selected mip is generated; there is no new quality cap or recompression.
Streams close on success, fallback and failure. Partial uploads are purged and
reported as errors, never published as successfully loaded images.

## Native storage and lifetime

The pinned VitaGL patch implements immutable RGBA8 cube storage through
`glTexStorage2D(GL_TEXTURE_CUBE_MAP, ...)` and complete partial face/level
updates through `glTexSubImage2D`. The new allocation fixes the GXM face stride
for all levels from the start. Native RGBA32 mipped cube faces are aligned to
2048 bytes for dimensions >=16; a no-mip descriptor uses tightly packed faces.
Morton addressing places Y in even bits and X in odd bits. Client row bytes are
consumed synchronously before upload returns, with no queued transfer keeping
a pointer to the staging buffer.

A sampled allocation uses copy-on-write and deferred retirement. A failed
replacement allocation leaves the previous bytes/pointer intact. Selecting a
non-mipped sampler cannot reinterpret mipped face strides: a lazily created,
tightly packed base-level view supplies that sampling layout. Texture and
sampler-object paths select the same policy, and updates invalidate old views
safely. Deletion frees both owned allocations; immutable redefinition is an
error. Mipmap generation for this storage operates on its allocated levels
and uses the same copy-on-write boundary. The proc lookup exports the new API.

This is the complete RGBA8 cube path used here, not a claim to implement every
OpenGL storage format/target. The previous compressed-cube limitations remain
outside this change. Image loading no longer skips RGBA8 cube levels. Existing
DDS/2D behavior and the remaining menu-brightness issue are unchanged. Native
GPU storage still needs the full cube: reducing CPU staging does not reduce
its resolution or make the total map fit automatically.

Reference contracts: pinned VitaGL texture_swizzler.cpp and GXM helpers;
Vita3K b5211c0d8736f3c1f20802447d12874b7fdbfced
vita3k/renderer/src/texture/cache.cpp (face alignment and mip traversal);
OpenQ4 R_LoadCubeImages/R_MipMap/R_MipMapWithGamma (orientation/filtering).

## Validation and limits

The full host suite passes 105 tests. Five new groups execute production
stream headers, loader bodies, original mip filters and patched native cube
storage with mocked filesystem and GXM services. 2688 parity cases compare
six faces/every mip, camera/native conventions, origins, RGB/gray/RLE,
downsize and gamma. Additional cases exercise partial reads, malformed input,
close ownership, immutable API errors, replacement-allocation failure,
sampler changes, copy-on-write and generated mip bytes. The same five groups
pass AddressSanitizer and UndefinedBehaviorSanitizer.

A synthetic 1024-square RGB sky with all six faces and eleven levels uses
20468 bytes of tracked CPU row/filter staging, with no individual allocation
above 4096 bytes. This excludes filesystem, stack/decoder metadata and GPU
allocations; it is not measured total map memory or a claim of device gameplay.
Cross-compilation/packaging and the next Vita/Vita3K run are separate checks.

## Device acceptance

Start fresh with the same original PK4s and graphics settings, and load
New Game / Mission directly. No menu wait is required. Keep the full emulator
log, loading.log and errors.log and a capture of the world or stopping point.
`[VOQ4][cube-stream] done` confirms the CPU stream completed, not GPU visual
correctness. Then look for load:images:done, load:renderer-finalize:done and
load:ready, and verify the actual sky, world/HUD and player controls. Repeat
return-to-menu/reload after first entry to qualify ownership over several loads.

## Target integration and real PK4 coverage

The first target attempt (#253) built the entire pinned VitaGL archive, but
identified two integration errors: Image_load.cpp did not include the VitaSDK
clib declaration used by its trace calls, and the engine test step did not
provide VOQ_VITAGL_SOURCE although VITAGL_REPO was available. The follow-up
includes the platform header explicitly and supplies the canonical test source
path. The full-engine lane also installs the offscreen EGL runtime and requires
GPU host tests, instead of weakening or skipping the new tests.

An additional ASan/UBSan harness uses the repository's actual Unzip.cpp and the
exact idFile_InZip Read/Length/destructor with stored and deflated synthetic
PK4s. All 1152 combinations pass: six cube faces, native/camera orientation,
raw/RLE gray/RGB/RGBA, source origins, gamma/downsize and every mip byte. This
qualifies the real ZIP I/O integration; allocation/submission to GXM remain
mocked. The harness and output are retained as supplemental evidence, not game
asset or hardware validation.
