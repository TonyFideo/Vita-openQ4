# First world-frame capture after build 257

## Measured boundary

The 20260921-020510 emulator log identifies 257 / 4f011386. Unlike 256,
this session initializes CDRAM/RAM/physical GPU pools, completes all 1337
pending images, streams the 1024-square sky's eleven levels, completes
renderer finalization and simulation settling, and reaches load:ready.
The previous session had only 322 completions before graphics allocation
errors. This is 1015 more entries in that queue, not a whole-game percentage
or a visual/interactive gameplay pass.

At player completion newlib reports 196363256 used bytes instead of the
previous 306227656 (109864400 bytes less in this heap at that milestone).
This is changed bank placement, not a claim to reduce total physical memory.
The new session has no failed allocation audit event. The final reported
load:ready heap use is 268929296 bytes; GPU-stat availability remains separate.

The first crash is 23:00:07.992: a branch through a null function pointer,
PC=0, LR=0x81702679, r10=0. The matching ELF resolves the return address to
`glTexSubImage2D`. The instructions load a pixel through r9/read_rgba8888,
then `blx r10` invokes its absent writer. r8=960 and input/destination buffer
sizes are consistent with a fullscreen U8-to-F16 transfer. This is not the
old OOM or evidence that input handling itself is faulty.

The engine's currentRender capture retains FMT_RGBA16F. CopyTex obtains RGBA8
bytes from the display, but the pinned texture update selector has no floating
writer. A second defect exists at image definition: setting fast_store for
RGBA16F disregards the external source type and can read eight bytes per
pixel from four-byte input. Fixing only the null call would leave that path
incorrect. The staged autosave validation warning about build 1 versus 661
is a separate unresolved issue, not the identified call-through-zero.

## Implemented transfer path

The active linear VitaGL profile now owns a typed 2D RGBA16F path for image
creation/redefinition, subimages and generated mip levels. It keeps external
format/type separate from internal storage, normalizes integer components,
handles HALF/FLOAT inputs, and preserves negative/HDR values. Binary16
conversion uses IEEE bit operations and ties-to-even rounding, independent
of ARM FP16 instructions. Loads/stores are alignment-safe. Source row length
and unpack alignment are validated; all selected mip levels use the existing
shared pitch/offset plan. Higher-level definition uses the profile's existing
base-first contract; this is not arbitrary out-of-order OpenGL level storage.

Allocation precedes old-storage retirement. Failure leaves existing bytes and
descriptors valid. Busy textures use copy-on-write and the existing deferred
free mechanism. Attached framebuffer descriptors are refreshed without changing
texture reference counts; pending rendering to an affected attachment is
finished before CPU mutation. Generated mipmaps average floating components,
not their encoded bytes. Changes to non-floating formats retain their existing
implementation; this does not claim every target/storage format is implemented.

Floating framebuffer readback uses eight-byte native pixels and actual
HALF_FLOAT/FLOAT/UNSIGNED_BYTE transfer types (not GL_RGBA16F as a type).
It preserves the backend's FBO/display orientation conventions and tight PACK
rows. HALF output retains native half bits, FLOAT output retains range, and
byte output clamps/normalizes. The four CopyTex/DSA copy entrypoints check
allocation, stop after failed readback, snapshot before destination mutation,
ignore/restore client unpack state, and preserve earlier GL errors. F16-to-F16
copies use HALF input rather than quantizing through U8. Self-copy snapshots
remain valid and attachment references follow replacement storage.

CopyFramebuffer restores the actual previous read selection, including FRONT,
and publishes new dimensions only on success. The GLES_D3 owner no longer
marks a failed scene capture as valid; it reports the failure rather than
silently drawing with stale contents. Four bounded frame-copy success traces
help qualify the next run. No material/effect is removed, no image is forced
to RGBA8, and no heap or pool budget is increased.

## Tests and limitations

Eleven new groups cover all 65536 half encodings, 150000 sampled binary32
roundings, 90 source-format/type combinations, six packed formats, padded and
unaligned input, the exact 960x544 U8-to-half dimensions, NPOT mip repacking,
partial updates, COW and allocation failure, floating mip generation, both FBO
orientation profiles, four copy APIs, self-copy and attachment refresh,
and the complete renderer CopyFramebuffer owner with simulated GL services.
The legacy writer-selection switch is executed as a negative control and
reports its missing F16 writer. Native harnesses also run with ASan/UBSan.

