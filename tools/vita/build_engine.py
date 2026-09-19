#!/usr/bin/env python3
"""Build real Vita sound objects first; keep complete logs and bounded CI output."""
from __future__ import annotations

import argparse
from collections import deque
import json
from pathlib import Path
import re
import shlex
import subprocess
import sys

DIAGNOSTIC = re.compile(r"(?:fatal error:|\berror:|undefined reference|multiple definition|FAILED:|ninja: (?:error|build stopped))", re.I)
PROGRESS = re.compile(r"^\[(\d+)/(\d+)\]")


def sound_objects(database: Path) -> list[str]:
    """Use Meson's actual compile database, not guessed Ninja object names."""
    entries = json.loads(database.read_text(encoding="utf-8"))
    outputs: set[str] = set()
    for entry in entries:
        source = entry.get("file", "").replace("\\", "/")
        if not re.search(r"(?:^|/)src/sound/", source):
            continue
        output = entry.get("output")
        if not output:
            args = entry.get("arguments") or shlex.split(entry.get("command", ""))
            try:
                output = args[args.index("-o") + 1]
            except (ValueError, IndexError):
                raise ValueError(f"No compiler output recorded for {source}") from None
        outputs.add(output)
    if not outputs:
        raise ValueError("No sound objects found: the gate must not silently test nothing")
    return sorted(outputs)


def run_logged(command: list[str], log: Path, label: str) -> int:
    """Preserve the child exit code, never turn compilation failures green."""
    log.parent.mkdir(parents=True, exist_ok=True)
    tail: deque[str] = deque(maxlen=16)
    diagnostics: list[str] = []
    matches = 0
    last_progress = 0
    print(f"[{label}] starting; complete output: {log}", flush=True)
    with log.open("w", encoding="utf-8") as handle:
        handle.write("$ " + shlex.join(command) + "\n")
        handle.flush()
        with subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              text=True, encoding="utf-8", errors="replace") as process:
            assert process.stdout is not None
            for line in process.stdout:
                handle.write(line)
                tail.append(line.rstrip())
                if DIAGNOSTIC.search(line):
                    matches += 1
                    if len(diagnostics) < 24:
                        diagnostics.append(line.rstrip()[:1500])
                progress = PROGRESS.match(line)
                if progress and int(progress[1]) >= last_progress + 25:
                    last_progress = int(progress[1])
                    print(f"[{label}] {progress[0]}", flush=True)
                    handle.flush()
            result = process.wait()
    if result:
        print(f"[{label}] FAILED (exit {result}); {matches} diagnostic lines", flush=True)
        for line in diagnostics or list(tail):
            print(line[:1500])
        print(f"Full diagnostics retained in {log}", flush=True)
    else:
        print(f"[{label}] PASS", flush=True)
    # Python uses negative codes for signals; shell callers expect 128+signal.
    return result if result >= 0 else 128 - result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, required=True)
    parser.add_argument("--logs-dir", type=Path, default=Path("build/vita-diagnostics"))
    parser.add_argument("--jobs", type=int, default=2)
    parser.add_argument("--target", default="openQ4-client_armv7")
    args = parser.parse_args(argv)
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    args.logs_dir.mkdir(parents=True, exist_ok=True)
    try:
        objects = sound_objects(args.build_dir / "compile_commands.json")
        (args.logs_dir / "sound-objects.json").write_text(
            json.dumps(objects, indent=2) + "\n", encoding="utf-8")
        print(f"[sound] checking {len(objects)} real engine translation units", flush=True)
        result = run_logged(["ninja", "-C", str(args.build_dir), "-k", "0",
                             "-j", str(args.jobs), *objects],
                            args.logs_dir / "sound.log", "sound")
        if result:
            return result
        return run_logged(["meson", "compile", "-C", str(args.build_dir),
                           args.target, "-j", str(args.jobs)],
                          args.logs_dir / "engine.log", "engine")
    except (OSError, ValueError, TypeError) as error:
        message = f"Vita build driver: {error}"
        (args.logs_dir / "driver-error.txt").write_text(message + "\n", encoding="utf-8")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
