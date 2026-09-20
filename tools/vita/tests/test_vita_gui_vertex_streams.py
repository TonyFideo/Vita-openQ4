"""Execute VitaGL's actual vertex-addressing code with the VitaSDK field widths.

No GPU emulation: the harness captures the stream pointers and uint16 offsets
passed to GXM by the pinned dependency, then checks the effective addresses.
Set VOQ_VITAGL_SOURCE to a source tree patched by patch_vitagl_vita3k.py.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


def function(text, signature):
    start = text.index(signature)
    begin = text.index('{', start)
    depth = 1
    for end in range(begin + 1, len(text)):
        depth += (text[end] == '{') - (text[end] == '}')
        if depth == 0:
            return text[start:end + 1]
    raise AssertionError('Unterminated function: ' + signature)


HEADER = r'''
#include <stdint.h>
#include <stddef.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#define VERTEX_ATTRIBS_NUM 8
#define GL_FALSE 0
#define GL_TRUE 1
typedef int GLboolean;
typedef int GLint;
typedef int GLsizei;
typedef unsigned SceGxmIndexSource;
typedef uint8_t SceGxmAttributeFormat;
/* VitaSDK psp2/gxm.h: offset and streamIndex are UINT16, not uintptr_t. */
typedef struct { uint16_t streamIndex,offset; uint8_t format,componentCount; uint16_t regIndex; } SceGxmVertexAttribute;
typedef struct { uint16_t stride,indexSource; } SceGxmVertexStream;
enum { SCE_GXM_ATTRIBUTE_FORMAT_F32=1, SCE_GXM_INDEX_SOURCE_INDEX_16BIT=0,
       SCE_GXM_INDEX_SOURCE_INSTANCE_16BIT=2, SCE_GXM_INDEX_FORMAT_U16=0 };
typedef struct { void *ptr; unsigned last_frame; } vbo;
typedef struct {
    unsigned vertex_attrib_state,vertex_attrib_divisor;
    uintptr_t vertex_attrib_vbo[8],vertex_attrib_offsets[8];
    unsigned vertex_attrib_size[8];
    SceGxmVertexAttribute vertex_attrib_config[8];
    SceGxmVertexStream vertex_stream_config[8];
    void *vertex_attrib_value[8];
} vao;
typedef struct {
    unsigned attr_num; uint8_t attr_map[8]; int has_unaligned_attrs;
    SceGxmVertexAttribute attr[8]; struct { int id; } *vshader; void *vprog;
} program;
static vao state, *cur_vao=&state;
static program prog;
static SceGxmVertexAttribute temp_attributes[8], submitted[8];
static SceGxmVertexStream temp_streams[8], submitted_streams[8];
static unsigned short orig_stride[8];
static SceGxmAttributeFormat orig_fmt[8];
static unsigned char orig_size[8];
static const uint8_t *submitted_ptrs[8];
static unsigned vgl_framecount=37, copies, draw_calls;
static void *gxm_context;
static unsigned char storage[5*1024*1024], other_storage[5*1024*1024];
static unsigned char temp_storage[8192];
static float constant_values[8][4];
static vbo buffer={storage,0}, other={other_storage,0};
#define vgl_memset memset
#define vgl_fast_memcpy memcpy
static void *gpu_alloc_mapped_temp(size_t n) { assert(n<=sizeof(temp_storage)); ++copies; return temp_storage; }
static void patch_vertex_program(int id, const SceGxmVertexAttribute *a, unsigned n,
                                 const SceGxmVertexStream *s, unsigned m, void **p) {
    (void)id;(void)m;(void)p;
    memcpy(submitted,a,n*sizeof(*a)); memcpy(submitted_streams,s,n*sizeof(*s));
}
static void sceGxmSetVertexProgram(void *c,void *p) {(void)c;(void)p;}
static void sceGxmSetVertexStream(void *c,int n,const void *p) {(void)c;submitted_ptrs[n]=p;}
static void sceGxmDraw(void *c,int p,int fmt,void *idx,int n) {
    (void)c;(void)p;(void)fmt;(void)idx;(void)n; ++draw_calls;
}
#define upload_uniforms() ((void)0)
'''

TAIL = r'''
static void configure(uintptr_t base, int mode) {
    memset(&state,0,sizeof(state)); memset(&prog,0,sizeof(prog));
    memset(submitted_ptrs,0,sizeof(submitted_ptrs));
    static struct { int id; } shader={1};
    prog.vshader=(void *)&shader;
    prog.attr_num=3;
    /* POSITION, COLOR, TEXCOORD as in GLES_D3; holes exercise attr_map. */
    prog.attr_map[0]=0; prog.attr_map[1]=1; prog.attr_map[2]=5;
    prog.has_unaligned_attrs=1;
    const unsigned relative[3]={0,12,56};
    for(unsigned i=0;i<3;++i) {
        unsigned a=prog.attr_map[i];
        state.vertex_attrib_state|=1u<<a;
        state.vertex_attrib_vbo[a]=(uintptr_t)&buffer;
        state.vertex_attrib_offsets[a]=base+relative[i];
        state.vertex_stream_config[a]=(SceGxmVertexStream){64,0};
        state.vertex_attrib_config[a]=(SceGxmVertexAttribute){a,0,1,4,a};
        state.vertex_attrib_size[a]=4;
        state.vertex_attrib_value[a]=constant_values[a];
        prog.attr[a].regIndex=a;
    }
    if(mode==1) { /* Separate colour stream, all VBOs still zero-copy. */
        state.vertex_attrib_vbo[1]=(uintptr_t)&other;
        state.vertex_stream_config[1].stride=4;
    } else if(mode==2) { /* Third attr outside a uint16 relative offset. */
        state.vertex_attrib_offsets[5]=base+0x10000;
    } else if(mode==3) { /* Third attribute before attr_map[0]. */
        state.vertex_attrib_offsets[5]=base>=128?base-128:0;
    } else if(mode==4) { /* Constant colour, not a GPU pointer. */
        state.vertex_attrib_state&=~(1u<<1);
    } else if(mode==5) { /* Same VBO, distinct per-attribute stride. */
        state.vertex_stream_config[5].stride=32;
    }
    copies=draw_calls=0; buffer.last_frame=other.last_frame=0;
}
static int verify(const char *path,uintptr_t base,int mode,unsigned first,unsigned index) {
    for(unsigned i=0;i<prog.attr_num;++i) {
        unsigned a=prog.attr_map[i];
        if(!(state.vertex_attrib_state&(1u<<a))) {
            if(strcmp(path,"multi")!=0 && submitted_ptrs[i]!=(const uint8_t *)constant_values[a]) return 2;
            continue;
        }
        vbo *b=(vbo *)state.vertex_attrib_vbo[a];
        const uint8_t *expected=(const uint8_t *)b->ptr+state.vertex_attrib_offsets[a]
            +(first+index)*state.vertex_stream_config[a].stride;
        const uint8_t *actual=submitted_ptrs[i]+submitted[i].offset+index*submitted_streams[i].stride;
        if(actual!=expected) {
            fprintf(stderr,"%s base=%zu mode=%d attr=%u: expected byte %zu, got %zu (GXM offset=%u)\n",
                    path,(size_t)base,mode,a,(size_t)((uintptr_t)expected-(uintptr_t)storage),(size_t)((uintptr_t)actual-(uintptr_t)storage),submitted[i].offset);
            return 1;
        }
    }
    assert(copies==0); assert(buffer.last_frame==vgl_framecount);
    return 0;
}
int main(int argc,char **argv) {
    if(argc!=4) return 4;
    const char *path=argv[1]; uintptr_t base=strtoul(argv[2],NULL,0); int mode=atoi(argv[3]);
    configure(base,mode);
    if(!strcmp(path,"elements")) {
        uint16_t idx[]={0,1,2}; run_elements(idx,3,0,0,0);
        return verify(path,base,mode,0,2);
    } else if(!strcmp(path,"arrays")) {
        run_arrays(3,3,GL_FALSE);
        return verify(path,base,mode,3,2);
    } else if(!strcmp(path,"multi")) {
        GLint first[]={3,8}; GLsizei count[]={3,3};
        run_multi(first,count,3,11,2);
        assert(draw_calls==2);
        return verify(path,base,mode,8,2);
    }
    return 3;
}
'''


def harness(text):
    # Keep the actual macros and actual three address-selection blocks, including
    # all pinned preprocessor branches. GXM submission is the only mocked edge.
    macros = text[text.index('#define disable_draw_attrib'):text.index('#ifndef HAVE_FFP_SHADER_SUPPORT')]
    align = re.search(r'#define align_attributes\(attributes, streams\).*?(?=\n\s*#ifdef HAVE_FFP_SHADER_SUPPORT)', text, re.S).group(0)
    output = HEADER + '\n' + macros + '\n' + align
    entries = [
        ('GLboolean _glDrawElements_CustomShadersIMPL(', 'static void run_elements(uint16_t *idx_buf, GLsizei count, uint32_t top_idx, uint32_t base_idx, SceGxmIndexSource index_type)', ''),
        ('GLboolean _glDrawArrays_CustomShadersIMPL(', 'static void run_arrays(GLint first, GLsizei count, GLboolean instanced)', ''),
        ('void _glMultiDrawArrays_CustomShadersIMPL(', 'static void run_multi(const GLint *first, const GLsizei *count, GLint lowest, GLsizei highest, GLsizei drawcount)', 'int gxm_p=0;void *idx_ptr=NULL;')]
    for sig, renamed, extra in entries:
        body = function(text, sig)
        address = body[body.index('// Aligning attributes'):body.rindex('#ifdef HAVE_PROFILING')]
        output += '\n'+renamed+' { program *p=&prog;'+extra+'\n'+address+'\n}\n'
    return output + TAIL


class VitaGuiVertexStreams(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root = os.environ.get('VOQ_VITAGL_SOURCE')
        if not root:
            if os.environ.get('VOQ_REQUIRE_GPU_TESTS') == '1':
                raise RuntimeError('VOQ_VITAGL_SOURCE is required in GUI CI')
            raise unittest.SkipTest('Set VOQ_VITAGL_SOURCE to the patched pinned VitaGL source')
        cc = shutil.which('cc')
        if not cc:
            raise RuntimeError('C compiler required for the GXM addressing regression')
        text = (Path(root)/'source/custom_shaders.c').read_text()
        (ROOT/'.tmp').mkdir(exist_ok=True)
        cls.temp = tempfile.TemporaryDirectory(dir=ROOT/'.tmp')
        source = Path(cls.temp.name)/'vertex_streams.c'
        source.write_text(harness(text))
        cls.exe = Path(cls.temp.name)/'vertex_streams'
        built = subprocess.run([cc,'-std=gnu11','-O1','-Wall','-Wextra',str(source),'-o',str(cls.exe)], text=True, capture_output=True)
        if built.returncode:
            raise RuntimeError(built.stderr)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def check(self,path,offset,mode=0):
        result = subprocess.run([str(self.exe),path,str(offset),str(mode)],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    def test_low_offsets_remain_correct(self):
        for path in ('elements','arrays','multi'):
            for offset in (0,64,4096,32768,65472):
                with self.subTest(path=path,offset=offset): self.check(path,offset)

    def test_ring_offsets_above_64k(self):
        for path in ('elements','arrays','multi'):
            for offset in (65536,65540,131072,262144,1048576,4194048):
                with self.subTest(path=path,offset=offset): self.check(path,offset)

    def test_crossing_64k_within_a_vertex(self):
        for path in ('elements','arrays','multi'):
            for offset in (65500,65520,65532):
                with self.subTest(path=path,offset=offset): self.check(path,offset)

    def test_mixed_layouts_preserve_each_address(self):
        for path in ('elements','arrays','multi'):
            for mode in (1,2,3,4,5):
                with self.subTest(path=path,mode=mode): self.check(path,131072,mode)


if __name__=='__main__':
    unittest.main()
