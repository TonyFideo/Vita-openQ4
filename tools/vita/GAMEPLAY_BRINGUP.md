# Vita gameplay bring-up: evidence before policy changes

## Build 246 acceptance and remaining failures (2026-09-20)

The user confirms Settings and full-screen font-atlas corruption are fixed by
`d1ccbe3d4c233d42467770a2ef246debe0dcd637`. Keep the full-width VBO addressing
correction. New Game's side graphics still brighten over several seconds.
The earlier frame-start colour clear did NOT establish visual acceptance.

The uploaded `VOQ000004 - [Vita-OpenQ4](20260920-193344).log` identifies build
246. It records the corrected indexed path using base 99328, stride 64 and
three attributes. These are observations, not a general renderer qualification.

## Where single-player loading actually stops

The request to load `game/airdefense1` reaches map geometry, collision/PVS/AAS,
script startup and entity population. The final chronological observations are:

- 16:31:34.927: 1777 entities spawned, zero inhibited.
- 16:31:34.964: population/event processing complete.
- 16:31:35.475: precache dedup reports 3512 skipped, 1927 unique, 5439 requests.
- 16:31:35.483: game init complete; total 21334 ms.
- 16:31:35.489 onward: lookup of `models/characters/player/player.md5mesh`.
- 16:31:35.495: `q4base/pak003.pk4` opens successfully.
- 16:31:35.496: `FATAL: Out of memory`, followed by recursive fatal handling.

Original log lines 144995-145142 contain this boundary. Failed *loose-file*
lookups followed by a successful PK4 open do not prove a missing player model.
The last file opened also does not prove that model data is corrupt.

In `src/framework/Session.cpp`, `game->InitFromNewMap()` precedes
`game->SpawnPlayer()`. `FinishLevelLoadCache`, renderer/sound/decl/BSE/UI
EndLevelLoad, cache release, settle frames and `mapSpawned=true` come later.
The log is consistent with failure during player spawning, before those later
milestones. There is no allocator size or stack trace proving the precise
failing request in build 246. Do not claim this candidate fixes the OOM.

The gameplay implementation is already linked from the pinned
`themuffinator/openQ4-game` commit
`8f411dbc38efcb0f5f63b1c300ab220beb73808c` (SP build, monolithic). Player,
weapons, AI, physics, scripts and map/entity code are not features to rewrite
from scratch. Canonical game-library edits belong in the companion repository,
not an engine-side mirror.

## Memory ownership: measurements required

The Vita port reserves a 300 MiB newlib heap. Kernel free USER memory is not
free space *inside* that heap. VitaGL has additional GPU-accessible allocator
pools; CDRAM is a separate bank. A kernel report of 10 MiB USER free and about
110 MiB CDRAM free cannot identify which allocator failed or justify increasing
the newlib reservation. The current context setup suppresses the CDRAM pool
using its free size as a threshold; enabling that bank is a separate hardware
and emulator qualification, not a blind fix for newlib allocation failures.

The diagnostic candidate wraps the external malloc/calloc/realloc/memalign
symbols using GNU ld --wrap. Each call reaches the original allocator exactly
once with the original arguments. There is no retry, fallback heap, resize,
new content preload, or changed deallocation behavior. On failure it logs:
request count/size, multiplication overflow, caller return address, mallinfo
arena/used/free/top counters, kernel banks and free VitaGL pools when ready.
It preserves errno and treats zero-sized NULL returns as legal.

Failure reporting uses stack storage and native console/I/O calls, not the
engine logger, idStr, virtual filesystem or FatalError. Reentrancy is guarded.
A limited successful checkpoint is sampled every 32 MiB of *allocation
traffic*, capped at 96 records. This is NOT live-byte accounting. Failed
requests remain reportable after the checkpoint cap. malloc wrappers do not
cover every internal libc _malloc_r call or a distinct GPU mspace failure.

Use the exact matching unstripped ELF from the engine CI artifact to resolve
`caller` (account for module relocation/load base before addr2line). The return
address may identify a shared allocator rather than the complete caller chain.
Heap free bytes are not the largest free block; arena growth/fragmentation need
separate interpretation. Next implementation depends on that result: fix bad
sizes, duplicated/premature ownership, or required cache-lifetime boundaries.
Do not drop entities/AI, globally downsize assets or enlarge pools just to pass.

## Remaining brightness: observe the clear boundary

The shipped build-246 executable was checked: RB_SetBuffer really calls
`glClear(GL_COLOR_BUFFER_BIT)` after removing scissor and enabling all colour
writes. The command loop binds the default target before executing commands.
GLES_D3 already contains a separate opaque-draw workaround for 3D interaction
clears. That is not evidence that the generic glClear implementation is correct
and must not be copied into every menu or used to erase portal/GUI content.

