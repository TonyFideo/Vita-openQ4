"""Compile the actual pool transaction, budget arithmetic and image failure paths.

SDK/GXM services are simulated. These tests are not a target execution.
"""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('pool_patch', ROOT/'tools/vita/patch_vitagl_memory.py')
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)


def run_c(code, language='c'):
    compiler = shutil.which('cc' if language == 'c' else 'c++')
    if not compiler:
        raise RuntimeError('native C/C++ compiler required')
    with tempfile.TemporaryDirectory(prefix='voq-pools-') as directory:
        path = Path(directory)
        src = path/('test.'+language)
        src.write_text(code)
        flags = ['-std=c11' if language == 'c' else '-std=c++17', '-O1', '-g', '-Wall', '-Wextra', '-Werror']
        if os.getenv('VOQ_POOLS_SANITIZE') == '1':
            flags += ['-fsanitize=address,undefined', '-fno-omit-frame-pointer', '-fno-pie', '-no-pie']
        proc = subprocess.run([compiler, *flags, str(src), '-o', str(path/'test')], capture_output=True, text=True)
        if proc.returncode:
            raise AssertionError(proc.stdout+proc.stderr)
        proc = subprocess.run([str(path/'test')], capture_output=True, text=True)
        if proc.returncode:
            raise AssertionError(proc.stdout+proc.stderr)
        print(proc.stdout.strip())


def actual(source, token, fallback):
    root = os.environ.get('VOQ_VITAGL_SOURCE')
    if not root:
        raise RuntimeError('VOQ_VITAGL_SOURCE must point to the patched pinned source')
    text = (Path(root)/source).read_text()
    if fallback not in text:
        raise AssertionError('compiled implementation differs from applied patch: '+token)
    return fallback


PRELUDE = r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#define HAVE_VITA3K_SUPPORT 1
#define HAVE_WRAPPED_ALLOCATORS 1
#define GL_FALSE 0
#define GL_TRUE 1
typedef int GLboolean;
typedef int SceUID;
typedef int SceKernelMemBlockType;
typedef int SceGxmMultisampleMode;
enum { VGL_MEM_VRAM, VGL_MEM_RAM, VGL_MEM_PHYCONT, VGL_MEM_BUDGET, VGL_MEM_EXTERNAL, VGL_MEM_ALL };
enum { SCE_KERNEL_MEMBLOCK_TYPE_USER_CDRAM_RW=1, SCE_KERNEL_MEMBLOCK_TYPE_USER_RW,
 SCE_KERNEL_MEMBLOCK_TYPE_USER_RW_UNCACHE, SCE_KERNEL_MEMBLOCK_TYPE_USER_MAIN_PHYCONT_RW,
 SCE_KERNEL_MEMBLOCK_TYPE_USER_MAIN_PHYCONT_NC_RW, SCE_KERNEL_MEMBLOCK_TYPE_USER_MAIN_CDIALOG_RW,
 SCE_KERNEL_MEMBLOCK_TYPE_USER_MAIN_CDIALOG_NC_RW, SCE_GXM_MEMORY_ATTRIB_RW };
