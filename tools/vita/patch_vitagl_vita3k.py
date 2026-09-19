#!/usr/bin/env python3
"""Apply the pinned vitaGL compatibility profile required by Vita3K."""

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

    # Current vitaGL injects helper functions using Cg bit_cast into every
    # translated GLSL program. The libshacccg path used by Vita3K rejects that
    # identifier while linking, even when the helpers are dead code. Our
    # Vita3K profile does not enable HAVE_FIXED_ATTRIBUTES, so vglUnpack is not
    # injected into shader main() and can safely be an identity helper here.
    shader_header_path = root / "source" / "shaders" / "glsl_translator_hdr.h"
    shader_header = shader_header_path.read_text(encoding="utf-8")
    shader_header = replace_once(
        shader_header,
        """#define GLFixedToFloat(fx) (float(bit_cast<short2>(fx).y + (bit_cast<unsigned short2>(fx).x * (1.0f / 65536.0f))))
inline float vglUnpack(float v) {
\tint bits = bit_cast<int>(v);
\tint exponent = (bits >> 23) & 0xFF;
\tif ((exponent == 0) || (exponent == 255))
\t\treturn GLFixedToFloat(v);
\treturn v;
}
inline float2 vglUnpack(float2 v) {
\treturn float2(vglUnpack(v.x), vglUnpack(v.y));
}
inline float3 vglUnpack(float3 v) {
\t\treturn float3(vglUnpack(v.x), vglUnpack(v.y), vglUnpack(v.z));
}
inline float4 vglUnpack(float4 v) {
\t\treturn float4(vglUnpack(v.x), vglUnpack(v.y), vglUnpack(v.z), vglUnpack(v.w));
}""",
        """#define GLFixedToFloat(fx) (float(fx))
inline float vglUnpack(float v) { return v; }
inline float2 vglUnpack(float2 v) { return v; }
inline float3 vglUnpack(float3 v) { return v; }
inline float4 vglUnpack(float4 v) { return v; }""",
        "Vita3K shader bit_cast helpers",
    )
    if "bit_cast" in shader_header:
        raise SystemExit("Vita3K shader compatibility patch left bit_cast in translator header")
    shader_header_path.write_text(shader_header, encoding="utf-8")

    # vitaGL's postponed GLSL path performs the actual shader compilation from
    # glLinkProgram().  Upstream currently assumes both compiles succeeded and
    # immediately dereferences the resulting GXM program pointers. Vita3K turns
    # any compiler rejection into an access violation at a small address. Keep
    # PROG_UNLINKED on failure so glGetProgramiv(GL_LINK_STATUS) can report it.
    custom_shaders_path = root / "source" / "custom_shaders.c"
    custom_shaders = custom_shaders_path.read_text(encoding="utf-8")
    custom_shaders = replace_once(
        custom_shaders,
        """\t\tglsl_sema_mode = VGL_MODE_POSTPONED;
\t}

\tif (p->status == PROG_LINKED) {""",
        """\t\tglsl_sema_mode = VGL_MODE_POSTPONED;
#ifndef SKIP_ERROR_HANDLING
\t\tif (!p->vshader->prog || !p->fshader->prog) {
\t\t\tvgl_log("%s:%d: %s: GLSL shader-pair compilation failed; link aborted.\\n", __FILE__, __LINE__, __func__);
\t\t\treturn;
\t\t}
#endif
\t}

\tif (p->status == PROG_LINKED) {""",
        "Vita3K GLSL link failure guard",
    )
    custom_shaders_path.write_text(custom_shaders, encoding="utf-8")

    checks = (
        "shark_init_simple(NULL)",
        "SCE_GXM_INITIALIZE_FLAG_DEFAULT",
        "sceGxmInitialize(&gxm_init_params)",
    )
    for token in checks:
        if token not in text:
            raise SystemExit(f"compat patch verification failed: {token}")

    print("Applied Vita3K compatibility init patch to", path)
    print("Applied Vita3K shader-compiler compatibility patch to", shader_header_path)
    print("Applied Vita3K GLSL link-failure guard to", custom_shaders_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