An independent Mesa desktop-OpenGL test verifies normalized-byte upload into
RGBA16F, half subimage values and readback. Desktop GL is intentional: GLES 3
restricts the sized float transfer combinations, whereas this VitaGL bridge
provides the desktop-style conversion the engine expects. The test does not
change the renderer format to satisfy an ES test context. Mesa reference,
mocked GXM tests, cross compilation and target execution are distinct checks.

The complete host suite passes 128 tests with both dependency variables set
and offscreen pixel tests required. Cross compilation/packaging must succeed
separately before a VPK is considered testable. No Vita/Vita3K execution of
this revision or completed playable frame has been observed here.

## Next session

Start fresh with unchanged original PK4s/settings, enter Mission and press
the normal continue button. Preserve the full emulator log, loading.log and
errors.log plus the first world/HUD frame or new stopping point. Look for the
bounded [VOQ4][frame-copy] image=_currentRender... ok=1 trace, then validate
world appearance and player control. Reaching a log marker alone is not
visual correctness. The menu brightness and autosave-validation issues remain
separate; neither is suppressed by this revision.


## Build 258 target result: first world/cinematic frame

The 20260921-034034 target session reaches the first rendered world/cinematic
frame and continues executing instead of crashing. The remaining visible stall
is accompanied by two independent state/lifetime defects rather than evidence
that the cinematic decoder stopped.

First, `GL_SelectTexture` selected both the shader image unit and the legacy
client texcoord-array unit. GLES_D3 uses explicit attributes and up to the
normal programmable sampler range; VitaGL intentionally exposes 16 image units
but only 2 client FFP texcoord sets (3 in its optional high-FFP profile). Units
2 through 5 are therefore valid sampler selections but invalid client-array
selections. GLES_D3 now changes only the image unit. The compatibility
renderer retains `glClientActiveTexture`, and image binding no longer toggles
fixed-function `GL_TEXTURE_2D`/`GL_TEXTURE_CUBE_MAP` enable caps on GLES.

Second, `_currentRender` is a 960x544 RGBA16F screen image. A CopyTex update of
that image legitimately follows draws which sampled its previous contents. The
generic F16 SubImage implementation uses copy-on-write for an in-flight client
update, so applying it directly to this ordered framebuffer copy allocated a
new 4,177,920-byte image repeatedly. The copy implementation already snapshots
the framebuffer source. It now closes and waits for prior GXM work when the F16
destination is still busy, marks that completed generation unused, and updates
the existing storage. Generic client SubImage calls retain COW semantics.
Allocation failure still leaves the old texture intact.

The current Vita3K GL renderer separately reports native GXM color format
`0x01200000` as unsupported during surface readback. VitaSDK identifies that
value as `SCE_GXM_COLOR_FORMAT_F16F16F16F16_RGBA`, the valid 64-bit surface
created by the pinned VitaGL for an RGBA16F attachment. This change does not
downgrade the render target or alter its channel swizzle just to satisfy the
emulator. Repeated attachment replacement was one trigger for those readbacks;
the next target run will show whether eliminating the replacement churn also
removes or reduces the emulator-side messages.

Host regression coverage preprocesses the production GLES and compatibility
paths, checks the pinned VitaGL image-unit/client-coordinate limits, and executes
32 consecutive busy CopyTex updates without a new GPU texture allocation. The
existing generic busy SubImage COW test remains in place. Target validation
must still confirm that the cinematic advances, the world renders correctly and
player input works; a running frame loop is not by itself a gameplay pass.


### Complete programmable unbind semantics

A second fixed-function leak was found in `idImageManager::BindNull`, which is
called by the active GLES interaction, fog and shader-pass paths. The desktop
renderer disables the previously enabled fixed-function target; GLES has no
such target-enable state. GLES now binds texture zero to the tracked 2D/cube
target, resets the corresponding binding-cache entry, and leaves the desktop
compatibility path unchanged. `UnbindAll` also restores the actual active
server image unit after walking the units instead of changing only its shadow
integer. This prevents a later bind from silently targeting the last unit.
The Doom 3 Vita reference likewise unbinds a texture object rather than relying
on fixed-function target enables.
