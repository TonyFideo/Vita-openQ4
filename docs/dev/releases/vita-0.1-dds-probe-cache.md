# Vita 0.1 candidate: texture metadata loading

## Changes

Texture lookup metadata now grows without repeatedly copying all earlier
entries and names. This removes a transient contiguous allocation implicated
in build 255's loading crash, while retaining the same texture selection,
resolution, mipmaps, and lookup results. Existing game data and settings need
no replacement.

## Validation

Host regressions pass, including growth, collisions and cache destruction.
Device/emulator gameplay entry still requires testing. The prior sky-loading
correction was not reached in the latest user run, and the separate menu
brightness issue remains open.
