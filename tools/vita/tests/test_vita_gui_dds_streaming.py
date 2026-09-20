"""Compile the actual DDS parser, binary image owner and transport routines.

Synthetic DDS files provide all authored bytes. Only VFS, containers and the
allocator are mocked; no game data, Vita runtime or GPU execution is claimed.
"""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


def function(text, signature):
    start = text.index(signature)
    opening = text.index('{', start)
    depth = 1
    for i in range(opening+1, len(text)):
        depth += (text[i] == '{') - (text[i] == '}')
        if depth == 0:
            return text[start:i+1]
    raise AssertionError(signature)


PRELUDE = r'''
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdlib>
#include <climits>
#include <string>
#include <vector>
#include <map>
using byte=unsigned char; using uint32=uint32_t; using int64=int64_t; using ID_TIME_T=long;
#define ID_INLINE inline
using textureFormat_t=int; using textureColor_t=int;
enum { FMT_NONE=0,FMT_DXT1,FMT_DXT5,FMT_BC7,FMT_RGBA8 };
enum { CFM_DEFAULT=0,CFM_NORMAL_DXT5=1,CFM_GREEN_ALPHA=4,TT_2D=1 };
enum textureUsage_t { TD_DEFAULT,TD_BUMP };
enum { FS_SEEK_SET,FS_SEEK_CUR };
static const int MAX_BINARY_IMAGE_DIMENSION=32768,MAX_BINARY_IMAGE_LEVELS=32,MAX_BINARY_IMAGE_DATA_SIZE=1<<30;
template<class T> T Max(T a,T b){return std::max(a,b);}
template<class T> T Min(T a,T b){return std::min(a,b);}
static int BitsForFormat(int f){return f==FMT_DXT1?4:f==FMT_RGBA8?32:8;}
static const ID_TIME_T FILE_NOT_FOUND_TIMESTAMP=-1;
class idStr {
 std::string s;
public:
 idStr(const char *p=""):s(p){} const char *c_str() const{return s.c_str();}
 char operator[](size_t i)const{return s[i];} int Length()const{return s.size();}
 void BackSlashesToSlashes(){std::replace(s.begin(),s.end(),'\\','/');}
 void ExtractFileExtension(idStr &out){auto p=s.find_last_of('.');out=p==s.npos?"":s.substr(p+1).c_str();}
 int Icmp(const char *p)const {std::string a=s,b=p;for(char &c:a)c=tolower(c);for(char &c:b)c=tolower(c);return a.compare(b);}
};
namespace idLib { static void Warning(const char *,...) {} }
template<class T> class idList {
 T *p=nullptr;int n=0;
public:
 ~idList(){Clear();} void Clear(){delete[]p;p=nullptr;n=0;}
 void SetNum(int size){T *q=new T[size];for(int i=0;i<std::min(n,size);++i)q[i]=p[i];delete[]p;p=q;n=size;}
 int Num()const{return n;} T *Ptr(){return p;} const T*Ptr()const{return p;}
 T &operator[](int i){assert(i>=0&&i<n);return p[i];} const T&operator[](int i)const{assert(i>=0&&i<n);return p[i];}
};
static std::map<void*,size_t> allocations;
static size_t live=0,peak=0,maximumRequest=0,allocationLimit=SIZE_MAX,allocationCalls=0;
static void *Mem_Alloc(size_t n){++allocationCalls;maximumRequest=std::max(maximumRequest,n);if(n>allocationLimit)return nullptr;void*p=malloc(n);assert(p);allocations[p]=n;live+=n;peak=std::max(peak,live);return p;}
static void Mem_Free(void*p){if(!p)return;assert(allocations.count(p));live-=allocations[p];allocations.erase(p);free(p);}
static void resetCounts(){assert(live==0);peak=maximumRequest=allocationCalls=0;allocationLimit=SIZE_MAX;}
struct Stats {int closed=0,forward=0,rewind=0;size_t read=0;};
class idFile {
public:
 std::vector<byte> bytes; int pos=0; Stats *stats; bool failSeek=false,failTell=false;int maxRead=INT_MAX,writeLimit=INT_MAX;
 idFile(std::vector<byte> b={},Stats*s=nullptr):bytes(std::move(b)),stats(s){}
 int Length(){return bytes.size();} int Tell(){return failTell?-1:pos;} ID_TIME_T Timestamp(){return 123;}
 int Read(void*p,int n){int got=std::min({n,(int)bytes.size()-pos,maxRead});if(got<0)return -1;memcpy(p,bytes.data()+pos,got);pos+=got;if(stats)stats->read+=got;return got;}
 int Seek(long n,int origin){if(failSeek)return -1;long next=origin==FS_SEEK_CUR?pos+n:n;if(next<0||next>(int)bytes.size())return -1;if(stats){if(origin==FS_SEEK_CUR)++stats->forward;else ++stats->rewind;}pos=next;return 0;}
 int Write(const void*p,int n){n=std::min(n,writeLimit);auto*b=(const byte*)p;bytes.insert(bytes.end(),b,b+n);return n;}
 template<class T> int WriteBig(T &v){return Write(&v,sizeof(v));}
};
struct FS {
 std::vector<byte> source;Stats stats;bool missing=false;int maxRead=INT_MAX;
 idFile* OpenFileRead(const char*){if(missing)return nullptr;auto*f=new idFile(source,&stats);f->maxRead=maxRead;return f;}
 void CloseFile(idFile*f){assert(f);if(f->stats)++f->stats->closed;delete f;}
} fs;
static FS *fileSystem=&fs;
struct Caps {bool textureCompressionAvailable=true,bptcTextureCompressionAvailable=true;} caps;
static const Caps&ImageTools_GetCompressionCaps(){return caps;}
'''

