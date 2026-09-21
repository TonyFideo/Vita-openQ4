# Vita 0.1 candidate: first world-frame capture

This candidate corrects the floating-point screen-texture transfer used after
pressing Continue at the end of loading. Byte pixels are converted to half
floats instead of invoking a missing converter or reading the wrong byte count.
Screen effects keep their original floating-point images; no material is removed.

Texture updates, mipmaps, readback and copy operations preserve their storage
and lifetime rules. Transfer failures are reported rather than marked successful.
No PK4 replacement or graphics-setting change is required.

Build 257 already completes the image queue and reaches Continue. This follow-up
still requires target validation of the world, HUD and controls. The separate
menu brightness and staged autosave validation issues are not claimed fixed.
