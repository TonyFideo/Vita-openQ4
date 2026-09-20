"""Execute generated BC allocator with GXM/allocator mocked, not a Vita3K run."""
from pathlib import Path
import importlib.util
import os
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('bc_patch', ROOT / 'patch_vitagl_vita3k.py')
patch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patch)

HARNESS = r'''
#include <assert.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#define HAVE_VITA3K_SUPPORT 1
#define TEX_VALID 1
#define OBJ_NOT_USED 0xffffffffu
#define FRAME_PURGE_FREQ 4
#define GL_INVALID_VALUE 1
#define GL_INVALID_OPERATION 2
#define GL_OUT_OF_MEMORY 3
#define SET_GL_ERROR(e) { error_code = (e); return; }
enum { SCE_GXM_TEXTURE_FORMAT_UBC1_1BGR=1, SCE_GXM_TEXTURE_FORMAT_UBC1_ABGR,
       SCE_GXM_TEXTURE_FORMAT_UBC4_R, SCE_GXM_TEXTURE_FORMAT_UBC2_ABGR,
       SCE_GXM_TEXTURE_FORMAT_UBC3_ABGR, SCE_GXM_TEXTURE_FORMAT_UBC5_GR };
typedef unsigned SceGxmTextureFormat;
typedef struct { unsigned width,height,format; void *data; } Descriptor;
typedef struct {
    Descriptor gxm_tex;
    unsigned status,mip_count,last_frame,use_mips;
    void *data,*palette_data;
} texture;
static unsigned vgl_framecount = 100, allocations, swizzles;
static int error_code, fail_alloc;
static void *retired[64];
static unsigned retired_count;
static void *gpu_alloc_mapped_for_gpu(size_t n) {
    if (fail_alloc) return NULL;
    ++allocations;
    void *p=malloc(n); assert(p); return p;
}
static void gpu_free_texture_data(texture *t) {
    if (t->data) {
        if (t->last_frame != OBJ_NOT_USED && vgl_framecount-t->last_frame <= FRAME_PURGE_FREQ)
            retired[retired_count++] = t->data;
        else free(t->data);
    }
    t->data=NULL;
}
static void reap(void) { while(retired_count) free(retired[--retired_count]); }
static unsigned vglGetTexFormat(const Descriptor *d) { return d->format; }
static void vglGetTexSizes(const Descriptor *d,unsigned *w,unsigned *h) { *w=d->width;*h=d->height; }
static void vglInitSwizzledTexture(Descriptor *d,void *p,unsigned f,unsigned w,unsigned h,unsigned m) {
    (void)m; *d=(Descriptor){w,h,f,p};
}
#define vgl_memcpy memcpy
#define vgl_memset memset
/* Portable transcription of upstream's scalar twiddle-mask traversal. The
 * production path calls its existing NEON swizzler, not this test double. */
static void swizzle(unsigned b,uint8_t *dst,uint8_t *src,unsigned x,unsigned y,
                    unsigned w,unsigned h,unsigned stride,unsigned tile) {
    assert(x==0 && y==0 && tile && !(tile&(tile-1)));
    ++swizzles;
    uint32_t xm=0xaaaaaaaau | ~(tile*tile-1u), ym=0x55555555u | ~(tile*tile-1u);
    uint32_t xt=0,yt=0;
    for(unsigned iy=0;iy<h;iy++) {
        for(unsigned ix=0;ix<w;ix++) {
            memcpy(dst+(xt+yt)*b,src+(iy*stride+ix)*b,b);
            xt=(xt-xm)&xm;
        }
        xt=0;yt=(yt-ym)&ym;
    }
}
#define SwizzleTexData64Bpp(d,s,x,y,w,h,p,t) swizzle(8,d,s,x,y,w,h,p,t)
#define SwizzleTexData128Bpp(d,s,x,y,w,h,p,t) swizzle(16,d,s,x,y,w,h,p,t)
__UPLOAD__

static unsigned char datum(unsigned level,unsigned x,unsigned y,unsigned byte) {
    return (unsigned char)(level*61+x*29+y*37+byte*19+3);
}
static unsigned spread(unsigned v) {
    unsigned r=0;for(unsigned b=0;b<12;b++) r|=((v>>b)&1u)<<(2*b);return r;
}
static void verify(texture *t,const voq_bc_layout *l,unsigned bb) {
    for(unsigned m=0;m<t->mip_count;m++) {
        unsigned bw=(l->width[m]+3)/4,bh=(l->height[m]+3)/4;
        unsigned tile=l->blocks_w[m]<l->blocks_h[m]?l->blocks_w[m]:l->blocks_h[m];
        for(unsigned y=0;y<bh;y++) for(unsigned x=0;x<bw;x++) {
            unsigned idx=((y/tile)*(l->blocks_w[m]/tile)+x/tile)*tile*tile;
            idx+=2*spread(x%tile)+spread(y%tile);
            assert((size_t)idx*bb+bb<=l->bytes[m]);
            for(unsigned b=0;b<bb;b++)
                assert(((uint8_t*)t->data)[l->offset[m]+idx*bb+b]==datum(m,x,y,b));
        }
    }
}
static void upload(texture *t, unsigned m, const voq_bc_layout *l,unsigned fmt,unsigned bb) {
    unsigned bw=(l->width[m]+3)/4,bh=(l->height[m]+3)/4;
    size_t n=(size_t)bw*bh*bb;
    uint8_t *s=malloc(n),*copy=malloc(n);assert(s&&copy);
    for(unsigned y=0;y<bh;y++)for(unsigned x=0;x<bw;x++)for(unsigned b=0;b<bb;b++)
        s[(y*bw+x)*bb+b]=datum(m,x,y,b);
    memcpy(copy,s,n);error_code=0;
    voq_upload_native_bc(m,l->width[m],l->height[m],fmt,(uint32_t)n,s,t,bb);
    assert(error_code==0);assert(memcmp(copy,s,n)==0);free(s);free(copy);
}
static void run_case(unsigned w,unsigned h,unsigned fmt) {
    unsigned bb=voq_bc_block_bytes(fmt);assert(bb);
    voq_bc_layout l;assert(voq_bc_build_layout(w,h,bb,&l));
    texture t={0};t.last_frame=OBJ_NOT_USED;t.use_mips=1;
    unsigned before=allocations;
    fail_alloc=1;error_code=0;
    voq_upload_native_bc(0,w,h,fmt,0,NULL,&t,bb);
    assert(error_code==GL_OUT_OF_MEMORY && !t.data && t.status!=TEX_VALID);
    fail_alloc=0;
    for(unsigned m=0;m<l.count;m++) {
        void *old=t.data;unsigned oldcount=t.mip_count;
        if(m) {
            fail_alloc=1;error_code=0;
            voq_upload_native_bc(m,l.width[m],l.height[m],fmt,0,NULL,&t,bb);
            assert(error_code==GL_OUT_OF_MEMORY && t.data==old && t.mip_count==oldcount);
            verify(&t,&l,bb);fail_alloc=0;
        }
        upload(&t,m,&l,fmt,bb);verify(&t,&l,bb);
    }
    assert(allocations-before==l.count);
    /* Updating an idle existing mip must not allocate, wipe siblings or move. */
    before=allocations;void *old=t.data;
    unsigned m=l.count>1?1:0;
    if(m) {upload(&t,m,&l,fmt,bb);assert(old==t.data && allocations==before);verify(&t,&l,bb);}
    /* A sampled mip must keep old storage valid until retirement. */
    size_t n=l.offset[t.mip_count-1]+l.bytes[t.mip_count-1];
    uint8_t *snapshot=malloc(n);memcpy(snapshot,t.data,n);
    old=t.data;t.last_frame=vgl_framecount;
    fail_alloc=1;error_code=0;
    voq_upload_native_bc(m,l.width[m],l.height[m],fmt,0,NULL,&t,bb);
    assert(error_code==GL_OUT_OF_MEMORY && old==t.data && !retired_count);
    fail_alloc=0;upload(&t,m,&l,fmt,bb);
    assert(old!=t.data && retired_count==1);
    assert(memcmp(old,snapshot,n)==0);free(snapshot);reap();
    if(m)verify(&t,&l,bb);
    old=t.data;error_code=0;
    voq_upload_native_bc(l.count,1,1,fmt,bb,NULL,&t,bb);
    assert(error_code==GL_INVALID_VALUE && t.data==old);
    error_code=0;voq_upload_native_bc(0,w,h,fmt,1,"x",&t,bb);
    assert(error_code==GL_INVALID_VALUE && t.data==old);
    if(l.count>1) {
        error_code=0;voq_upload_native_bc(1,4096,4096,fmt,0,NULL,&t,bb);
        assert(error_code==GL_INVALID_VALUE && t.data==old);
    }
    t.last_frame=OBJ_NOT_USED;gpu_free_texture_data(&t);reap();
}
/* Minimal reproduction of the old async-copy + realloc ownership sequence.
 * Force movement, hold the DMA destination, then execute the pending write.
 * This models that sequence, not the Vita3K process or its crash stack. */
#if defined(__GNUC__) && !defined(__clang__) && __GNUC__ >= 12
#pragma GCC diagnostic push
#pragma GCC diagnostic ignored "-Wuse-after-free"
#endif
static __attribute__((noinline)) void legacy_async_repro(void) {
    uint8_t *tex=malloc(128),*pending=tex;
    uint8_t *grown=malloc(160);memcpy(grown,tex,128);free(tex);tex=grown;
    memset(pending,0x71,128);
    volatile uint8_t sink=pending[17];(void)sink;free(tex);
}
#if defined(__GNUC__) && !defined(__clang__) && __GNUC__ >= 12
#pragma GCC diagnostic pop
#endif
int main(int argc,char **argv) {
    if(argc>1 && strcmp(argv[1],"old")==0){legacy_async_repro();return 0;}
    unsigned cases=0;
    for(unsigned w=1;w<=65;w++)for(unsigned h=1;h<=33;h++)for(unsigned f=1;f<=6;f++) {
        run_case(w,h,f);++cases;
    }
    const unsigned dims[][2]={{1,4096},{4096,1},{960,544},{1024,8},{8,1024},{257,513}};
    for(unsigned d=0;d<sizeof(dims)/sizeof(dims[0]);d++)for(unsigned f=1;f<=6;f++) {
        run_case(dims[d][0],dims[d][1],f);++cases;
    }
    voq_bc_layout l;
    assert(!voq_bc_build_layout(0,1,8,&l));assert(!voq_bc_build_layout(1,0,8,&l));
    assert(!voq_bc_build_layout(4097,1,8,&l));assert(!voq_bc_build_layout(1,1,7,&l));
    assert(voq_bc_build_layout(4096,4096,16,&l) && l.count==13);
    assert(l.offset[l.count-1]+l.bytes[l.count-1]==l.capacity);
    printf("PASS %u shapes/formats: exact BC bytes, all mips, OOM rollback, COW and bounds\n",cases);
    return 0;
}
'''


