"""Compile production DDS memoization and idBlockAlloc; simulate only VFS and strings.

The tracked string owns its name and detects relocation/deep copying. The real
idStr hash implementation and real idList/idHashIndex are compiled too so the
same harness can exercise a baseline source via VOQ_DDS_PROBE_SOURCE.
These tests do not execute target rendering or prove a map fits in memory.
"""
from pathlib import Path
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


def function(text, signature):
    a = text.index(signature)
    brace = text.index('{', a)
    depth = 1
    for i in range(brace + 1, len(text)):
        depth += (text[i] == '{') - (text[i] == '}')
        if depth == 0:
            return text[a:i + 1]
    raise AssertionError('unterminated: ' + signature)


PRELUDE = r'''
#include <algorithm>
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <limits>
#include <new>
#include <utility>
#define ID_INLINE inline
#define MEM_SCOPED_TAG(a,b) ((void)0)
template<class T>T Max(T a,T b){return std::max(a,b);}
using byte = unsigned char;
using ID_TIME_T = long;
static const ID_TIME_T FILE_NOT_FOUND_TIMESTAMP = -1;
static bool tracked = false;
static size_t ceiling = SIZE_MAX, live = 0, peak = 0, largest = 0, rejected = 0;
static unsigned copies = 0, names = 0;
union alignas(std::max_align_t) Allocation {struct { size_t size; bool tracked; } info; std::max_align_t align;};
void *operator new(size_t n) {
    if (tracked) { largest = std::max(largest,n); if(n>ceiling){rejected=n;throw std::bad_alloc();} }
    auto *h = static_cast<Allocation*>(std::malloc(sizeof(Allocation)+std::max(n,size_t(1))));
    if(!h) throw std::bad_alloc();
    h->info={n,tracked}; if(tracked){live+=n;peak=std::max(peak,live);} return h+1;
}
void operator delete(void *p) noexcept {if(!p)return;auto*h=static_cast<Allocation*>(p)-1;if(h->info.tracked)live-=h->info.size;std::free(h);}
void *operator new[](size_t n){return ::operator new(n);}
void operator delete[](void*p)noexcept{::operator delete(p);}
void operator delete(void*p,size_t)noexcept{::operator delete(p);}
void operator delete[](void*p,size_t)noexcept{::operator delete(p);}
struct idMath {
 static constexpr int INT_MAX = std::numeric_limits<int>::max();
 static bool IsPowerOfTwo(int n){return n>0 && !(n&(n-1));}
 static int CeilPowerOfTwo(int n){int p=1;while(p<n)p*=2;return p;}
 static int ClampInt(int a,int b,int n){return std::max(a,std::min(b,n));}
};
struct idVec3 {float v[3];float operator[](int i)const{return v[i];}};
class idStr {
 char *data=nullptr;
public:
 idStr()=default;
 ~idStr(){delete[]data;}
 idStr &operator=(const char *s){size_t n=std::strlen(s)+1;char*p=new char[n];std::memcpy(p,s,n);delete[]data;data=p;++names;return *this;}
 idStr &operator=(const idStr &s){++copies;return *this=s.c_str();}
 const char *c_str()const{return data?data:"";}
 size_t Allocated()const{return data?std::strlen(data)+1:0;}
 static byte ToLower(byte c){return c>='A'&&c<='Z'?c+('a'-'A'):c;}
 int Icmp(const char *s)const{const auto*a=(const byte*)c_str();const auto*b=(const byte*)s;for(;*a&&ToLower(*a)==ToLower(*b);++a,++b){}return int(ToLower(*a))-int(ToLower(*b));}
 static int IHash(const char*);
 static int Hash(const char *s){return IHash(s);}
};
struct ddsFileInfo_t {int format,dataOffset,fileSize,numLevels;uint32_t width,height;};
static unsigned probes=0, generation=1;
static bool R_ReadDDSFileInfoUncached(const char *name,ddsFileInfo_t &info,ID_TIME_T *time){
 ++probes;bool found=std::strstr(name,"missing")==nullptr && std::strstr(name,"MISSING")==nullptr;
 if(time)*time=found?100+generation:FILE_NOT_FOUND_TIMESTAMP;
 if(found) info={5,128,4096,4,generation,16};return found;
}
'''

