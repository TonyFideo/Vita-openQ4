#!/usr/bin/env python3
"""Pinned VitaGL profile: linear mips and lifetime-safe native BC uploads.

Prior linear/init changes are preserved byte-for-byte in the sibling
patch_vitagl_vita3k_linear.py. This entrypoint contains all new generated code,
so the existing Actions cache key is invalidated when this implementation changes.
"""
from __future__ import annotations
import importlib.util
import pathlib
import sys

_legacy_module = None


def _legacy():
    global _legacy_module
    if _legacy_module is None:
        path = pathlib.Path(__file__).with_name('patch_vitagl_vita3k_linear.py')
        spec = importlib.util.spec_from_file_location('voq_linear_patch', path)
        if spec is None or spec.loader is None:
            raise RuntimeError('Cannot load pinned linear mip patch')
        _legacy_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(_legacy_module)
    return _legacy_module


def __getattr__(name):
    # Preserve the existing native regression-test API.
    if name not in {'LAYOUT_HEADER', 'MIP_ALLOCATOR', 'SUBIMAGE_GUARD',
                    'SUBIMAGE_ADDRESS', 'patch_mips', 'function_span', 'replace_once'}:
        raise AttributeError(name)
    return getattr(_legacy(), name)


BC_LAYOUT_HEADER = r'''/* Exact block storage; no decompression/recompression or missing mips. */
#ifndef VGL_VOQ_BC_LAYOUT_H
#define VGL_VOQ_BC_LAYOUT_H
#include <stdint.h>
#include <stddef.h>
#define VOQ_BC_LEVELS 13

typedef struct {
    uint32_t width[VOQ_BC_LEVELS], height[VOQ_BC_LEVELS];
    uint32_t blocks_w[VOQ_BC_LEVELS], blocks_h[VOQ_BC_LEVELS];
    size_t offset[VOQ_BC_LEVELS], bytes[VOQ_BC_LEVELS];
    unsigned count;
    size_t capacity;
} voq_bc_layout;

static int voq_bc_build_layout(uint32_t w, uint32_t h, unsigned block_bytes,
                               voq_bc_layout *out) {
    if (!out || !w || !h || w > 4096 || h > 4096 ||
        (block_bytes != 8 && block_bytes != 16)) return 0;
    uint32_t pw = 1, ph = 1;
    while (pw < w) pw <<= 1;
    while (ph < h) ph <<= 1;
    out->count = 0;
    out->capacity = 0;
    do {
        unsigned i = out->count++;
        out->width[i] = w;
        out->height[i] = h;
        out->blocks_w[i] = (pw + 3) / 4;
        out->blocks_h[i] = (ph + 3) / 4;
        out->offset[i] = out->capacity;
        out->bytes[i] = (size_t)out->blocks_w[i] * out->blocks_h[i] * block_bytes;
        out->capacity += out->bytes[i];
        if (w == 1 && h == 1) return 1;
        w = w > 1 ? w >> 1 : 1;
        h = h > 1 ? h >> 1 : 1;
        pw = pw > 1 ? pw >> 1 : 1;
        ph = ph > 1 ? ph >> 1 : 1;
    } while (out->count < VOQ_BC_LEVELS);
    return 0;
}
#endif
'''