static int has_cached_mem, vgl_has_cdlg_support;
static void *mempool_addr[VGL_MEM_ALL], *mempool_end[VGL_MEM_ALL], *mempool_mspace[VGL_MEM_EXTERNAL];
static size_t mempool_size[VGL_MEM_ALL];
typedef struct { size_t size; void *mappedBase; size_t mappedSize; } SceKernelMemBlockInfo;
static unsigned char storage[5][16384];
static int operations, fail_at, blocks, mappings, spaces, dummy_live, logs;
static size_t allocated_sizes[4];
static int failure(void) { ++operations; return operations==fail_at; }
static int sceClibPrintf(const char *format, ...) { (void)format; ++logs; return 0; }
static SceUID sceKernelAllocMemBlock(const char *name, int type, size_t n, void *p) {
 (void)name;(void)type;(void)p;
 if(failure())return -42;
 allocated_sizes[blocks]=n;
 ++blocks;return 100+blocks-1;
}
static int sceKernelGetMemBlockBase(int id,void **out) {
 if(failure())return -43;
 *out=storage[id-100];return 0;
}
static int sceGxmMapMemory(void *p,size_t n,int a) {
 (void)n;(void)a;assert(p);
 if(failure())return -44;
 ++mappings;return 0;
}
static void *sceClibMspaceCreate(void *p,size_t n) {
 assert(p && n);if(failure())return NULL;
 ++spaces;return p;
}
static void sceClibMspaceDestroy(void *p) {assert(p); --spaces;}
static int sceGxmUnmapMemory(void *p) {assert(p);--mappings;return 0;}
static int sceKernelFreeMemBlock(int id) {assert(id>=100);--blocks;return 0;}
static void *__real_malloc(size_t n) {assert(n==1);if(failure())return NULL;dummy_live=1;return storage[4]+16;}
static void __real_free(void *p) {assert(p==storage[4]+16 && dummy_live);dummy_live=0;}
static int sceKernelGetMemBlockInfoByAddr(void *p,SceKernelMemBlockInfo *i) {
 assert(dummy_live && p==storage[4]+16 && i->size==sizeof(*i));
 if(failure())return -45;
 i->mappedBase=storage[4];i->mappedSize=sizeof(storage[4]);return 0;
}
'''

BUDGET = r'''
#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <limits.h>
#include <stdio.h>
#include <stdarg.h>
#define GL_FALSE 0
#define GL_TRUE 1
#define SCE_KERNEL_MAX_MAIN_CDIALOG_MEM_SIZE 0x8C6000
typedef int GLboolean; typedef int SceGxmMultisampleMode;
static int system_app_mode,queryResult,initCalls,budgetCalls,customCalls;
static size_t budget[3]={10*1024*1024,115343384,0};
static int requested[4];
typedef struct {size_t size,size_user,size_cdram,size_phycont;} SceKernelFreeMemorySizeInfo;
typedef struct {size_t size,free_user_rw;} SceAppMgrBudgetInfo;
static void init_gxm(void) {++initCalls;}
static int sceClibPrintf(const char *f,...) {(void)f;return 0;}
static int sceKernelGetFreeMemorySize(SceKernelFreeMemorySizeInfo *i) {
 assert(initCalls && i->size==sizeof(*i) && !i->size_user && !i->size_cdram);
 ++budgetCalls;if(queryResult<0)return queryResult;
 i->size_user=budget[0];i->size_cdram=budget[1];i->size_phycont=budget[2];return 0;
}
static int sceAppMgrGetBudgetInfo(SceAppMgrBudgetInfo *i) {
 assert(initCalls && i->size==sizeof(*i) && !i->free_user_rw);
 ++budgetCalls;if(queryResult<0)return queryResult;i->free_user_rw=budget[0];return 0;
}
static int vglInitWithCustomSizes(int pool,int w,int h,int ram,int vram,int phy,int dlg,int msaa) {
 assert(!pool && w==960 && h==544 && !msaa);++customCalls;
 requested[0]=ram;requested[1]=vram;requested[2]=phy;requested[3]=dlg;return 0;
}
'''


class MemoryPoolTests(unittest.TestCase):
    def test_budget_and_reservation_semantics(self):
        code = actual('source/vgl.c', 'threshold', patch.THRESHOLD_CODE)
        run_c(BUDGET + code + r'''
