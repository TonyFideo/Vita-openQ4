# Vita 0.1 development: lower DDS loading peaks

DDS textures now load their existing mip levels sequentially instead of keeping
the whole compressed file in the CPU heap during upload. This reduces temporary
memory requirements without reducing texture quality or changing the original
Quake 4 data. File layouts and reads are validated, and partial loads fail
explicitly rather than displaying incomplete textures.

This follows the build-251 test which successfully created the player and then
ran out of memory while finalizing images. Completion of gameplay is still
unverified; this is a development candidate, not a claim that campaign loading
or sustained play now works. The separate brightening menu defect remains open.

Install the matching full-engine VPK and test the same Mission campaign from a
fresh launch. Keep graphics settings and data files unchanged. New per-image
markers make any remaining load failure identifiable in the emulator log.
