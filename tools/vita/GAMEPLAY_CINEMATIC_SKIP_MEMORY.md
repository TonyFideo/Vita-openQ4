# Vita cinematic-skip milestone (build 266)

Build 266 reaches `load:ready`, runs the opening airdefense1 cinematic with a
working 60 Hz async clock, and advances game simulation continuously. The
cinematic itself is therefore no longer the failing boundary.

## What the target log actually shows after Start

The Start press is followed immediately by `Game Map Shutdown`, main-menu
construction, and a second `Game Map Init` for airdefense1. That second load
again reaches `load:ready`. Only later does the fragmented 300 MiB CPU heap
fail a 262,144-byte allocation, followed by the expected recursive-fatal
allocation. The OOM is therefore downstream of an unintended session
menu/reload transition, not evidence that cinematic fast-forward itself needs a
larger heap.

The ownership bug is in Session::ProcessEvent. Vita Start is K_JOY7 and enters
the generic ESC path. The game layer receives HandleESC first. During a
cinematic, idPlayer::HandleESC delegates to SkipCinematic. Some valid game skip
modes (notably an instantSkip camera) stop the cinematic and return false;
Session interpreted that as ESC_MAIN and then called StartMenu on the *same*
button press.

The Vita path now consumes Start after delivering it to the active cinematic
game layer. The game's own instantSkip, fast-forward, camera stop and queued
disconnect behavior is unchanged. Outside cinematics Start remains the normal
pause/menu key. Select (K_JOY8) is no longer stolen by session pause handling,
so its configured gameplay binding remains reachable.

The allocator/frame-arena probes added after build 266 remain useful
observability and do not change allocator policy. The next target run should
show `[VOQ4][input] Start cinematic ...` and should not immediately show
`Game Map Shutdown` merely because Start was pressed. If the game itself
subsequently queues its documented disconnect transition, that later shutdown
is legitimate and can be distinguished in the log.
