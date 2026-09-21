"""Typed RGBA16F transfers for the pinned linear VitaGL texture profile.

Keep external transfer representation distinct from GPU storage representation.
A byte pixel is normalized, never copied as two half pixels or dispatched to a
missing callback. All allocation/retirement uses VitaGL's existing ownership.
"""
from pathlib import Path

FLOAT_CODE = r'''
/* BEGIN VOQ FLOAT TRANSFERS */
#ifdef HAVE_VITA3K_SUPPORT
#include "utils/vita3k_mip_layout.h"
#include <stdint.h>
#include <string.h>
#include <limits.h>

#include "utils/voq_float_codec.h"

typedef struct {
    GLenum type;
    unsigned count, bytes, scalar_bytes;
    int map[4]; /* output R/G/B/A -> input component; -1=zero, -2=one */
    unsigned bits[4], shift[4];
    size_t stride;
} voq_float_source;

static GLenum voq_float_source_init(voq_float_source *out, GLenum format, GLenum type,
                                     int width, int height, int row_length, int alignment) {
    memset(out, 0, sizeof(*out));
    if (width < 0 || height < 0 || row_length < 0 ||
        (alignment != 1 && alignment != 2 && alignment != 4 && alignment != 8)) return GL_INVALID_VALUE;
    out->map[0] = out->map[1] = out->map[2] = -1; out->map[3] = -2;
    switch (format) {
    case GL_RED: case GL_R8: out->count=1; out->map[0]=0; break;
    case GL_RG: case GL_RG8: out->count=2; out->map[0]=0; out->map[1]=1; break;
    case GL_RGB: out->count=3; out->map[0]=0; out->map[1]=1; out->map[2]=2; break;
    case GL_BGR: out->count=3; out->map[0]=2; out->map[1]=1; out->map[2]=0; break;
    case GL_RGBA: out->count=4; out->map[0]=0; out->map[1]=1; out->map[2]=2; out->map[3]=3; break;
    case GL_BGRA: out->count=4; out->map[0]=2; out->map[1]=1; out->map[2]=0; out->map[3]=3; break;
    case GL_ABGR_EXT: out->count=4; out->map[0]=3; out->map[1]=2; out->map[2]=1; out->map[3]=0; break;
    case GL_LUMINANCE: out->count=1; out->map[0]=out->map[1]=out->map[2]=0; break;
    case GL_ALPHA: out->count=1; out->map[3]=0; break;
    case GL_LUMINANCE_ALPHA: out->count=2; out->map[0]=out->map[1]=out->map[2]=0; out->map[3]=1; break;
    default: return GL_INVALID_ENUM;
    }
    out->type = type;
    switch (type) {
    case GL_BYTE: case GL_UNSIGNED_BYTE: out->scalar_bytes=1; break;
    case GL_SHORT: case GL_UNSIGNED_SHORT: case GL_HALF_FLOAT: case GL_HALF_FLOAT_OES: out->scalar_bytes=2; break;
    case GL_INT: case GL_UNSIGNED_INT: case GL_FLOAT: out->scalar_bytes=4; break;
    case GL_UNSIGNED_SHORT_5_6_5:
        if (format != GL_RGB) return GL_INVALID_OPERATION;
        out->bytes=2; out->bits[0]=5; out->bits[1]=6; out->bits[2]=5;
        out->shift[0]=11; out->shift[1]=5; break;
    case GL_UNSIGNED_SHORT_4_4_4_4: case GL_UNSIGNED_SHORT_5_5_5_1:
    case GL_UNSIGNED_SHORT_1_5_5_5_REV: case GL_UNSIGNED_INT_8_8_8_8: case GL_UNSIGNED_INT_8_8_8_8_REV:
        if (format != GL_RGBA && format != GL_BGRA) return GL_INVALID_OPERATION;
        if (type == GL_UNSIGNED_SHORT_4_4_4_4) {
            out->bytes=2;
            for (unsigned i=0;i<4;++i) {out->bits[i]=4;out->shift[i]=12-4*i;}
        } else if (type == GL_UNSIGNED_SHORT_5_5_5_1) {
            out->bytes=2; out->bits[0]=out->bits[1]=out->bits[2]=5; out->bits[3]=1;
            out->shift[0]=11;out->shift[1]=6;out->shift[2]=1;
        } else if (type == GL_UNSIGNED_SHORT_1_5_5_5_REV) {
            out->bytes=2; out->bits[0]=out->bits[1]=out->bits[2]=5; out->bits[3]=1;
            out->shift[1]=5;out->shift[2]=10;out->shift[3]=15;
        } else {
            out->bytes=4;
            for (unsigned i=0;i<4;++i) {out->bits[i]=8;out->shift[i]=type==GL_UNSIGNED_INT_8_8_8_8 ? 24-8*i : 8*i;}
        }
        break;
    default: return GL_INVALID_ENUM;
    }
    if (out->scalar_bytes) out->bytes=out->count*out->scalar_bytes;
    const size_t columns = (size_t)(row_length ? row_length : width);
    if (columns > (SIZE_MAX - (unsigned)alignment + 1) / out->bytes) return GL_INVALID_VALUE;
    out->stride = (columns*out->bytes + (unsigned)alignment-1) & ~((size_t)alignment-1);
    if (height && out->stride > (SIZE_MAX - (size_t)width*out->bytes)/(size_t)height) return GL_INVALID_VALUE;
    return GL_NO_ERROR;
}
static uint16_t voq_float_component(const uint8_t *src, const voq_float_source *s, int c) {
    if (c < 0) return c == -2 ? 0x3c00u : 0;
    if (!s->scalar_bytes) {
        uint32_t packed=0; memcpy(&packed,src,s->bytes);
        const uint32_t mask=(1u<<s->bits[c])-1u;
        return voq_float_to_half((float)((packed>>s->shift[c])&mask)/(float)mask);
    }
    src += (unsigned)c*s->scalar_bytes;
    float value=0;
    switch (s->type) {
    case GL_UNSIGNED_BYTE: value=*src/255.0f; break;
    case GL_BYTE: {int8_t v;memcpy(&v,src,1);value=v < -127 ? -1.0f : v/127.0f;break;}
    case GL_UNSIGNED_SHORT: {uint16_t v;memcpy(&v,src,2);value=v/65535.0f;break;}
    case GL_SHORT: {int16_t v;memcpy(&v,src,2);value=v < -32767 ? -1.0f : v/32767.0f;break;}
    case GL_UNSIGNED_INT: {uint32_t v;memcpy(&v,src,4);value=(float)((double)v/4294967295.0);break;}
    case GL_INT: {int32_t v;memcpy(&v,src,4);value=v == INT32_MIN ? -1.0f : (float)((double)v/2147483647.0);break;}
    case GL_HALF_FLOAT: case GL_HALF_FLOAT_OES: {uint16_t v;memcpy(&v,src,2);return v;}
    case GL_FLOAT: memcpy(&value,src,4);break;
    }
    return voq_float_to_half(value);
}
static void voq_float_rows(uint8_t *dst, size_t dst_stride, const void *pixels,
                            int width, int height, const voq_float_source *source) {
    const uint8_t *src=(const uint8_t *)pixels;
    for (int y=0;y<height;++y) for (int x=0;x<width;++x) {
        uint16_t rgba[4];
        for (int c=0;c<4;++c) rgba[c]=voq_float_component(src+(size_t)y*source->stride+(size_t)x*source->bytes,source,source->map[c]);
        memcpy(dst+(size_t)y*dst_stride+(size_t)x*8,rgba,8);
    }
}
static int voq_float_busy(const texture *tex) {
#ifndef TEXTURES_SPEEDHACK
    return tex->last_frame != OBJ_NOT_USED && vgl_framecount-tex->last_frame <= FRAME_PURGE_FREQ;
#else
    return 1;
#endif
}
static void voq_float_publish(texture *tex, void *data, unsigned width, unsigned height, unsigned levels, int replaced) {
    tex->data=data;tex->palette_data=NULL;tex->mip_count=levels;tex->status=TEX_VALID;
    tex->write_cb=NULL; /* Floating storage is handled by typed transfers only. */
    tex->format=SCE_GXM_TEXTURE_FORMAT_F16F16F16F16_RGBA;
    vglInitLinearTexture(&tex->gxm_tex,data,tex->format,width,height,tex->use_mips?levels:0);
    vglSetTexUMode(&tex->gxm_tex,tex->u_mode);vglSetTexVMode(&tex->gxm_tex,tex->v_mode);
    vglSetTexMinFilter(&tex->gxm_tex,tex->min_filter);vglSetTexMagFilter(&tex->gxm_tex,tex->mag_filter);
    vglSetTexMipFilter(&tex->gxm_tex,tex->mip_filter);vglSetTexLodBias(&tex->gxm_tex,tex->lod_bias);
    tex->overridden=GL_TRUE;
    voq_float_texture_changed(tex);
#ifndef TEXTURES_SPEEDHACK
    tex->last_frame=OBJ_NOT_USED;
#endif
#ifdef HAVE_TEX_CACHE
    if (replaced) { mark_as_cacheable(tex) }
#else
    (void)replaced;
#endif
}
static GLenum voq_float_image(texture *tex,int level,int width,int height,GLenum format,GLenum type,
                               const void *pixels,int row_length,int alignment) {
    voq_float_source source;
    GLenum error=voq_float_source_init(&source,format,type,width,height,row_length,alignment);
    if (error) return error;
    if (tex->voq_cube_levels) return GL_INVALID_OPERATION;
    if (level<0 || level>=VGL_VITA3K_MAX_MIPS || width<=0 || height<=0 || width>4096 || height>4096) return GL_INVALID_VALUE;
    uint32_t w=(uint32_t)width,h=(uint32_t)height;
    vgl_vita3k_mip_layout layout,old_layout;
    unsigned levels=1;
    if (level) {
        if (tex->status!=TEX_VALID || !tex->data || vglGetTexFormat(&tex->gxm_tex)!=SCE_GXM_TEXTURE_FORMAT_F16F16F16F16_RGBA) return GL_INVALID_OPERATION;
        vglGetTexSizes(&tex->gxm_tex,&w,&h);
        if (!vgl_vita3k_build_mip_layout(w,h,8,1,&layout) || (unsigned)level>=layout.levels ||
            layout.width[level]!=(unsigned)width || layout.height[level]!=(unsigned)height) return GL_INVALID_VALUE;
        levels=tex->mip_count > (unsigned)level+1 ? tex->mip_count : (unsigned)level+1;
    } else if (!vgl_vita3k_build_mip_layout(w,h,8,0,&layout)) return GL_INVALID_VALUE;
#ifdef HAVE_TEX_CACHE
    restore_tex_cache(tex);
#endif
    voq_float_prepare_write(tex);
    /* Allocate before retiring the old image, including redefinition and mip
     * growth. A failed reservation leaves every previous descriptor intact. */
    const int replace=!level || tex->mip_count<=1 || voq_float_busy(tex);
    uint8_t *dest=(uint8_t *)tex->data;
    if (replace) {
        dest=(uint8_t *)gpu_alloc_mapped_for_gpu(layout.size);
        if (!dest) return GL_OUT_OF_MEMORY;
        memset(dest,0,layout.size);
        if (level) {
            vgl_vita3k_build_mip_layout(w,h,8,tex->mip_count>1,&old_layout);
            for (unsigned i=0;i<tex->mip_count;++i) for (unsigned y=0;y<old_layout.height[i];++y)
                memcpy(dest+layout.offset[i]+(size_t)y*layout.stride[i],
                       (uint8_t *)tex->data+old_layout.offset[i]+(size_t)y*old_layout.stride[i],old_layout.width[i]*8);
        }
    }
    if (pixels) voq_float_rows(dest+layout.offset[level],layout.stride[level],pixels,width,height,&source);
    if (replace && tex->status==TEX_VALID) gpu_free_texture_data(tex);
    voq_float_publish(tex,dest,w,h,levels,replace);
    return GL_NO_ERROR;
}
static GLenum voq_float_subimage(texture *tex,GLenum target,int level,int x,int y,int width,int height,
                                 GLenum format,GLenum type,const void *pixels,int row_length,int alignment) {
    if (target!=GL_TEXTURE_2D
#ifdef HAVE_UNPURE_TEXFORMATS
        && target!=GL_TEXTURE_1D
#endif
    ) return GL_INVALID_ENUM;
    if (tex->status!=TEX_VALID || !tex->data) return GL_INVALID_OPERATION;
    voq_float_source source;
    GLenum error=voq_float_source_init(&source,format,type,width,height,row_length,alignment);
    if (error) return error;
    uint32_t w,h;vglGetTexSizes(&tex->gxm_tex,&w,&h);
    vgl_vita3k_mip_layout layout;
    if (!vgl_vita3k_build_mip_layout(w,h,8,tex->mip_count>1,&layout) || level<0 ||
        (unsigned)level>=layout.levels || (unsigned)level>=tex->mip_count || x<0 || y<0 ||
        (unsigned)x>layout.width[level] || (unsigned)y>layout.height[level] ||
        (unsigned)width>layout.width[level]-(unsigned)x || (unsigned)height>layout.height[level]-(unsigned)y) return GL_INVALID_VALUE;
    if (!width || !height) return GL_NO_ERROR;
    if (!pixels) return GL_INVALID_VALUE;
#ifdef HAVE_TEX_CACHE
    restore_tex_cache(tex);
#endif
    voq_float_prepare_write(tex);
    uint8_t *dest=(uint8_t *)tex->data;
    const int replace=voq_float_busy(tex);
    if (replace) {
        dest=(uint8_t *)gpu_alloc_mapped_for_gpu(layout.size);
        if (!dest) return GL_OUT_OF_MEMORY;
        memcpy(dest,tex->data,layout.size);
    }
    voq_float_rows(dest+layout.offset[level]+(size_t)y*layout.stride[level]+(size_t)x*8,
                   layout.stride[level],pixels,width,height,&source);
    if (replace) gpu_free_texture_data(tex);
    voq_float_publish(tex,dest,w,h,tex->mip_count,replace);
    return GL_NO_ERROR;
}

/* Mip generation averages components in floating point, never the bytes of a
 * half value. Retain the same level/stride plan and retire only sampled data. */
static GLenum voq_float_generate(texture *tex) {
    if(tex->status!=TEX_VALID || !tex->data)return GL_INVALID_OPERATION;
#ifdef HAVE_TEX_CACHE
    restore_tex_cache(tex);
#endif
    uint32_t w,h;vglGetTexSizes(&tex->gxm_tex,&w,&h);
    vgl_vita3k_mip_layout layout,old_layout;
    if(!vgl_vita3k_build_mip_layout(w,h,8,1,&layout) ||
       !vgl_vita3k_build_mip_layout(w,h,8,tex->mip_count>1,&old_layout))return GL_INVALID_VALUE;
    voq_float_prepare_write(tex);
    const int replace=tex->mip_count<=1 || voq_float_busy(tex);
    uint8_t *dest=(uint8_t *)tex->data;
    if(replace){
        dest=(uint8_t *)gpu_alloc_mapped_for_gpu(layout.size);
        if(!dest)return GL_OUT_OF_MEMORY;
        memset(dest,0,layout.size);
        for(unsigned y=0;y<h;++y)
            memcpy(dest+(size_t)y*layout.stride[0],(uint8_t *)tex->data+(size_t)y*old_layout.stride[0],w*8);
    }
    for(unsigned level=1;level<layout.levels;++level){
        const unsigned pw=layout.width[level-1],ph=layout.height[level-1];
        for(unsigned y=0;y<layout.height[level];++y)for(unsigned x=0;x<layout.width[level];++x){
            float sum[4]={0,0,0,0};unsigned count=0;
            for(unsigned j=0;j<(ph>1?2u:1u);++j)for(unsigned i=0;i<(pw>1?2u:1u);++i){
                uint16_t rgba[4];memcpy(rgba,dest+layout.offset[level-1]+(size_t)(y*2+j)*layout.stride[level-1]+(x*2+i)*8,8);
                for(unsigned c=0;c<4;++c)sum[c]+=voq_half_to_float(rgba[c]);++count;
            }
            uint16_t rgba[4];for(unsigned c=0;c<4;++c)rgba[c]=voq_float_to_half(sum[c]/count);
            memcpy(dest+layout.offset[level]+(size_t)y*layout.stride[level]+x*8,rgba,8);
        }
    }
    if(replace)gpu_free_texture_data(tex);
    voq_float_publish(tex,dest,w,h,layout.levels,replace);
    return GL_NO_ERROR;
}
#endif
/* END VOQ FLOAT TRANSFERS */
'''

