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



# SceGxmVertexAttribute::offset is uint16_t. A GL buffer offset is not: keep
# the common allocation offset in the stream pointer and only the field offset
# in the GXM descriptor. This is a GXM contract, not a Vita3K-only workaround.
PACKED_VBO_GUARD = r"""
#ifndef STRICT_DRAW_COMPLIANCE
    const uintptr_t voq_packed_vbo_base = cur_vao->vertex_attrib_offsets[p->attr_map[0]];
    if (is_packed && target_vbo) {
        /* All enabled attributes must fit the SAME rebased stream. Checking
         * just attr_map[1] misses separate/earlier UV streams and mixed strides.
         * The existing unpacked VBO route is also zero-copy and handles those
         * layouts with one full-width address per attribute.
         */
        for (int i = 0; i < p->attr_num; ++i) {
            const uint8_t attr_idx = p->attr_map[i];
            if (!(cur_vao->vertex_attrib_state & (1 << attr_idx))) continue;
            const uintptr_t offset = cur_vao->vertex_attrib_offsets[attr_idx];
            if ((vbo *)cur_vao->vertex_attrib_vbo[attr_idx] != target_vbo ||
                offset < voq_packed_vbo_base ||
                offset - voq_packed_vbo_base > UINT16_MAX ||
                streams[i].stride != streams[0].stride) {
                is_packed = GL_FALSE;
                break;
            }
        }
#ifdef LOG_ERRORS
        static int voq_reported_large_vbo_base = 0;
        if (is_packed && !voq_reported_large_vbo_base && voq_packed_vbo_base > UINT16_MAX) {
            voq_reported_large_vbo_base = 1;
            sceClibPrintf("[VOQ4][vertex] %s: rebased VBO base=%u stride=%u attrs=%u\n",
                __func__, (unsigned)voq_packed_vbo_base, (unsigned)streams[0].stride,
                (unsigned)p->attr_num);
        }
#endif
    }
#endif
"""


def patch_vertex_streams(root: pathlib.Path) -> None:
    """Rebase the three packed VBO draw paths without truncating GL offsets."""
    path = root / 'source/custom_shaders.c'
    text = path.read_text(encoding='utf-8')
    if 'voq_packed_vbo_base' in text:
        raise RuntimeError('Packed VBO addressing patch already applied')
    # Only this macro copies an absolute VBO offset into GXM's uint16 field.
    # Independent/client streams retain their original pointer semantics.
    old = 'attributes[i].offset = cur_vao->vertex_attrib_offsets[attr_idx];'
    new = ('attributes[i].offset = (uint16_t)'
           '(cur_vao->vertex_attrib_offsets[attr_idx] - voq_packed_vbo_base);')
    text = _legacy().replace_once(text, old, new, 'packed VBO relative offset')
    entries = (
        ('void _glMultiDrawArrays_CustomShadersIMPL(',
         '#ifdef STRICT_DRAW_COMPLIANCE\n\t// Gathering real attribute data pointers',
         '(void *)target_vbo->ptr + lowest * streams[0].stride',
         '(uint8_t *)target_vbo->ptr + voq_packed_vbo_base + lowest * streams[0].stride'),
        ('GLboolean _glDrawArrays_CustomShadersIMPL(',
         '#ifdef STRICT_DRAW_COMPLIANCE\n\t// Gathering real attribute data pointers',
         '(void *)target_vbo->ptr + first * streams[0].stride',
         '(uint8_t *)target_vbo->ptr + voq_packed_vbo_base + first * streams[0].stride'),
        ('GLboolean _glDrawElements_CustomShadersIMPL(',
         '\t// Detecting highest index value',
         '(void *)target_vbo->ptr;',
         '(uint8_t *)target_vbo->ptr + voq_packed_vbo_base;'),
    )
    for signature, marker, before, after in entries:
        start, end = _legacy().function_span(text, signature)
        body = text[start:end]
        body = _legacy().replace_once(body, marker, PACKED_VBO_GUARD + '\n' + marker,
                                      signature + ' packed layout validation')
        body = _legacy().replace_once(body, before, after, signature + ' stream base')
        text = text[:start] + body + text[end:]
    path.write_text(text, encoding='utf-8')
    print('Applied full-width VBO stream bases and bounded relative GXM attributes (3 draw paths)')