BC_UPLOAD_CODE = r'''
#ifdef HAVE_VITA3K_SUPPORT
#include "voq_bc_layout.h"

static unsigned voq_bc_block_bytes(SceGxmTextureFormat format) {
    switch (format) {
    case SCE_GXM_TEXTURE_FORMAT_UBC1_1BGR:
    case SCE_GXM_TEXTURE_FORMAT_UBC1_ABGR:
    case SCE_GXM_TEXTURE_FORMAT_UBC4_R:
        return 8;
    case SCE_GXM_TEXTURE_FORMAT_UBC2_ABGR:
    case SCE_GXM_TEXTURE_FORMAT_UBC3_ABGR:
    case SCE_GXM_TEXTURE_FORMAT_UBC5_GR:
        return 16;
    default:
        return 0;
    }
}

static void voq_upload_native_bc(int32_t level, uint32_t w, uint32_t h,
                                 SceGxmTextureFormat format, uint32_t image_size,
                                 const void *data, texture *tex, unsigned block_bytes) {
    uint32_t base_w = w, base_h = h;
    if (!tex || level < 0 || level >= VOQ_BC_LEVELS) {
        SET_GL_ERROR(GL_INVALID_VALUE)
    }
    if (level > 0) {
        if (tex->status != TEX_VALID || !tex->data ||
            vglGetTexFormat(&tex->gxm_tex) != format) {
            SET_GL_ERROR(GL_INVALID_OPERATION)
        }
        vglGetTexSizes(&tex->gxm_tex, &base_w, &base_h);
    }
    voq_bc_layout layout;
    if (!voq_bc_build_layout(base_w, base_h, block_bytes, &layout) ||
        (unsigned)level >= layout.count ||
        w != layout.width[level] || h != layout.height[level]) {
        SET_GL_ERROR(GL_INVALID_VALUE)
    }
    const uint32_t bw = (w + 3) / 4, bh = (h + 3) / 4;
    const size_t required = (size_t)bw * bh * block_bytes;
    if (image_size != 0 && image_size != required) {
        SET_GL_ERROR(GL_INVALID_VALUE)
    }
    int busy = 0;
#ifndef TEXTURES_SPEEDHACK
    busy = tex->status == TEX_VALID && tex->last_frame != OBJ_NOT_USED &&
        vgl_framecount - tex->last_frame <= FRAME_PURGE_FREQ;
#endif
    /* Growing a chain uses a new GPU-aligned block, never realloc. CPU block
     * reordering finishes before return, so no queued transfer owns the old
     * destination. Redefinition / sampled textures use copy-on-write.
     */
    unsigned count = level == 0 ? 1 : tex->mip_count;
    if (count < (unsigned)level + 1) count = (unsigned)level + 1;
    if (count == 0 || count > layout.count) { SET_GL_ERROR(GL_INVALID_VALUE) }
    const size_t storage_bytes = layout.offset[count - 1] + layout.bytes[count - 1];
    const int replace = level == 0 || busy || count > tex->mip_count;
    uint8_t *storage = (uint8_t *)tex->data;
    if (replace) {
        storage = (uint8_t *)gpu_alloc_mapped_for_gpu(storage_bytes);
        if (!storage) { SET_GL_ERROR(GL_OUT_OF_MEMORY) }
        vgl_memset(storage, 0, storage_bytes);
        if (level > 0 && tex->mip_count > 0) {
            const unsigned last = tex->mip_count - 1;
            const size_t old_bytes = layout.offset[last] + layout.bytes[last];
            vgl_memcpy(storage, tex->data, old_bytes);
        }
    }
    uint8_t *dest = storage + layout.offset[level];
    /* Reordering BC blocks is lossless; GPU still samples native UBC1/2/3/4/5.
     * Use the same NEON block swizzler as upstream's NPOT/small-mip path.
     * In particular no asynchronous TransferCopy can outlive these buffers.
     */
    vgl_memset(dest, 0, layout.bytes[level]);
    if (data) {
        const uint32_t tile = layout.blocks_w[level] < layout.blocks_h[level]
            ? layout.blocks_w[level] : layout.blocks_h[level];
        if (block_bytes == 16) {
            SwizzleTexData128Bpp(dest, (uint8_t *)data, 0, 0, bw, bh, bw, tile);
        } else {
            SwizzleTexData64Bpp(dest, (uint8_t *)data, 0, 0, bw, bh, bw, tile);
        }
    }
    if (replace && tex->status == TEX_VALID) gpu_free_texture_data(tex);
    tex->mip_count = count;
    vglInitSwizzledTexture(&tex->gxm_tex, storage, format, base_w, base_h,
                          tex->use_mips ? count : 0);
    tex->palette_data = NULL;
    tex->data = storage;
    tex->status = TEX_VALID;
#ifndef TEXTURES_SPEEDHACK
    tex->last_frame = OBJ_NOT_USED;
#endif
#ifdef HAVE_TEX_CACHE
    if (replace) { mark_as_cacheable(tex) }
#endif
#ifdef LOG_ERRORS
    static unsigned reported = 0;
    if (level == 0 && data && reported < 8) {
        ++reported;
        sceClibPrintf("[VOQ4][BC] native blocks %ux%u block=%u levels=%u bytes=%u\n",
            base_w, base_h, block_bytes, layout.count, (unsigned)storage_bytes);
    }
#endif
}
#endif
'''

BC_ROUTE = r'''
#ifdef HAVE_VITA3K_SUPPORT
    const unsigned voq_block_bytes = voq_bc_block_bytes(format);
    if (!uncompressed && voq_block_bytes) {
        voq_upload_native_bc(mip_level, w, h, format, image_size, data, tex, voq_block_bytes);
        return;
    }
#endif
'''


def patch_bc(root: pathlib.Path) -> None:
    path = root / 'source/utils/gpu_utils.c'
    text = path.read_text(encoding='utf-8')
    signature = 'void gpu_alloc_compressed_texture(int32_t mip_level,'
    if text.count(signature) != 1 or 'voq_upload_native_bc' in text:
        raise RuntimeError('Unexpected / already patched compressed allocator')
    start = text.index(signature)
    opening = text.index('{', start)
    text = text[:opening + 1] + BC_ROUTE + text[opening + 1:]
    text = text[:start] + BC_UPLOAD_CODE + '\n' + text[start:]
    (path.parent / 'voq_bc_layout.h').write_text(BC_LAYOUT_HEADER, encoding='utf-8')
    path.write_text(text, encoding='utf-8')
    print('Applied lossless BC upload storage, source lifetime and sampled-texture COW')


def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit('usage: patch_vitagl_vita3k.py <vitaGL-repo>')
    _legacy().main()
    patch_bc(pathlib.Path(sys.argv[1]))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
