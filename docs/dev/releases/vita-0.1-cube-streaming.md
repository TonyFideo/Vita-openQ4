# Vita 0.1 candidate: sky loading

## Changes

The native RGBA8 sky loader now processes TGA cube faces a row at a time,
without retaining six decoded faces in the engine heap. The source resolution,
face orientation and every mip level are preserved. Native cube storage now
accepts complete mip chains and bounded row/column updates with safe lifetime
handling when sampled textures change.

## Test status

This targets the build-252 failure while loading gfx/env/act_2/act2. Host tests
pass; real gameplay entry and the remaining menu brightness require target
validation. No PK4 replacement or graphics-setting change is required.