int main(void) {
 assert(voq_pool_size(115343384,0,262144)==115343360);
 assert(voq_pool_size(115343384,115343384,262144)==0); /* old client mistake */
 assert(voq_pool_size(123,123,4096)==0 && voq_pool_size(123,456,4096)==0);
 assert(voq_pool_size(SIZE_MAX,0,4096)==-1 && voq_pool_size(5000,-1,4096)==-1);
 assert(voq_pool_size(5000,0,0)==-1 && voq_pool_size(5000,0,3)==-1);
 assert(!voq_init_threshold(0,960,544,10485760,0,0,0x8C6000,0));
 assert(customCalls==1 && requested[0]==0 && requested[1]==115343360 && requested[2]==0 && requested[3]==0);
 int before=customCalls;queryResult=-1;
 voq_init_threshold(0,960,544,10485760,0,0,0x8C6000,0);assert(customCalls==before);
 queryResult=0;system_app_mode=1;budget[0]=123;
 voq_init_threshold(0,960,544,10485760,0,0,0x8C6000,0);
 assert(!requested[0] && !requested[1] && !requested[2] && !requested[3]);
 before=customCalls;voq_init_threshold(0,960,544,-1,0,0,0,0);assert(customCalls==before);
 puts("PASS reservation semantics, 110 MiB CDRAM plan, granules, errors and system-app budget");
}
''')

    def test_pool_transaction_failure_at_every_stage(self):
        code = actual('source/utils/mem_utils.c', 'pool init', patch.POOL_CODE)
        run_c(PRELUDE + code + r'''
int main(void) {
 for(int failurePoint=1;failurePoint<=19;++failurePoint) {
   operations=0;fail_at=failurePoint;
   assert(!voq_init_mspace_pools(4096,262144,1048576,4096));
   assert(!voq_vgl_memory_init_ok() && !blocks && !mappings && !spaces && !dummy_live);
   for(int i=0;i<VGL_MEM_ALL;++i) assert(!mempool_addr[i] && !mempool_end[i] && !mempool_size[i]);
 }
 operations=0;fail_at=0;has_cached_mem=1;
 assert(voq_init_mspace_pools(4096,262144,1048576,4096));
 assert(voq_vgl_memory_init_ok() && blocks==4 && mappings==5 && spaces==4 && !dummy_live);
 assert(!vgl_has_cdlg_support && mempool_size[VGL_MEM_VRAM]==262144);
 assert(mempool_addr[VGL_MEM_VRAM]==storage[0]);
 int before=operations;assert(voq_init_mspace_pools(0,0,0,0) && operations==before);
 puts("PASS 19 initialization failures roll back all ownership; publication only after mapping+mspace");
}
''')

    def test_zero_pools_overflow_and_alignment(self):
        code = actual('source/utils/mem_utils.c', 'pool init', patch.POOL_CODE)
        run_c(PRELUDE + code + r'''
int main(void) {
 assert(!voq_init_mspace_pools(SIZE_MAX,0,0,0));assert(!blocks && !mappings && !spaces);
 assert(voq_init_mspace_pools(1,1,0,0));
 assert(mempool_size[VGL_MEM_RAM]==4096 && mempool_size[VGL_MEM_VRAM]==262144);
 assert(!mempool_addr[VGL_MEM_PHYCONT] && !mempool_addr[VGL_MEM_BUDGET]);
 assert(blocks==2 && mappings==3 && spaces==2 && vgl_has_cdlg_support);
 puts("PASS empty banks, overflow rejection and alignment without fictitious pools");
}
''')

    def test_gpu_allocation_uses_cdram_and_matching_free(self):
        root = Path(os.environ['VOQ_VITAGL_SOURCE'])
        import sys
        sys.path.insert(0, str(ROOT / 'tools/vita'))
        from patch_vitagl_vita3k import function_span
        text = (root/'source/utils/mem_utils.c').read_text()
        functions = []
        for signature in ('vglMemType vgl_mem_get_type_by_addr(', 'void *vgl_memalign(', 'void vgl_free('):
            a,b = function_span(text, signature)
            functions.append(text[a:b])
        text = (root/'source/utils/gpu_utils.c').read_text()
        a,b = function_span(text, 'static inline __attribute__((always_inline)) void *gpu_alloc_mapped_aligned_for_gpu_inner(')
        functions.append(text[a:b])
        stubs = r'''
 typedef int vglMemType;
 static int use_extra_mem=1,textureFrees;
 static void *__real_memalign(size_t alignment,size_t bytes) {(void)alignment;(void)bytes;assert(!"unexpected CPU heap allocation");return NULL;}
 static void *sceClibMspaceMemalign(void *space,size_t alignment,size_t bytes) {
   assert(space==storage[0] && alignment==16 && bytes==1024);return storage[0]+4096;
 }
 static void sceClibMspaceFree(void *space,void *p) {assert(space==storage[0] && p==storage[0]+4096);++textureFrees;}
 #define vgl_alloc_attempt(alignment,size,type) res=vgl_memalign(alignment,size,type); if(res) return res;
