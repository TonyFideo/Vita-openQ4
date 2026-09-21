# Vita cinematic-skip memory milestone (build 266)

Build 266 reaches `load:ready`, runs the opening airdefense1 cinematic with a
working 60 Hz async clock, and repeatedly captures `_currentRender` through the
typed RGBA16F path. The user-triggered cinematic skip is now the first failing
boundary.

The first allocation failure is an aligned 262144-byte request after the engine
has spent roughly 27 seconds inside the synchronous cinematic fast-forward. The
libc heap reports about 312.9 MB live with only a small top chunk. The wrapper's
return address resolves to `Mem_Alloc16`; that is not yet the allocation's
semantic owner.

A separate, exact arithmetic clue exists during map settle. Between
`load:media:done` and `load:settle:done`, the libc arena grows 9,474,048
bytes. This equals nine times 1,052,672 bytes (1 MiB plus a 4 KiB arena/page
increment). The renderer frame allocator itself grows in 1 MiB
`MEMORY_BLOCK_SIZE` chunks and only resets usage at a presentation-frame
toggle. The cinematic skip likewise executes many authoritative game tics
inside one session frame. This is strong evidence worth measuring, not yet a
license to reset renderer memory from inside gameplay.

The diagnostic revision therefore changes no heap size, no assets, no skip
duration and no simulation logic. It records every retained frame-arena block
growth, the immediate `Mem_Alloc`/`Mem_Alloc16` caller on allocation failure,
re-arms the bounded allocation-traffic sampler after `load:ready`, and records
the ESC/START event before and after the game accepts it. The next target log
can establish whether frame-arena growth begins specifically after the skip
request and identify which renderer callsite crosses each 1 MiB boundary.


## Build 269 target result: renderer publication is the retained-memory owner

The 20260921-104050 target run is build 269 / 6b7b953. START reaches
`game->HandleESC()` and is accepted as `ESC_IGNORE`, so the game enters the
stock synchronous cinematic-skip path rather than opening a menu. At that
boundary newlib reports 292,719,504 live bytes. About 2.9 seconds later the
first fatal reservation is exactly 1,048,576 bytes. The immediate aligned
allocator caller resolves in the matching ELF to
`idDynamicBlockAlloc<idDrawVert,1048576,1024,0>::AllocInternal`, i.e. the
renderer triangle-vertex allocator requesting another base block. The frame
arena does not grow after the skip request, disproving the earlier frame-arena
candidate.

This is consistent with the renderer lifetime contract. Static/dynamic
triangle frees are deferred until a real render-frame boundary. The stock game
skip intentionally executes many authoritative 60 Hz simulation tics inside
one Session frame, while entity/light Present paths can still publish changed
renderer defs on every skipped tic. Updating a def retires dynamic geometry,
but there is no intervening backend frame to drain the deferred-free list.
Roughly 19.5 MiB of additional live CPU heap accumulates before the new
triVertexAllocator base block can no longer be allocated.

The Vita integration now exposes the game's existing `skipCinematic` state
through the idGame interface and defers only RenderWorld Add/Update publication
for entity and light defs while that synchronous fast-forward is active.
FreeEntityDef/FreeLightDef remain live, BSE effect ServiceEffect remains live,
and all game tics, scripts, AI, physics, events, sound-time advancement and
cinematic timing execute unchanged. New entity/light additions return the
normal invalid handle during the unpublished interval, so their owners will
publish them on the first ordinary tic after the skip instead of retaining a
phantom renderer slot.

This is deliberately not a timescale change, a capped skip loop, an extra
presentation frame, an allocator reset, a heap increase, or an asset-quality
change. The engine continues to drain deferred geometry only at its existing
safe render-frame boundary.
