"""Execute the engine's actual frame-start and image-format selection functions."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[3]


def function(text, signature):
    start = text.index(signature)
    opening = text.index("{", start)
    depth = 1
    for pos in range(opening + 1, len(text)):
        depth += (text[pos] == "{") - (text[pos] == "}")
        if depth == 0:
            return text[start:pos + 1]
    raise AssertionError("Unterminated function: " + signature)


class GuiRenderContract(unittest.TestCase):
    def test_frame_start_and_format_selection(self):
        compiler = shutil.which("c++")
        if compiler is None:
            self.skipTest("C++ compiler not installed")
        frame = function((ROOT / "src/renderer/tr_backend.cpp").read_text(),
                         "static void\tRB_SetBuffer( const void *data )")
        decode = function((ROOT / "src/renderer/GLES_D3/gles_shaderpasses.cpp").read_text(),
                          "static float GLESD3_TextureGreenAlpha(")
        source = r'''
#include <cassert>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <string>
typedef bool GLboolean;
const bool GL_TRUE=true;
const int GL_SCISSOR_TEST=1, GL_COLOR_BUFFER_BIT=2;
struct Cvar {
    std::string value;
    Cvar(const char *s="0"): value(s) {}
    float GetFloat() const { return std::atof(value.c_str()); }
    int GetInteger() const { return std::atoi(value.c_str()); }
    const char *GetString() const { return value.c_str(); }
    bool GetBool() const { return GetFloat()!=0; }
} r_clear, r_lockSurfaces, r_singleArea, r_showOverDraw;
struct idStr { static int Length(const char *s) { return std::strlen(s); } };
struct { int frameCount; } backEnd;
struct setBufferCommand_t { int frameCount; int buffer; };
static bool scissor=true, masks[4]={false,false,false,false};
static float clearColor[4], pixel[4];
static int clears=0, invalidations=0;
void glDrawBuffer(int) {}
GLboolean glIsEnabled(int cap) { assert(cap==GL_SCISSOR_TEST); return scissor; }
void glDisable(int cap) { assert(cap==GL_SCISSOR_TEST); scissor=false; }
void glEnable(int cap) { assert(cap==GL_SCISSOR_TEST); scissor=true; }
void glColorMask(bool r,bool g,bool b,bool a) { masks[0]=r;masks[1]=g;masks[2]=b;masks[3]=a; }
void glClearColor(float r,float g,float b,float a) { clearColor[0]=r;clearColor[1]=g;clearColor[2]=b;clearColor[3]=a; }
void glClear(int bits) {
    assert(bits==GL_COLOR_BUFFER_BIT);
#ifdef VITA
    assert(!scissor);
    for(bool m:masks) assert(m);
#endif
    for(int i=0;i<4;i++) pixel[i]=clearColor[i];
    ++clears;
}
void GL_ClearStateDelta() { ++invalidations; }
enum { CFM_DEFAULT, CFM_GREEN_ALPHA };
struct Opts { int colorFormat; };
struct idImage { Opts opts; const Opts &GetOpts() const {return opts;} };
'''+frame+'\n'+decode+r'''
int main() {
    idImage ordinary={{CFM_DEFAULT}}, font={{CFM_GREEN_ALPHA}};
    assert(GLESD3_TextureGreenAlpha(&ordinary)==0);
#ifdef VITA
    assert(GLESD3_TextureGreenAlpha(&font)==1);
#else
    assert(GLESD3_TextureGreenAlpha(&font)==0); // already swizzled by the driver
#endif
    assert(GLESD3_TextureGreenAlpha(nullptr)==0);
    assert(GLESD3_TextureGreenAlpha(&ordinary)==0);

    setBufferCommand_t cmd={1,0};
#ifdef VITA
    // The initial target is dirty, masked and scissored to a small widget.
    // Repeated additive GUI edges must see the new frame, not its predecessor.
    for(int n=0;n<120;n++) {
        cmd.frameCount=n; RB_SetBuffer(&cmd);
        assert(backEnd.frameCount==n && scissor);
        for(int i=0;i<3;i++) { pixel[i]+=0.1f; assert(std::fabs(pixel[i]-0.1f)<1e-6); }
        assert(pixel[3]==1);
    }
    assert(clears==120 && invalidations==120);
    scissor=false; RB_SetBuffer(&cmd); assert(!scissor);
#else
    RB_SetBuffer(&cmd); assert(clears==0 && invalidations==0);
#endif
    const int before=clears;
    r_clear.value="0.2 0.3 0.4"; RB_SetBuffer(&cmd);
    assert(clears==before+1 && std::fabs(clearColor[1]-0.3f)<1e-6);
    r_clear.value="2"; RB_SetBuffer(&cmd); assert(clearColor[0]==0);
    r_clear.value="0"; r_showOverDraw.value="1"; RB_SetBuffer(&cmd); assert(clearColor[0]==1);
}
'''
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "contract.cpp"
            path.write_text(source)
            for platform in ("VITA", "DESKTOP"):
                exe = Path(temp) / platform
                subprocess.run([compiler, "-std=c++11", "-Wall", "-Wextra", "-D"+platform,
                                str(path), "-o", str(exe)], check=True, capture_output=True)
                subprocess.run([str(exe)], check=True, capture_output=True)

    def test_depth_prepass_does_not_inherit_gui_decode(self):
        source = (ROOT / "src/renderer/GLES_D3/gles_shaderpasses.cpp").read_text()
        depth = function(source, "static void RB_GLESD3_T_FillDepthBuffer(")
        for image, program in (("pStage->texture.image", "alphaTestProgram"),
                               ("globalImages->whiteImage", "program")):
            bind = depth.index(image + "->Bind();")
            decode = depth.index("glUniform1f( " + program + "->uTextureGreenAlpha,", bind)
            draw = depth.index("R_GLESD3_DrawElementsWithIndexCache(", bind)
            self.assertLess(bind, decode)
            self.assertLess(decode, draw)
        binder = function(source, "static const idImage *GLESD3_BindStageImage(")
        for image in ("globalImages->defaultImage", "globalImages->cinematicImage",
                      "globalImages->blackImage", "texture->image"):
            self.assertIn("return " + image + ";", binder)

    def test_every_material_stage_sets_decode_after_loading(self):
        source = (ROOT / "src/renderer/GLES_D3/gles_shaderpasses.cpp").read_text()
        draw = function(source, "static void RB_GLESD3_T_RenderShaderPasses(")
        bind = draw.index("GLESD3_BindStageImage( &pStage->texture, regs );")
        decode = draw.index("glUniform1f( stageProgram->uTextureGreenAlpha,")
        self.assertLess(bind, decode)
        self.assertLess(decode, draw.index("R_GLESD3_DrawElementsWithIndexCache( tri, indexCache );", decode))
        # No clear in each GUI view: a HUD must composite over its scene.
        view = function((ROOT / "src/renderer/GLES_D3/gles_d3_backend.cpp").read_text(),
                        "static void RB_GLESD3_BeginDrawingView(")
        self.assertNotIn("glClear(", view[view.index("// 2D:"):])


if __name__ == "__main__":
    unittest.main()