class BCUploadTest(unittest.TestCase):
    def test_native_contract(self):
        cc = os.environ.get('HOST_CC') or shutil.which('clang') or shutil.which('cc')
        if not cc:
            self.skipTest('native compiler required')
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'voq_bc_layout.h').write_text(patch.BC_LAYOUT_HEADER)
            (root/'test.c').write_text(HARNESS.replace('__UPLOAD__',patch.BC_UPLOAD_CODE))
            cmd=[cc,'-std=c99','-O1','-g','-Wall','-Wextra','-Werror',str(root/'test.c'),'-o',str(root/'test')]
            sanitize=os.environ.get('VOQ_BC_SANITIZE')=='1'
            if sanitize:cmd+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
            built=subprocess.run(cmd,text=True,capture_output=True)
            self.assertEqual(built.returncode,0,built.stdout+built.stderr)
            run=subprocess.run([str(root/'test')],text=True,capture_output=True)
            self.assertEqual(run.returncode,0,run.stdout+run.stderr)
            print(run.stdout.strip())
            if sanitize:
                old=subprocess.run([str(root/'test'),'old'],text=True,capture_output=True)
                self.assertNotEqual(old.returncode,0)
                self.assertIn('heap-use-after-free',old.stderr)
                print('CONFIRMED: delayed-copy/relocation model fails with heap-use-after-free')

    def test_pinned_hook_and_idempotence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);p=root/'source/utils/gpu_utils.c';p.parent.mkdir(parents=True)
            p.write_text('void gpu_alloc_compressed_texture(int32_t mip_level, int x) { /* old body */ }\n')
            patch.patch_bc(root)
            s=p.read_text()
            self.assertEqual(s.count('void gpu_alloc_compressed_texture('),1)
            self.assertIn('if (!uncompressed && voq_block_bytes)',s)
            self.assertIn('/* old body */',s)
            with self.assertRaises(RuntimeError):patch.patch_bc(root)


if __name__=='__main__':unittest.main()
