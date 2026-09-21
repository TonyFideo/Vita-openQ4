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
