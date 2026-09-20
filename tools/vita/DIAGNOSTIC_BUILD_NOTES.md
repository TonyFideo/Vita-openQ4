# Vita diagnostic build: clearing and SP load failures

## What this build changes

Keep build 246's user-validated Settings/font fix. Make the existing framebuffer
and allocation observers buildable with the actual VitaSDK toolchain. This is a
diagnostic candidate, not a claimed visual fix or a successful gameplay session.
No GUI art, authored material stages, brightness values, entity counts, memory
pool sizes or asset resolutions are changed.

Two integration errors are corrected:

- Build 247: `display_read_mode` belongs to `framebuffers.c`. An internal
  `vgl_get_read_buffer()` accessor and declaration expose the query without
  exporting that private variable. The regression compiles separate C files.
- Build 248: global `--wrap` flags affected Meson's library probes, which do not
  link the engine's observer definitions. A libc reference to `__wrap_calloc`
  made the VitaGL search fail even though the archive had built successfully.
  Wrapping now belongs only to the Vita engine client target in `meson.build`.
  The cross file contains ordinary toolchain link options. C and C++ probes
  and a separately wrapped test target are exercised by the host regression.

The observers retain native allocator behavior. They do not retry a failed
allocation, grow a pool, or return a different kind of memory. The clear observer
forwards the real GL clear once and restores the read-framebuffer selection.

## Test session

Install the full-engine VPK, not the isolated Render Probe. On a fresh launch,
enter New Game promptly and leave it open for 30-45 seconds. Capture the side
panels near entry and after the wait. The clear observer samples at most 12
eligible frames, five seconds apart, starting after engine initialization; it
is not continuous recording and a much later visit may miss that window.
Then start the Mission campaign / airdefense1 and retain the emulator log plus
`logs/loading.log` and `logs/errors.log`. Do not change graphics or brightness.

Expect occasional readback stalls. FPS during this diagnostic run does not
measure gameplay performance. The old side saturation and load failure may
still occur; the purpose is to capture their exact boundary before selecting a
runtime correction. Failed allocations remain reportable after successful
memory checkpoints hit their cap.

## Automated report

Run from the repository root, with no game data required:

```sh
python3 tools/vita/analyze_runtime_audit.py session.log --output report.json
```

The parser streams the log instead of loading its file-lookup noise into
memory. It bounds detailed records, identifies builds, keeps separate sessions,
reports exact captured allocation requests and observed heap counters, and
compares post-clear RGBA8 samples with the requested clear only when target,
scissor, masks and all five points are present and eligible.

`matches_requested_at_sampled_points` is not a visual pass. It does not exclude
an unsampled timing problem, later composition into a different target, or a
readback defect. `differs_from_requested` is an observation, not identification
of a defective shader. Missing observations, partial write masks and incomplete
pixel records remain unqualified. Heap free space is not the largest free block;
allocation traffic must not be mistaken for live bytes. The mathematical product
of an overflowing request is reported without treating it as a valid reservation.

Applying the tool to the user's build-246 log correctly reports the OOM text
but no allocation/clear observations. It does not invent a caller, size, or
successful clear for that older build.

## Gameplay investigation

The earlier log establishes 1777 entities and completed game initialization,
followed by the player model lookup and an OOM, before later Session.cpp
finalization/settle milestones are shown. Exact reservation data is still needed.
A missing loose-file probe followed by a successful PK4 open is not evidence
that the model is missing or corrupt.

Source review identified another candidate for subsequent measurement:
`idMD5Mesh::BuildGpuSkinningSidecar()` constructs bind-pose and four-weight GPU
side arrays during MD5 loading even when `r_gpuSkinning` is disabled. Vita's
current backend uses CPU skinning. This is not yet a measured explanation for
the load failure, and no side-array policy is changed in this candidate.
Any subsequent lifetime/capability correction must preserve CPU deformation,
weight data, normal/tangent generation, mirrored vertices and load/reload parity.

Use the exact unstripped ELF from the matching engine CI artifact to resolve a
reported caller, accounting for the module's relocation and ARM Thumb address.
A caller may resolve only to an intermediate allocator, not an entire stack.
After load completion, follow GAMEPLAY_BRINGUP.md for world/HUD, input,
collision/scripts, animation/lighting, combat/AI, audio and persistence checks.

## Host validation and limits

The complete local suite passes 85 tests: the preceding 77 plus eight streaming
report tests. Native linking, extracted observer bodies, EGL shader pixels and
mocked GXM address submissions are host tests, not execution on Vita/Vita3K.
The cross compilation and packaging must succeed separately before a VPK is
presented as testable. Runtime correctness remains dependent on target results.
