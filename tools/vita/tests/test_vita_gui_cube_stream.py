"""Execute production TGA, mip reducer, filesystem ownership and cube storage."""
from pathlib import Path
import importlib.util
import os
import re
import shutil
import subprocess
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[3]

def function(text, signature):
    a=text.index(signature);b=text.index('{',a);depth=1;i=b+1
    while depth:
        depth += (text[i]=='{')-(text[i]=='}');i+=1
    return text[a:i]

class CubeStreamTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory(prefix='voq-cube-test-')
        p=Path(cls.tmp.name)
        for name in ('TgaStream.h','CubeStream.h'):shutil.copy(ROOT/'src/imagetools'/name,p/name)
        s=(ROOT/'src/imagetools/Image_files.cpp').read_text()
        source=s[s.index('idCubeImageStream::idCubeImageStream()'):s.index('bool R_LoadCubeImages(')]
        m=(ROOT/'src/imagetools/Image_process.cpp').read_text()
        gamma=re.search(r'float mip_gammaTable\[256\] = \{.*?\};',m,re.S)[0]
        (p/'cube_production.inc').write_text(gamma+'\n'+function(m,'byte * R_MipMapWithGamma(')+'\n'+function(m,'byte * R_MipMap(')+'\n'+source)
        root=os.environ.get('VOQ_VITAGL_SOURCE')
        if not root:raise RuntimeError('freshly patched pinned VitaGL is required')
        native=(Path(root)/'source/textures.c').read_text()
        native=native.split('/* BEGIN VOQ IMMUTABLE CUBE STORAGE */',1)[1].split('/* END VOQ IMMUTABLE CUBE STORAGE */',1)[0]
        (p/'cube_gpu.inc').write_text(native)
        entire=(Path(root)/'source/textures.c').read_text()
        (p/'cube_api.inc').write_text(function(entire, 'void glTexStorage2D('))
        compiler=shutil.which('c++');assert compiler
        cls.exe=p/'cube-test'
        flags=['-std=c++17','-O2','-Wall','-Wextra','-Werror','-Wno-misleading-indentation']
        if os.environ.get('VOQ_CUBE_SANITIZERS')=='1':flags+=['-fsanitize=address,undefined','-fno-omit-frame-pointer']
        result=subprocess.run([compiler,*flags,'-I',str(p),str(ROOT/'tools/vita/tests/native/CubeStreamTest.cpp'),'-o',str(cls.exe)],text=True,capture_output=True)
        if result.returncode:raise AssertionError(result.stdout+result.stderr)
    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()
    def run_case(self,case):
        result=subprocess.run([str(self.exe),case],text=True,capture_output=True)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr);print(result.stdout.strip())
    def test_cube_orientation_and_every_mip(self):self.run_case('parity')
    def test_tga_failures_and_source_ownership(self):self.run_case('corrupt')
    def test_native_storage_lifetime_and_sampling(self):self.run_case('gpu')
    def test_1024_sky_bounded_cpu_staging(self):self.run_case('bounded')
    def test_submission_routes(self):
        s=(ROOT/'src/renderer/Image_load.cpp').read_text();self.assertIn('stream.Upload( firstLevel, opts.numLevels',s)
        self.assertIn('stream.Close();\n\t\t\t\t\t\tcommon->Error( "Incomplete cube image stream:',s)
        gl=(ROOT/'src/renderer/OpenGL/gl_Image.cpp').read_text()
        self.assertIn('glTexStorage2D( GL_TEXTURE_CUBE_MAP_EXT, opts.numLevels',gl)
        self.assertIn('opts.format != FMT_RGBA8 && mipLevel > 0',gl)
        root=Path(os.environ['VOQ_VITAGL_SOURCE'])
        for name in ('custom_shaders.c','ffp.c'):
            native=(root/'source'/name).read_text();self.assertNotIn('vglSetTexMipmapCount(&tex->gxm_tex,',native)
            self.assertIn('voq_set_texture_mip_count(tex, smp->use_mips',native)
