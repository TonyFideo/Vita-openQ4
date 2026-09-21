#!/usr/bin/env python3
"""Stage openQ4-game for Vita and apply the Vita monolithic presentation contract.

The companion repository remains the canonical source.  This wrapper first
runs the normal audited staging path, then applies two narrow interface
additions required by the Vita monolithic engine.  The staged manifest is
rehash-updated and revalidated; source drift makes the build fail instead of
silently applying a fuzzy patch.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

PATCHED_FILES = (
    "src/game/Game.h",
    "src/game/Game_local.h",
    "src/game/Entity.cpp",
    "src/game/Light.cpp",
    "src/game/AFEntity.cpp",
    "src/game/BrittleFracture.cpp",
    "src/game/Item.cpp",
    "src/game/SecurityCamera.cpp",
    "src/game/client/ClientModel.cpp",
)


def _replace_once(path: Path, pattern: str, replacement: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(pattern)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one source match in {path}, found {count}")
    path.write_text(text.replace(pattern, replacement, 1), encoding="utf-8")


def _insert_skip_guard(path: Path, signature: str) -> None:
    text = path.read_text(encoding="utf-8")
    if text.count(signature) != 1:
        raise RuntimeError(
            f"cinematic presentation guard: expected one {signature!r} in {path}, found {text.count(signature)}"
        )
    start = text.index(signature)
    opening = text.index("{", start)
    guard = "\n\tif ( gameLocal.IsCinematicFastForwarding() ) {\n\t\treturn;\n\t}\n"
    body_prefix = text[opening + 1:opening + 1 + len(guard)]
    if body_prefix == guard:
        raise RuntimeError(f"cinematic presentation guard already present in {path}: {signature}")
    path.write_text(text[:opening + 1] + guard + text[opening + 1:], encoding="utf-8")


def apply_vita_game_patches(stage_root: Path) -> None:
    game_h = stage_root / "src/game/Game.h"
    game_local_h = stage_root / "src/game/Game_local.h"
    _replace_once(
        game_h,
        "\tvirtual bool\t\t\t\tInCinematic( void ) = 0;\n",
        "\tvirtual bool\t\t\t\tInCinematic( void ) = 0;\n"
        "\tvirtual bool\t\t\t\tIsCinematicFastForwarding( void ) = 0;\n",
        "idGame cinematic fast-forward query",
    )
    _replace_once(
        game_local_h,
        "\tbool\t\t\t\t\tInCinematic( void ) { return inCinematic; }\n",
        "\tbool\t\t\t\t\tInCinematic( void ) { return inCinematic; }\n"
        "\tbool\t\t\t\t\tIsCinematicFastForwarding( void ) { return skipCinematic; }\n",
        "idGameLocal cinematic fast-forward query",
    )

    # These functions own presentation dirty-state consumption or publish a
    # secondary renderer def after the base Present() call. Returning before
    # them preserves the final authoritative state for the first ordinary tic.
    guards = (
        ("src/game/Entity.cpp", "void idEntity::Present( void )"),
        ("src/game/Light.cpp", "void idLight::Present( void )"),
        ("src/game/AFEntity.cpp", "void idMultiModelAF::Present( void )"),
        ("src/game/AFEntity.cpp", "void idAFEntity_Gibbable::Present( void )"),
        ("src/game/BrittleFracture.cpp", "void idBrittleFracture::Present()"),
        ("src/game/Item.cpp", "void idItem::Present( void )"),
        ("src/game/SecurityCamera.cpp", "void idSecurityCamera::Present( void )"),
        ("src/game/client/ClientModel.cpp", "void rvClientModel::PresentPresentation( int presentationTime )"),
    )
    for relative, signature in guards:
        _insert_skip_guard(stage_root / relative, signature)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def refresh_manifest(stage_root: Path) -> None:
    manifest_path = stage_root / "openq4_gamelibs_stage_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = {entry["path"]: entry for entry in manifest["files"]}
    for relative in PATCHED_FILES:
        if relative not in entries:
            raise RuntimeError(f"staged manifest is missing patched file: {relative}")
        entries[relative]["sha256"] = _sha256(stage_root / relative)
    manifest["vitaProfile"] = {
        "cinematicFastForwardPresentationGate": 1,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_generic_stage(project_root: Path):
    path = project_root / "tools/build/stage_gamelibs.py"
    spec = importlib.util.spec_from_file_location("openq4_stage_gamelibs", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"could not load generic staging module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("usage: stage_gamelibs_vita.py <project-root> <gamelibs-root> <stage-root>", file=sys.stderr)
        return 2

    project_root = Path(argv[1]).resolve()
    generic_script = project_root / "tools/build/stage_gamelibs.py"
    completed = subprocess.run(
        [sys.executable, str(generic_script), argv[1], argv[2], argv[3]],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    if completed.returncode != 0:
        sys.stderr.write(completed.stderr)
        return completed.returncode

    output = completed.stdout.strip()
    if not output:
        print("error: generic GameLibs staging returned no stage root", file=sys.stderr)
        return 1
    stage_root = Path(output).resolve()

    try:
        apply_vita_game_patches(stage_root)
        refresh_manifest(stage_root)
        generic = _load_generic_stage(project_root)
        generic.validate_stage_manifest(stage_root)
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        print(f"error: Vita GameLibs staging failed: {exc}", file=sys.stderr)
        return 1

    print(stage_root.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
