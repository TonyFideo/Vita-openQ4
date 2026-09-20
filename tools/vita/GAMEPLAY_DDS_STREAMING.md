# Gameplay load: DDS staging after build 251

## Runtime evidence and limits

The uploaded 20260920-215242 Vita3K log identifies build 251 / 3e7b95a.
It records load:player:done at 18:46:27.022, with 305558864 heap bytes used.
The previous build stopped before that milestone. Renderer finalization then
finishes models (0 purged, 1153 kept), enters idImageManager::EndLevelLoad,
and fails at 18:46:34.951: malloc(349832), no multiplication overflow,
heapArena=314265600, heapUsed=312264944, heapFree=2000656, heapTop=6592.
The return address resolves to Mem_Alloc in the matching build-251 ELF; it is
not an allocation stack and does not identify an exact texture. The next
369664-byte failure is during recursive fatal handling.

Total free heap bytes do not measure its largest free block. The kernel's
CDRAM counter is not space available to a newlib malloc. gpuReady=0 means
pool statistics are unavailable, not that the GPU pools were measured empty.
The named image-loading milestones and first failed reservation are the useful
boundary; startup hang diagnostics and ordinary loose-file misses followed by
successful PK4 reads do not identify this failure.

## Implementation

The existing DDS path copied the whole file into the renderer's heap and kept
it until image upload completed. During texture allocation Vita also inherited
a desktop NVIDIA workaround that allocated a second throwaway CPU buffer for
each compressed mip even though pinned VitaGL accepts NULL data explicitly.
These are avoidable transient reservations on a nearly full heap, not proof
that either alone accounts for the exact 349832-byte failing request.

The new source path first reads the 128-byte DDS header, adding the 20-byte DX10
extension only when present. It validates the complete declared mip layout,
format/capability and file length before allocating payload storage. The same
downsize policy, image usage, RXGB/DXT5 normal interpretation and selected levels
are retained. There is no new quality reduction or format conversion.

idBinaryImage has an explicit file-backed compressed source. A valid source is
adopted only after all descriptors pass validation; Clear closes it exactly
once. ReadImageData materializes a requested mip; ReleaseImageData frees that
payload while preserving the validated descriptor for re-reading. The actual
renderer reads one mip, uploads it, and releases it before the next mip.
Sequential reads use CUR rather than restarting the PK4 inflater with SET.
Re-reads may seek backwards normally. Other existing callers keep their buffered
API; that path now retains only the selected payload span rather than the file
header, unselected top mips and any unrelated trailing bytes.

The renderer's upload consumes client bytes before they are released. In the
pinned VitaGL native-BC path block reordering into GPU storage is synchronous;
there is no queued transfer retaining the DDS source pointer. GPU storage and
sampled-texture copy-on-write semantics are unchanged. A source read failure
purges the partial texture and reports an error instead of exposing incomplete
data as a successful load. Serialization also materializes and releases each
streamed mip, and retains the buffered serialized byte sequence.

Vita passes NULL when defining empty compressed GPU storage, removing only the
unneeded desktop CPU reservation. Other platforms retain the existing driver
workaround. No heap/pool size, asset, entity, shader, gameplay rule or menu
brightness is changed. CPU image-program and generated-bimage paths are not
converted to streaming in this change.

Per-image begin/done markers identify the pending asset and storage size.
Periodic image-phase heap checkpoints retain the existing successful/failure
allocation audit. They do not estimate live texture bytes from allocation traffic.

## Validation

The host suite contains 100 tests. Six new tests compile the production DDS
parser/layout, downsize calculation, BinaryImage class and staging methods with
a simulated filesystem and tracked payload allocator. Cases include DXT1,
DXT5, RXGB and BC7, rectangular/tiny levels, selected mip ranges, serialization
parity, truncated headers/payloads, unsupported formats/capabilities, short writes,
failed seeks/reads/allocations, repeated reads and ownership replacement.

A synthetic 512x512 DXT5 full chain cannot use the buffered path with a 262144-byte
per-reservation ceiling. Streaming uploads all ten original levels with a
262144-byte peak tracked payload. This excludes container metadata, filesystem
and GPU allocations and is not a measurement of a real map's memory saving.
A negative-control build which omits mip release fails the lifetime test.
The C++ stream harness also passes AddressSanitizer and UndefinedBehaviorSanitizer.
The render submission order and partial-read failure path have source-contract
checks; those checks are not target GPU execution.

VitaSDK compilation/packaging and a subsequent device/emulator test are separate
requirements. This reduces a verified transient working-set requirement; it
neither proves sufficient memory for the full world/HUD nor claims gameplay works.

## Next target run

Start fresh, enter New Game / Mission and load the same campaign map directly.
No menu wait is needed. Keep the same graphics settings and original PK4s.
Retain the complete emulator log, loading.log and errors.log, plus the first
world image or stopping point. The last unmatched [VOQ4][image-load] begin marker
identifies an image still being processed. load:images:done and
load:renderer-finalize:done indicate completed loading phases; load:ready is
not a substitute for seeing and controlling the rendered world.