FLOAT_CODEC = r'''
#ifndef VOQ_FLOAT_CODEC_H
#define VOQ_FLOAT_CODEC_H
#include <stdint.h>
#include <string.h>
/* IEEE binary32 -> binary16, round-to-nearest ties-to-even. No ARM FP16 ISA
 * dependency, unaligned loads, type punning or saturation of HDR values. */
static uint16_t voq_float_to_half(float value) {
    uint32_t bits; memcpy(&bits, &value, sizeof(bits));
    const uint32_t sign = (bits >> 16) & 0x8000u;
    const uint32_t exponent = (bits >> 23) & 255u;
    uint32_t mantissa = bits & 0x7fffffu;
    if (exponent == 255u)
        return (uint16_t)(sign | 0x7c00u | (mantissa ? 0x0200u | (mantissa >> 13) : 0));
    int e = (int)exponent - 127 + 15;
    if (e >= 31) return (uint16_t)(sign | 0x7c00u);
    if (e <= 0) {
        if (e < -10) return (uint16_t)sign;
        mantissa |= 0x800000u;
        const unsigned shift = (unsigned)(14 - e);
        const uint32_t rounded = (mantissa + ((1u << (shift - 1)) - 1u)
                                  + ((mantissa >> shift) & 1u)) >> shift;
        return (uint16_t)(sign | rounded);
    }
    mantissa += 0xfffu + ((mantissa >> 13) & 1u);
    if (mantissa & 0x800000u) { mantissa = 0; ++e; }
    return (uint16_t)(sign | ((uint32_t)e << 10) | (mantissa >> 13));
}
static float voq_half_to_float(uint16_t value) {
    uint32_t sign = ((uint32_t)value & 0x8000u) << 16;
    uint32_t e = (value >> 10) & 31u, m = value & 1023u, bits;
    if (!e) {
        if (!m) bits = sign;
        else {
            int exponent = -14;
            while (!(m & 1024u)) { m <<= 1; --exponent; }
            bits = sign | ((uint32_t)(exponent + 127) << 23) | ((m & 1023u) << 13);
        }
    } else if (e == 31) bits = sign | 0x7f800000u | (m << 13);
    else bits = sign | ((e + 112u) << 23) | (m << 13);
    float out; memcpy(&out, &bits, sizeof(out)); return out;
}

#endif
'''

