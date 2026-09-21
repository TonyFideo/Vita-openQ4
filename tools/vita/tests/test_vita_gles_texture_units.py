"""GLES_D3 sampler units must not become legacy client texture-coordinate units."""
from pathlib import Path
import subprocess, tempfile, unittest

ROOT=Path(__file__).resolve().parents[3]

def function(text, signature):
    start=text.index(signature)
    opening=text.index('{',start); depth=0
    for i in range(opening,len(text)):
        if text[i]=='{': depth+=1
        elif text[i]=='}':
            depth-=1
            if depth==0:return text[start:i+1]
    raise AssertionError(signature)

class TextureUnitStateTest(unittest.TestCase):
    def run_profile(self,gles):
        body=function((ROOT/'src/renderer/tr_backend.cpp').read_text(),'void GL_SelectTexture( int unit )')
        source=r'''
#include <cassert>
#include <cstdarg>
#include <cstdio>
#define GL_TEXTURE0_ARB 0x84C0
#define MAX_MULTITEXTURE_UNITS 16
struct State { int currenttmu=-1; }; struct Back { State glState; } backEnd;
struct Config { int maxTextureUnits=16,maxTextureImageUnits=16; } glConfig;
struct Common { void Warning(const char*,...){} } commonObject; Common *common=&commonObject;
static int activeCalls=0,clientCalls=0,lastActive=-1,lastClient=-1;
static void glActiveTextureARB(int u){++activeCalls;lastActive=u-GL_TEXTURE0_ARB;}
[[maybe_unused]] static void glClientActiveTextureARB(int u){++clientCalls;lastClient=u-GL_TEXTURE0_ARB;}
static void RB_LogComment(const char*,...){}
'''+body+r'''
int main(){
 GL_SelectTexture(5); assert(activeCalls==1&&lastActive==5);
#ifdef OPENQ4_RENDERER_GLES_MODULE
 assert(clientCalls==0);
#else
 assert(clientCalls==1&&lastClient==5);
#endif
 GL_SelectTexture(5); assert(activeCalls==1); return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='voq-unit-') as d:
            p=Path(d); (p/'t.cpp').write_text(source)
            cmd=['c++','-std=c++17','-Wall','-Wextra','-Werror']
            if gles:cmd+=['-DOPENQ4_RENDERER_GLES_MODULE=1']
            cmd += [str(p/'t.cpp'),'-o',str(p/'t')]
            result=subprocess.run(cmd,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
            result=subprocess.run([str(p/'t')],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stdout+result.stderr)
    def test_gles_sampler_units_are_server_state_only(self):self.run_profile(True)
    def test_legacy_renderer_keeps_client_unit_selection(self):self.run_profile(False)
    def test_gles_default_state_does_not_touch_client_texture_arrays(self):
        text=(ROOT/'src/renderer/tr_backend.cpp').read_text()
        start=text.index('#ifdef OPENQ4_RENDERER_GLES_MODULE', text.index('RB_SetDefaultGLState'))
        end=text.index('#else',start)
        self.assertNotIn('glClientActiveTextureARB',text[start:end])
    def test_vitagl_rejects_out_of_range_client_units_without_state_change(self):
        import os
        root=os.environ.get('VOQ_VITAGL_SOURCE')
        if not root:self.skipTest('patched VitaGL source required')
        text=(Path(root)/'source/ffp.c').read_text()
        body=function(text,'void glClientActiveTexture(GLenum texture)')
        self.assertIn('texture - GL_TEXTURE0 >= TEXTURE_COORDS_NUM',body)
        self.assertIn('SET_GL_ERROR_WITH_VALUE(GL_INVALID_ENUM, texture)',body)
        self.assertLess(body.index('SET_GL_ERROR_WITH_VALUE(GL_INVALID_ENUM, texture)', body.index('TEXTURE_COORDS_NUM')), body.index('client_texture_unit ='))

if __name__=='__main__':unittest.main()
