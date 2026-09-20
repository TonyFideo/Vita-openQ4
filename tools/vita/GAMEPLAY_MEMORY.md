# Vita map-loading memory: follow-up to build 250

## Evidence and scope

The uploaded 20260920-211120 log identifies build 250 / 1ad2041. The first
failed reservation is malloc(198912), with heapArena=314519552,
heapUsed=313820632, heapFree=698920 and heapTop=44832. There is no size
multiplication overflow. The matching ELF resolves return address 0x81173251
(Thumb bit removed) to Mem_Alloc; subsequent 92416-byte failures resolve
0x8117351b to Mem_ClearedAlloc during recursive fatal handling. These are
allocator entry points, not a complete allocation stack or proof of a corrupt
player model. Loose-file misses are followed by a successful pak003.pk4 open.

1777 entities are spawned and game initialization completes before the player
lookup fails. Aggregate heap free bytes are not a largest-free-block measure.
The 115343384 free CDRAM bytes do not belong to the 300 MiB newlib heap; the
unavailable GPU-pool counters are not zeros measured from a working query.

Menu clear samples still retain non-black values after a requested black clear.
For example sample 3 has identical before/after values. Record the failed
observation without treating readback as proof of the exact defective layer.
No menu drawing, materials, brightness, framebuffer or clear behavior is changed
by this candidate. Gameplay loading is the current priority.

## Corrected ownership

1. idMD5Mesh::ParseMesh creates a private CPU surface to derive its bind basis.
   After copying position/normal/tangents into baseVectors it used the general
   deferred-free route. R_GeoDeferFree retains the surface on frameData until
   a frame boundary. This is unnecessary for scratch that was never submitted.
   Use R_ReallyFreeStaticTriSurf at that ownership boundary. The existing
   deformed-surface destructor frees owned vertices/planes but retains borrowed
   deformInfo topology. Submitted surfaces still use the deferred route.
2. rvRenderModelMD5R::BuildDynamicMeshTemplate likewise releases its private
   temporary static surface after the persistent vertices and deform data are
   copied, including the invalid-input cleanup branch. No general purge or
   forced GPU synchronization is introduced.
3. The compiled Vita GLES_D3 skinning backend has no GPU deformation consumer.
   R_GpuSkinning_UsesSourceSidecars expresses this policy independently of a
   desktop user's r_gpuSkinning setting. Both MD5 and MD5R loaders avoid the
   duplicate GPU bind-pose/four-influence streams on this backend. Surface
   contract admission also rejects it before allocating joint palettes; MD5R
   keeps CPU tangents enabled. Other platforms retain their original builders
   and runtime cvar toggles. A future Vita GPU skinning implementation must
   explicitly enable this capability when it implements the consumer.

CPU deformation weights, bind basis, mirrored vertices, indices, collision,
silhouette data, entity population and original assets are preserved. No heap
or pool is enlarged, no asset is downscaled, and no reserve failure is retried
through a substitute allocator. The exact live-byte reduction requires another
target run; 94 passing host tests are not a successful gameplay session.

## Milestones in the next log

VitaRuntimeAudit_Memory now caps only allocation-traffic snapshots. Explicit
load checkpoints and failures remain visible after the 96-snapshot budget.
Session brackets world construction, game initialization, player creation,
renderer finalization, load-cache release, settle frames and mapSpawned=true.
Names start with load:, including load:player:begin, load:player:done,
load:renderer-finalize:done, load:settle:done and load:ready.

load:ready means the session is permitted to draw the world, not proof of a
correct world/HUD image. If a new failure occurs, retain the entire log and the
exact build's unstripped ELF; the next blocker may lie after player creation.

## Tests and next device run

Six new host tests execute extracted production policy, sidecar/admission
boundaries and CPU scratch tails with mocked geometry allocation/math. They
cover both platform spellings, the unchanged desktop policy, 1024 repeated
scratch builds without a frame boundary, copied basis values, packed-template
success/failure and reuse, CPU fallback, and the source order of load stages.
The existing allocator test verifies an explicit player checkpoint after the
traffic cap. These are lifetime/control-flow tests, not GXM or real asset tests.

Install the matching full-engine VPK. Enter Mission and start the same campaign
map directly; no menu wait is required. Preserve the emulator log, loading.log,
and errors.log, and capture the first world image or the new stopping point.
If loading reaches its continue prompt, press the normal continue button.
Do not change graphics quality or heap settings for this comparison. After the
first successful load, repeat return-to-menu and reload to test ownership over
multiple loads before moving to input, combat and sustained gameplay.
