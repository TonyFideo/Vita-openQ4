#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <map>
#include <string>
#include <vector>
#include "gl_constants.h"
using GLenum=unsigned;using GLuint=unsigned;using GLint=int;using GLsizei=int;using GLboolean=int;using GLvoid=void;
using SceGxmTextureFormat=unsigned;
#define HAVE_VITA3K_SUPPORT 1
#define GXM_TEX_MAX_SIZE 4096
#define TEXTURES_NUM 4
#define THREAD_SAFE()
static GLenum vgl_error=GL_NO_ERROR;
#define SET_GL_ERROR(e) vgl_error=(e);return;
#define SET_GL_ERROR_WITH_VALUE(e,v) vgl_error=(e);return;
enum {SCE_GXM_TEXTURE_FORMAT_F16F16F16F16_RGBA=1,SCE_GXM_TEXTURE_FORMAT_U8U8U8U8_ABGR,
 SCE_GXM_TEXTURE_FORMAT_U8U8U8U8_ARGB,SCE_GXM_TEXTURE_FORMAT_U8U8U8_BGR,SCE_GXM_TEXTURE_FORMAT_U8_R,
 SCE_GXM_TEXTURE_FORMAT_U8U8_GR,SCE_GXM_TEXTURE_FORMAT_U4U4U4U4_RGBA,SCE_GXM_TEXTURE_FORMAT_U5U6U5_RGB,SCE_GXM_TEXTURE_FORMAT_U1U5U5U5_ABGR};
