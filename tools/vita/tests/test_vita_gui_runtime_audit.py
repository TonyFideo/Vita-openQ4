"""Execute the production observers with mock platform/GL entrypoints.

No claim of executing GXM: these tests prove forwarding, bounded observations,
state restoration and allocation-free failure reporting control flow.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


def block(path, begin, end):
    return path.read_text().split(begin, 1)[1].split(end, 1)[0]


def execute(source):
    cc = shutil.which('c++')
    if not cc:
        raise RuntimeError('a native C++ compiler is required')
    with tempfile.TemporaryDirectory(prefix='voq-audit-') as directory:
        path = Path(directory)
        (path/'test.cpp').write_text(source)
        result = subprocess.run([cc, '-std=c++17', '-Wall', '-Wextra', '-Werror',
                                 str(path/'test.cpp'), '-o', str(path/'test')],
                                text=True, capture_output=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        result = subprocess.run([str(path/'test')], text=True, capture_output=True)
        if result.returncode:
            raise AssertionError(result.stdout + result.stderr)
        return result.stdout


class RuntimeAuditTest(unittest.TestCase):
    def test_real_allocation_wrapper_control_flow(self):
        code = block(ROOT/'src/sys/vita/vita_main.cpp',
                     '// BEGIN VITA ALLOCATION AUDIT', '// END VITA ALLOCATION AUDIT')
        prelude = r'''
#include <stddef.h>
#include <stdint.h>
#include <errno.h>
#include <cstdio>
#include <cstdarg>
#include <cstring>
#include <cassert>
#include <string>
#define VITA_OPENQ4_WRITABLE_ROOT "root"
#define SCE_O_WRONLY 1
#define SCE_O_CREAT 2
#define SCE_O_APPEND 4
using SceUID=int;
struct mallinfo { int arena,uordblks,fordblks,keepcost; };
static struct mallinfo mallinfo() { return {1000,600,400,200}; }
struct SceKernelFreeMemorySizeInfo { size_t size; unsigned size_user,size_phycont,size_cdram; };
static bool fail=false, recurse=false;
static unsigned allocations=0, frees=0, reports=0, written=0;
static size_t lastCount=0,lastSize=0,lastAlignment=0;
static void *lastPointer=nullptr;
static char token;
extern "C" void *__wrap_malloc(size_t);
static int sceKernelGetFreeMemorySize(SceKernelFreeMemorySizeInfo *p) {
    p->size_user=10; p->size_phycont=0;p->size_cdram=112;
    if(recurse) { recurse=false; assert(__wrap_malloc(99)==nullptr); }
    return 0;
}
static bool VitaRuntimeAudit_GpuFree(size_t p[3]) {p[0]=11;p[1]=0;p[2]=22;return true;}
static int sceClibSnprintf(char *p,size_t n,const char*f,...) {
    va_list a;va_start(a,f);int r=vsnprintf(p,n,f,a);va_end(a);return r;
}
static std::string lastReport;
static int sceClibPrintf(const char*,const char *p) {lastReport=p; ++reports;return 0;}
static int sceIoOpen(const char*,int,int){return 3;}
static int sceIoWrite(int,const char*,size_t n){++written;return n>7?7:(int)n;}
static int sceIoClose(int){return 0;}
static void *reserve(size_t c,size_t s) {++allocations;lastCount=c;lastSize=s;errno=ENOMEM;return fail?nullptr:&token;}
extern "C" void *__real_malloc(size_t s){return reserve(1,s);}
extern "C" void *__real_calloc(size_t c,size_t s){return reserve(c,s);}
extern "C" void *__real_realloc(void*p,size_t s){lastPointer=p;return reserve(1,s);}
extern "C" void *__real_memalign(size_t a,size_t s){lastAlignment=a;return reserve(1,s);}
'''
        checks = r'''
int main() {
    assert(__wrap_malloc(11)==&token && allocations==1 && lastSize==11);
    assert(errno==ENOMEM && reports==0);
    assert(__wrap_calloc(3,19)==&token && lastCount==3 && lastSize==19);
    assert(__wrap_memalign(64,128)==&token && lastAlignment==64);
    fail=true;
    assert(__wrap_realloc(&token,1234)==nullptr && lastPointer==&token && frees==0);
    assert(errno==ENOMEM && reports==1 && written>1);
    assert(lastReport.find("heapFree=400")!=std::string::npos);
    assert(lastReport.find("size=1234")!=std::string::npos);
    unsigned old=reports;
    __wrap_malloc(0);__wrap_realloc(&token,0);__wrap_calloc(0,99);
    assert(reports==old);
    __wrap_calloc(2,SIZE_MAX);
    assert(reports==old+1 && lastReport.find("overflow=1")!=std::string::npos);
    old=reports;recurse=true;__wrap_malloc(77);
    assert(reports==old+1 && errno==ENOMEM);
    fail=false;old=reports;__wrap_malloc(1u<<25);
    assert(reports==old+1 && lastReport.find("allocation-traffic")!=std::string::npos);
    vitaAuditSnapshots=96;old=reports;
    __wrap_malloc(1u<<25);assert(reports==old);
    fail=true;__wrap_malloc(42);assert(reports==old+1);
    old=reports;
    VitaRuntimeAudit_Memory("load:player:begin",0,0,nullptr,false);
    assert(reports==old+1 && vitaAuditSnapshots==96);
    fail=false;old=reports;__wrap_malloc(1u<<25);assert(reports==old);

    puts("PASS allocation forwarding, sizes, overflow, zero-size, errno, recursion, bounded checkpoints");
}
'''
        print(execute(prelude+code+checks).strip())

    def test_real_clear_wrapper_and_read_state(self):
        code = block(ROOT/'src/sys/vita/vita_glimp.cpp',
                     '// BEGIN VITA CLEAR AUDIT','// END VITA CLEAR AUDIT')
        prelude = r'''
#include <stddef.h>
#include <stdint.h>
#include <cassert>
#include <cstdio>
#include <cstring>
using GLenum=unsigned;using GLbitfield=unsigned;using GLuint=unsigned;
using GLint=int;using GLboolean=unsigned char;using GLubyte=unsigned char;using GLfloat=float;
enum {GL_BACK=1,GL_FRONT,GL_READ_FRAMEBUFFER_BINDING,GL_READ_FRAMEBUFFER,GL_READ_BUFFER,
GL_RGBA,GL_UNSIGNED_BYTE,GL_FRAMEBUFFER_BINDING,GL_COLOR_WRITEMASK,GL_COLOR_CLEAR_VALUE,
GL_SCISSOR_BOX,GL_SCISSOR_TEST,GL_COLOR_BUFFER_BIT=0x4000,GL_FALSE=0};
enum {VGL_MEM_RAM,VGL_MEM_VRAM,VGL_MEM_PHYCONT};
static bool vitaGLReady=true;
static unsigned clearCalls=0,reads=0,queries=0;
static GLenum lastMask=0, readMode=GL_FRONT;
static GLint readFbo=13,drawFbo=0;
static uint64_t now=1;
static bool statsAvailable=true;
extern "C" int voq_vgl_query_free_pools(size_t p[3]){if(!statsAvailable)return 0;for(int i=0;i<3;++i)p[i]=100+i;return 1;}
static uint64_t sceKernelGetProcessTimeWide(){return now;}
static void glGetIntegerv(GLenum e,GLint*p) {
    ++queries;
    if(e==GL_READ_FRAMEBUFFER_BINDING)*p=readFbo;
    else if(e==GL_FRAMEBUFFER_BINDING)*p=drawFbo;
    else if(e==GL_READ_BUFFER)*p=(GLint)readMode;
    else if(e==GL_SCISSOR_BOX){p[0]=3;p[1]=7;p[2]=10;p[3]=12;}
    else assert(false);
}
static void glBindFramebuffer(GLenum e,GLuint v){assert(e==GL_READ_FRAMEBUFFER);readFbo=v;}
static void glReadBuffer(GLenum e){assert(readFbo==0);readMode=e;}
static void glReadPixels(int x,int y,int w,int h,GLenum,GLenum,void*p) {
    assert(readFbo==0 && readMode==GL_BACK && w==1 && h==1);
    assert(x>=0 && x<960 && y>=0 && y<544);++reads;memset(p,123,4);
}
static void glGetBooleanv(GLenum,GLboolean*p){memset(p,1,4);}
static void glGetFloatv(GLenum,GLfloat*p){p[0]=p[1]=p[2]=0;p[3]=1;}
static GLboolean glIsEnabled(GLenum){return 1;}
static int sceClibPrintf(const char*,...){return 0;}
extern "C" void __real_glClear(GLbitfield m){++clearCalls;lastMask=m;}
'''
        checks=r'''
int main() {
    size_t gpu[3]={};assert(VitaRuntimeAudit_GpuFree(gpu)&&gpu[0]==100);
    vitaGLReady=false;assert(!VitaRuntimeAudit_GpuFree(gpu));vitaGLReady=true;
    statsAvailable=false;assert(!VitaRuntimeAudit_GpuFree(gpu));statsAvailable=true;
    __wrap_glClear(GL_COLOR_BUFFER_BIT);assert(clearCalls==1 && reads==0 && queries==0);
    VitaRuntimeAudit_Start();
    __wrap_glClear(0x100);assert(clearCalls==2 && lastMask==0x100 && queries==0);
    drawFbo=42;__wrap_glClear(GL_COLOR_BUFFER_BIT);assert(reads==0);drawFbo=0;
    for(unsigned i=0;i<12;++i) {
        const unsigned old=clearCalls;
        __wrap_glClear(GL_COLOR_BUFFER_BIT);
        assert(clearCalls==old+1 && lastMask==GL_COLOR_BUFFER_BIT);
        assert(readFbo==13 && readMode==GL_FRONT);
        VitaClearAuditBeforePresent();
        assert(readFbo==13 && readMode==GL_FRONT);
        const unsigned oldReads=reads;
        VitaClearAuditBeforePresent();assert(reads==oldReads);
        __wrap_glClear(GL_COLOR_BUFFER_BIT);assert(reads==oldReads); // 5-second interval
        now+=5000000;
    }
    assert(vitaClearAuditSamples==12 && reads==150);
    unsigned old=reads;__wrap_glClear(GL_COLOR_BUFFER_BIT);assert(reads==old);
    puts("PASS real clear forwarded once, 12 samples, five points, FBO and FRONT read selection restored");
}
'''
        print(execute(prelude+code+checks).strip())

    def test_dependency_read_buffer_query(self):
        source = os.environ.get('VOQ_VITAGL_SOURCE')
        if not source:
            self.skipTest('patched pinned VitaGL required')
        root = Path(source) / 'source'
        query = re.search(r'case GL_READ_BUFFER:\s*(.*?)\s*break;',
                          (root / 'get_info.c').read_text(), re.S)
        accessor = re.search(r'GLenum vgl_get_read_buffer\(void\) \{.*?\n\}',
                             (root / 'framebuffers.c').read_text(), re.S)
        declaration = re.search(r'GLenum vgl_get_read_buffer\(void\);',
                                (root / 'shared.h').read_text())
        self.assertIsNotNone(query)
        self.assertIsNotNone(accessor)
        self.assertIsNotNone(declaration)
        # A single translation unit hid build 247's illegal reference to the
        # static display_read_mode. Compile/link the real accessor and query
        # in separate C translation units with only the production prototype.
        cc = shutil.which('cc')
        if not cc:
            raise RuntimeError('a native C compiler is required')
        with tempfile.TemporaryDirectory(prefix='voq-read-query-') as directory:
            out = Path(directory)
            (out / 'shared.h').write_text(
                'typedef unsigned GLenum; typedef int GLint;\n'
                '#define GL_COLOR_ATTACHMENT0 7\n' + declaration[0] + '\n')
            (out / 'framebuffers.c').write_text(
                '#include "shared.h"\n'
                'static GLenum display_read_mode = 1;\n'
                'static void *active_read_fb = 0;\n' + accessor[0] + '\n'
                'void set_test_read_state(unsigned mode, int fbo) {\n'
                ' display_read_mode = mode; active_read_fb = fbo ? &display_read_mode : 0; }\n')
            (out / 'get_info.c').write_text(
                '#include "shared.h"\nvoid query_read(GLint *data) {\n' + query[1] + '\n}\n')
            (out / 'test.c').write_text(
                '#include <assert.h>\n#include <stdio.h>\n#include "shared.h"\n'
                'void set_test_read_state(unsigned, int); void query_read(GLint *);\n'
                'int main(void) { GLint value = 0;\n'
                'set_test_read_state(1,0); query_read(&value); assert(value==1);\n'
                'set_test_read_state(2,0); query_read(&value); assert(value==2);\n'
                'set_test_read_state(1,1); query_read(&value); assert(value==7);\n'
                'puts("PASS read-buffer query: private state, separate translation units, FRONT/BACK/FBO"); }\n')
            result = subprocess.run(
                [cc, '-std=c11', '-Wall', '-Wextra', '-Werror',
                 str(out / 'framebuffers.c'), str(out / 'get_info.c'),
                 str(out / 'test.c'), '-o', str(out / 'test')],
                text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            result = subprocess.run([str(out / 'test')], text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout.strip())

    def test_link_contract(self):
        import ast
        cross = (ROOT / 'tools/vita/meson-vita.ini').read_text()
        meson = (ROOT / 'meson.build').read_text()
        for name in ('malloc', 'calloc', 'realloc', 'memalign', 'glClear'):
            self.assertNotIn('--wrap=' + name, cross)
            self.assertEqual(meson.count('--wrap=' + name), 1)
        target = meson.split('  client_link_args = engine_link_args', 1)[1]
        target = target.split("  if host_system != 'vita'", 1)[0]
        self.assertTrue(target.lstrip().startswith("if host_system == 'vita'"))
        self.assertEqual(target.count('link_args: client_link_args,'), 3)
        flags = ast.literal_eval(re.search(
            r'client_link_args \+= (\[[^\n]+\])', target)[1])
        # Link a dependency probe with ordinary libc, then a target with the
        # exact production wrapping flags and definitions. This catches flags
        # escaping into the compiler checks, without a VitaSDK installation.
        for compiler in ('cc', 'c++'):
            cc = shutil.which(compiler)
            self.assertIsNotNone(cc, 'native C and C++ compilers are required')
            with tempfile.TemporaryDirectory(prefix='voq-link-scope-') as directory:
                out = Path(directory)
                probe = '#include <stdlib.h>\nint main(void) { void *p = calloc(2,7); free(p); return 0; }\n'
                (out / 'probe.c').write_text(probe)
                result = subprocess.run([cc, '-fno-builtin', str(out / 'probe.c'),
                    '-o', str(out / 'probe')], text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                (out / 'wrap.c').write_text("""
#include <stdlib.h>
#include <stddef.h>
#ifdef __cplusplus
extern "C" {
#endif
void *__real_malloc(size_t); void *__real_calloc(size_t,size_t);
void *__real_realloc(void*,size_t);
void *__wrap_malloc(size_t n) { return __real_malloc(n); }
void *__wrap_calloc(size_t n,size_t s) { return __real_calloc(n,s); }
void *__wrap_realloc(void *p,size_t n) { return __real_realloc(p,n); }
void *__wrap_memalign(size_t a,size_t n) { (void)a; return __real_malloc(n); }
void __wrap_glClear(unsigned m) { (void)m; }
#ifdef __cplusplus
}
#endif
""")
                result = subprocess.run([cc, '-fno-builtin', str(out / 'probe.c'),
                    str(out / 'wrap.c'), *flags, '-o', str(out / 'client')],
                    text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                result = subprocess.run([str(out / 'client')], text=True, capture_output=True)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__=='__main__': unittest.main()