CHECKS = r'''
static void begin(){R_SetDDSProbeCacheActive(false);assert(live==0);ceiling=SIZE_MAX;peak=largest=rejected=0;copies=names=probes=0;generation=1;tracked=true;R_SetDDSProbeCacheActive(true);}
static void end(){R_SetDDSProbeCacheActive(false);assert(live==0);tracked=false;}
static void semantics(){
 begin();ddsFileInfo_t a={},b={};ID_TIME_T t=0;
 assert(R_ReadDDSFileInfo("dds/tex/normal.dds",a,&t)&&t==101&&probes==1);
 assert(R_ReadDDSFileInfo("DDS/TEX/NORMAL.DDS",b,&t)&&t==101&&probes==1);
 assert(!std::memcmp(&a,&b,sizeof(a)));
 b={77,78,79,80,81,82};auto old=b;t=44;
 assert(!R_ReadDDSFileInfo("dds/missing.dds",b,&t)&&t==-1);
 assert(!std::memcmp(&old,&b,sizeof(b)));
 assert(!R_ReadDDSFileInfo("DDS/MISSING.DDS",b,nullptr)&&probes==2);
 assert(!std::memcmp(&old,&b,sizeof(b)));
 end();puts("PASS cached hits/misses, case fold, NULL timestamps and untouched failed output");
}
static void growth(){
 begin();ddsFileInfo_t info={};char name[128];
 for(int i=0;i<2304;++i){std::snprintf(name,sizeof(name),"dds/long_owned_name/texture_%05d.dds",i);assert(R_ReadDDSFileInfo(name,info,nullptr));}
 // Build 255 requested a relocated 2320-entry array (148480 + 8 bytes on ARM).
 // This ceiling is a test allocator fault, not a runtime memory/asset cap.
 ceiling=8192;largest=0;copies=0;
 for(int i=2304;i<6000;++i){std::snprintf(name,sizeof(name),"dds/long_owned_name/texture_%05d.dds",i);assert(R_ReadDDSFileInfo(name,info,nullptr));}
 assert(probes==6000&&copies==0&&largest<=8192);
 for(int i=0;i<6000;++i){std::snprintf(name,sizeof(name),"DDS/LONG_OWNED_NAME/TEXTURE_%05d.DDS",i);assert(R_ReadDDSFileInfo(name,info,nullptr));}
 assert(probes==6000&&copies==0);
 std::printf("PASS 6000 retained entries; largest growth allocation=%zu; no existing-key copies; peak=%zu\n",largest,peak);
 end();
}
static void collisions(){
 begin();int first[1024];std::fill_n(first,1024,-1);char a[80],b[80];bool collision=false;ddsFileInfo_t info={};
 for(int i=0;i<10000&&!collision;++i){std::snprintf(b,sizeof(b),"dds/collision_%d.dds",i);unsigned k=(unsigned)idStr::IHash(b)&1023;
 if(first[k]>=0){std::snprintf(a,sizeof(a),"dds/collision_%d.dds",first[k]);collision=true;break;}first[k]=i;}
 assert(collision&&std::strcmp(a,b));assert(R_ReadDDSFileInfo(a,info,nullptr));assert(R_ReadDDSFileInfo(b,info,nullptr));
 assert(probes==2);assert(R_ReadDDSFileInfo(a,info,nullptr));assert(R_ReadDDSFileInfo(b,info,nullptr));assert(probes==2);
 char longName[3072];std::memset(longName,'x',sizeof(longName));longName[sizeof(longName)-1]=0;
 assert(R_ReadDDSFileInfo(longName,info,nullptr));longName[sizeof(longName)-2]='y';assert(R_ReadDDSFileInfo(longName,info,nullptr));
 longName[sizeof(longName)-2]='x';assert(R_ReadDDSFileInfo(longName,info,nullptr));assert(probes==4);
 end();puts("PASS hash collisions and distinct full-length keys (no truncation)");
}
static void lifecycle(){
 begin();ddsFileInfo_t info={};ID_TIME_T t=0;
 for(int cycle=0;cycle<100;++cycle){
   assert(R_ReadDDSFileInfo("reload",info,&t)&&info.width==generation);
   unsigned calls=probes;++generation;assert(R_ReadDDSFileInfo("reload",info,&t)&&info.width==generation-1&&probes==calls);
   R_SetDDSProbeCacheActive(true);assert(live==0);
 }
 end();assert(R_ReadDDSFileInfo("reload",info,&t)&&info.width==generation);
 ++generation;assert(R_ReadDDSFileInfo("reload",info,&t)&&info.width==generation);
 assert(live==0);puts("PASS repeated begin/reset/end destruction and uncached hot reload");
}
static void failure(){
 begin();ddsFileInfo_t info={};char key[32];
 for(int i=0;i<32;++i){std::snprintf(key,sizeof(key),"old%d",i);assert(R_ReadDDSFileInfo(key,info,nullptr));}
 ceiling=1;bool threw=false;
 try{R_ReadDDSFileInfo("new-block",info,nullptr);}catch(const std::bad_alloc&){threw=true;}
 assert(threw);unsigned calls=probes;
 assert(R_ReadDDSFileInfo("old0",info,nullptr)&&probes==calls);
 ceiling=SIZE_MAX;assert(R_ReadDDSFileInfo("new-block",info,nullptr));end();
 puts("PASS failed block allocation preserves existing entries and clean shutdown");
}
int main(int argc,char**argv){
 assert(argc==2);
 try {
  if(!std::strcmp(argv[1],"semantics"))semantics();else if(!std::strcmp(argv[1],"growth"))growth();
  else if(!std::strcmp(argv[1],"collisions"))collisions();else if(!std::strcmp(argv[1],"lifecycle"))lifecycle();
  else if(!std::strcmp(argv[1],"failure"))failure();else return 4;
 }catch(const std::bad_alloc&){std::fprintf(stderr,"FAIL unexpected allocation %zu exceeds %zu-byte test ceiling\n",rejected,ceiling);ceiling=SIZE_MAX;R_SetDDSProbeCacheActive(false);tracked=false;return 3;}
}
'''


class DDSProbeCacheTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cc = shutil.which('c++')
        if cc is None:
            raise RuntimeError('native C++ compiler required')
        source = Path(os.environ.get('VOQ_DDS_PROBE_SOURCE', ROOT / 'src/imagetools/Image_files.cpp')).read_text()
        block = (ROOT / 'src/idlib/Heap.h').read_text()
        a = block.index('template<class type, int blockSize, byte memoryTag>\nclass idBlockAlloc')
        b = block.index('// RAVEN END', block.index('void idBlockAlloc<type,blockSize,memoryTag>::Shutdown', a))
        allocator = block[a:b]
        a = source.index('struct ddsProbeCacheEntry_t {')
        b = source.index('static bool R_ImageNameHasDDSShadowPrefix', a)
        cache = source[a:b]
        hashes = function((ROOT / 'src/idlib/Str.h').read_text(), 'ID_INLINE int idStr::IHash( const char *string )')
        hashcpp = (ROOT / 'src/idlib/containers/HashIndex.cpp').read_text()
        hashcpp = '\n'.join(l for l in hashcpp.splitlines() if not l.startswith('#include') and not l.startswith('#pragma'))
        cls.directory = tempfile.TemporaryDirectory(prefix='voq-dds-cache-')
        cls.addClassCleanup(cls.directory.cleanup)
        out = Path(cls.directory.name)
        prefix = PRELUDE + hashes + '\n#include "src/idlib/containers/List.h"\n#include "src/idlib/containers/HashIndex.h"\n'
        code = '\n'.join([prefix, hashcpp, allocator, cache, CHECKS])
        (out / 'test.cpp').write_text(code)
        cls.exe = out / 'test'
        command = [cc, '-std=c++17', '-Wall', '-Wextra', '-Werror', '-Wno-misleading-indentation', '-I', str(ROOT), str(out / 'test.cpp'), '-o', str(cls.exe)]
        if os.environ.get('VOQ_CACHE_SANITIZE'):
            command[1:1] = ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-g']
        build = subprocess.run(command, text=True, capture_output=True)
        if build.returncode:
            raise AssertionError(build.stdout + build.stderr)

    def run_case(self, name):
        result = subprocess.run([str(self.exe), name], text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        print(result.stdout.strip())

    def test_cached_results(self): self.run_case('semantics')
    def test_growth_without_relocation(self): self.run_case('growth')
    def test_collision_and_full_path_identity(self): self.run_case('collisions')
    def test_load_lifetime_and_hot_reload(self): self.run_case('lifecycle')
    def test_failed_block_allocation_preserves_cache(self): self.run_case('failure')


if __name__ == '__main__': unittest.main()
