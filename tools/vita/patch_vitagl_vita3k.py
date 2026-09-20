#!/usr/bin/env python3
"""Apply the pinned Vita3K profile and bounded uncompressed mip storage.

The pre-existing compatibility edits are preserved in
patch_vitagl_vita3k_base.py (blob 4356b1acae867856905ecd4b151e0ad87c5e2355).
All additional generated code lives here so the existing CI cache hash covers it.
"""
from __future__ import annotations
import pathlib
import sys

LAYOUT_HEADER = r'''/* OpenQ4 Vita3K compatibility profile: shared linear mip layout.
 * No GXM dependencies: exercised by the native regression test.
 */
#ifndef VGL_VITA3K_MIP_LAYOUT_H
#define VGL_VITA3K_MIP_LAYOUT_H
#include <stdint.h>
#include <stddef.h>
#define VGL_VITA3K_MAX_MIPS 16

typedef struct {
    uint32_t width[VGL_VITA3K_MAX_MIPS];
    uint32_t height[VGL_VITA3K_MAX_MIPS];
    uint32_t stride[VGL_VITA3K_MAX_MIPS];
    size_t offset[VGL_VITA3K_MAX_MIPS];
    size_t size;
    unsigned levels;
} vgl_vita3k_mip_layout;

static int vgl_vita3k_build_mip_layout(uint32_t width, uint32_t height,
                                      uint32_t bpp, int mipmapped,
                                      vgl_vita3k_mip_layout *out) {
    if (!out || !width || !height || width > 4096 || height > 4096 ||
        !bpp || bpp > 16) return 0;
    uint32_t sw = width, sh = height;
    if (mipmapped) {
        sw = sh = 1;
        while (sw < width) sw <<= 1;
        while (sh < height) sh <<= 1;
    }
    out->levels = 0;
    out->size = 0;
    do {
        const unsigned i = out->levels++;
        out->width[i] = width;
        out->height[i] = height;
        out->stride[i] = ((sw + 7u) & ~7u) * bpp;
        out->offset[i] = out->size;
        out->size += (size_t)out->stride[i] * sh;
        if (!mipmapped || (width == 1 && height == 1)) break;
        width = width > 1 ? width >> 1 : 1;
        height = height > 1 ? height >> 1 : 1;
        sw = sw > 1 ? sw >> 1 : 1;
        sh = sh > 1 ? sh >> 1 : 1;
    } while (out->levels < VGL_VITA3K_MAX_MIPS);
    return 1;
}
#endif
'''

