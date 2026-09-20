# Vita 0.1 development candidate - map-loading memory

This candidate reduces avoidable model-loading memory on Vita while preserving
the original models and CPU animation. Private construction scratch is released
when it is no longer needed; GPU-only deformation copies are not created for
the current CPU-skinning backend.

Install the new full-engine VPK and test the Mission campaign with unchanged
graphics settings. Loading logs now identify player creation and the remaining
steps before the world can be drawn. A completed build is not confirmation that
the campaign reaches gameplay; target testing is still required.

The previously fixed Options text is retained. The separate menu-side brightness
problem remains open. No game data replacement, reduced textures, increased heap,
or changed controls are required by this candidate.
