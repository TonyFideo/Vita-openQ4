# Vita 0.1 candidate: first world-frame capture

This candidate corrects the floating-point screen-texture transfer used after
pressing Continue at the end of loading. Byte pixels are converted to half
floats instead of invoking a missing converter or reading the wrong byte count.
Screen effects keep their original floating-point images; no material is removed.

Texture updates, mipmaps, readback and copy operations preserve their storage
and lifetime rules. Transfer failures are reported rather than marked successful.
No PK4 replacement or graphics-setting change is required.

Build 257 already completes the image queue and reaches Continue. Build 258
reaches and displays the first world/cinematic frame. The follow-up separates
programmable sampler selection from legacy fixed-function texcoord state and
reuses the ordered RGBA16F screen-capture storage instead of reallocating a
full 960x544 half-float image while it advances. This removes two large sources
of runtime error/logging and allocation pressure without reducing image format,
texture count, mip levels or effects.

Target validation still needs to confirm that the cinematic advances, the world
and HUD render correctly, and controls reach the player. The separate menu
brightness and staged autosave validation issues are not claimed fixed.
