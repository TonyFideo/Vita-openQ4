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

    # _glTexImage2D_FlatIMPL accepts GL_HALF_FLOAT for RGBA16F, but the matching
    # _glTexSubImage2D path rejects the same type. OpenQ4 allocates first and
    # uploads afterwards, so add a native F16 fast-store subimage path.
    textures_path = root / "source" / "textures.c"
    textures = textures_path.read_text(encoding="utf-8")
    subimage_marker = "static inline __attribute__((always_inline)) void _glTexSubImage2D("
    subimage_pos = textures.find(subimage_marker)
    if subimage_pos < 0:
        raise SystemExit("Vita3K half-float patch: _glTexSubImage2D marker not found")

    textures_prefix = textures[:subimage_pos]
    textures_subimage = textures[subimage_pos:]
    textures_subimage = replace_once(
        textures_subimage,
        """\tcase GL_RGBA:
\t\tswitch (type) {
\t\tcase GL_UNSIGNED_BYTE:
\t\t\tdata_bpp = 4;
\t\t\tread_cb = read_rgba8888;
\t\t\tbreak;""",
        """\tcase GL_RGBA:
\t\tswitch (type) {
\t\tcase GL_HALF_FLOAT:
\t\tcase GL_HALF_FLOAT_OES:
\t\t\tif (tex_format != SCE_GXM_TEXTURE_FORMAT_F16F16F16F16_RGBA) {
\t\t\t\tSET_GL_ERROR_WITH_VALUE(GL_INVALID_ENUM, type)
\t\t\t}
\t\t\tdata_bpp = 8;
\t\t\tfast_store = GL_TRUE;
\t\t\tbreak;
\t\tcase GL_UNSIGNED_BYTE:
\t\t\tdata_bpp = 4;
\t\t\tread_cb = read_rgba8888;
\t\t\tbreak;""",
        "Vita3K half-float texture subimage support",
    )
    textures = textures_prefix + textures_subimage
    textures_path.write_text(textures, encoding="utf-8")

    gpu_utils_path = root / "source" / "utils" / "gpu_utils.c"
    gpu_utils = gpu_utils_path.read_text(encoding="utf-8")
    gpu_utils = replace_once(
        gpu_utils,
        """			if (curWidth <= 1024 && curHeight <= 1024) {
				sceGxmTransferDownscale(
					fmt, curPtr, 0, 0,
					curWidth, curHeight,
					curSrcStride * bpp,
					fmt, dstPtr, 0, 0,
					curDstStride * bpp,
					NULL, 0, NULL);
			} else { // sceGxmTransferDownscale doesn't support higher sizes, so we go for CPU downscaling
				for (int y = 0, y2 = 0; y < curHeight; y += 2, y2++) {
					uint8_t *srcLine = curPtr + curSrcStride * bpp * y;
					uint8_t *dstLine = dstPtr + curDstStride * bpp * y2;
					for (int x = 0, x2 = 0; x < curWidth; x += 2, x2++) {
						sceClibMemcpy(dstLine + x2 * bpp, srcLine + x * bpp, bpp);
					}
				}
			}""",
        """#ifndef HAVE_VITA3K_SUPPORT
			if (curWidth <= 1024 && curHeight <= 1024) {
				sceGxmTransferDownscale(
					fmt, curPtr, 0, 0,
					curWidth, curHeight,
					curSrcStride * bpp,
					fmt, dstPtr, 0, 0,
					curDstStride * bpp,
					NULL, 0, NULL);
			} else
#endif
			{
				// Vita3K's transfer-downscale HLE path has crashed while vitaGL was
				// building tiny OpenQ4 intrinsic mip chains. Keep the same nearest
				// downscale semantics entirely in guest memory on the emulator.
				for (int y = 0, y2 = 0; y < curHeight; y += 2, y2++) {
					uint8_t *srcLine = curPtr + curSrcStride * bpp * y;
					uint8_t *dstLine = dstPtr + curDstStride * bpp * y2;
					for (int x = 0, x2 = 0; x < curWidth; x += 2, x2++) {
						sceClibMemcpy(dstLine + x2 * bpp, srcLine + x * bpp, bpp);
					}
				}
			}""",
        "Vita3K guest-CPU mip downscale",
    )
    gpu_utils_path.write_text(gpu_utils, encoding="utf-8")

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
    print("Applied Vita3K half-float subimage support to", textures_path)
    print("Applied Vita3K guest-CPU mip downscale patch to", gpu_utils_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
