#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <stdexcept>
#include <string>
#include <vector>
using byte = unsigned char;
using int64 = int64_t;
using ID_TIME_T = int64_t;
template<class T> T Min(T a,T b) {return std::min(a,b);}
template<class T> T Max(T a,T b) {return std::max(a,b);}
static size_t live=0,peak=0,maxAlloc=0,limit=SIZE_MAX;
static std::map<void*,size_t> allocations;
static void *Mem_Alloc(size_t n) {
    if(n>limit) throw std::bad_alloc();
    auto p=malloc(n); assert(p);allocations[p]=n;live+=n;peak=std::max(peak,live);maxAlloc=std::max(maxAlloc,n);return p;
}
static void Mem_Free(void *p) {if(!p)return;assert(allocations.count(p));live-=allocations[p];allocations.erase(p);free(p);}
static void *R_StaticAlloc(size_t n) {return Mem_Alloc(n);}
namespace idMath { static float Pow(float a,float b){return powf(a,b);} static byte Ftob(float x){return (byte)std::clamp((int)x,0,255);} }
class idFile {
public:
    std::vector<byte> bytes;size_t pos=0;int partial=4096,failAfter=-1;
    int Read(void *out,int n) {
        if(failAfter>=0 && (int)pos>=failAfter)return -1;
        n=std::min(n,partial);n=std::min(n,(int)(bytes.size()-pos));
        memcpy(out,bytes.data()+pos,n);pos+=n;return n;
    }
    int Length() const {return (int)bytes.size();}
    ID_TIME_T Timestamp() const {return 42;}
};
template<class T> struct idTempArray {
    T *p; explicit idTempArray(int n):p((T*)Mem_Alloc(n*sizeof(T))){} ~idTempArray(){Mem_Free(p);} T *Ptr(){return p;}
};
enum cubeFiles_t { CF_2D,CF_NATIVE,CF_CAMERA };
struct idStr {std::string s;idStr(){}idStr(const char *p):s(p){}void operator+=(const char*p){s+=p;}const char *c_str()const{return s.c_str();}};
struct FakeFS {
    std::map<std::string,std::vector<byte>> files;int opened=0,closed=0;bool partial=false;
    idFile *OpenFileRead(const char *path){auto it=files.find(path);if(it==files.end())return nullptr;auto f=new idFile;f->bytes=it->second;if(partial)f->partial=7;++opened;return f;}
    void CloseFile(idFile*f){assert(f);delete f;++closed;}
} fs;
static FakeFS *fileSystem=&fs;
static bool replacement=false;
static bool R_ResolvePreferredDDSImageSource(const char*,idStr&,ID_TIME_T*,bool,bool*){return replacement;}
static int retailSuppressed = 0;
struct idSuppressRetailProgramDDS { idSuppressRetailProgramDDS() { ++retailSuppressed; } ~idSuppressRetailProgramDDS() { --retailSuppressed; } };
#include "CubeStream.h"
#include "cube_production.inc"