'''
        checks = r'''
 int main(void) {
  assert(voq_init_mspace_pools(0,262144,0,0));
  void *p=gpu_alloc_mapped_aligned_for_gpu_inner(16,1024);
  assert(p==storage[0]+4096 && vgl_mem_get_type_by_addr(p)==VGL_MEM_VRAM);
  vgl_free(p);assert(textureFrees==1);
  puts("PASS production GPU allocation selects mapped CDRAM and frees to the same mspace, not newlib");
 }
'''
        run_c(PRELUDE+patch.POOL_CODE+stubs+'\n'.join(functions)+checks)

    def test_context_does_not_start_after_pool_failure(self):
        root = Path(os.environ['VOQ_VITAGL_SOURCE'])
        code = (root/'source/vgl.c').read_text()
        after = code.split('vgl_mem_init(ram_pool_size, cdram_pool_size, phycont_pool_size, cdlg_pool_size);',1)[1]
        self.assertLess(after.index('if (!voq_vgl_memory_init_ok()) return GL_FALSE;'), after.index('init_gxm_context('))
        src = (ROOT/'src/sys/vita/vita_glimp.cpp').read_text()
        self.assertIn('const int cdramThreshold = 0;',src)
        self.assertNotIn('VitaGLimp_FreeCdramBytes',src)
        self.assertLess(src.index('if ( !voq_vgl_memory_init_ok() )'), src.index('vitaGLReady = rendererValid;'))

    def test_texture_failures_stop_and_release_before_reporting(self):
        source = (ROOT/'src/renderer/OpenGL/gl_Image.cpp').read_text()
        storage = source.split('// BEGIN VITA IMAGE STORAGE RESULT')[1].split('// END VITA IMAGE STORAGE RESULT')[0]
        src = (ROOT/'src/renderer/Image_load.cpp').read_text()
        upload = src.split('// BEGIN VITA IMAGE UPLOAD RESULT')[1].split('// END VITA IMAGE UPLOAD RESULT')[0]
        prelude = r'''
#include <cassert>
#include <cstdio>
using GLenum=unsigned;const GLenum GL_NO_ERROR=0;
static GLenum error=0;static int calls=0,purged=0,cleared=0,reported=0;
static bool uploading=false;
GLenum glGetError() {return error;}
void PurgeImage() {++purged;}
const char *GetName() {return "texture";}
struct Image {int level=3;} img;
struct Binary {void Clear(){++cleared;img.level=-1;}} im;
struct Common {void Error(const char*,...){assert(purged && (!uploading || cleared));++reported;}} console;
Common *common=&console;
'''
        code = prelude + '\nvoid storage_test() {\nfor(int side=0;side<6;++side) for(int level=0;level<10;++level) {++calls;\n'+storage+'\n}}\n'
        code += '\nvoid upload_test() {\nfor(int i=0;i<10;++i) {++calls;\n'+upload+'\n}}\n'
        code += r'''
int main(){storage_test();assert(calls==60 && !reported);calls=0;error=0x505;
 storage_test();assert(calls==1 && reported==1 && purged==1);
 calls=0;uploading=true;upload_test();assert(calls==1 && reported==2 && purged==2 && cleared==1);
 puts("PASS first failed level stops, texture purged, staging/file released before error handler");}
'''
        run_c(code,'cpp')


if __name__=='__main__': unittest.main()