MIP_ALLOCATOR = r'''void gpu_alloc_mipmaps(int level, texture *tex) {
#ifdef HAVE_VITA3K_SUPPORT
    /* Vita3K's transfer-downscale HLE path is intentionally not used here.
     * Allocation and uploads must agree on the entire chain, including 1xN,
     * Nx1 and the rectangular tail. Preserve the engine-authored mip levels.
     */
    if (tex->status != TEX_VALID || !tex->data) return;
    const SceGxmTextureFormat format = vglGetTexFormat(&tex->gxm_tex);
    const uint32_t bpp = tex_format_to_bytespp(format);
    uint32_t orig_w, orig_h;
    vglGetTexSizes(&tex->gxm_tex, &orig_w, &orig_h);
    vgl_vita3k_mip_layout layout;
    if (!vgl_vita3k_build_mip_layout(orig_w, orig_h, bpp, 1, &layout)) {
        SET_GL_ERROR(GL_INVALID_VALUE)
    }
    if (level >= (int)layout.levels) {
        SET_GL_ERROR(GL_INVALID_VALUE)
    }
    const unsigned requested = level < 0 ? layout.levels : (unsigned)level + 1;
    if (requested <= 1 || (level >= 0 && requested <= tex->mip_count)) return;

    const int already_mipped = tex->mip_count > 1;
#ifdef LOG_ERRORS
    if (!already_mipped) {
        sceClibPrintf("[VOQ4][mip] alloc %ux%u bpp=%u levels=%u bytes=%u\n",
            orig_w, orig_h, bpp, layout.levels, (unsigned)layout.size);
    }
#endif
    int copy_on_write = 0;
#ifndef TEXTURES_SPEEDHACK
    copy_on_write = tex->last_frame != OBJ_NOT_USED &&
        vgl_framecount - tex->last_frame <= FRAME_PURGE_FREQ;
#endif
    uint8_t *new_data = (uint8_t *)tex->data;
    if (!already_mipped || copy_on_write) {
        /* Do not realloc a potentially in-flight GXM pointer; preserve mapping
         * alignment and let the normal texture GC retire the old allocation.
         */
        new_data = (uint8_t *)gpu_alloc_mapped_for_gpu(layout.size);
        if (!new_data) {
            SET_GL_ERROR(GL_OUT_OF_MEMORY)
        }
        if (already_mipped) {
            vgl_memcpy(new_data, tex->data, layout.size);
        } else {
            vgl_memset(new_data, 0, layout.size);
            const uint32_t old_stride = VGL_ALIGN(orig_w, 8) * bpp;
            for (uint32_t y = 0; y < orig_h; ++y) {
                vgl_memcpy(new_data + y * layout.stride[0],
                    (const uint8_t *)tex->data + y * old_stride, orig_w * bpp);
            }
        }
    }
    /* Same nearest-neighbour CPU policy as the prior emulator patch, with
     * clamped dimensions, floor-sized NPOT levels and explicit row pitches.
     */
    for (unsigned i = 1; i < requested; ++i) {
        const uint8_t *src = new_data + layout.offset[i - 1];
        uint8_t *dst = new_data + layout.offset[i];
        for (uint32_t y = 0; y < layout.height[i]; ++y) {
            const uint32_t sy = layout.height[i - 1] > 1 ? y * 2 : 0;
            for (uint32_t x = 0; x < layout.width[i]; ++x) {
                const uint32_t sx = layout.width[i - 1] > 1 ? x * 2 : 0;
                sceClibMemcpy(dst + y * layout.stride[i] + x * bpp,
                    src + sy * layout.stride[i - 1] + sx * bpp, bpp);
            }
        }
    }
    if (new_data != tex->data) gpu_free_texture_data(tex);
    tex->mip_count = requested;
    vglInitLinearTexture(&tex->gxm_tex, new_data, format, orig_w, orig_h,
                        tex->use_mips ? tex->mip_count : 0);
    tex->palette_data = NULL;
    tex->status = TEX_VALID;
    tex->data = new_data;
#ifndef TEXTURES_SPEEDHACK
    tex->last_frame = OBJ_NOT_USED;
#endif
#ifdef HAVE_TEX_CACHE
    mark_as_cacheable(tex)
#endif
#else
__ORIGINAL_BODY__
#endif
}'''

SUBIMAGE_GUARD = r'''
#ifdef HAVE_VITA3K_SUPPORT
    vgl_vita3k_mip_layout voq_layout;
    int voq_linear_target = target == GL_TEXTURE_2D;
#ifdef HAVE_UNPURE_TEXFORMATS
    voq_linear_target |= target == GL_TEXTURE_1D;
#endif
    if (voq_linear_target) {
        if (tex->status != TEX_VALID || !tex->data) {
            SET_GL_ERROR(GL_INVALID_OPERATION)
        }
        if (!vgl_vita3k_build_mip_layout(orig_w, orig_h, bpp,
                                        tex->mip_count > 1, &voq_layout) ||
            level < 0 || (unsigned)level >= voq_layout.levels ||
            (unsigned)level >= tex->mip_count || xoffset < 0 || yoffset < 0 ||
            width < 0 || height < 0 ||
            (uint32_t)xoffset > voq_layout.width[level] ||
            (uint32_t)yoffset > voq_layout.height[level] ||
            (uint32_t)width > voq_layout.width[level] - (uint32_t)xoffset ||
            (uint32_t)height > voq_layout.height[level] - (uint32_t)yoffset) {
            SET_GL_ERROR(GL_INVALID_VALUE)
        }
        if (width == 0 || height == 0) return;
        if (!pixels) { SET_GL_ERROR(GL_INVALID_VALUE) }
    }
#endif
'''

SUBIMAGE_ADDRESS = r'''#ifdef HAVE_VITA3K_SUPPORT
        /* The same layout is used for allocation, copy-on-write and upload.
         * In particular never derive pitch from an uninitialized local when
         * the dirty-texture branch has already calculated the jump table.
         */
        mip_w = voq_layout.width[level];
        mip_stride = voq_layout.stride[level];
        ptr += voq_layout.offset[level];
#else
__ORIGINAL_ADDRESS__
#endif
'''


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if text.count(old) != 1:
        raise RuntimeError(f"{label}: expected one pinned-source match, got {text.count(old)}")
    return text.replace(old, new, 1)


