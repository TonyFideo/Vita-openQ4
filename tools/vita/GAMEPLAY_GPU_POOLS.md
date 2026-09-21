# Gameplay loading: restore actual GPU memory ownership after build 256

## Runtime evidence

The uploaded 20260921-012058 emulator file contains BOTH build 255 and build
256. The newer session starts at 22:16:57.955, commit 7a408d3; do not attribute
the earlier 21:31 new[] failure to this build. Player creation completes again.
Image 317 (marine_fighter) now finishes. Images through 322 finish before the
first graphics allocation failure at image 323 (underlit_alpha), 22:19:39.400.
The first failure is memalign(87408) in gpu_alloc_mapped_aligned_for_gpu, not
the metadata-cache new[] from build 255. heapUsed=313807224, heapFree=700040,
heapArena=314507264, kernelCdram=115343384; the latter is a separate bank.

The old code logs eleven GL_OUT_OF_MEMORY results, continues uploading, reports
image 323 done anyway, and finally fails a CPU payload read at image 324.
Thus 322 is the last completion before GL failures, six entries beyond build
255, not a claim of 323 valid images or any rendered gameplay. The prior sky
path at image 333 is still not reached in this session.

## Root cause: thresholds are reservations

GLimp_Init passed VitaGLimp_FreeCdramBytes() as cdram_threshold. The pinned
vglInitWithCustomThreshold computes pool = max(free - threshold, 0), so this
reserved essentially the entire available CDRAM bank OUT of VitaGL. GPU
allocations then followed the ordinary fallback path into the newlib heap,
competing with game data. The 110 MiB unused CDRAM was not evidence that those
newlib allocations could succeed; it was evidence that the bank was excluded.

The client now leaves zero additional CDRAM reservation. Already-owned memory,
including the native loading framebuffer, is already excluded by the kernel
free-memory query. The framebuffer handoff ownership is unchanged. The CPU
heap remains 300 MiB; no asset, resolution, mip count, entity, gameplay rule or
menu material is reduced or replaced. This restores the intended GPU bank,
not an allocator retry that conceals a failing request.

## Complete initialization for the active allocator profile

The pinned mspace profile computes pool sizes only after init_gxm, checks the
kernel/budget query, subtracts reservations without underflow and rounds DOWN
to each bank's allocation granule. This is essential because the observed
115343384-byte report is not a 256 KiB multiple: its usable CDRAM plan is
115343360 bytes (110 MiB). Common-dialog reservation and the 10 MiB RAM
reservation remain unchanged. System-app budgets also retain their reservation
rather than allocating it when free memory is below the requested threshold.

Each requested pool is initialized as a transaction: kernel allocation,
base-address lookup, GPU mapping, then native sceClibMspaceCreate. Only a
completed set is published to the allocation/free routing tables. Failure rolls
back created mspaces, mappings and kernel blocks before returning; no partial
pool is advertised as configured capacity. Newlib's block is queried and mapped
while a temporary allocation remains alive, rather than querying a freed pointer.
The dummy is freed on success/failure, and is never itself the mapped region.
Successful pool backing stays alive for the process-wide VitaGL context.

An explicit readiness query separates initialization success from VitaGL's
boolean resolution-fallback result. Context construction is not attempted after
failed pool setup, and GLimp does not mark the renderer ready. Existing custom
heap/on-demand profiles retain their original implementation; this patch fully
implements the pinned mspace profile used by the port, not all allocator modes.
Per-bank [VOQ4][gpu-pool] lines report actual mapped pool backing. Unimplemented
Vita3K mspace statistics remain unavailable, rather than fabricated free bytes.

## Texture failure propagation

AllocImage now checks each level's GL result before proceeding, purges partial
storage and reports the named asset, side and level on failure. Previously
GL_CheckErrors consumed errors and let the loop continue. The normal binary
upload loop releases staging, checks the upload result, closes its source and
purges the partial texture before reporting. Debug builds no longer consume
Vita upload errors before the owning load/cube callback can check them.
No missing level or failed texture is deliberately accepted as a loaded one.

## Validation and next target run

117 host tests pass with a freshly patched pinned VitaGL, both dependency
variables set and offscreen pixel tests required. Six added groups cover budget
arithmetic, real allocation routing to CDRAM and matching free, all 19 injectable
pool-setup failure points, retry/duplicate setup, empty/aligned banks, overflow,
context gating and first-error termination of image storage/upload loops.
The six groups also pass ASan/UBSan. SDK/GXM services in these tests are mocked;
no hardware memory consumption, GPU pixels or successful gameplay is claimed.

References: pinned VitaGL source/vgl.c, source/utils/mem_utils.c and gpu_utils.c;
VitaSDK psp2/kernel/sysmem.h and clib.h; Doom 3 ReArmed neo/sys/glimp.cpp uses
zero CDRAM threshold too. Android OpenQ4's texture loaders inform source/mip
semantics, but cannot define the Vita memory-bank budget. Existing image-loader
byte/orientation tests remain required rather than copying an Android allocator.

Compile the full engine with VitaSDK and verify its build identity before testing.
Start fresh, keep the same PK4s/settings and enter Mission directly. Check for
an active bank=0 and the actual cdram plan, then load:player:done, the first
image failure or cube-stream completion, load:images:done and load:ready. Logs
are not a substitute for verifying the world/HUD and controlling the player.
