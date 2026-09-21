"""Execute the production half codec, storage, readback and copy implementations.

GXM descriptors and allocators are simulated. Separate Mesa checks establish
pixel conversion semantics; neither is execution of the Vita GPU or gameplay.
"""
from pathlib import Path
import os
import re
import shutil
import subprocess
import tempfile
import unittest
import importlib.util

ROOT=Path(__file__).resolve().parents[3]

def function(text, signature):
    spec=importlib.util.spec_from_file_location('float_patch_util',ROOT/'tools/vita/patch_vitagl_vita3k_linear.py')
    util=importlib.util.module_from_spec(spec);spec.loader.exec_module(util)
    a,b=util.function_span(text,signature)
    return text[a:b]

def marked(text,begin,end):
    return text.split(begin,1)[1].split(end,1)[0]

class FloatTransferTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=os.environ.get('VOQ_VITAGL_SOURCE')
        if not root:raise RuntimeError('patched pinned VitaGL source required')
        cls.native=Path(root)/'source';cls.tmp=tempfile.TemporaryDirectory(prefix='voq-float-');out=Path(cls.tmp.name)
        (out/'utils').mkdir()
        for name in ('voq_float_codec.h','vita3k_mip_layout.h'):
            shutil.copy(cls.native/'utils'/name,out/'utils'/name)
        header=(cls.native/'vitaGL.h').read_text()
        (out/'gl_constants.h').write_text('\n'.join(line for line in header.splitlines() if re.match(r'#define GL_\w+\s+[^\\]+$',line)))
        textures=(cls.native/'textures.c').read_text();readback=(cls.native/'framebuffers.c').read_text()
        (out/'float_impl.inc').write_text(marked(textures,'/* BEGIN VOQ FLOAT TRANSFERS */','/* END VOQ FLOAT TRANSFERS */'))
        (out/'float_read.inc').write_text(marked(readback,'/* BEGIN VOQ FLOAT READBACK */','/* END VOQ FLOAT READBACK */'))
        callbacks=(cls.native/'texture_callbacks.c').read_text()
        cb='#define convert_u16_to_u32_cspace(color, lshift, rshift, mask) (((((color << lshift) >> rshift) & mask) * 0xFF) / mask)\n'
        for name in ('read_rgba8888','read_bgra8888','read_rgb888','read_r8','read_rg88','read_bgra4444','read_rgb565','read_rgba5551'):
            cb+=function(callbacks,'uint32_t '+name+'(')+'\n'
        (out/'callbacks.inc').write_text(cb)
        copy=marked(textures,'/* BEGIN VOQ COPY TRANSFER */','/* END VOQ COPY TRANSFER */')
        for signature in ('void glCopyTexImage2D(', 'void glCopyTextureImage2D(', 'void glCopyTexSubImage2D(', 'void glCopyTextureSubImage2D('):
            copy+='\n'+function(textures,signature)
        (out/'float_copy.inc').write_text(copy)
        # Compile the exact routing prefixes, with an explicit sentinel for the
        # unrelated legacy tail. The storage/conversion implementations are full.
        flat=function(textures,'static inline __attribute__((always_inline)) void _glTexImage2D_FlatIMPL(')
        prefix=flat.split('SceGxmTextureFormat tex_format;',1)[0]
        (out/'float_dispatch.inc').write_text(prefix+'++legacyRoutes;\n}\n')
        flags=['-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-Wno-unused-function']
        if os.environ.get('VOQ_FLOAT_SANITIZERS')=='1':flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
        cls.exe=out/'float-test'
        result=subprocess.run([shutil.which('c++'),*flags,'-I',str(out),str(ROOT/'tools/vita/tests/native/FloatTransferTest.cpp'),'-o',str(cls.exe)],capture_output=True,text=True)
        if result.returncode:raise AssertionError(result.stdout+result.stderr)
        # Both native FBO orientations must remain consistent with the old U8 reader.
        cls.flipped=out/'float-test-flipped'
        result=subprocess.run([shutil.which('c++'),*flags,'-DHAVE_UNFLIPPED_FBOS','-I',str(out),str(ROOT/'tools/vita/tests/native/FloatTransferTest.cpp'),'-o',str(cls.flipped)],capture_output=True,text=True)
        if result.returncode:raise AssertionError(result.stdout+result.stderr)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_case(self,case,exe=None):
        result=subprocess.run([str(exe or self.exe),case],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr);print(result.stdout.strip())
    def test_ieee_half_conversion(self):self.run_case('codec')
    def test_external_formats_and_row_layout(self):self.run_case('formats')
    def test_rgba8_to_rgba16f_crash_regression(self):self.run_case('capture')
    def test_mip_storage_lifetime_and_errors(self):self.run_case('storage')
    def test_float_mipmap_generation(self):self.run_case('mips')
    def test_half_readback(self):self.run_case('read');self.run_case('read',self.flipped)
    def test_copy_apis_and_state_restore(self):self.run_case('copy');self.run_case('copy',self.flipped)
    def test_renderer_and_public_dispatch(self):
        textures=(self.native/'textures.c').read_text();fb=(self.native/'framebuffers.c').read_text()
        self.assertIn('voq_float_subimage(tex,target,level',function(textures,'static inline __attribute__((always_inline)) void _glTexSubImage2D('))
        for sig in ('void glGenerateMipmap(', 'void glGenerateTextureMipmap('):self.assertIn('voq_float_generate(tex)',function(textures,sig))
        self.assertIn('voq_float_read_pixels',function(fb,'void glReadPixels('))
        engine=(ROOT/'src/renderer/Image_load.cpp').read_text();copy=function(engine,'bool idImage::CopyFramebuffer(')
        self.assertLess(copy.index('if ( copyError != GL_NO_ERROR )'),copy.index('opts.width = imageWidth;'))
        self.assertIn('glReadBuffer( previousReadBuffer );',copy)
        self.assertNotIn('opts.format = FMT_RGBA8',copy)
        capture=function((ROOT/'src/renderer/GLES_D3/gles_shaderpasses.cpp').read_text(),'void R_GLESD3_CaptureCurrentRender(')
        self.assertIn('if ( !sceneImage->CopyFramebuffer(',capture)
        self.assertIn('Cannot capture _currentRender',capture)


    def test_copy_owner_state_and_failure(self):
        body=function((ROOT/'src/renderer/Image_load.cpp').read_text(),'bool idImage::CopyFramebuffer(')
        with tempfile.TemporaryDirectory(prefix='voq-copy-owner-') as directory:
            out=Path(directory)
            (out/'owner.inc').write_text(body)
            header=(self.native/'vitaGL.h').read_text()
            (out/'gl_constants.h').write_text('\n'.join(line for line in header.splitlines() if re.match(r'#define GL_\w+\s+[^\\]+$',line)))
            flags=['-std=c++17','-Wall','-Wextra','-Werror','-Wno-unused-variable']
            if os.environ.get('VOQ_FLOAT_SANITIZERS')=='1':flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
            result=subprocess.run(['c++',*flags,'-I',str(out),str(ROOT/'tools/vita/tests/native/FrameCopyOwnerTest.cpp'),'-o',str(out/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(out/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr);print(result.stdout.strip())

class FloatPixelReferenceTest(unittest.TestCase):
    def test_mesa_half_texture_upload_and_subimage(self):
        import ctypes as C
        import struct
        from test_vita_gui_material_pixels import OffscreenGL, I, U, P
        gl=OffscreenGL();tex=U();fbo=U()
        # VitaGL exposes this desktop-style typed conversion. GLES 3 restricts
        # sized float formats to FLOAT/HALF transfers; use desktop GL as the
        # independent reference instead of treating that ES restriction as a
        # reason to change the engine image to RGBA8.
        gl.egl.eglMakeCurrent(gl.display,None,None,None)
        gl.egl.eglDestroyContext(gl.display,gl.context);gl.context=None
        gl.egl.eglDestroySurface(gl.display,gl.surface);gl.surface=None
        self.assertTrue(gl.egl.eglBindAPI(0x30A2))  # EGL_OPENGL_API
        config=P();count=I()
        attrs=(I*13)(0x3024,8,0x3023,8,0x3022,8,0x3021,8,0x3033,1,0x3040,8,0x3038)
        self.assertTrue(gl.egl.eglChooseConfig(gl.display,attrs,C.byref(config),1,C.byref(count)))
        self.assertTrue(count.value)
        gl.surface=gl.egl.eglCreatePbufferSurface(gl.display,config,(I*5)(0x3057,4,0x3056,2,0x3038))
        gl.context=gl.egl.eglCreateContext(gl.display,config,None,(I*1)(0x3038))
        self.assertTrue(gl.context and gl.surface and gl.egl.eglMakeCurrent(gl.display,gl.surface,gl.surface,gl.context))
        try:
            gl.glGenTextures(1,C.byref(tex));gl.glBindTexture(0x0de1,tex)
            image=(C.c_ubyte*24)(*range(0,240,10))
            gl.glTexImage2D(0x0de1,0,0x881a,3,2,0,0x1908,0x1401,C.cast(image,P))
            self.assertEqual(gl.glGetError(),0)
            gen=gl.proc('glGenFramebuffers',None,I,C.POINTER(U));bind=gl.proc('glBindFramebuffer',None,U,U)
            attach=gl.proc('glFramebufferTexture2D',None,U,U,U,U,I)
            gen(1,C.byref(fbo));bind(0x8d40,fbo);attach(0x8d40,0x8ce0,0x0de1,tex,0)
            check=gl.proc('glCheckFramebufferStatus',U,U);self.assertEqual(check(0x8d40),0x8cd5)
            out=(C.c_float*24)();gl.glReadPixels(0,0,3,2,0x1908,0x1406,C.cast(out,P));self.assertEqual(gl.glGetError(),0)
            for actual,b in zip(out,image):
                expected=struct.unpack('<e',struct.pack('<e',b/255.0))[0]
                self.assertAlmostEqual(actual,expected,delta=1/1024)
            sub=gl.proc('glTexSubImage2D',None,U,I,I,I,I,I,U,U,P)
            half=(C.c_uint16*4)(0xc100,0x4480,0x3555,0x3c00)
            sub(0x0de1,0,1,1,1,1,0x1908,0x140b,C.cast(half,P));self.assertEqual(gl.glGetError(),0)
            gl.glReadPixels(0,0,3,2,0x1908,0x1406,C.cast(out,P));self.assertEqual(gl.glGetError(),0)
            for c in range(4):self.assertEqual(out[16+c],struct.unpack('<e',struct.pack('<H',half[c]))[0])
            print('PASS Mesa RGBA16F U8 upload and HALF subimage: normalized color, negative/HDR data, unmodified neighbors')
        finally:
            if fbo.value:gl.proc('glDeleteFramebuffers',None,I,C.POINTER(U))(1,C.byref(fbo))
            if tex.value:gl.proc('glDeleteTextures',None,I,C.POINTER(U))(1,C.byref(tex))
            gl.close()

    def test_original_dispatch_negative_control(self):
        # The legacy selector remains verbatim in the non-float tail. Execute
        # that real switch independently: F16 + read_rgba8888 has no writer.
        source=Path(os.environ['VOQ_VITAGL_SOURCE'])/'source/textures.c'
        body=function(source.read_text(),'static inline __attribute__((always_inline)) void _glTexSubImage2D(')
        block=function(body[body.index('// Detecting proper write callback'):],'switch (tex_format)')
        native=set(re.findall(r'SCE_GXM_TEXTURE_FORMAT_\w+',block))|{'SCE_GXM_TEXTURE_FORMAT_F16F16F16F16_RGBA'}
        reads=(set(re.findall(r'\bread_\w+',block))|{'read_rgba8888'})-{'read_cb'};writes=set(re.findall(r'\bwrite_\w+',block))-{'write_cb'}
        code='#include <stdint.h>\n#include <stdio.h>\n#define GL_TRUE 1\n'
        code+='enum {'+','.join(sorted(native))+'};\n'
        for name in sorted(reads):code+='static uint32_t '+name+'(void*p){(void)p;return 0;}\n'
        for name in sorted(writes):code+='static void '+name+'(void*p,uint32_t v){(void)p;(void)v;}\n'
        code+='int main(void){int fast_store=0;uint32_t(*read_cb)(void*)=read_rgba8888;void(*write_cb)(void*,uint32_t)=0;int tex_format=SCE_GXM_TEXTURE_FORMAT_F16F16F16F16_RGBA;\n'+block
        code+='\nif(!fast_store&&!write_cb){puts("EXPECTED FAILURE: original U8 -> F16 selector leaves writer NULL");return 7;}return 0;}\n'
        with tempfile.TemporaryDirectory(prefix='voq-float-negative-') as directory:
            out=Path(directory);(out/'test.c').write_text(code)
            result=subprocess.run(['cc','-std=c11','-Wall','-Wextra','-Werror',str(out/'test.c'),'-o',str(out/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(out/'test')],capture_output=True,text=True)
            self.assertEqual(result.returncode,7,result.stdout+result.stderr);print(result.stdout.strip())

if __name__=='__main__':unittest.main()
