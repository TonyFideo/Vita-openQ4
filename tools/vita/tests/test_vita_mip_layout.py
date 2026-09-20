#!/usr/bin/env python3
"""Native memory regression for the exact generated VitaGL mip implementation.

GXM allocation/descriptor calls are mocked; no claim of emulator/game execution.
Run: python3 -m unittest discover -s tools/vita/tests -p 'test_vita_mip_layout.py' -v
Clang ASan/UBSan can be enabled with VOQ_MIP_SANITIZE=1.
"""
from __future__ import annotations
import importlib.util
import os
import pathlib
import shutil
import subprocess
import tempfile
import unittest

HERE = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("voq_mip_patch", HERE / "patch_vitagl_vita3k.py")
patch = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(patch)

HARNESS = r'''
#include <assert.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "layout.h"
#define HAVE_VITA3K_SUPPORT 1
#define TEX_VALID 1
#define OBJ_NOT_USED 0xffffffffu
#define FRAME_PURGE_FREQ 3
#define GL_INVALID_VALUE 1
#define GL_INVALID_OPERATION 2
#define GL_OUT_OF_MEMORY 3
#define VGL_ALIGN(x,a) (((x)+(a)-1)&~((a)-1))
static int error_code, fail_alloc;
static unsigned vgl_framecount;
#define SET_GL_ERROR(e) { error_code=(e); return; }
typedef unsigned SceGxmTextureFormat;
typedef struct { unsigned w,h,bpp; void *data; } descriptor;
typedef struct {
    descriptor gxm_tex; void *data; void *palette_data;
    unsigned mip_count, use_mips, status, last_frame;
} texture;
static unsigned vglGetTexFormat(const descriptor *d) { return d->bpp; }
static unsigned tex_format_to_bytespp(unsigned f) { return f; }
static void vglGetTexSizes(const descriptor *d, unsigned *w, unsigned *h) {
    *w=d->w; *h=d->h;
}
static void *gpu_alloc_mapped_for_gpu(size_t n) { return fail_alloc ? NULL : malloc(n); }
static void gpu_free_texture_data(texture *t) { free(t->data); }
#define vgl_memcpy memcpy
#define vgl_memset memset
#define sceClibMemcpy memcpy
static void vglInitLinearTexture(descriptor *d, void *p, unsigned f,
                                unsigned w, unsigned h, unsigned count) {
    (void)count; d->data=p; d->w=w; d->h=h; d->bpp=f;
}
__ALLOCATOR__

static unsigned char pixel(unsigned x, unsigned y, unsigned c) {
    return (unsigned char)(x*17+y*11+c*29);
}
static texture make_texture(unsigned w, unsigned h, unsigned bpp) {
    texture t={0};
    const unsigned stride=VGL_ALIGN(w,8)*bpp;
    t.data=malloc((size_t)stride*h); assert(t.data);
    memset(t.data,0xa5,(size_t)stride*h);
    t.gxm_tex=(descriptor){w,h,bpp,t.data};
    t.mip_count=t.use_mips=t.status=1; t.last_frame=OBJ_NOT_USED;
    for(unsigned y=0;y<h;y++) for(unsigned x=0;x<w;x++) for(unsigned c=0;c<bpp;c++)
        ((unsigned char *)t.data)[y*stride+x*bpp+c]=pixel(x,y,c);
    return t;
}
static void check_chain(texture *t, const vgl_vita3k_mip_layout *l) {
    for(unsigned i=0;i<t->mip_count;i++) {
        for(unsigned y=0;y<l->height[i];y++) for(unsigned x=0;x<l->width[i];x++) {
            for(unsigned c=0;c<t->gxm_tex.bpp;c++) {
                size_t pos=l->offset[i]+y*l->stride[i]+x*t->gxm_tex.bpp+c;
                assert(pos<l->size);
                assert(((unsigned char *)t->data)[pos]==pixel(x<<i,y<<i,c));
            }
        }
    }
}
static void check(unsigned w,unsigned h,unsigned bpp) {
    texture t=make_texture(w,h,bpp);
    vgl_vita3k_mip_layout l; assert(vgl_vita3k_build_mip_layout(w,h,bpp,1,&l));
    unsigned expected=1, edge=w>h?w:h; while(edge>1){edge>>=1;expected++;}
    assert(l.levels==expected);
    if(expected>1) {
        void *old=t.data;
        fail_alloc=1; error_code=0; gpu_alloc_mipmaps(1,&t);
        assert(error_code==GL_OUT_OF_MEMORY && t.data==old && t.mip_count==1);
        fail_alloc=0;
        for(unsigned i=1;i<expected;i++) {
            error_code=0; gpu_alloc_mipmaps((int)i,&t);
            assert(!error_code && t.mip_count==i+1); check_chain(&t,&l);
        }
        old=t.data; t.last_frame=vgl_framecount;
        fail_alloc=1; error_code=0; gpu_alloc_mipmaps(-1,&t);
        assert(error_code==GL_OUT_OF_MEMORY && t.data==old);
        fail_alloc=0; error_code=0; gpu_alloc_mipmaps(-1,&t);
        assert(!error_code && t.data!=old && t.mip_count==expected); check_chain(&t,&l);
        /* Authored subimage writes use precisely this shared row pitch/offset.
         * Exercise every last byte, especially after the short axis reaches 1.
         */
        for(unsigned i=0;i<l.levels;i++) for(unsigned y=0;y<l.height[i];y++)
            memset((unsigned char *)t.data+l.offset[i]+y*l.stride[i],0x37,l.width[i]*bpp);
    }
    error_code=0; gpu_alloc_mipmaps((int)l.levels,&t);
    assert(error_code==GL_INVALID_VALUE); free(t.data);
    t=make_texture(w,h,bpp); error_code=0; gpu_alloc_mipmaps(-1,&t);
    assert(!error_code && t.mip_count==expected);
    if(expected>1) check_chain(&t,&l);
    free(t.data);
}
/* Isolated transcription of the old allocation arithmetic (not the game).
 * 64x1 reserves only level 0, then OpenQ4's level-1 upload writes past it.
 */
static void legacy_repro(void) {
    unsigned w=64,h=1,bpp=4; size_t n=0;
    while(w>1 && h>1){n+=(w>8?w:8)*h*bpp; w/=2;h/=2;}
    n+=(w>8?w:8)*h*bpp;
    unsigned char *p=malloc(n);
    memset(p+64*4,0x42,32*4);
    volatile unsigned char observable=p[n+31]; (void)observable;
    free(p);
}
int main(int argc,char **argv) {
    if(argc>1 && strcmp(argv[1],"legacy")==0){legacy_repro();return 0;}
    const unsigned dims[][2]={{1,1},{1,2},{2,1},{64,1},{1,64},{128,8},{8,128},
        {64,16},{16,64},{128,128},{7,3},{13,9},{127,65},{960,544},{4096,1}};
    const unsigned bpps[]={1,2,3,4,8};
    unsigned count=0;
    for(unsigned d=0;d<sizeof(dims)/sizeof(dims[0]);d++)
        for(unsigned b=0;b<sizeof(bpps)/sizeof(bpps[0]);b++){
            check(dims[d][0],dims[d][1],bpps[b]);count++;
        }
    vgl_vita3k_mip_layout l;
    assert(!vgl_vita3k_build_mip_layout(0,1,4,1,&l));
    assert(!vgl_vita3k_build_mip_layout(1,0,4,1,&l));
    assert(!vgl_vita3k_build_mip_layout(4097,1,4,1,&l));
    assert(!vgl_vita3k_build_mip_layout(1,1,0,1,&l));
    assert(vgl_vita3k_build_mip_layout(4096,4096,16,1,&l));
    assert(l.levels==13 && l.width[12]==1 && l.height[12]==1);
    printf("PASS: %u texture shapes/formats, authored mips, generation, COW, OOM, bounds\n",count);
    return 0;
}
'''


