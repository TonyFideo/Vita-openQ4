# Vita-OpenQ4: material and depth probe

This is an isolated renderer integration test, not the full Quake 4 engine.
It compiles the production GLES_D3 debug and material shaders through the
production VitaGL normalizer. The VitaGL bootstrap is reused from
`src/sys/vita/vita_renderer_smoke.cpp`; it is not a new GXM initialization path.
No commercial game files are required.

The expected view is a rotating checker-textured cube above a checker floor.
The floor uses an indexed draw starting at byte offset 72 in the same IBO.
The vertex buffer uses a 24-byte interleaved layout: float position, normalized
RGBA8 colour, and float texture coordinates. This is a diagnostic fixture,
not an assertion that it has the engine's full idDrawVert layout.

Controls:
- Cross: cycle 0 (single-pass LEQUAL), 1 (debug-shader depth prepass followed by
  material-shader EQUAL), 2 (the same prepass followed by LEQUAL).
- Triangle: pause/resume rotation for an exact visual comparison between modes.
- Square: record three framebuffer pixel samples to the log.

All three modes should show the same solid geometry. If only mode 1 loses
surfaces, report that explicitly: it isolates cross-program depth equality.
If the floor alone is missing in every mode, report it separately from a
completely black frame. Pixel samples are observations, not automatic proof
of image correctness.

Runtime log: `ux0:data/Vita-OpenQ4/logs/renderer-probe.log`.
The build SHA is printed at startup. The log is also mirrored to Vita3K stdout.

Application name: Vita-OpenQ4. Title ID: VOQ000004. Project version: 0.1
(`APP_VER` 00.10). Installing this probe replaces the previous application with
that Title ID; it does not need or modify game PK4 files in the data folder.
Close via the system UI. No teardown experiment is performed in this test.

The independent `Vita Render Probe` workflow produces the VPK even while
full-engine integration has unrelated compile errors. Compilation and packaging
are not a claim of runtime success on hardware or Vita3K.
