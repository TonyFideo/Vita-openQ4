# Build 234: native compressed mip storage lifetime

## Observations, not a crash backtrace

The supplied Vita3K log contains two concatenated launches. Only the final one
belongs to 55429b01af03865c9022343cd9794bd6608d64cb (Action 234). In that launch,
the earlier forced 4 MiB stream-buffer allocation is absent. UI/game setup
finishes, Session opens mainmenu.gui, the lexer succeeds, and Desktop parsing
begins. The final lines open icon_repeater.dds in pak021.pk4 and then end inside
a close-file trace. There is no final exception address or host backtrace.
The smaller loading.log ends earlier at INITIALIZING MENUS. Neither last line
identifies a faulting instruction. The fullscreen font atlas reported for 232
is still a separate unverified rendering symptom.

## Defect found in the pinned native-BC uploader

VitaGL eccee6d767ad5f632812414a6b8251031fe62f0b, gpu_utils.c:

- gpu_alloc_compressed_texture queues sceGxmTransferCopy into a mip destination.
- Loading the next mip can call vgl_realloc on that destination without a
  transfer-completion barrier. Movement can invalidate an outstanding write.
- The manual relocation fallback also copies/releases the previous block and
  does not check the new allocation before copying into it.
- General realloc does not express the original GPU allocation's alignment
  requirement; sampled-texture updates also need ownership protection.

This is a concrete storage-lifetime defect. It has not been proven to be the
instruction responsible for the user's particular Vita3K termination.

## Correction

For already-compressed, native 2D BC formats (UBC1/2/3/4/5), the compatibility
profile now uses the existing upstream block swizzlers synchronously. It does
not decode or recompress DDS pixels: all compressed blocks, image dimensions,
formats and authored mip levels are retained. The GPU still samples native
compressed textures. Only their memory ordering is prepared by the CPU.

A checked per-level layout defines offsets and sizes, including rectangular,
NPOT and sub-block tails. Chain growth allocates GPU-aligned replacement memory,
then copies the existing mip prefix, and only then retires old storage. An idle
existing level updates in place; a sampled texture uses copy-on-write and the
library's existing deferred retirement. Allocation failure leaves the previous
texture valid. No asynchronous transfer remains queued by this BC path.

Other formats, runtime compression and cubemap paths keep their previous
implementations. Eager defineicon loading restored before 234 remains enabled.
No icon/material is skipped, no mipmaps are removed, and no image-name exception
or rendering bypass is introduced. Previous linear-mip/init compatibility edits
are preserved byte-for-byte in patch_vitagl_vita3k_linear.py and its base helper.
All new generated code remains in the entrypoint hashed by the existing CI
VitaGL cache key, so the dependency must rebuild rather than reuse the old code.

This trades queued transfer setup for CPU block reordering. Its actual load-time
cost on Vita/Vita3K has not been measured and is not claimed as an optimization.

## Executed native tests

Command (run independently with HOST_CC=clang and HOST_CC=gcc):

    VOQ_BC_SANITIZE=1 python3 -m unittest discover -s tools/vita/tests -p test_vita_bc_upload.py -v

Both compilers pass two tests with AddressSanitizer and UndefinedBehaviorSanitizer:
12,906 shape/format cases each, checking every compressed byte in all mip levels,
unchanged input, rectangular/NPOT layouts, initial/growth/COW allocation failures,
old sampled backing lifetime, idle writes and invalid levels/sizes. The test
executes the generated allocator and layout. GXM, allocation and retirement are
mocked. The swizzler mock transcribes upstream scalar twiddle-mask traversal and
is checked against independent Morton/tile addressing; this is not execution of
the production ARM NEON swizzler or the game's renderer.

A separate minimal model forces relocation while retaining a delayed-copy
pointer; AddressSanitizer reports heap-use-after-free as expected. This models
the old ownership sequence, not a complete VitaGL or Vita3K reproduction.

CI must still apply the combined patch to the real pinned dependency, compile
VitaGL and the full engine, and validate the resulting VPK. The VPK needs a real
run with the user's retail data to establish whether the startup crash or the
font-atlas symptom changes.

## Source references

- https://github.com/Rinnegatamante/vitaGL/blob/eccee6d767ad5f632812414a6b8251031fe62f0b/source/utils/gpu_utils.c
- https://github.com/Rinnegatamante/vitaGL/blob/eccee6d767ad5f632812414a6b8251031fe62f0b/source/utils/gpu_utils.h
- https://github.com/Rinnegatamante/vitaGL/blob/eccee6d767ad5f632812414a6b8251031fe62f0b/source/utils/texture_swizzler.cpp
- https://github.com/TonyFideo/Vita-openQ4/blob/55429b01af03865c9022343cd9794bd6608d64cb/src/renderer/OpenGL/gl_Image.cpp
