# Gameplay loading: stable DDS metadata after build 255

## Measured progress, not an inferred gameplay pass

The uploaded 20260921-004439 log identifies build 255 / 4ab3da6. It spawns
1777 entities and completes load:player:done, then enters image finalization.
316 of 1337 pending images complete; image 317 is gfx/effects/ships/marine_fighter.
The build-252 session completed 332 of the same 1337 images before failing at
the sky cube. Thus this attempt stopped 16 entries earlier (23.635% versus
24.832% of this particular queue), not closer to a playable frame. Neither
number is a whole-game loading percentage or evidence of GPU-correct images.
No cube-stream marker was reached; the prior sky correction remains untested.

The first failed allocation is malloc(148488), heapUsed=313356936,
heapArena=314421248, heapFree=1064312, heapTop=3576. CDRAM availability and
unavailable GPU pool counters do not extend the newlib heap. The allocation
failure precedes std::bad_alloc, terminate and the final UDF/CPU error. The
later watchdog dumps do not establish a separate initial instruction fault.

## Exact allocator and source evidence

The matching unstripped build-255 ELF resolves 0x81739DD1 to operator new
(after normalizing Thumb). A candidate return address from the crash stack,
0x81404E24, belongs to R_ResolvePreferredDDSImageSource. This is stack scanning,
not a fully unwound stack, but the disassembly supplies a stronger cross-check:
0x81405104 shifts the entry count left by six, adds eight, and branches to
new[] at 0x81404E20. The subsequent loop constructs and copies 64-byte entries.
148488 = 2320 * 64 + 8, exactly the 16-entry idList growth at this cache size.
The source's inline R_ReadDDSFileInfo appends to idList<ddsProbeCacheEntry_t>.

This metadata growth reserves a second contiguous array and deep-copies each
owned name while the old entries remain live. It is not a texture-pixel
allocation and does not identify a corrupt marine_fighter texture. The heap
is also close to its overall limit; removing this spike does not establish
that later image/GPU/world allocations will all fit.

## Implementation and invariants

Use the existing idBlockAlloc to construct 32 stable cache entries at a time.
1024 fixed hash buckets match the prior default bucket count, with linked
entries rather than a growing index/entry pair of arrays. Full case-insensitive
name comparison resolves collisions; no names are truncated, no results are
evicted, and no limit is imposed on the number of images or cache entries.
All hits and misses remain memoized for the original level-load window.
Outside it, probes still read current filesystem state for hot reload.

A miss is probed into initialized metadata before linking a new node. A false
result leaves the caller's metadata untouched and reports the not-found time,
including when timestamp is NULL. Beginning or ending a load clears every
bucket before shutting down the allocator, whose real destructor destroys all
idStr names. No GPU/pixel ownership, format, mip, file-selection precedence,
model, shader, content file, memory pool, or gameplay rule changes.

The cache-release trace reports entry/hit counts, reserved entry bytes and
owned name capacity. Entry bytes exclude allocator link/block overhead and
fixed buckets; this is not a whole-process memory profiler. Block granularity
controls growth allocation size only; it is not a runtime asset/quality cap.

## Regression tests and limits

Five added native test groups compile the production cache code, actual
idBlockAlloc, actual idStr IHash, and the original idList/idHashIndex for the
negative control. The test string owns memory and records deep copies; VFS
metadata responses are simulated. Cases cover 6000 entries with no existing
name copies, positive/negative cache hits, case folding, hash collisions, long
full keys, NULL timestamps, block-allocation failure, repeated clearing and
uncached reload. All five also pass ASan/UBSan.

A test-only 8192-byte per-allocation ceiling is enabled after 2304 entries.
The original cache fails its next array growth (111368 bytes in this host
fixture); the replacement continues to 6000 retained entries, allocating no
more than 2056 bytes at once in this fixture. These are host fixture sizes,
not claimed ARM ABI or complete game measurements. The linked ARM binary's
old 148488-byte reservation is established separately by disassembly.

All 111 host tests pass, with the pinned patched VitaGL supplied and offscreen
pixel tests required. This is not a Vita/Vita3K gameplay pass. Cross-compilation,
packaging, linked-binary inspection and a target run are separate validation.

## Next target test

Start fresh with the same PK4s and graphics settings; enter New Game / Mission
directly. Retain emulator/loading/errors logs and the first world image or new
stopping point. First verify image 317 and then the previously untested cube
at image 333, followed by load:images:done, load:renderer-finalize:done and
load:ready. Finally validate actual world/HUD appearance and player input.
The menu side-brightness bug is intentionally unchanged.