READ_CODE = r'''

/* BEGIN VOQ FLOAT READBACK */
#include "utils/vita3k_mip_layout.h"
/* Keep framebuffer attachment descriptors in sync after floating storage is
 * replaced. Do not detach/re-attach: that would disturb texture refcounts. */
void voq_float_prepare_write(texture *tex) {
    if(in_use_framebuffer && in_use_framebuffer->tex==tex){
        dirty_framebuffer=GL_TRUE;scene_reset();sceGxmFinish(gxm_context);
    }
}
/* CopyTex is ordered after all earlier draws in the GL command stream. The
 * source snapshot is complete before this helper is called, so a destination
 * sampled by an earlier draw can be updated in-place after explicitly closing
 * and waiting for that GXM scene. Generic client SubImage updates retain the
 * normal COW path; this synchronization is specific to framebuffer copies and
 * avoids allocating an entire screen-sized float texture every frame. */
void voq_float_sync_copy_destination(texture *tex) {
    if(!tex || tex->status!=TEX_VALID || !tex->data)return;
#ifndef TEXTURES_SPEEDHACK
    if(tex->last_frame==OBJ_NOT_USED || vgl_framecount-tex->last_frame>FRAME_PURGE_FREQ)return;
#endif
    dirty_framebuffer=GL_TRUE;
    scene_reset();
    sceGxmFinish(gxm_context);
#ifndef TEXTURES_SPEEDHACK
    tex->last_frame=OBJ_NOT_USED;
#endif
}
void voq_float_texture_changed(texture *tex) {
    for(unsigned i=0;i<BUFFERS_NUM;++i){
        framebuffer *fb=&framebuffers[i];
        if(!fb->active || fb->tex!=tex)continue;
        uint32_t w,h;vglGetTexSizes(&tex->gxm_tex,&w,&h);
        if(fb->width!=w || fb->height!=h){
            if(fb->target){mark_rt_as_dirty(fb->target);fb->target=NULL;}
            if(fb->depthbuffer_ptr){
#ifndef DEPTH_STENCIL_HACK
                mark_as_dirty(fb->depthbuffer_ptr->depthData);
#endif
                fb->depthbuffer_ptr=NULL;fb->depthbuffer_state&=~DEPTHBUFFER_READY;
            }
        }
        vgl_vita3k_mip_layout layout;
        if(!vgl_vita3k_build_mip_layout(w,h,8,tex->mip_count>1,&layout))continue;
        fb->width=w;fb->height=h;fb->stride=layout.stride[0];
        fb->data=tex->data;fb->format=tex->format;fb->is_float=GL_TRUE;
        sceGxmColorSurfaceInit(&fb->colorbuffer,get_color_from_texture(tex->format),SCE_GXM_COLOR_SURFACE_LINEAR,
            msaa_mode==SCE_GXM_MULTISAMPLE_NONE?SCE_GXM_COLOR_SURFACE_SCALE_NONE:SCE_GXM_COLOR_SURFACE_SCALE_MSAA_DOWNSCALE,
            SCE_GXM_OUTPUT_REGISTER_SIZE_64BIT,w,h,layout.stride[0]/8,fb->data);
        if(fb==active_write_fb)dirty_framebuffer=GL_TRUE;
    }
}

#include "utils/voq_float_codec.h"
/* Convert actual framebuffer components, not an internal-format enum passed
 * as a client type. In particular F16 RGBA occupies EIGHT bytes per pixel.
 * This profile exposes tight PACK rows, as does its existing readback API. */
static GLenum voq_float_read_pixels(GLint x,GLint y,GLsizei width,GLsizei height,
                                    GLenum format,GLenum type,void *data) {
    if (width<0 || height<0) return GL_INVALID_VALUE;
    unsigned components=0,map[4]={0,1,2,3},scalar=0;
    switch (format) {
    case GL_RGBA:case GL_RGBA8:components=4;break;
    case GL_BGRA:components=4;map[0]=2;map[2]=0;break;
    case GL_RGB:case GL_RGB8:components=3;break;
    case GL_BGR:components=3;map[0]=2;map[2]=0;break;
    case GL_RG:case GL_RG8:components=2;break;
    case GL_RED:case GL_R8:components=1;break;
    default:return GL_INVALID_ENUM;
    }
    switch(type){case GL_UNSIGNED_BYTE:scalar=1;break;
    case GL_HALF_FLOAT:case GL_HALF_FLOAT_OES:scalar=2;break;
    case GL_FLOAT:scalar=4;break;default:return GL_INVALID_ENUM;}
    const size_t pixel_bytes=components*scalar;
    if ((size_t)width>SIZE_MAX/pixel_bytes ||
        (height && (size_t)width*pixel_bytes>SIZE_MAX/(size_t)height)) return GL_INVALID_VALUE;
    if (!width || !height) return GL_NO_ERROR;
    if (!data) return GL_INVALID_VALUE;
    const uint8_t *source=NULL;
    size_t stride=0;int source_width,source_height;unsigned bpp;
    SceGxmTextureFormat storage;
    if (active_read_fb) {
        if(!active_read_fb->tex || !active_read_fb->data) return GL_INVALID_FRAMEBUFFER_OPERATION;
        source=(const uint8_t *)active_read_fb->data;stride=active_read_fb->stride;
        source_width=active_read_fb->width;source_height=active_read_fb->height;
        storage=active_read_fb->format;
    } else {
        source=(const uint8_t *)gxm_color_surfaces_addr[display_read_mode==GL_BACK?gxm_back_buffer_index:gxm_front_buffer_index];
        stride=(size_t)DISPLAY_STRIDE*4;source_width=DISPLAY_WIDTH;source_height=DISPLAY_HEIGHT;
        storage=SCE_GXM_TEXTURE_FORMAT_U8U8U8U8_ABGR;
    }
    uint32_t (*read_color)(const void *)=NULL;
    switch(storage){
    case SCE_GXM_TEXTURE_FORMAT_F16F16F16F16_RGBA:bpp=8;break;
    case SCE_GXM_TEXTURE_FORMAT_U8U8U8U8_ABGR:bpp=4;read_color=read_rgba8888;break;
    case SCE_GXM_TEXTURE_FORMAT_U8U8U8U8_ARGB:bpp=4;read_color=read_bgra8888;break;
    case SCE_GXM_TEXTURE_FORMAT_U8U8U8_BGR:bpp=3;read_color=read_rgb888;break;
    case SCE_GXM_TEXTURE_FORMAT_U8_R:bpp=1;read_color=read_r8;break;
    case SCE_GXM_TEXTURE_FORMAT_U8U8_GR:bpp=2;read_color=read_rg88;break;
    case SCE_GXM_TEXTURE_FORMAT_U4U4U4U4_RGBA:bpp=2;read_color=read_bgra4444;break;
    case SCE_GXM_TEXTURE_FORMAT_U5U6U5_RGB:bpp=2;read_color=read_rgb565;break;
    case SCE_GXM_TEXTURE_FORMAT_U1U5U5U5_ABGR:bpp=2;read_color=read_rgba5551;break;
    default:return GL_INVALID_OPERATION;
    }
    if (!source || source_width<=0 || source_height<=0 || stride<(size_t)source_width*bpp) return GL_INVALID_OPERATION;
#ifndef READBACKS_SPEEDHACK
    if (in_use_framebuffer==active_read_fb) {
        dirty_framebuffer=GL_TRUE;scene_reset();sceGxmFinish(gxm_context);
    }
#endif
    for(int row=0;row<height;++row) {
        /* Preserve VitaGL's native FBO/display orientation conventions. */
#ifdef HAVE_UNFLIPPED_FBOS
        const int64_t sy=(int64_t)source_height-1-((int64_t)y+row);
#else
        const int64_t sy=active_read_fb ? (int64_t)source_height-y-height+row : (int64_t)source_height-1-y-row;
#endif
        for(int col=0;col<width;++col) {
            const int64_t sx=(int64_t)x+col;
            uint8_t *out=(uint8_t *)data+((size_t)row*width+col)*pixel_bytes;
            if(sx<0 || sy<0 || sx>=source_width || sy>=source_height){memset(out,0,pixel_bytes);continue;}
            const uint8_t *in=source+(size_t)sy*stride+(size_t)sx*bpp;
            uint16_t half[4]={0,0,0,0};float rgba[4];
            if(!read_color){
                memcpy(half,in,8);for(unsigned c=0;c<4;++c)rgba[c]=voq_half_to_float(half[c]);
            }else{
                const uint32_t color=read_color((void *)in);
                for(unsigned c=0;c<4;++c)rgba[c]=(float)((color>>(8*c))&255u)/255.0f;
            }
            for(unsigned c=0;c<components;++c) {
                const float value=rgba[map[c]];
                if(type==GL_FLOAT)memcpy(out+c*4,&value,4);
                else if(scalar==2){const uint16_t v=read_color?voq_float_to_half(value):half[map[c]];memcpy(out+c*2,&v,2);}
                else out[c]=!(value>0)?0:value>=1?255:(uint8_t)(value*255.0f+0.5f);
            }
        }
    }
    return GL_NO_ERROR;
}
/* END VOQ FLOAT READBACK */
'''
COPY_CODE = r'''
/* BEGIN VOQ COPY TRANSFER */
/* The source is snapshotted before any destination allocation or retirement,
 * including self-copies. No GPU command retains this client pointer. CopyTex
 * ignores client unpack state; save and restore it rather than inheriting it. */
static void voq_copy_texture(GLenum target,GLuint tex_id,int direct,int subimage,
                             GLint level,GLenum internalformat,GLint xoffset,GLint yoffset,
                             GLint x,GLint y,GLsizei width,GLsizei height,GLint border) {
    if(level<0 || width<0 || height<0 || width>GXM_TEX_MAX_SIZE || height>GXM_TEX_MAX_SIZE || border!=0) {
        SET_GL_ERROR(GL_INVALID_VALUE)
    }
    if(direct && tex_id>=TEXTURES_NUM){SET_GL_ERROR(GL_INVALID_VALUE)}
    if(!direct && target!=GL_TEXTURE_2D
#ifdef HAVE_UNPURE_TEXFORMATS
       && target!=GL_TEXTURE_1D
#endif
       && (target<GL_TEXTURE_CUBE_MAP_POSITIVE_X || target>GL_TEXTURE_CUBE_MAP_NEGATIVE_Z)) {
        SET_GL_ERROR(GL_INVALID_ENUM)
    }
    const int binding=(target>=GL_TEXTURE_CUBE_MAP_POSITIVE_X && target<=GL_TEXTURE_CUBE_MAP_NEGATIVE_Z)?2:
#ifdef HAVE_UNPURE_TEXFORMATS
        target==GL_TEXTURE_1D?1:
#endif
        0;
    texture *tex=&texture_slots[direct?tex_id:texture_units[server_texture_unit].tex_id[binding]];
    const int half_destination=subimage ? tex->status==TEX_VALID &&
        vglGetTexFormat(&tex->gxm_tex)==SCE_GXM_TEXTURE_FORMAT_F16F16F16F16_RGBA : internalformat==GL_RGBA16F;
    const GLenum type=half_destination && active_read_fb &&
        active_read_fb->format==SCE_GXM_TEXTURE_FORMAT_F16F16F16F16_RGBA ? GL_HALF_FLOAT : GL_UNSIGNED_BYTE;
    const size_t bpp=type==GL_HALF_FLOAT?8:4;
    if((size_t)width>SIZE_MAX/bpp || (height && (size_t)width*bpp>SIZE_MAX/(size_t)height)){SET_GL_ERROR(GL_INVALID_VALUE)}
    if(!width || !height)return;
    void *pixels=vglMalloc((size_t)width*height*bpp);
    if(!pixels){SET_GL_ERROR(GL_OUT_OF_MEMORY)}
    const GLenum previous_error=vgl_error;
    vgl_error=GL_NO_ERROR;
    glReadPixels(x,y,width,height,GL_RGBA,type,pixels);
    if(vgl_error==GL_NO_ERROR){
        /* glReadPixels has snapshotted the source. Preserve GL ordering for a
         * sampled F16 destination without turning every screen capture into a
         * 960x544x8 copy-on-write allocation. */
        if(subimage && half_destination)voq_float_sync_copy_destination(tex);
        const int previous_row_length=unpack_row_len,previous_alignment=voq_unpack_alignment;
        unpack_row_len=0;voq_unpack_alignment=1;
        if(subimage){
            if(direct)glTextureSubImage2D(tex_id,level,xoffset,yoffset,width,height,GL_RGBA,type,pixels);
            else glTexSubImage2D(target,level,xoffset,yoffset,width,height,GL_RGBA,type,pixels);
        }else{
            if(direct)glTextureImage2D(tex_id,level,internalformat,width,height,border,GL_RGBA,type,pixels);
            else glTexImage2D(target,level,internalformat,width,height,border,GL_RGBA,type,pixels);
        }
        unpack_row_len=previous_row_length;voq_unpack_alignment=previous_alignment;
    }
    vgl_free(pixels);
    if(previous_error!=GL_NO_ERROR)vgl_error=previous_error;
}
/* END VOQ COPY TRANSFER */
'''