using GLenum=unsigned;using GLuint=unsigned;using GLsizei=int;using uint32=uint32_t;
enum {GL_NO_ERROR=0,GL_INVALID_OPERATION=1,GL_INVALID_ENUM=2,GL_INVALID_VALUE=3,GL_OUT_OF_MEMORY=4,GL_RGBA8=5,GL_RGBA=6,GL_UNSIGNED_BYTE=7};
enum {TEX_VALID=1,OBJ_NOT_USED=0xffffffffu,FRAME_PURGE_FREQ=3,SCE_GXM_TEXTURE_FORMAT_U8U8U8U8_ABGR=10,SCE_GXM_TEXTURE_ADDR_CLAMP=1};
using GLboolean=int;
static constexpr int GL_TRUE=1;
struct SceGxmTexture {void *data=nullptr;unsigned count=0,width=0;};
struct texture {
    unsigned last_frame=OBJ_NOT_USED,status=0,mip_count=0,faces_counter=0,format=0;
    uint8_t voq_cube_levels=0;uint16_t voq_cube_size=0;
    void *data=nullptr,*palette_data=nullptr,*voq_cube_base_view=nullptr;
    unsigned min_filter=0,mag_filter=0,mip_filter=0,lod_bias=0;bool overridden=false;
    SceGxmTexture gxm_tex;
};
static uint32_t vgl_framecount=100;static GLenum gl_error=0;static bool gpuFail=false;
static std::map<void*,size_t> gpu;
static std::vector<void*> retired;
#define SET_GL_ERROR(e) gl_error=e; return;
static void *gpu_alloc_mapped_for_gpu(size_t n){if(gpuFail)return nullptr;auto p=malloc(n+32);assert(p);memset((byte*)p+n,0xcc,32);gpu[p]=n;return p;}
static void vgl_free(void*p){if(!p)return;assert(gpu.count(p));for(int i=0;i<32;++i)assert(((byte*)p)[gpu[p]+i]==0xcc);gpu.erase(p);free(p);}
static void mark_as_dirty(void*p){retired.push_back(p);}
static void vgl_memcpy(void*d,const void*s,size_t n){memcpy(d,s,n);}
static void vgl_memset(void*d,int v,size_t n){memset(d,v,n);}
static void vglSetTexMipmapCount(SceGxmTexture*t,uint32_t n){t->count=n;}
static void sceGxmTextureSetData(SceGxmTexture*t,void*p){t->data=p;}
static void vglInitCubeTexture(SceGxmTexture*t,void*p,unsigned,int w,int,unsigned n){t->data=p;t->count=n;t->width=w;}
static void vglSetTexUMode(SceGxmTexture*,unsigned){}static void vglSetTexVMode(SceGxmTexture*,unsigned){}
static void vglSetTexMinFilter(SceGxmTexture*,unsigned){}static void vglSetTexMagFilter(SceGxmTexture*,unsigned){}
static void vglSetTexMipFilter(SceGxmTexture*,unsigned){}static void vglSetTexLodBias(SceGxmTexture*,unsigned){}
void voq_cube_release_view(texture*);
static void gpu_free_texture_data(texture*t){voq_cube_release_view(t);if(t->data){vgl_free(t->data);t->data=nullptr;}}
#include "cube_gpu.inc"
static const GLenum GL_TEXTURE_CUBE_MAP = 8;
#define THREAD_SAFE()
#define SET_GL_ERROR_WITH_VALUE(e, value) gl_error=e; return;
struct texture_unit { GLuint tex_id[3] = {}; };
static texture_unit texture_units[16];
static texture texture_slots[4];
static int server_texture_unit = 0;
#include "cube_api.inc"