class MipLayoutRegression(unittest.TestCase):
    def test_native_memory_contract(self):
        compiler = os.environ.get("HOST_CC") or shutil.which("clang") or shutil.which("cc")
        if not compiler:
            self.skipTest("a native C compiler is required")
        sanitize = os.environ.get("VOQ_MIP_SANITIZE") == "1"
        with tempfile.TemporaryDirectory(prefix="voq-mips-") as directory:
            root = pathlib.Path(directory)
            (root / "layout.h").write_text(patch.LAYOUT_HEADER, encoding="utf-8")
            allocator = patch.MIP_ALLOCATOR.replace("__ORIGINAL_BODY__", "")
            source = HARNESS.replace("__ALLOCATOR__", allocator)
            (root / "test.c").write_text(source, encoding="utf-8")
            command = [compiler, "-std=c99", "-O1", "-g", str(root / "test.c"), "-o", str(root / "test")]
            if sanitize:
                command += ["-fsanitize=address,undefined", "-fno-omit-frame-pointer"]
            subprocess.run(command, check=True, capture_output=True, text=True)
            result = subprocess.run([str(root / "test")], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            print(result.stdout.strip())
            if sanitize:
                old = subprocess.run([str(root / "test"), "legacy"], capture_output=True, text=True)
                self.assertNotEqual(old.returncode, 0, "old arithmetic unexpectedly passed")
                self.assertIn("heap-buffer-overflow", old.stderr)
                print("CONFIRMED: old 64x1 allocation/upload arithmetic fails AddressSanitizer")

    def test_patch_contract(self):
        # Patch against a real downloaded/pinned tree during CI when available.
        # The normal patcher itself verifies unique source anchors beforehand.
        root = os.environ.get("VITAGL_REPO")
        if not root:
            self.skipTest("set VITAGL_REPO to check patched dependency wiring")
        textures = (pathlib.Path(root) / "source/textures.c").read_text(encoding="utf-8")
        gpu = (pathlib.Path(root) / "source/utils/gpu_utils.c").read_text(encoding="utf-8")
        self.assertIn("mip_stride = voq_layout.stride[level]", textures)
        self.assertIn("size = voq_layout.size", textures)
        self.assertIn("(unsigned)level >= tex->mip_count", textures)
        self.assertIn("const unsigned requested = level < 0 ? layout.levels", gpu)
        self.assertIn("Vita3K's transfer-downscale HLE path", gpu)
        self.assertIn("w >= 8 && h >= 4 && aligned_width == w", gpu)


if __name__ == "__main__":
    unittest.main()