def patch(root: Path) -> None:
    import patch_vitagl_vita3k_linear as util
    (root/"source/utils/voq_float_codec.h").write_text(FLOAT_CODEC)
    header=root/'source/vitaGL.h';text=header.read_text()
    if '#define GL_INVALID_FRAMEBUFFER_OPERATION ' not in text:
        text=util.replace_once(text,'#define GL_INVALID_OPERATION', '#define GL_INVALID_FRAMEBUFFER_OPERATION 0x0506\n#define GL_INVALID_OPERATION','framebuffer error enum')
    header.write_text(text)
    path=root/'source/textures.c';text=path.read_text()
    text=util.replace_once(text,'#include "shared.h"','#include "shared.h"\n'+FLOAT_CODE,'float transfer implementation')
    text=util.replace_once(text,'int unpack_row_len = 0;', 'int voq_unpack_alignment = 4;\nint unpack_row_len = 0;', 'unpack alignment state')
    sig='static inline __attribute__((always_inline)) void _glTexImage2D_FlatIMPL('
    a,b=util.function_span(text,sig);body=text[a:b];opening=body.index('{')+1
    route='''
#ifdef HAVE_VITA3K_SUPPORT
    if (internalFormat == GL_RGBA16F) {
        const GLenum error=voq_float_image(tex,level,width,height,format,type,data,unpack_row_len,voq_unpack_alignment);
        if (error != GL_NO_ERROR) { SET_GL_ERROR(error) }
        return;
    }
#endif
'''
    body=body[:opening]+route+body[opening:];text=text[:a]+body+text[b:]
    # Both public and direct-state entrypoints use the shared implementation.
    marker='\tSceGxmTextureFormat tex_format = vglGetTexFormat(&tex->gxm_tex);'
    a,b=util.function_span(text,'static inline __attribute__((always_inline)) void _glTexSubImage2D(');body=text[a:b]
    route='''
#ifdef HAVE_VITA3K_SUPPORT
    if (tex->status == TEX_VALID && vglGetTexFormat(&tex->gxm_tex) == SCE_GXM_TEXTURE_FORMAT_F16F16F16F16_RGBA) {
        const GLenum error=voq_float_subimage(tex,target,level,xoffset,yoffset,width,height,format,type,pixels,unpack_row_len,voq_unpack_alignment);
        if (error != GL_NO_ERROR) { SET_GL_ERROR(error) }
        return;
    }
#endif
'''
    body=util.replace_once(body,marker,route+marker,'half subimage route');text=text[:a]+body+text[b:]
    # A missing converter for any other combination must not branch through 0.
    text=util.replace_once(text,'\t\t} else { // Executing texture modification via callbacks',
        '\t\t} else { // Executing texture modification via callbacks\n'
        '\t\t\tif (!read_cb || !write_cb) { SET_GL_ERROR(GL_INVALID_OPERATION) }','undefined conversion error')
    text=util.replace_once(text,'\tcase GL_UNPACK_ROW_LENGTH:\n\t\tunpack_row_len = param;',
        '\tcase GL_UNPACK_ALIGNMENT:\n\t\tif (param != 1 && param != 2 && param != 4 && param != 8) { SET_GL_ERROR(GL_INVALID_VALUE) }\n'
        '\t\tvoq_unpack_alignment = param;\n\t\tbreak;\n\tcase GL_UNPACK_ROW_LENGTH:\n'
        '\t\tif (param < 0) { SET_GL_ERROR(GL_INVALID_VALUE) }\n\t\tunpack_row_len = param;','pixel store validation')
    text=util.replace_once(text,'void glCopyTexImage2D(',COPY_CODE+'\nvoid glCopyTexImage2D(','checked copy implementation')
    calls={
        'void glCopyTexImage2D(':'voq_copy_texture(target,0,0,0,level,internalformat,0,0,x,y,width,height,border);',
        'void glCopyTextureImage2D(':'voq_copy_texture(GL_TEXTURE_2D,tex_id,1,0,level,internalformat,0,0,x,y,width,height,border);',
        'void glCopyTexSubImage2D(':'voq_copy_texture(target,0,0,1,level,0,xoffset,yoffset,x,y,width,height,0);',
        'void glCopyTextureSubImage2D(':'voq_copy_texture(GL_TEXTURE_2D,tex_id,1,1,level,0,xoffset,yoffset,x,y,width,height,0);',
    }
    for signature,call in calls.items():
        a,b=util.function_span(text,signature);body=text[a:b];opening=body.index('{')
        text=text[:a]+body[:opening+1]+'\n\tTHREAD_SAFE()\n\t'+call+'\n}'+text[b:]
    for signature in ('void glGenerateMipmap(', 'void glGenerateTextureMipmap('):
        a,b=util.function_span(text,signature);body=text[a:b]
        marker='\n#ifndef SKIP_ERROR_HANDLING'
        route='\n#ifdef HAVE_VITA3K_SUPPORT\n    if(tex->status==TEX_VALID && vglGetTexFormat(&tex->gxm_tex)==SCE_GXM_TEXTURE_FORMAT_F16F16F16F16_RGBA){\n        const GLenum error=voq_float_generate(tex);\n        if(error!=GL_NO_ERROR){SET_GL_ERROR(error)}\n        return;\n    }\n#endif\n'
        body=util.replace_once(body,marker,route+marker,'float mip generation dispatch')
        text=text[:a]+body+text[b:]
    path.write_text(text)
    path=root/'source/framebuffers.c' ;text=path.read_text()
    text=util.replace_once(text,'void glReadPixels(',READ_CODE+'\nvoid glReadPixels(','typed framebuffer reader')
    a,b=util.function_span(text,'void glReadPixels(');body=text[a:b]
    marker='\tTHREAD_SAFE()'
    route='\n    if (type==GL_HALF_FLOAT || type==GL_HALF_FLOAT_OES || type==GL_FLOAT ||\n        (active_read_fb && active_read_fb->format==SCE_GXM_TEXTURE_FORMAT_F16F16F16F16_RGBA)) {\n        const GLenum error=voq_float_read_pixels(x,y,width,height,format,type,data);\n        if(error!=GL_NO_ERROR){SET_GL_ERROR(error)}\n        return;\n    }\n'
    body=util.replace_once(body,marker,marker+route,'float readback dispatch')
    text=text[:a]+body+text[b:];path.write_text(text)
    path=root/'source/shared.h' ;text=path.read_text();text=util.replace_once(text,'extern int unpack_row_len;',
        'void voq_float_prepare_write(texture *tex);\nvoid voq_float_sync_copy_destination(texture *tex);\nvoid voq_float_texture_changed(texture *tex);\nextern int voq_unpack_alignment;\nextern int unpack_row_len;','alignment declaration');path.write_text(text)
    path=root/'source/get_info.c';text=path.read_text();text=util.replace_once(text,'\tcase GL_UNPACK_ALIGNMENT:\n\t\t*data = 1;',
        '\tcase GL_UNPACK_ALIGNMENT:\n\t\t*data = voq_unpack_alignment;','alignment query');path.write_text(text)
    print('Applied typed RGBA16F uploads, exact half/float conversion, transactional storage and COW')