CHECKS = r'''
static std::vector<byte> dds(int w,int h,uint32 cc,int levels=32,bool dx10=false){
 int b=cc==R_MakeFourCC('D','X','T','1')?8:16;
 int actual=R_DDSMaxMipLevelsForSize(w,h);levels=std::min(levels,actual);
 std::vector<byte> out(dx10?148:128,0);
 R_WriteLittleUInt32(out.data(),R_MakeFourCC('D','D','S',' '));
 R_WriteLittleUInt32(out.data()+4,124);R_WriteLittleUInt32(out.data()+8,DDS_HEADER_FLAG_MIPMAPCOUNT);
 R_WriteLittleUInt32(out.data()+12,h);R_WriteLittleUInt32(out.data()+16,w);R_WriteLittleUInt32(out.data()+28,levels);
 R_WriteLittleUInt32(out.data()+76,32);R_WriteLittleUInt32(out.data()+80,DDS_PIXELFORMAT_FOURCC);
 R_WriteLittleUInt32(out.data()+84,cc);
 if(dx10){R_WriteLittleUInt32(out.data()+128,DDS_DXGI_FORMAT_BC7_UNORM);R_WriteLittleUInt32(out.data()+132,DDS_DX10_RESOURCE_DIMENSION_TEXTURE2D);R_WriteLittleUInt32(out.data()+140,1);}
 for(int i=0;i<levels;++i){size_t n=(size_t)((w+3)/4)*((h+3)/4)*b;for(size_t j=0;j<n;++j)out.push_back((byte)(j*37+i*19));w=std::max(1,w>>1);h=std::max(1,h>>1);}
 return out;
}
static void start(std::vector<byte> b){fs.source=std::move(b);fs.stats={};fs.missing=false;fs.maxRead=INT_MAX;caps={};resetCounts();}
static void verify(idBinaryImage &im,const std::vector<byte>&original,int first,int offset){
 int w=im.GetFileHeader().width,h=im.GetFileHeader().height;
 for(int i=0;i<im.NumImages();++i){const auto before=im.GetImageHeader(i);
  assert(before.level==i&&before.destZ==0&&before.width==w&&before.height==h);
  assert(im.ReadImageData(i));const byte*p=im.GetImageData(i);assert(p);
  assert(!memcmp(p,original.data()+offset,before.dataSize));
  assert(im.ReadImageData(i)&&im.GetImageData(i)==p);
  im.ReleaseImageData(i);if(im.IsFileBacked())assert(live==0&&im.GetImageData(i)==nullptr);
  assert(im.GetImageHeader(i).dataSize==before.dataSize);
  offset+=before.dataSize;w=std::max(1,w>>1);h=std::max(1,h>>1);
 }
 (void)first;
}
static void parity(){
 for(auto shape:std::vector<std::pair<int,int>>{{1,1},{2,3},{7,19},{128,32},{512,512},{1024,256}}){
  for(int fmt=0;fmt<4;++fmt){uint32 cc=fmt==0?R_MakeFourCC('D','X','T','1'):fmt==1?R_MakeFourCC('D','X','T','5'):fmt==2?R_MakeFourCC('R','X','G','B'):R_MakeFourCC('D','X','1','0');
   auto input=dds(shape.first,shape.second,cc,32,fmt==3);start(input);idBinaryImage im("test");ID_TIME_T time=0;
   assert(R_LoadPrecompressedDDS("test.dds",im,&time,TD_DEFAULT,{},true,true));assert(time==123&&im.IsFileBacked());
   assert(allocationCalls==0&&fs.stats.closed==0&&fs.stats.read==(size_t)(fmt==3?148:128));
   verify(im,input,0,fmt==3?148:128);assert(fs.stats.rewind==0&&fs.stats.forward==0&&fs.stats.read==input.size());
   assert(maximumRequest==(size_t)im.GetImageHeader(0).dataSize);
   idFile streamed;assert(im.WriteToFile(&streamed,123));assert(live==0);im.Clear();assert(fs.stats.closed==1);
   resetCounts();idBinaryImage buffered("test");assert(R_LoadPrecompressedDDS("test.dds",buffered,nullptr,TD_DEFAULT,{},true,false));assert(!buffered.IsFileBacked());
   const byte *old=buffered.GetImageData(0);buffered.ReleaseImageData(0);assert(old==buffered.GetImageData(0));
   idFile packed;assert(buffered.WriteToFile(&packed,123));assert(streamed.bytes==packed.bytes);buffered.Clear();assert(live==0);
  }
 }
}
static void selected(){
 auto in=dds(512,256,R_MakeFourCC('D','X','T','5'));in.insert(in.end(),10000,0xab);
 for(bool mips:{false,true})for(bool stream:{false,true}){
  start(in);idBinaryImage im("s");imageDownsizePolicy_t policy;policy.maxDimension=128;
  assert(R_LoadPrecompressedDDS("a.dds",im,nullptr,TD_BUMP,policy,mips,stream));
  int off=128+(512/4)*(256/4)*16+(256/4)*(128/4)*16;
  assert(im.GetFileHeader().width==128&&im.GetFileHeader().height==64&&im.GetFileHeader().colorFormat==CFM_NORMAL_DXT5);
  assert(im.NumImages()==(mips?8:1));verify(im,in,2,off);
  assert(fs.stats.forward==1&&fs.stats.rewind==0);im.Clear();assert(fs.stats.closed==1&&live==0);
 }
}
static void corrupt(){
 auto original=dds(64,32,R_MakeFourCC('D','X','T','1'));
 for(int kind=0;kind<9;++kind){auto in=original;
  if(kind==0)in.resize(10);if(kind==1)in[0]='?';if(kind==2)in.pop_back();
  if(kind==3)R_WriteLittleUInt32(in.data()+4,123);if(kind==4)R_WriteLittleUInt32(in.data()+16,0);
  if(kind==5)R_WriteLittleUInt32(in.data()+112,DDS_CAPS2_CUBEMAP);if(kind==6)R_WriteLittleUInt32(in.data()+84,R_MakeFourCC('?','?','?','?'));
  if(kind==7){R_WriteLittleUInt32(in.data()+84,R_MakeFourCC('D','X','1','0'));in.resize(140);}
  start(in);if(kind==8)fs.maxRead=64;idBinaryImage im("bad");assert(!R_LoadPrecompressedDDS("b.dds",im,nullptr,TD_DEFAULT,{},true,true));assert(allocationCalls==0&&fs.stats.closed==1);
 }
 start(original);caps.textureCompressionAvailable=false;idBinaryImage im("caps");assert(!R_LoadPrecompressedDDS("b.dds",im,nullptr,TD_DEFAULT,{},true,true));assert(allocationCalls==0&&fs.stats.closed==1);
 start(dds(16,16,R_MakeFourCC('D','X','1','0'),32,true));caps.bptcTextureCompressionAvailable=false;
 assert(!R_LoadPrecompressedDDS("b.dds",im,nullptr,TD_DEFAULT,{},true,true));assert(allocationCalls==0&&fs.stats.closed==1);
}
static void ownership(){
 start(dds(64,64,R_MakeFourCC('D','X','T','5')));idBinaryImage im("r");
 assert(R_LoadPrecompressedDDS("r.dds",im,nullptr,TD_DEFAULT,{},true,true));
 assert(!im.ReadImageData(-1)&&!im.ReadImageData(100));assert(im.ReadImageData(0));im.ReleaseImageData(0);
 assert(im.ReadImageData(0));assert(fs.stats.rewind==1);im.ReleaseImageData(0);
 idFile shortOutput;shortOutput.writeLimit=1024;assert(!im.WriteToFile(&shortOutput,0));assert(live==0);

 assert(R_LoadPrecompressedDDS("r.dds",im,nullptr,TD_DEFAULT,{},true,true));assert(fs.stats.closed==1);im.Clear();im.Clear();assert(fs.stats.closed==2&&live==0);
 int offsets[]={0},sizes[]={16};Stats stats;auto*f=new idFile(std::vector<byte>(16),&stats);
 assert(!im.Load2DFromCompressedFile(0,1,1,FMT_DXT5,CFM_DEFAULT,f,offsets,sizes));assert(stats.closed==0);
 assert(im.Load2DFromCompressedFile(1,1,1,FMT_DXT5,CFM_DEFAULT,f,offsets,sizes));
 assert(!im.Load2DFromCompressedFile(1,1,1,FMT_DXT5,CFM_DEFAULT,f,offsets,sizes));assert(!im.WriteToFile(f,0));
 f->maxRead=8;assert(!im.ReadImageData(0));assert(live==0&&im.GetImageHeader(0).dataSize==16);
 f->maxRead=INT_MAX;assert(im.ReadImageData(0));im.ReleaseImageData(0);
 f->failSeek=true;assert(!im.ReadImageData(0)&&live==0);f->failSeek=false;
 f->failTell=true;assert(!im.ReadImageData(0)&&live==0);f->failTell=false;
 allocationLimit=8;assert(!im.ReadImageData(0)&&live==0&&im.GetImageHeader(0).dataSize==16);
 im.Clear();assert(stats.closed==1&&live==0);
}
static void bounded(){
 auto in=dds(512,512,R_MakeFourCC('D','X','T','5'));start(in);allocationLimit=262144;
 idBinaryImage im("limit");assert(!R_LoadPrecompressedDDS("l.dds",im,nullptr,TD_DEFAULT,{},true,false));assert(fs.stats.closed==1);
 maximumRequest=peak=allocationCalls=0;
 assert(R_LoadPrecompressedDDS("l.dds",im,nullptr,TD_DEFAULT,{},true,true));assert(allocationCalls==0);
 verify(im,in,0,128);assert(peak==262144&&maximumRequest==262144);im.Clear();assert(live==0);
 puts("PASS: all 10 DXT5 levels preserved with 262144-byte peak payload staging instead of a whole DDS");
}
int main(int argc,char**argv){assert(argc==2);std::string which=argv[1];
 if(which=="parity")parity();else if(which=="selected")selected();else if(which=="corrupt")corrupt();else if(which=="ownership")ownership();else if(which=="bounded")bounded();else assert(false);
 assert(live==0);puts(("PASS DDS stream "+which).c_str());
}
'''


class DdsStreamingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc=shutil.which('c++')
        if not cc: raise RuntimeError('C++ compiler required')
        cls.temp=tempfile.TemporaryDirectory(prefix='voq-dds-stream-')
        out=Path(cls.temp.name)
        files=(ROOT/'src/imagetools/Image_files.cpp').read_text()
        binary=(ROOT/'src/imagetools/BinaryImage.cpp').read_text()
        process=(ROOT/'src/imagetools/Image_process.cpp').read_text()
        header=(ROOT/'src/renderer/Image.h').read_text()
        policy=header[header.index('struct imageDownsizePolicy_t {'):header.index('\n};',header.index('struct imageDownsizePolicy_t {'))+3]
        functions='\n'.join(function(binary,s) for s in (
            'static bool R_BinaryImageFormatIsBlockCompressed(', 'static int R_BinaryImageMinimumDataSize(',
            'void idBinaryImage::Clear(', 'void idBinaryImage::Load2DFromOwnedCompressedData(',
            'bool idBinaryImage::Load2DFromCompressedFile(', 'bool idBinaryImage::ReadImageData(',
            'void idBinaryImage::ReleaseImageData(', 'bool idBinaryImage::WriteToFile('))
        functions+='\n'+function(process,'void R_ApplyImageDownsizePolicy(')+'\n'+function(process,'int R_ImageDownsizePolicyMipSkip(')
        functions+='\n'+files[files.index('static ID_INLINE uint32 R_ReadLittleUInt32('):files.index('static bool R_ReadDDSFileInfoUncached(')]
        functions+='\n'+function(files,'bool R_LoadPrecompressedDDS(')
        code=PRELUDE+'\n'+policy+'\n#include "BinaryImage.h"\n'+functions+CHECKS
        (out/'test.cpp').write_text(code)
        cls.exe=out/'test'
        result=subprocess.run([cc,'-std=c++17','-Wall','-Wextra','-Werror','-Wno-misleading-indentation',
            '-I',str(ROOT/'src/imagetools'),str(out/'test.cpp'),'-o',str(cls.exe)],capture_output=True,text=True)
        if result.returncode: raise AssertionError(result.stdout+result.stderr)

    @classmethod
    def tearDownClass(cls): cls.temp.cleanup()

    def run_case(self,case):
        p=subprocess.run([str(self.exe),case],capture_output=True,text=True)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        print(p.stdout.strip())

    def test_authored_bytes_and_serialization_parity(self): self.run_case('parity')
    def test_selected_mips_and_forward_only_pk4_reads(self): self.run_case('selected')
    def test_header_rejection_precedes_payload_allocation(self): self.run_case('corrupt')
    def test_ownership_retry_and_io_failures(self): self.run_case('ownership')
    def test_peak_payload_is_one_mip_not_one_file(self): self.run_case('bounded')

    def test_renderer_consumes_before_releasing_and_aborts_io_failure(self):
        source=(ROOT/'src/renderer/Image_load.cpp').read_text()
        body=function(source,'void idImage::ActuallyLoadImage(')
        self.assertIn('precompressedDownsizePolicy, usePrecompressedMipmaps, true',body)
        read=body.index('if ( !im.ReadImageData( i ) )')
        get=body.index('im.GetImageData( i )',read)
        upload=body.index('SubImageUpload(',get)
        release=body.index('im.ReleaseImageData( i )',upload)
        self.assertLess(read,get);self.assertLess(get,upload);self.assertLess(upload,release)
        self.assertIn('PurgeImage();',body[read:get]);self.assertIn('common->Error(',body[read:get])
        self.assertIn('return;',body[read:get])
        source=(ROOT/'src/renderer/OpenGL/gl_Image.cpp').read_text()
        self.assertIn('#elif !defined(VITA) && !defined(__vita__)\n\t\t\t\tdata = malloc( compressedSize );',source)


if __name__=='__main__': unittest.main()