def function_span(text: str, signature: str) -> tuple[int, int]:
    """Pinned functions have no unmatched braces in strings/comments."""
    if text.count(signature) != 1:
        raise RuntimeError(f"expected one function: {signature}")
    start = text.index(signature)
    opening = text.index("{", start)
    depth = 1
    for pos in range(opening + 1, len(text)):
        depth += (text[pos] == "{") - (text[pos] == "}")
        if depth == 0:
            return start, pos + 1
    raise RuntimeError(f"unterminated function: {signature}")


def patch_mips(root: pathlib.Path) -> None:
    gpu_path = root / "source/utils/gpu_utils.c"
    text = gpu_path.read_text(encoding="utf-8")
    start, end = function_span(text, "void gpu_alloc_mipmaps(int level, texture *tex)")
    old = text[start:end]
    # Fail closed if the pinned dependency no longer has the problematic loop.
    if "while ((w > 1) && (h > 1))" not in old:
        raise RuntimeError("unexpected original mip allocator")
    original_body = old[old.index("{") + 1:old.rfind("}")]
    replacement = MIP_ALLOCATOR.replace("__ORIGINAL_BODY__", original_body)
    text = text[:start] + replacement + text[end:]
    text = replace_once(text, '#include "../shared.h"',
        '#include "../shared.h"\n#ifdef HAVE_VITA3K_SUPPORT\n#include "vita3k_mip_layout.h"\n#endif',
        "mip allocator layout include")
    # Compressed 2D/cube upload paths pass w/4,h/4 (or w/8,h/4)
    # to GXM. Sub-block authored DDS mips must use the existing CPU swizzler;
    # otherwise these calls submit a zero width/height to the transfer backend.
    transfer_predicate = "aligned_width == w && aligned_height == h && h <= 2048"
    if text.count(transfer_predicate) < 2:
        raise RuntimeError("expected compressed transfer predicates in pinned vitaGL")
    text = text.replace(transfer_predicate,
        "w >= 8 && h >= 4 && " + transfer_predicate)
    gpu_path.write_text(text, encoding="utf-8")
    (root / "source/utils/vita3k_mip_layout.h").write_text(LAYOUT_HEADER, encoding="utf-8")

    path = root / "source/textures.c"
    text = path.read_text(encoding="utf-8")
    start, end = function_span(text, "static inline __attribute__((always_inline)) void _glTexSubImage2D(")
    sub = text[start:end]
    sub = replace_once(sub, "\tuint32_t po2_h;", "\tuint32_t po2_h;\n" + SUBIMAGE_GUARD,
                       "per-mip upload bounds")
    alloc = "\t\tvoid *texture_data = gpu_alloc_mapped_for_gpu(size);"
    sub = replace_once(sub, alloc,
        "#ifdef HAVE_VITA3K_SUPPORT\n"
        "\t\tif (voq_linear_target) size = voq_layout.size;\n"
        "#endif\n" + alloc + "\n"
        "#ifdef HAVE_VITA3K_SUPPORT\n"
        "\t\tif (!texture_data) { SET_GL_ERROR(GL_OUT_OF_MEMORY) }\n"
        "#endif", "copy-on-write capacity and OOM")
    a = sub.index("\t\tif (level > 0) {", sub.index("uint32_t mip_w, mip_stride;"))
    b = sub.index("\t\tptr += xoffset * bpp + yoffset * mip_stride;", a)
    old_address = sub[a:b]
    sub = sub[:a] + SUBIMAGE_ADDRESS.replace("__ORIGINAL_ADDRESS__", old_address) + sub[b:]
    text = text[:start] + sub + text[end:]
    # Append the include before the function; shared.h has already been included.
    start = text.index("static inline __attribute__((always_inline)) void _glTexSubImage2D(")
    text = text[:start] + '#ifdef HAVE_VITA3K_SUPPORT\n#include "utils/vita3k_mip_layout.h"\n#endif\n\n' + text[start:]
    path.write_text(text, encoding="utf-8")
    print("Applied bounded Vita3K linear mip allocation/upload and copy-on-write")


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit("usage: patch_vitagl_vita3k.py <vitaGL-repo>")
    import patch_vitagl_vita3k_base
    patch_vitagl_vita3k_base.main()
    patch_mips(pathlib.Path(sys.argv[1]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
