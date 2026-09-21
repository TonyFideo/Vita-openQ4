# Vita 0.1 candidate: graphics memory initialization

The port now assigns available CDRAM to VitaGL instead of inadvertently reserving
that bank out of use. This prevents graphics resources from unnecessarily
competing with the game's CPU heap. Initialization validates and owns the actual
mapped pools, and a failed texture allocation stops at the affected resource
instead of being reported as a completed image.

No new PK4s, quality reduction or heap setting is required. The existing sky,
DDS loading and metadata-cache corrections are retained. Host tests pass;
compilation with VitaSDK and target gameplay are separate acceptance checks.
The menu's progressive side brightness remains a separate unresolved issue.