The candidate observes the real clear, not a substitute draw. After engine
initialization, at most 12 eligible default-framebuffer clears are sampled,
separated by five seconds. It records clear value, masks, target and scissor,
then five RGBA pixel samples across the frame. Odd samples include a pre-clear
read; even samples only read after clear. The corresponding pre-presentation
samples distinguish clear failure from colour reintroduced later in the frame.
Read-framebuffer and default FRONT/BACK read selection are restored.

The pinned VitaGL did not expose GL_READ_BUFFER through glGetIntegerv. The
patch now returns its existing `display_read_mode`, or COLOR_ATTACHMENT0 for
an FBO. This is a query implementation, not a change to rendering or clearing.

Readback serializes GPU work and CAN change timing. A sampled clear reading
black only proves those pixels in that observed frame; it does not by itself
rule out an unsampled race, wrong target later, or a readback defect. In this
candidate, expect occasional diagnostic stalls, not meaningful FPS benchmarks.
Do not report the side accumulation fixed before the user's next capture.

## Gameplay acceptance sequence

1. **Finish a real SP load.** Identify the failing reservation, establish CPU,
   GPU and staging peaks, pass SpawnPlayer and resource-finalization boundaries,
   reach settle frames, and render the first real world/HUD frame. Repeat load,
   quit-to-menu and reload to distinguish a peak from retained allocations.
2. **Validate movement and simulation.** Trace Vita events to usercmd; verify
   look/move axes, crouch/jump, collision, floor/door traversal and map scripts.
   Validate gameplay timing separately from display FPS and 60-Hz presentation.
3. **Validate the world renderer.** Check depth/interactions, stencil shadows,
   deformed/animated meshes, texture lifetime, fog, particles/BSE, cinematics,
   portal skies and scene resolve with original content. Audit each remaining
   GLES compatibility stub against actual material requirements before marking
   it supported. Remove obsolete bring-up substitutes only with parity tests.
4. **Validate interactions.** Player weapon switching/fire/reload, projectiles,
   AI navigation and animation, damage/death, pickups, triggers and objectives;
   then sound spatialization and pause/menu-over-world ownership.
5. **Persistence and stability.** Save/load, death/restart, map transitions,
   menu return, repeat-load memory baselines and sustained sessions. Then profile
   CPU passes, GPU time and allocation churn on hardware; optimize measured
   bottlenecks without altering gameplay or authored visual semantics.

Arena multiplayer rules are a separate acceptance track. Use airdefense1 SP
as the reproducible first milestone, not a simultaneous rewrite of every mode.

## Validation of this diagnostic implementation

`test_vita_gui_runtime_audit.py` compiles and executes the actual observer bodies
with mocked platform/GL calls. It checks allocator forwarding, zero requests,
overflow reporting, preserved errno, reentrant failure handling, checkpoint
caps, one real clear per call, sampling limits, and restored FBO/FRONT selection.
It also executes the new query branch for FRONT, BACK and an FBO. These are
control-flow tests, not VitaGL/GXM readback or heap exhaustion on a device.

Run from the root with the fully patched pinned VitaGL checkout:

```sh
VOQ_VITAGL_SOURCE="$PWD/.tmp/vitagl" VITAGL_REPO="$PWD/.tmp/vitagl" \
  VOQ_REQUIRE_GPU_TESTS=1 LIBGL_ALWAYS_SOFTWARE=1 \
  python3 -m unittest discover -s tools/vita/tests -p 'test_*.py' -v
```

References: root AGENTS.md; GUI_VERTEX_STREAM_CONTRACT.md;
GUI_RENDER_CONTRACT.md; engine Session.cpp and Heap.cpp; pinned VitaGL
source/misc.c, source/get_info.c and source/framebuffers.c. The GL clear
contract specifies that blend/depth tests are ignored, but write masks and
scissor apply: https://wikis.khronos.org/opengl/GLAPI/glClear . Compare the
Android OpenQ4 and Doom3-ReArmed command/asset contracts, not their unrelated
memory capacities or renderer workarounds.


## Build 266 cinematic milestone and Start ownership

Target build 266 reaches and continuously advances the airdefense1 cinematic.
The Vita async timer produces increasing 60 Hz tics and the session repeatedly
runs game tics with `cinematic=1`. This establishes that map loading, player
creation, renderer finalization, cinematic simulation and presentation all
crossed their previous bring-up boundaries.

A Start press entered Session::ProcessEvent's generic JOY7 escape path. The game
was already cinematic, but an ESC_MAIN result caused Session to call StartMenu,
unload airdefense1, parse the main menu and then load airdefense1 a second time.
That second complete load later exhausted the fragmented 300 MiB CPU heap; the
first failed allocation was 262,144 bytes. The session now gives Vita Start to
Game::HandleESC while cinematic and consumes that event regardless of the skip
mode's continuation return value. This preserves the game's own instantSkip,
fast-forward and queued-disconnect semantics without also opening the session
menu in the same input event. Outside cinematics Start remains pause/menu. Vita
Select (JOY8) is no longer intercepted as pause and reaches its configured
gameplay binding.
