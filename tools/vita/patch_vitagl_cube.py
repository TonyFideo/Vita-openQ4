"""Native immutable RGBA8 cubes: complete mip storage and bounded subimage writes.

Keep the GXM face layout independent from sampling policy. A non-mipped view
uses a separately packed base-level snapshot, never a changed stride over the
mipped allocation. Client pixel bytes are consumed before an upload returns.
"""
from pathlib import Path
import re

CUBE_CODE = r'''
/* BEGIN VOQ IMMUTABLE CUBE STORAGE */
static size_t voq_cube_face_bytes(unsigned size, unsigned levels) {
    size_t bytes = 0;
    for (unsigned i = 0, w = size; i < levels; ++i, w >>= 1) bytes += (size_t)w * w * 4;
    /* No-mip descriptors use tightly packed planes. Mipped RGBA32 cube faces
     * require 2 KiB alignment at dimensions >=16 (GXM cube layout). */
    return levels > 1 && size >= 16 ? (bytes + 2047u) & ~(size_t)2047u : bytes;
}
static size_t voq_cube_level_offset(unsigned size, unsigned level) {
    size_t bytes = 0;
    for (unsigned i = 0, w = size; i < level; ++i, w >>= 1) bytes += (size_t)w * w * 4;
    return bytes;
}
static unsigned voq_cube_morton(unsigned x, unsigned y) {
    /* GXM interleaves Y in even bits and X in odd bits. */
    x = (x | (x << 8)) & 0x00ff00ffu;
    y = (y | (y << 8)) & 0x00ff00ffu;
    x = (x | (x << 4)) & 0x0f0f0f0fu;
    y = (y | (y << 4)) & 0x0f0f0f0fu;
    x = (x | (x << 2)) & 0x33333333u;
    y = (y | (y << 2)) & 0x33333333u;
    x = (x | (x << 1)) & 0x55555555u;
    y = (y | (y << 1)) & 0x55555555u;
    return (x << 1) | y;
}
static int voq_cube_busy(const texture *tex) {
#ifndef TEXTURES_SPEEDHACK
    return tex->last_frame != OBJ_NOT_USED && vgl_framecount - tex->last_frame <= FRAME_PURGE_FREQ;
#else
    return 1;
#endif
}
static void voq_cube_retire(texture *tex, void *data) {
    if (!data) return;
    if (voq_cube_busy(tex)) mark_as_dirty(data);
    else vgl_free(data);
}
void voq_cube_release_view(texture *tex) {
    voq_cube_retire(tex, tex->voq_cube_base_view);
    tex->voq_cube_base_view = NULL;
    tex->voq_cube_levels = 0;
    tex->voq_cube_size = 0;
}

/* Called in texture state changes and BOTH programmable/FFP sampler paths.
 * The ordinary 2D path remains untouched. */
void voq_set_texture_mip_count(texture *tex, uint32_t requested) {
    if (!tex->voq_cube_levels) {
        vglSetTexMipmapCount(&tex->gxm_tex, requested);
        return;
    }
    void *data = tex->data;
    unsigned count = tex->voq_cube_levels;
    if (count == 1) count = 0;
    else if (requested <= 1) {
        const size_t base_bytes = (size_t)tex->voq_cube_size * tex->voq_cube_size * 4;
        const size_t face_bytes = voq_cube_face_bytes(tex->voq_cube_size, tex->voq_cube_levels);
        if (!tex->voq_cube_base_view) {
            void *view = gpu_alloc_mapped_for_gpu(base_bytes * 6);
            if (!view) { SET_GL_ERROR(GL_OUT_OF_MEMORY) }
            for (unsigned face = 0; face < 6; ++face)
                vgl_memcpy((uint8_t *)view + face * base_bytes,
                           (uint8_t *)tex->data + face * face_bytes, base_bytes);
            tex->voq_cube_base_view = view;
        }
        data = tex->voq_cube_base_view;
        count = 0;
    }
    sceGxmTextureSetData(&tex->gxm_tex, data);
    vglSetTexMipmapCount(&tex->gxm_tex, count);
}
static GLenum voq_cube_storage(texture *tex, int levels, GLenum internalformat, int width, int height) {
    if (tex->voq_cube_levels) return GL_INVALID_OPERATION;
    if (internalformat != GL_RGBA8) return GL_INVALID_ENUM;
    if (width <= 0 || height != width || width > 4096 || (width & (width-1)) || levels < 1 || levels > 13 ||
        (width >> (levels-1)) == 0) return GL_INVALID_VALUE;
    const size_t bytes = 6 * voq_cube_face_bytes((unsigned)width, (unsigned)levels);
    void *data = gpu_alloc_mapped_for_gpu(bytes);
    if (!data) return GL_OUT_OF_MEMORY;
    vgl_memset(data, 0, bytes);
    if (tex->status == TEX_VALID) gpu_free_texture_data(tex);
    tex->voq_cube_size = (uint16_t)width;
    tex->voq_cube_levels = (uint8_t)levels;
    tex->voq_cube_base_view = NULL;
    tex->data = data;
    tex->palette_data = NULL;
    tex->mip_count = (uint8_t)levels;
    tex->status = TEX_VALID;
    tex->faces_counter = 6;
    tex->format = SCE_GXM_TEXTURE_FORMAT_U8U8U8U8_ABGR;
    vglInitCubeTexture(&tex->gxm_tex, data, tex->format, width, height, levels == 1 ? 0 : levels);
    vglSetTexUMode(&tex->gxm_tex, SCE_GXM_TEXTURE_ADDR_CLAMP);
    vglSetTexVMode(&tex->gxm_tex, SCE_GXM_TEXTURE_ADDR_CLAMP);
    vglSetTexMinFilter(&tex->gxm_tex, tex->min_filter);
    vglSetTexMagFilter(&tex->gxm_tex, tex->mag_filter);
    vglSetTexMipFilter(&tex->gxm_tex, tex->mip_filter);
    vglSetTexLodBias(&tex->gxm_tex, tex->lod_bias);
    tex->overridden = GL_TRUE;
#ifndef TEXTURES_SPEEDHACK
    tex->last_frame = OBJ_NOT_USED;
#endif
    return GL_NO_ERROR;
}
static GLenum voq_cube_begin_write(texture *tex) {
    const size_t face_bytes = voq_cube_face_bytes(tex->voq_cube_size, tex->voq_cube_levels);
    const int busy = voq_cube_busy(tex);
    if (busy) {
        void *replacement = gpu_alloc_mapped_for_gpu(face_bytes * 6);
        if (!replacement) return GL_OUT_OF_MEMORY;
        vgl_memcpy(replacement, tex->data, face_bytes * 6);
        voq_cube_retire(tex, tex->data);
        tex->data = replacement;
    }
    voq_cube_retire(tex, tex->voq_cube_base_view);
    tex->voq_cube_base_view = NULL;
#ifndef TEXTURES_SPEEDHACK
    tex->last_frame = OBJ_NOT_USED;
#endif
    tex->overridden = GL_TRUE;
    sceGxmTextureSetData(&tex->gxm_tex, tex->data);
    vglSetTexMipmapCount(&tex->gxm_tex, tex->voq_cube_levels == 1 ? 0 : tex->voq_cube_levels);
    return GL_NO_ERROR;
}
static GLenum voq_cube_subimage(texture *tex, int face, int level, int x, int y, int width, int height,
                                GLenum format, GLenum type, const void *pixels, int row_length) {
    if (!tex->voq_cube_levels || tex->status != TEX_VALID) return GL_INVALID_OPERATION;
    if (format != GL_RGBA || type != GL_UNSIGNED_BYTE) return GL_INVALID_ENUM;
    if (face < 0 || face >= 6 || level < 0 || level >= tex->voq_cube_levels) return GL_INVALID_VALUE;
    const int size = tex->voq_cube_size >> level;
    if (x < 0 || y < 0 || width < 0 || height < 0 || width > size || height > size ||
        x > size-width || y > size-height || row_length < 0) return GL_INVALID_VALUE;
    if (!width || !height) return GL_NO_ERROR;
    if (!pixels) return GL_INVALID_VALUE;
    const size_t face_bytes = voq_cube_face_bytes(tex->voq_cube_size, tex->voq_cube_levels);
    const GLenum prepared = voq_cube_begin_write(tex);
    if (prepared != GL_NO_ERROR) return prepared;
    uint8_t *dest = (uint8_t *)tex->data + face * face_bytes + voq_cube_level_offset(tex->voq_cube_size, level);
    const uint8_t *source = (const uint8_t *)pixels;
    const size_t stride = (size_t)(row_length ? row_length : width) * 4;
    for (int row = 0; row < height; ++row) {
        for (int col = 0; col < width; ++col)
            vgl_memcpy(dest + 4 * voq_cube_morton(x+col, y+row), source + row * stride + col * 4, 4);
    }
    /* Reapply the sampler at submission; no allocation per uploaded row for
     * non-mipped sampling of storage that also contains higher levels. */
    tex->overridden = GL_TRUE;
    sceGxmTextureSetData(&tex->gxm_tex, tex->data);
    vglSetTexMipmapCount(&tex->gxm_tex, tex->voq_cube_levels == 1 ? 0 : tex->voq_cube_levels);
    return GL_NO_ERROR;
}
static GLenum voq_cube_generate(texture *tex) {
    if (!tex->voq_cube_levels || tex->status != TEX_VALID) return GL_INVALID_OPERATION;
    if (tex->voq_cube_levels == 1) return GL_NO_ERROR;
    const GLenum prepared = voq_cube_begin_write(tex);
    if (prepared != GL_NO_ERROR) return prepared;
    const size_t face_bytes = voq_cube_face_bytes(tex->voq_cube_size, tex->voq_cube_levels);
    for (unsigned face = 0; face < 6; ++face) {
        uint8_t *base = (uint8_t *)tex->data + face * face_bytes;
        for (unsigned level = 1; level < tex->voq_cube_levels; ++level) {
            const unsigned size = tex->voq_cube_size >> level;
            const uint8_t *source = base + voq_cube_level_offset(tex->voq_cube_size, level - 1);
            uint8_t *dest = base + voq_cube_level_offset(tex->voq_cube_size, level);
            for (unsigned y = 0; y < size; ++y) for (unsigned x = 0; x < size; ++x) {
                for (unsigned c = 0; c < 4; ++c) {
                    const unsigned sum = source[4 * voq_cube_morton(2*x,2*y) + c]
                        + source[4 * voq_cube_morton(2*x+1,2*y) + c]
                        + source[4 * voq_cube_morton(2*x,2*y+1) + c]
                        + source[4 * voq_cube_morton(2*x+1,2*y+1) + c];
                    dest[4 * voq_cube_morton(x,y) + c] = (uint8_t)(sum >> 2);
                }
            }
        }
    }
    return GL_NO_ERROR;
}
/* END VOQ IMMUTABLE CUBE STORAGE */
'''