static unsigned referenceIndex(int x,int y,int size){
    unsigned index=0;
    for(int half=size/2;half;half/=2) {
        index*=4;index+=(x>=half?2:0)+(y>=half?1:0);x%=half;y%=half;
    }return index;
}
static bool upload(void*p,int face,int level,int x,int y,int w,int h,const byte*data){
    return voq_cube_subimage((texture*)p,face,level,x,y,w,h,GL_RGBA,GL_UNSIGNED_BYTE,data,0)==GL_NO_ERROR;
}
static int levels(int size){int n=0;do{++n;size>>=1;}while(size);return n;}
static std::vector<byte> rgba(int size,int face,int bytes){
    std::vector<byte> result(size*size*4);uint32_t seed=0x12345678u+face;
    for(size_t i=0;i<result.size();i+=4){seed=seed*1664525u+1013904223u;
        for(int c=0;c<4;++c)result[i+c]=(byte)(seed>>(c*8));
        if(bytes==1)result[i+1]=result[i+2]=result[i];if(bytes!=4)result[i+3]=255;
    }return result;
}
static std::vector<byte> tga(const std::vector<byte>&image,int size,int bpp,int type,int flags){
    std::vector<byte> result(18+5);result[0]=5;result[2]=type;result[12]=size&255;result[13]=size>>8;
    result[14]=result[12];result[15]=result[13];result[16]=bpp*8;result[17]=flags;
    // Raw RLE packets cross row boundaries; repeated packets tested separately.
    int remaining=0;
    for(int row=0;row<size;++row)for(int col=0;col<size;++col){
        if(type>=10 && remaining==0){remaining=std::min(128,size*size-row*size-col);result.push_back((byte)(remaining-1));}
        int x=flags&0x10?size-1-col:col,y=flags&0x20?row:size-1-row;
        const byte*p=image.data()+4*(y*size+x);
        if(bpp==1)result.push_back(p[0]);else {result.push_back(p[2]);result.push_back(p[1]);result.push_back(p[0]);if(bpp==4)result.push_back(p[3]);}
        --remaining;
    }return result;
}
static std::vector<byte> orient(const std::vector<byte>&v,int size,int side,bool camera){
    std::vector<byte> out(v.size());
    for(int y=0;y<size;++y)for(int x=0;x<size;++x){
        int dx=x,dy=y;
        if(camera){switch(side){case 0:case 4:case 5:dx=y;dy=x;break;case 1:dx=size-1-y;dy=size-1-x;break;case 2:dy=size-1-y;break;case 3:dx=size-1-x;break;}}
        memcpy(out.data()+4*(dy*size+dx),v.data()+4*(y*size+x),4);
    }return out;
}
static const char *cameraNames[]={"_forward.tga","_back.tga","_left.tga","_right.tga","_up.tga","_down.tga"};
static const char *nativeNames[]={"_px.tga","_nx.tga","_py.tga","_ny.tga","_pz.tga","_nz.tga"};
static void fixtures(int size,int bpp,int type,int flags,bool camera){fs.files.clear();for(int side=0;side<6;++side)fs.files[std::string("sky")+(camera?cameraNames[side]:nativeNames[side])]=tga(rgba(size,side,bpp),size,bpp,type,flags);}
static void testParity(){
    unsigned cases=0;
    for(bool camera:{false,true})for(int size:{1,2,4,8,16,32,64})for(int flags:{0,0x10,0x20,0x30})
    for(int bpp:{1,3,4})for(bool rle:{false,true})for(bool gamma:{false,true}) {
        int type=(bpp==1?3:2)+(rle?8:0);fixtures(size,bpp,type,flags,camera);
        for(int skip=0;skip<levels(size);++skip){
            texture tex;int outputSize=size>>skip,n=levels(outputSize);
            assert(voq_cube_storage(&tex,n,GL_RGBA8,outputSize,outputSize)==GL_NO_ERROR);
            {idCubeImageStream stream;assert(stream.Open("sky",camera?CF_CAMERA:CF_NATIVE));
            assert(stream.Upload(skip,n,!gamma,gamma,upload,&tex));}
            size_t faceBytes=voq_cube_face_bytes(outputSize,n);
            for(int side=0;side<6;++side){
                auto expected=orient(rgba(size,side,bpp),size,side,camera);int w=size;
                for(int level=0;level<levels(size);++level){
                    if(level>=skip){
                        byte*stored=(byte*)tex.data+side*faceBytes+voq_cube_level_offset(outputSize,level-skip);
                        for(int y=0;y<w;++y)for(int x=0;x<w;++x)
                            assert(memcmp(stored+4*referenceIndex(x,y,w),expected.data()+4*(y*w+x),4)==0);
                    }
                    if(w>1){byte*next=(level<skip?!gamma:gamma)?R_MipMapWithGamma(expected.data(),w,w):R_MipMap(expected.data(),w,w);
                        expected.assign(next,next+(w*w));Mem_Free(next);w>>=1;}
                }
            }
            gpu_free_texture_data(&tex);assert(live==0 && gpu.empty());++cases;
        }
    }printf("PASS %u cube cases: six faces, all mips, origins, RGB/gray/RLE, gamma/downsize and GXM layout\n",cases);
}
static void testCorrupt(){
    fixtures(8,4,10,0,true);auto good=fs.files["sky_forward.tga"];
    for(size_t cut=0;cut<good.size();++cut){
        idFile file;file.bytes.assign(good.begin(),good.begin()+cut);tgaStreamHeader_t h{};
        if(R_TgaStreamHeader(&file,h)){idTgaStreamDecoder d(&file,h);byte row[8*4];bool ok=true;for(int i=0;i<8&&ok;++i)ok=d.ReadRow(row);assert(!ok || !d.Finished());}
    }
    for(int corrupt:{1,2,12,14,16,17}){idFile f;f.bytes=good;f.bytes[corrupt]=corrupt==17?0x40:0xff;tgaStreamHeader_t h{};assert(!R_TgaStreamHeader(&f,h) || corrupt==12 || corrupt==14);}
    idFile f;f.bytes=tga(rgba(4,0,3),4,3,10,0);f.bytes.resize(27);f.bytes[23]=0xff; // packet exceeds remaining image
    tgaStreamHeader_t h{};assert(R_TgaStreamHeader(&f,h));idTgaStreamDecoder d(&f,h);byte row[16];assert(!d.ReadRow(row));
    // A repeated packet legitimately spans rows.
    f.pos=0;f.bytes.resize(27);f.bytes[23]=0x8f;f.bytes[24]=3;f.bytes[25]=2;f.bytes[26]=1;
    assert(R_TgaStreamHeader(&f,h));idTgaStreamDecoder repeated(&f,h);for(int i=0;i<4;++i){assert(repeated.ReadRow(row));for(int j=0;j<4;++j)assert(row[4*j]==1&&row[4*j+3]==255);}assert(repeated.Finished());
    fixtures(8,4,2,0,true);fs.files.erase("sky_down.tga");int before=fs.opened-fs.closed;{idCubeImageStream stream;assert(!stream.Open("sky",CF_CAMERA));}assert(fs.opened-fs.closed==before);
    fixtures(8,4,2,0,true);fs.partial=true;{idCubeImageStream stream;assert(stream.Open("sky",CF_CAMERA));texture tex;assert(!voq_cube_storage(&tex,4,GL_RGBA8,8,8));assert(stream.Upload(0,4,false,false,upload,&tex));gpu_free_texture_data(&tex);}fs.partial=false;
    replacement=true;{idCubeImageStream stream;assert(!stream.Open("sky",CF_CAMERA));}replacement=false;
    assert(fs.opened==fs.closed && live==0 && gpu.empty());puts("PASS truncated/invalid TGA, RLE boundaries, partial reads, source replacement and close ownership");
}
static void testGpu(){
    texture t;assert(voq_cube_storage(&t,5,GL_RGBA8,16,16)==0);assert(voq_cube_face_bytes(16,5)==2048);
    auto v=rgba(16,0,4);assert(!voq_cube_subimage(&t,5,0,0,0,16,16,GL_RGBA,GL_UNSIGNED_BYTE,v.data(),0));
    assert(voq_cube_storage(&t,1,GL_RGBA8,8,8)==GL_INVALID_OPERATION);
    void *old=t.data;t.last_frame=vgl_framecount;gpuFail=true;
    assert(voq_cube_subimage(&t,5,0,0,0,16,16,GL_RGBA,GL_UNSIGNED_BYTE,v.data(),0)==GL_OUT_OF_MEMORY && t.data==old);
    gpuFail=false;assert(!voq_cube_subimage(&t,5,0,0,0,16,16,GL_RGBA,GL_UNSIGNED_BYTE,v.data(),0));assert(t.data!=old && retired.size()==1);
    voq_set_texture_mip_count(&t,0);assert(t.gxm_tex.count==0 && t.gxm_tex.data==t.voq_cube_base_view);
    byte *base=(byte*)t.gxm_tex.data+5*16*16*4;
    for(int y=0;y<16;++y)for(int x=0;x<16;++x)assert(memcmp(base+4*referenceIndex(x,y,16),v.data()+4*(16*y+x),4)==0);
    void*view=t.voq_cube_base_view;voq_set_texture_mip_count(&t,5);assert(t.gxm_tex.data==t.data&&t.gxm_tex.count==5);
    t.last_frame=vgl_framecount;assert(!voq_cube_subimage(&t,5,4,0,0,1,1,GL_RGBA,GL_UNSIGNED_BYTE,v.data(),0));assert(!t.voq_cube_base_view);assert(std::find(retired.begin(),retired.end(),view)!=retired.end());
    for(auto p:retired)vgl_free(p);retired.clear();
    assert(voq_cube_subimage(&t,6,0,0,0,1,1,GL_RGBA,GL_UNSIGNED_BYTE,v.data(),0)==GL_INVALID_VALUE);
    assert(voq_cube_subimage(&t,0,5,0,0,1,1,GL_RGBA,GL_UNSIGNED_BYTE,v.data(),0)==GL_INVALID_VALUE);
    assert(voq_cube_subimage(&t,0,0,16,0,1,1,GL_RGBA,GL_UNSIGNED_BYTE,v.data(),0)==GL_INVALID_VALUE);
    gpu_free_texture_data(&t);assert(gpu.empty());
    for(int size:{1,2,4,8,16,32,1024}){texture one;assert(!voq_cube_storage(&one,1,GL_RGBA8,size,size));voq_set_texture_mip_count(&one,1);assert(one.gxm_tex.count==0&&one.gxm_tex.data==one.data&&!one.voq_cube_base_view);gpu_free_texture_data(&one);}
    texture fail;gpuFail=true;assert(voq_cube_storage(&fail,4,GL_RGBA8,8,8)==GL_OUT_OF_MEMORY&&fail.data==nullptr);gpuFail=false;
    assert(voq_cube_storage(&fail,4,GL_RGBA8,7,7)==GL_INVALID_VALUE);
    puts("PASS GPU storage: alignment, single-level and mipped views, immutable rejection, COW, failure rollback and bounds");
}
static void testBounded(){
    fixtures(1024,3,2,0,true);texture tex;assert(!voq_cube_storage(&tex,11,GL_RGBA8,1024,1024));
    live=peak=maxAlloc=0;limit=64*1024;
    {idCubeImageStream stream;assert(stream.Open("sky",CF_CAMERA));assert(stream.Upload(0,11,false,false,upload,&tex));}
    assert(live==0 && peak<64*1024 && maxAlloc<=4096 && fs.opened==fs.closed);
    printf("PASS 1024-square RGB sky: 6 faces, 11 levels, peak tracked CPU staging=%zu, largest=%zu (file/GPU allocations excluded)\n",peak,maxAlloc);
    gpu_free_texture_data(&tex);limit=SIZE_MAX;
}
static void generationTest() {
    gl_error = 0;
    glTexStorage2D(0,3,GL_RGBA8,4,4);assert(gl_error==GL_INVALID_ENUM);
    glTexStorage2D(GL_TEXTURE_CUBE_MAP,3,GL_RGBA8,4,4);assert(gl_error==GL_INVALID_OPERATION);
    texture_units[0].tex_id[2]=1;
    gl_error=0;glTexStorage2D(GL_TEXTURE_CUBE_MAP,3,GL_RGBA8,4,4);assert(gl_error==0);
    texture &tex=texture_slots[1];
    for(int face=0;face<6;++face) {
        auto pixels=rgba(4,face,4);
        assert(voq_cube_subimage(&tex,face,0,0,0,4,4,GL_RGBA,GL_UNSIGNED_BYTE,pixels.data(),0)==GL_NO_ERROR);
    }
    void *old=tex.data; tex.last_frame=vgl_framecount; gpuFail=true;
    assert(voq_cube_generate(&tex)==GL_OUT_OF_MEMORY && tex.data==old);gpuFail=false;
    assert(voq_cube_generate(&tex)==GL_NO_ERROR && tex.data!=old);
    for(int face=0;face<6;++face) {
        auto source=rgba(4,face,4);int w=4;
        for(int level=1;level<3;++level) {
            byte *lower=R_MipMap(source.data(),w,w);w/=2;
            const byte *base=(byte*)tex.data+face*voq_cube_face_bytes(4,3)+voq_cube_level_offset(4,level);
            for(int y=0;y<w;++y)for(int x=0;x<w;++x)
                assert(!memcmp(base+4*referenceIndex(x,y,w),lower+4*(y*w+x),4));
            source.assign(lower,lower+w*w*4);Mem_Free(lower);
        }
    }
    gpu_free_texture_data(&tex); tex=texture{};
    for(void *p:retired)vgl_free(p);retired.clear();assert(gpu.empty());
    puts("PASS immutable public allocation API and in-place mip generation with COW rollback");
}
int main(int argc,char**argv){assert(argc==2);std::string mode=argv[1];if(mode=="parity")testParity();else if(mode=="corrupt")testCorrupt();else if(mode=="gpu"){testGpu();generationTest();}else if(mode=="bounded")testBounded();else return 2;return 0;}