def patch_read_buffer_query(root: pathlib.Path) -> None:
    """Expose the read selection already maintained by glReadBuffer.

    Necessary for state-preserving readbacks, not a new rendering policy.
    """
    header = root / 'source/vitaGL.h'
    text = header.read_text(encoding='utf-8')
    text = _legacy().replace_once(text,
        '#define GL_FRAMEBUFFER_BINDING                          0x8CA6',
        '#define GL_READ_BUFFER                                  0x0C02\n'
        '#define GL_FRAMEBUFFER_BINDING                          0x8CA6',
        'GL_READ_BUFFER query enum')
    header.write_text(text, encoding='utf-8')
    # Read-buffer selection is private to framebuffers.c. Keep it private and
    # query through a declared accessor rather than referencing a static symbol
    # from another translation unit.
    shared = root / 'source/shared.h'
    text = shared.read_text(encoding='utf-8')
    text = _legacy().replace_once(text,
        '// Framebuffers\n',
        '// Framebuffers\nGLenum vgl_get_read_buffer(void);\n',
        'internal read-buffer query declaration')
    shared.write_text(text, encoding='utf-8')
    framebuffer = root / 'source/framebuffers.c'
    text = framebuffer.read_text(encoding='utf-8')
    text = _legacy().replace_once(text,
        'void glReadBuffer(GLenum mode) {',
        'GLenum vgl_get_read_buffer(void) {\n'
        '\treturn active_read_fb ? GL_COLOR_ATTACHMENT0 : display_read_mode;\n'
        '}\n\nvoid glReadBuffer(GLenum mode) {',
        'private read-buffer state accessor')
    framebuffer.write_text(text, encoding='utf-8')
    path = root / 'source/get_info.c'
    text = path.read_text(encoding='utf-8')
    text = _legacy().replace_once(text,
        '\tcase GL_READ_FRAMEBUFFER_BINDING:\n\t\t*data = (GLint)active_read_fb;\n\t\tbreak;',
        '\tcase GL_READ_FRAMEBUFFER_BINDING:\n\t\t*data = (GLint)active_read_fb;\n\t\tbreak;\n'
        '\tcase GL_READ_BUFFER:\n'
        '\t\t*data = (GLint)vgl_get_read_buffer();\n'
        '\t\tbreak;', 'read buffer selection query')
    path.write_text(text, encoding='utf-8')
    print('Applied GL_READ_BUFFER query for state-preserving readbacks')



MEMORY_QUERY = r"""
/* Diagnostic query: a non-empty pool must receive valid stats. Some emulators
 * leave sceClibMspaceMallocStats output untouched; never expose stack garbage
 * as free memory. This does not participate in allocation or pool sizing.
 */
int voq_vgl_query_free_pools(size_t free_bytes[3]) {
    if (!free_bytes) return 0;
    free_bytes[0] = free_bytes[1] = free_bytes[2] = 0;
#ifdef PHYCONT_ON_DEMAND
    /* There is no bounded physical pool to measure in this allocator mode. */
    return 0;
#else
    const vglMemType types[3] = { VGL_MEM_RAM, VGL_MEM_VRAM, VGL_MEM_PHYCONT };
    size_t observed[3] = {0, 0, 0};
    for (unsigned i = 0; i < 3; ++i) {
        const vglMemType type = types[i];
        if (!mempool_size[type]) continue;
#ifdef HAVE_CUSTOM_HEAP
        observed[i] = tm_free[type];
        if (observed[i] > mempool_size[type]) return 0;
#else
        if (!mempool_mspace[type]) return 0;
        /* SDK declares a void return: validity comes from the filled struct,
         * not an invented status code. Zero capacity cannot describe a live
         * non-empty mspace, so an unimplemented HLE remains unavailable.
         */
        SceClibMspaceStats stats = {0};
        sceClibMspaceMallocStats(mempool_mspace[type], &stats);
        if (!stats.capacity || stats.capacity > mempool_size[type] ||
            stats.current_in_use > stats.capacity) return 0;
        observed[i] = stats.capacity - stats.current_in_use;
#endif
    }
    for (unsigned i = 0; i < 3; ++i) free_bytes[i] = observed[i];
    return 1;
#endif
}
"""


def patch_memory_query(root: pathlib.Path) -> None:
    path = root / 'source/utils/mem_utils.c'
    text = path.read_text(encoding='utf-8')
    marker = 'size_t vgl_mem_get_total_space(vglMemType type) {'
    text = _legacy().replace_once(text, marker, MEMORY_QUERY + '\n' + marker,
                                  'validated diagnostic pool query')
    path.write_text(text, encoding='utf-8')
    print('Applied initialized and validated diagnostic mspace query')


def patch_client_texture_units(root: pathlib.Path) -> None:
    """Reject client texture-coordinate units outside the implemented FFP range."""
    path = root / 'source/ffp.c'
    text = path.read_text(encoding='utf-8')
    old = '\tif (texture - GL_TEXTURE0 >= TEXTURE_COORDS_NUM) {\n\t\tvgl_log("%s:%d Attempting to use a too high client texture unit (GL_TEXTURE%d).\\n", __FILE__, __LINE__, texture - GL_TEXTURE0);\n\t}'
    new = '\tif (texture - GL_TEXTURE0 >= TEXTURE_COORDS_NUM) {\n\t\tSET_GL_ERROR_WITH_VALUE(GL_INVALID_ENUM, texture)\n\t}'
    text = _legacy().replace_once(text, old, new, 'bounded client texture coordinate unit')
    path.write_text(text, encoding='utf-8')
    print('Applied strict fixed-function client texture-coordinate bounds')

def main() -> int:
    if len(sys.argv) != 2:
        raise SystemExit('usage: patch_vitagl_vita3k.py <vitaGL-repo>')
    _legacy().main()
    patch_bc(pathlib.Path(sys.argv[1]))
    patch_vertex_streams(pathlib.Path(sys.argv[1]))
    patch_read_buffer_query(pathlib.Path(sys.argv[1]))
    patch_memory_query(pathlib.Path(sys.argv[1]))
    patch_client_texture_units(pathlib.Path(sys.argv[1]))
    import patch_vitagl_memory
    patch_vitagl_memory.patch(pathlib.Path(sys.argv[1]))
    from patch_vitagl_cube import patch as patch_cube
    patch_cube(pathlib.Path(sys.argv[1]))
    import patch_vitagl_float_upload
    patch_vitagl_float_upload.patch(pathlib.Path(sys.argv[1]))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