enum {TEX_VALID=1,OBJ_NOT_USED=0xffffffffu,FRAME_PURGE_FREQ=3};
struct SceGxmTexture{void*data=nullptr;unsigned width=0,height=0,format=0,levels=0;};
struct texture{
 unsigned last_frame=OBJ_NOT_USED,status=0,mip_count=0,format=0,voq_cube_levels=0;
 void*data=nullptr,*palette_data=nullptr;void(*write_cb)(void*,uint32_t)=nullptr;
 unsigned u_mode=7,v_mode=8,min_filter=9,mag_filter=10,mip_filter=11,lod_bias=12;
 bool use_mips=false,overridden=false;SceGxmTexture gxm_tex;
};
static uint32_t vgl_framecount=100;
static bool gpuFail=false,clientFail=false;static unsigned allocations=0,clientCalls=0;
static std::map<void*,size_t> gpu,clients;static std::vector<void*> retired;
static void*allocate(std::map<void*,size_t>&map,size_t n){void*p=malloc(n);assert(p);map[p]=n;return p;}
static void*gpu_alloc_mapped_for_gpu(size_t n){++allocations;return gpuFail?nullptr:allocate(gpu,n);}
static void* vglMalloc(size_t n){++clientCalls;return clientFail?nullptr:allocate(clients,n);}
static void vgl_free(void*p){if(!p)return;assert(gpu.erase(p)||clients.erase(p));free(p);}
static void gpu_free_texture_data(texture*t){if(t->data){if(t->last_frame!=OBJ_NOT_USED && vgl_framecount-t->last_frame<=FRAME_PURGE_FREQ)retired.push_back(t->data);else vgl_free(t->data);}t->data=nullptr;}
static void vglGetTexSizes(const SceGxmTexture*t,uint32_t*w,uint32_t*h){*w=t->width;*h=t->height;}
static unsigned vglGetTexFormat(const SceGxmTexture*t){return t->format;}
static void vglInitLinearTexture(SceGxmTexture*t,void*p,unsigned f,unsigned w,unsigned h,unsigned levels){*t={p,w,h,f,levels};}
static void vglSetTexUMode(SceGxmTexture*,unsigned){}static void vglSetTexVMode(SceGxmTexture*,unsigned){}
static void vglSetTexMinFilter(SceGxmTexture*,unsigned){}static void vglSetTexMagFilter(SceGxmTexture*,unsigned){}
static void vglSetTexMipFilter(SceGxmTexture*,unsigned){}static void vglSetTexLodBias(SceGxmTexture*,unsigned){}
static void voq_float_prepare_write(texture*);static void voq_float_texture_changed(texture*);
#include "float_impl.inc"
static int unpack_row_len=0,voq_unpack_alignment=4;static unsigned legacyRoutes=0;
#include "float_dispatch.inc"
struct depthbuffer{void *depthData=nullptr;};
struct framebuffer{texture*tex=nullptr;void*data=nullptr;unsigned stride=0,width=0,height=0,format=0;bool active=true;void*target=nullptr;depthbuffer*depthbuffer_ptr=nullptr;unsigned depthbuffer_state=0;bool is_float=false;unsigned colorbuffer=0;};
#define BUFFERS_NUM 4
static framebuffer framebuffers[BUFFERS_NUM];
static framebuffer*active_write_fb=nullptr;
enum{DEPTHBUFFER_READY=1,SCE_GXM_COLOR_SURFACE_LINEAR=1,SCE_GXM_MULTISAMPLE_NONE=0,SCE_GXM_COLOR_SURFACE_SCALE_NONE=0,SCE_GXM_COLOR_SURFACE_SCALE_MSAA_DOWNSCALE=1,SCE_GXM_OUTPUT_REGISTER_SIZE_64BIT=2};
static int msaa_mode=0;
static void mark_rt_as_dirty(void*){}static void mark_as_dirty(void*){}
static unsigned get_color_from_texture(unsigned f){return f;}
static void sceGxmColorSurfaceInit(unsigned*,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,unsigned,void*){}
static framebuffer*active_read_fb=nullptr,*in_use_framebuffer=nullptr;
static bool dirty_framebuffer=false;static unsigned syncs=0;
static int gxm_context=0;static void scene_reset(){++syncs;}static void sceGxmFinish(int){++syncs;}
static constexpr unsigned DISPLAY_WIDTH=3,DISPLAY_HEIGHT=2,DISPLAY_STRIDE=4;
static uint8_t displayPixels[32];static void*gxm_color_surfaces_addr[]={displayPixels,displayPixels};
static unsigned gxm_back_buffer_index=0,gxm_front_buffer_index=1;static GLenum display_read_mode=GL_BACK;
#include "callbacks.inc"
#include "float_read.inc"
struct texture_unit{GLuint tex_id[3]={};};static texture_unit texture_units[1];static texture texture_slots[TEXTURES_NUM];static int server_texture_unit=0;
static bool readFail=false;static GLenum observedReadType=0;
static void glReadPixels(GLint x,GLint y,GLsizei w,GLsizei h,GLenum f,GLenum t,void*p){observedReadType=t;vgl_error=readFail?GL_INVALID_OPERATION:voq_float_read_pixels(x,y,w,h,f,t,p);}
static void glTextureImage2D(GLuint id,GLint level,GLint internal,GLsizei w,GLsizei h,GLint border,GLenum f,GLenum t,const void*p){assert(border==0);_glTexImage2D_FlatIMPL(&texture_slots[id],level,internal,w,h,f,t,p);}
static void glTexImage2D(GLenum target,GLint level,GLint internal,GLsizei w,GLsizei h,GLint border,GLenum f,GLenum t,const void*p){assert(target==GL_TEXTURE_2D);glTextureImage2D(texture_units[0].tex_id[0],level,internal,w,h,border,f,t,p);}
static void glTextureSubImage2D(GLuint id,GLint level,GLint x,GLint y,GLsizei w,GLsizei h,GLenum f,GLenum t,const void*p){vgl_error=voq_float_subimage(&texture_slots[id],GL_TEXTURE_2D,level,x,y,w,h,f,t,p,unpack_row_len,voq_unpack_alignment);}
static void glTexSubImage2D(GLenum target,GLint level,GLint x,GLint y,GLsizei w,GLsizei h,GLenum f,GLenum t,const void*p){assert(target==GL_TEXTURE_2D);glTextureSubImage2D(texture_units[0].tex_id[0],level,x,y,w,h,f,t,p);}
#include "float_copy.inc"
static void cleanup(texture&t){t.last_frame=OBJ_NOT_USED;gpu_free_texture_data(&t);t=texture();for(void*p:retired)vgl_free(p);retired.clear();}
static uint16_t halfAt(const texture&t,unsigned level,unsigned x,unsigned y,unsigned c){vgl_vita3k_mip_layout l;assert(vgl_vita3k_build_mip_layout(t.gxm_tex.width,t.gxm_tex.height,8,t.mip_count>1,&l));uint16_t v;memcpy(&v,(uint8_t*)t.data+l.offset[level]+y*l.stride[level]+x*8+c*2,2);return v;}
static uint16_t referenceHalf(float f){_Float16 h=(_Float16)f;uint16_t v;memcpy(&v,&h,2);return v;}
static void codec(){
 for(unsigned i=0;i<65536;++i){uint16_t h=i;_Float16 ref;memcpy(&ref,&h,2);float f=(float)ref,g=voq_half_to_float(h);assert(std::isnan(f)?std::isnan(g):memcmp(&f,&g,4)==0);if(!std::isnan(f))assert(voq_float_to_half(f)==h);}
 uint32_t seed=17;for(unsigned i=0;i<150000;++i){seed=seed*1664525+1013904223;float f;memcpy(&f,&seed,4);if(!std::isnan(f))assert(voq_float_to_half(f)==referenceHalf(f));}
 assert(voq_float_to_half(1.00048828125f)==0x3c00);assert(voq_float_to_half(1.00146484375f)==0x3c02);
 puts("PASS binary16 exhaustive decode/roundtrip, 150000 binary32 roundings, ties-even, subnormal, infinities");
}
static void formats(){
 const GLenum fs[]={GL_RED,GL_RG,GL_RGB,GL_BGR,GL_RGBA,GL_BGRA,GL_ABGR_EXT,GL_LUMINANCE,GL_ALPHA,GL_LUMINANCE_ALPHA};
 const GLenum ts[]={GL_BYTE,GL_UNSIGNED_BYTE,GL_SHORT,GL_UNSIGNED_SHORT,GL_INT,GL_UNSIGNED_INT,GL_FLOAT,GL_HALF_FLOAT,GL_HALF_FLOAT_OES};
 unsigned count=0;
 for(auto f:fs)for(auto t:ts){voq_float_source src;assert(voq_float_source_init(&src,f,t,3,2,5,8)==0);std::vector<uint8_t>data(src.stride*2+1,0);auto p=data.data()+1;
  for(unsigned y=0;y<2;++y)for(unsigned x=0;x<3;++x)for(unsigned c=0;c<src.count;++c){uint8_t*q=p+y*src.stride+x*src.bytes+c*src.scalar_bytes;
    switch(t){case GL_BYTE:*q=64;break;case GL_UNSIGNED_BYTE:*q=128;break;case GL_SHORT:{int16_t v=16384;memcpy(q,&v,2);break;}case GL_UNSIGNED_SHORT:{uint16_t v=32768;memcpy(q,&v,2);break;}case GL_INT:{int32_t v=1073741824;memcpy(q,&v,4);break;}case GL_UNSIGNED_INT:{uint32_t v=2147483648u;memcpy(q,&v,4);break;}case GL_FLOAT:{float v=-2.5;memcpy(q,&v,4);break;}default:{uint16_t v=0x4400;memcpy(q,&v,2);break;}}
  }
  uint8_t out[64];memset(out,0xcc,sizeof(out));voq_float_rows(out,32,p,3,2,&src);
  for(unsigned y=0;y<2;++y)for(unsigned x=0;x<3;++x)for(unsigned c=0;c<4;++c){uint16_t actual;memcpy(&actual,out+y*32+x*8+c*2,2);float v=src.map[c]<0?(src.map[c]==-2?1:0):t==GL_BYTE?64.0f/127:t==GL_UNSIGNED_BYTE?128.0f/255:t==GL_SHORT?16384.0f/32767:t==GL_UNSIGNED_SHORT?32768.0f/65535:t==GL_FLOAT?-2.5f:t==GL_HALF_FLOAT||t==GL_HALF_FLOAT_OES?4.0f:0.5f;assert(actual==referenceHalf(v));}
  for(unsigned y=0;y<2;++y)for(unsigned c=24;c<32;++c)assert(out[y*32+c]==0xcc);++count;
 }
 const GLenum packed[]={GL_UNSIGNED_SHORT_5_6_5,GL_UNSIGNED_SHORT_4_4_4_4,GL_UNSIGNED_SHORT_5_5_5_1,GL_UNSIGNED_SHORT_1_5_5_5_REV,GL_UNSIGNED_INT_8_8_8_8,GL_UNSIGNED_INT_8_8_8_8_REV};
 for(auto t:packed){voq_float_source src;GLenum f=t==GL_UNSIGNED_SHORT_5_6_5?GL_RGB:GL_BGRA;assert(voq_float_source_init(&src,f,t,1,1,0,1)==0);uint32_t v=~0u;uint16_t out[4];voq_float_rows((uint8_t*)out,8,&v,1,1,&src);for(auto x:out)assert(x==0x3c00);}
 voq_float_source bad;assert(voq_float_source_init(&bad,GL_RGBA,GL_UNSIGNED_BYTE,1,1,-1,4)==GL_INVALID_VALUE);assert(voq_float_source_init(&bad,GL_RGBA,GL_UNSIGNED_BYTE,1,1,0,3)==GL_INVALID_VALUE);assert(voq_float_source_init(&bad,GL_RGBA,GL_UNSIGNED_SHORT_5_6_5,1,1,0,4)==GL_INVALID_OPERATION);
 printf("PASS %u format/type combinations, unaligned source, row padding, six packed encodings, validation\n",count);
}
static void capture(){
 texture t;const int w=960,h=544;std::vector<uint8_t>bytes(w*h*4);for(size_t i=0;i<bytes.size();++i)bytes[i]=i%256;
 _glTexImage2D_FlatIMPL(&t,0,GL_RGBA16F,w,h,GL_RGBA,GL_UNSIGNED_BYTE,bytes.data());assert(!vgl_error&&!legacyRoutes);
 for(unsigned y=0;y<(unsigned)h;++y)for(unsigned x=0;x<(unsigned)w;++x)for(unsigned c=0;c<4;++c)assert(halfAt(t,0,x,y,c)==referenceHalf(bytes[(y*w+x)*4+c]/255.0f));
 std::fill(bytes.begin(),bytes.end(),255);assert(voq_float_subimage(&t,GL_TEXTURE_2D,0,0,0,w,h,GL_RGBA,GL_UNSIGNED_BYTE,bytes.data(),0,4)==0);
 assert(halfAt(t,0,0,0,3)==0x3c00&&halfAt(t,0,w-1,h-1,0)==0x3c00);cleanup(t);
 puts("PASS exact 960x544 byte allocation -> half storage and SubImage; no null converter or 8-byte source overread");
}
static void storage(){
 texture t;t.use_mips=true;std::vector<uint8_t>bytes(9*5*4,128);assert(!voq_float_image(&t,0,9,5,GL_RGBA,GL_UNSIGNED_BYTE,bytes.data(),0,4));
 std::vector<uint16_t>mip(4*2*4,0x4400);assert(!voq_float_image(&t,1,4,2,GL_RGBA,GL_HALF_FLOAT,mip.data(),0,4));assert(t.mip_count==2);assert(halfAt(t,0,8,4,0)==referenceHalf(128.0f/255));assert(halfAt(t,1,3,1,0)==0x4400);
 void*old=t.data;size_t n=gpu[old];std::vector<uint8_t>saved((uint8_t*)old,(uint8_t*)old+n);t.last_frame=vgl_framecount;gpuFail=true;
 assert(voq_float_subimage(&t,GL_TEXTURE_2D,1,1,1,1,1,GL_RGBA,GL_HALF_FLOAT,mip.data(),0,4)==GL_OUT_OF_MEMORY);assert(t.data==old&&memcmp(old,saved.data(),n)==0&&retired.empty());gpuFail=false;
 uint16_t pixel[]={0x3c00,0,0xc000,0x3c00};assert(!voq_float_subimage(&t,GL_TEXTURE_2D,1,1,1,1,1,GL_RGBA,GL_HALF_FLOAT,pixel,0,4));assert(t.data!=old&&retired.size()==1&&memcmp(old,saved.data(),n)==0);assert(halfAt(t,1,1,1,2)==0xc000&&halfAt(t,1,0,0,2)==0x4400);assert(t.gxm_tex.levels==2);
 auto allocationsBefore=allocations;old=t.data;assert(voq_float_subimage(&t,GL_TEXTURE_2D,1,4,0,1,1,GL_RGBA,GL_UNSIGNED_BYTE,bytes.data(),0,4)==GL_INVALID_VALUE);assert(voq_float_subimage(&t,GL_TEXTURE_2D,0,0,0,0,0,GL_RGBA,GL_UNSIGNED_BYTE,nullptr,0,4)==0);assert(allocations==allocationsBefore&&t.data==old);
 gpuFail=true;assert(voq_float_image(&t,0,4,4,GL_RGBA,GL_FLOAT,nullptr,0,4)==GL_OUT_OF_MEMORY);assert(t.data==old&&t.gxm_tex.width==9);gpuFail=false;cleanup(t);
 puts("PASS NPOT mip repacking, per-level update, untouched mip data, busy COW, failures leave old storage intact");
}
static void mips(){
 texture t;float values[8*4*4];for(unsigned y=0;y<4;++y)for(unsigned x=0;x<8;++x){auto p=values+(y*8+x)*4;p[0]=x*4;p[1]=-4;p[2]=2;p[3]=1;}
 assert(!voq_float_image(&t,0,8,4,GL_RGBA,GL_FLOAT,values,0,4));t.last_frame=vgl_framecount;auto old=t.data;assert(!voq_float_generate(&t));assert(t.mip_count==4&&retired[0]==old);assert(halfAt(t,1,0,0,0)==referenceHalf(2));assert(halfAt(t,3,0,0,0)==referenceHalf(14));assert(halfAt(t,3,0,0,1)==referenceHalf(-4));cleanup(t);
 puts("PASS floating-component mip averages and COW; HDR/negative values preserved through final 1x1");
}
static unsigned expectedRow(unsigned j){
#ifdef HAVE_UNFLIPPED_FBOS
 return 1-j;
#else
 return j;
#endif
}
static void readback(){
 texture t;float values[3*2*4];for(unsigned i=0;i<6;++i){values[i*4]=i;values[i*4+1]=-2;values[i*4+2]=0.5;values[i*4+3]=1;}
 assert(!voq_float_image(&t,0,3,2,GL_RGBA,GL_FLOAT,values,0,4));framebuffer fb{&t,t.data,64,3,2,SCE_GXM_TEXTURE_FORMAT_F16F16F16F16_RGBA};active_read_fb=in_use_framebuffer=&fb;
 float out[24];assert(!voq_float_read_pixels(0,0,3,2,GL_RGBA,GL_FLOAT,out));assert(syncs==2&&dirty_framebuffer);
 for(unsigned j=0;j<2;++j)for(unsigned x=0;x<3;++x){unsigned i=j*3+x;assert(out[i*4]==float(expectedRow(j)*3+x)&&out[i*4+1]==-2&&out[i*4+2]==0.5);}
 uint8_t bytes[24];assert(!voq_float_read_pixels(0,0,3,2,GL_RGBA,GL_UNSIGNED_BYTE,bytes));for(unsigned i=0;i<6;++i)assert(bytes[i*4+1]==0&&bytes[i*4+2]==128&&bytes[i*4+3]==255);
 uint16_t half[24];assert(!voq_float_read_pixels(0,0,3,2,GL_RGBA,GL_HALF_FLOAT,half));for(unsigned j=0;j<2;++j)for(unsigned x=0;x<3;++x)for(unsigned c=0;c<4;++c)assert(half[(j*3+x)*4+c]==halfAt(t,0,x,expectedRow(j),c));
 assert(voq_float_read_pixels(0,0,-1,2,GL_RGBA,GL_FLOAT,out)==GL_INVALID_VALUE);assert(voq_float_read_pixels(0,0,3,2,GL_RGBA,GL_RGBA16F,out)==GL_INVALID_ENUM);assert(!voq_float_read_pixels(-5,-5,1,1,GL_RGBA,GL_FLOAT,out));for(unsigned i=0;i<4;++i)assert(out[i]==0);active_read_fb=in_use_framebuffer=nullptr;cleanup(t);
 puts("PASS F16 framebuffer eight-byte stride, RGBA/FLOAT/HALF/UBYTE, clipped reads, native FBO orientation");
}
static void copies(){
 texture_units[0].tex_id[0]=1;for(unsigned y=0;y<2;++y)for(unsigned x=0;x<3;++x){auto p=displayPixels+y*16+x*4;p[0]=y*120+x*20;p[1]=64;p[2]=128;p[3]=255;}
 unpack_row_len=19;voq_unpack_alignment=8;glCopyTexImage2D(GL_TEXTURE_2D,0,GL_RGBA16F,0,0,3,2,0);assert(!vgl_error&&observedReadType==GL_UNSIGNED_BYTE&&unpack_row_len==19&&voq_unpack_alignment==8&&clients.empty());
 for(unsigned y=0;y<2;++y)for(unsigned x=0;x<3;++x)assert(halfAt(texture_slots[1],0,x,y,0)==referenceHalf(displayPixels[(1-y)*16+x*4]/255.0f));
 glCopyTextureImage2D(2,0,GL_RGBA16F,0,0,3,2,0);assert(!vgl_error&&clients.empty());
 glCopyTextureSubImage2D(2,0,0,0,0,0,3,2);glCopyTexSubImage2D(GL_TEXTURE_2D,0,0,0,0,0,3,2);assert(!vgl_error&&clients.empty());
 // A framebuffer CopyTex update is ordered after the draws which sampled the
 // destination. The production path must synchronize those draws and update
 // the existing allocation, not COW an entire fullscreen F16 texture per frame.
 auto stable=texture_slots[1].data;const unsigned stableAllocations=allocations;
 for(unsigned frame=0;frame<32;++frame){
  texture_slots[1].last_frame=vgl_framecount;const unsigned syncBefore=syncs;
  glCopyTexSubImage2D(GL_TEXTURE_2D,0,0,0,0,0,3,2);assert(!vgl_error);
  assert(texture_slots[1].data==stable&&allocations==stableAllocations&&retired.empty());
  assert(texture_slots[1].last_frame==OBJ_NOT_USED&&syncs==syncBefore+4);++vgl_framecount;
 }
 auto old=texture_slots[1].data;readFail=true;glCopyTexSubImage2D(GL_TEXTURE_2D,0,0,0,0,0,3,2);assert(vgl_error==GL_INVALID_OPERATION&&texture_slots[1].data==old&&clients.empty());readFail=false;vgl_error=0;
 clientFail=true;glCopyTexImage2D(GL_TEXTURE_2D,0,GL_RGBA16F,0,0,3,2,0);assert(vgl_error==GL_OUT_OF_MEMORY&&texture_slots[1].data==old);clientFail=false;vgl_error=0;
 // Float source -> float destination must retain HDR, not quantize through U8.
 float hdr[24];for(unsigned i=0;i<24;++i)hdr[i]=i%4==3?1.0f:3.5f;
 assert(!voq_float_image(&texture_slots[2],0,3,2,GL_RGBA,GL_FLOAT,hdr,0,4));framebuffers[0]={&texture_slots[2],texture_slots[2].data,64,3,2,SCE_GXM_TEXTURE_FORMAT_F16F16F16F16_RGBA};active_read_fb=in_use_framebuffer=&framebuffers[0];
 glCopyTexSubImage2D(GL_TEXTURE_2D,0,0,0,0,0,3,2);assert(!vgl_error&&observedReadType==GL_HALF_FLOAT&&halfAt(texture_slots[1],0,0,0,0)==referenceHalf(3.5));
 // Aliased read source survives until the snapshot has been consumed.
 glCopyTextureImage2D(2,0,GL_RGBA16F,0,0,3,2,0);assert(!vgl_error&&halfAt(texture_slots[2],0,1,1,0)==referenceHalf(3.5));
 assert(framebuffers[0].data==texture_slots[2].data);
 glCopyTexSubImage2D(GL_TEXTURE_2D,0,0,0,0,0,3,2);assert(!vgl_error&&halfAt(texture_slots[1],0,1,1,0)==referenceHalf(3.5));
 active_read_fb=in_use_framebuffer=nullptr;framebuffers[0].tex=nullptr;
 vgl_error=GL_INVALID_ENUM;glCopyTexSubImage2D(GL_TEXTURE_2D,0,0,0,0,0,3,2);assert(vgl_error==GL_INVALID_ENUM&&clients.empty());vgl_error=0;
 assert(unpack_row_len==19&&voq_unpack_alignment==8);cleanup(texture_slots[1]);cleanup(texture_slots[2]);
 puts("PASS four CopyTex/DSA APIs, U8 and F16 precision, ordered busy-destination reuse, self copy, allocation/read failure");
}
int main(int argc,char**argv){assert(argc==2);std::string mode=argv[1];if(mode=="codec")codec();else if(mode=="formats")formats();else if(mode=="capture")capture();else if(mode=="storage")storage();else if(mode=="mips")mips();else if(mode=="read")readback();else if(mode=="copy")copies();else return 2;assert(gpu.empty()&&clients.empty()&&retired.empty());}