API_CODE = r'''
void glTexStorage2D(GLenum target, GLsizei levels, GLenum internalformat, GLsizei width, GLsizei height) {
    THREAD_SAFE()
    if (target != GL_TEXTURE_CUBE_MAP) { SET_GL_ERROR_WITH_VALUE(GL_INVALID_ENUM, target) }
    texture_unit *unit = &texture_units[server_texture_unit];
    const GLuint id = unit->tex_id[2];
    if (!id) { SET_GL_ERROR(GL_INVALID_OPERATION) }
    texture *tex = &texture_slots[id];
    const GLenum error = voq_cube_storage(tex, levels, internalformat, width, height);
    if (error != GL_NO_ERROR) { SET_GL_ERROR(error) }
}
'''

def replace(text, old, new):
    if text.count(old) != 1: raise RuntimeError('unexpected cube patch anchor: '+old[:100])
    return text.replace(old,new)

def patch(root: Path):
    path=root/'source/shared.h';s=path.read_text()
    s=replace(s,'\tuint8_t faces_counter;', '\tuint8_t faces_counter;\n\tuint8_t voq_cube_levels;\n\tuint16_t voq_cube_size;\n\tvoid *voq_cube_base_view;')
    s=replace(s,'#include "utils/gpu_utils.h"', 'void voq_cube_release_view(texture *tex);\nvoid voq_set_texture_mip_count(texture *tex, uint32_t requested);\n#include "utils/gpu_utils.h"')
    path.write_text(s)
    path=root/'source/utils/gpu_utils.h';s=path.read_text()
    s=replace(s,'static inline __attribute__((always_inline)) void gpu_free_texture_data(texture *tex) {',
              'static inline __attribute__((always_inline)) void gpu_free_texture_data(texture *tex) {\n\tvoq_cube_release_view(tex);')
    path.write_text(s)
    # Every sampler override must select the corresponding cube memory layout.
    for name in ('textures.c','custom_shaders.c','ffp.c'):
        path=root/'source'/name;s=path.read_text()
        s,n=re.subn(r'vglSetTexMipmapCount\(&tex->gxm_tex, ([^;]+)\);',r'voq_set_texture_mip_count(tex, \1);',s)
        if not n: raise RuntimeError('missing sampler path '+name)
        path.write_text(s)
    path=root/'source/textures.c';s=path.read_text()
    s=replace(s,'#include "shared.h"', '#include "shared.h"\n'+CUBE_CODE)
    s=replace(s,'\t\t\ttexture_slots[i].faces_counter = 0;', '\t\t\ttexture_slots[i].faces_counter = 0;\n\t\t\ttexture_slots[i].voq_cube_levels = 0;\n\t\t\ttexture_slots[i].voq_cube_size = 0;\n\t\t\ttexture_slots[i].voq_cube_base_view = NULL;')
    s=replace(s,'void glCreateTextures(GLenum target, GLsizei n, GLuint *textures) {',API_CODE+'\nvoid glCreateTextures(GLenum target, GLsizei n, GLuint *textures) {')
    # Early route, before the legacy cube path compares base-level dimensions.
    anchor='static inline __attribute__((always_inline)) void _glTexSubImage2D('
    start=s.index(anchor);opening=s.index('{',start)
    route=r'''
    if (tex->voq_cube_levels) {
        if (target < GL_TEXTURE_CUBE_MAP_POSITIVE_X || target > GL_TEXTURE_CUBE_MAP_NEGATIVE_Z) {
            SET_GL_ERROR_WITH_VALUE(GL_INVALID_ENUM, target)
        }
        GLenum error = voq_cube_subimage(tex, target - GL_TEXTURE_CUBE_MAP_POSITIVE_X,
            level, xoffset, yoffset, width, height, format, type, pixels, unpack_row_len);
        if (error != GL_NO_ERROR) { SET_GL_ERROR(error) }
        return;
    }
'''
    s=s[:opening+1]+route+s[opening+1:]
    # Immutable storage cannot be redefined through mutable image entrypoints.
    for signature in ('void _glTexImage2D_CubeIMPL(', 'void _glTexImage2D_FlatIMPL(', 'void _glCompressedTexImage2D('):
        start=s.index(signature);opening=s.index('{',start)
        s=s[:opening+1]+'\n\tif (tex->voq_cube_levels) { SET_GL_ERROR(GL_INVALID_OPERATION) }\n'+s[opening+1:]
    # Mipmap generation obeys immutable allocation and never enters 2D storage.
    anchor = 'void glGenerateMipmap(GLenum target) {\n\tTHREAD_SAFE()'
    route = r"""
    if (target == GL_TEXTURE_CUBE_MAP) {
        texture *tex = &texture_slots[texture_units[server_texture_unit].tex_id[2]];
        const GLenum error = voq_cube_generate(tex);
        if (error != GL_NO_ERROR) { SET_GL_ERROR(error) }
        return;
    }
"""
    s=replace(s, anchor, anchor + route)
    start=s.index('void glGenerateTextureMipmap(')
    marker='texture *tex = &texture_slots[target];'
    at=s.index(marker,start)+len(marker)
    s=s[:at]+r"""
    if (tex->voq_cube_levels) {
        const GLenum error = voq_cube_generate(tex);
        if (error != GL_NO_ERROR) { SET_GL_ERROR(error) }
        return;
    }
"""+s[at:]
    path.write_text(s)
    path=root/'source/vitaGL.h';s=path.read_text()
    marker = 'void glTexImage2D('
    index=s.index(marker)
    s=s[:index]+'void glTexStorage2D(GLenum target, GLsizei levels, GLenum internalformat, GLsizei width, GLsizei height);\n'+s[index:]
    path.write_text(s)
    path=root/'source/lookup.c';s=path.read_text()
    s=replace(s, '{"glTexImage2D", (void *)glTexImage2D},', '{"glTexImage2D", (void *)glTexImage2D},\n\t{"glTexStorage2D", (void *)glTexStorage2D},')
    path.write_text(s)
    print('Applied immutable RGBA8 cube storage, every mip, partial writes and sampler layout views')
