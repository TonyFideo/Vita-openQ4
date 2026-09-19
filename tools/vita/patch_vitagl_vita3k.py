#!/usr/bin/env python3
"""Restore the minimal historical Vita3K init path in a pinned current vitaGL."""

from __future__ import annotations

import pathlib
import sys


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_vitagl_vita3k.py <vitaGL-repo>")

    root = pathlib.Path(sys.argv[1])
    path = root / "source" / "gxm.c"
    text = path.read_text(encoding="utf-8")

    text = replace_once(
        text,
        "\tis_shark_online = shark_init(NULL) >= 0;",
        """#ifdef HAVE_VITA3K_SUPPORT
\tis_shark_online = shark_init_simple(NULL) >= 0;
#else
\tis_shark_online = shark_init(NULL) >= 0;
#endif""",
        "primary shark init",
    )

    text = replace_once(
        text,
        '\t\tis_shark_online = shark_init("ur0:data/external/libshacccg.suprx") >= 0;',
        """#ifdef HAVE_VITA3K_SUPPORT
\t\tis_shark_online = shark_init_simple("ur0:data/external/libshacccg.suprx") >= 0;
#else
\t\tis_shark_online = shark_init("ur0:data/external/libshacccg.suprx") >= 0;
#endif""",
        "fallback shark init",
    )

    text = replace_once(
        text,
        "\tgxm_init_params.flags = SCE_GXM_INITIALIZE_FLAG_EXTENDED_FORMAT;",
        """#ifdef HAVE_VITA3K_SUPPORT
\tgxm_init_params.flags = SCE_GXM_INITIALIZE_FLAG_DEFAULT;
#else
\tgxm_init_params.flags = SCE_GXM_INITIALIZE_FLAG_EXTENDED_FORMAT;
#endif""",
        "GXM init flags",
    )

    text = replace_once(
        text,
        "\tsceGxmVshInitialize(&gxm_init_params);",
        """#ifdef HAVE_VITA3K_SUPPORT
\tsceGxmInitialize(&gxm_init_params);
#else
\tsceGxmVshInitialize(&gxm_init_params);
#endif""",
        "GXM init entrypoint",
    )

    path.write_text(text, encoding="utf-8")

    checks = (
        "shark_init_simple(NULL)",
        "SCE_GXM_INITIALIZE_FLAG_DEFAULT",
        "sceGxmInitialize(&gxm_init_params)",
    )
    for token in checks:
        if token not in text:
            raise SystemExit(f"compat patch verification failed: {token}")

    print("Applied Vita3K compatibility init patch to", path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
