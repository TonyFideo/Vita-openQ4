// Standalone renderer integration probe. Reuse the previously tested VitaGL
// bootstrap and the production GLES_D3 shaders, without linking the engine.
#include "../../../src/sys/vita/vita_renderer_smoke.cpp"
#include "probe_scene.h"
#include <psp2/ctrl.h>
#include <psp2/io/stat.h>
#include <psp2/kernel/threadmgr/thread.h>
#include <vector>
#include <cstddef>
#include <cstdint>

#ifndef PROBE_BUILD_SHA
#define PROBE_BUILD_SHA "local"
#endif
extern "C" { int _newlib_heap_size_user = 32 * 1024 * 1024; }

namespace Probe {
static GLuint material = 0, meshVao = 0, meshVbo = 0, meshIbo = 0;
static GLuint checker = 0, hudVao = 0, hudVbo = 0;
static GLint materialMvp = -1;
static GLsizei hudCount = 0;
static bool sceneReady = false, paused = false, lastGlOk = true;
static int mode = 0;
static const char *modeNames[] = {
    "0 TEXTURA LEQUAL", "1 PREPASADA MAS EQUAL", "2 PREPASADA MAS LEQUAL"
};

static bool CreateMaterial() {
    RendererLog("probe.material.begin");
    const std::string vp = Vita_GLESD3_NormalizeShaderSource(glesMaterialShaderVP, GL_VERTEX_SHADER);
    const std::string fp = Vita_GLESD3_NormalizeShaderSource(glesMaterialShaderFP, GL_FRAGMENT_SHADER);
    const GLchar *vs = vp.c_str(), *fs = fp.c_str();
    const GLuint v = glCreateShader(GL_VERTEX_SHADER), f = glCreateShader(GL_FRAGMENT_SHADER);
    if (!v || !f) {
        if (v) glDeleteShader(v);
        if (f) glDeleteShader(f);
        return false;
    }
    glShaderSource(v, 1, &vs, NULL); glCompileShader(v);
    glShaderSource(f, 1, &fs, NULL); glCompileShader(f);
    if (!CheckShader(v, "material-vertex") || !CheckShader(f, "material-fragment")) {
        glDeleteShader(v); glDeleteShader(f); return false;
    }
    material = glCreateProgram();
    if (!material) { glDeleteShader(v); glDeleteShader(f); return false; }
    glAttachShader(material, v); glAttachShader(material, f);
    glBindAttribLocation(material, 0, "inPosition");
    glBindAttribLocation(material, 1, "inColor");
    glBindAttribLocation(material, 5, "inTexCoord");
    glLinkProgram(material);
    const bool linked = CheckProgram(material);
    glDeleteShader(v); glDeleteShader(f);
    if (!linked) { glDeleteProgram(material); material = 0; return false; }
    glUseProgram(material);
    RendererLog("probe.material.linked");
    materialMvp = glGetUniformLocation(material, "uMVP");
    const GLint texture = glGetUniformLocation(material, "uTexture0");
    const GLint color = glGetUniformLocation(material, "uColor");
    const GLint vertexColor = glGetUniformLocation(material, "uVertexColor");
    const GLint s = glGetUniformLocation(material, "uTexMatrixS");
    const GLint t = glGetUniformLocation(material, "uTexMatrixT");
    if (materialMvp < 0 || texture < 0 || color < 0 || vertexColor < 0 || s < 0 || t < 0) {
        RendererLog("probe.material.required_uniform_missing"); return false;
    }
    glUniform1i(texture, 0);
    glUniform4f(color, 1, 1, 1, 1);
    glUniform4f(vertexColor, 1, 0, 1, 0);
    glUniform4f(s, 1, 0, 0, 0); glUniform4f(t, 0, 1, 0, 0);
    const bool ok = CheckGl("probe.material");
    RendererLog(ok ? "probe.material.ok" : "probe.material.gl-error");
    return ok;
}

static bool CreateSceneGpu() {
    const Scene scene = MakeScene();
    glGenVertexArrays(1, &meshVao); glBindVertexArray(meshVao);
    glGenBuffers(1, &meshVbo); glBindBuffer(GL_ARRAY_BUFFER, meshVbo);
    glBufferData(GL_ARRAY_BUFFER, sizeof(scene.vertices), scene.vertices.data(), GL_STATIC_DRAW);
    glGenBuffers(1, &meshIbo); glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, meshIbo);
    glBufferData(GL_ELEMENT_ARRAY_BUFFER, sizeof(scene.indices), scene.indices.data(), GL_STATIC_DRAW);
    if (!meshVao || !meshVbo || !meshIbo || !CheckGl("probe.mesh.buffers")) {
        RendererLog("probe.mesh.buffers=failed");
        return false;
    }
    RendererLog("probe.mesh.buffers=ok");
    unsigned char pixels[64 * 64 * 4];
    for (int y = 0; y < 64; ++y) for (int x = 0; x < 64; ++x) {
        const bool light = ((x / 8) ^ (y / 8)) & 1;
        const int i = (y * 64 + x) * 4;
        pixels[i] = light ? 245 : 45;
        pixels[i+1] = light ? 245 : 60;
        pixels[i+2] = light ? 245 : 80; pixels[i+3] = 255;
    }
    glActiveTexture(GL_TEXTURE0);
    glGenTextures(1, &checker); glBindTexture(GL_TEXTURE_2D, checker);
    // vitaGL only implements GL_UNPACK_ROW_LENGTH in glPixelStorei.  This
    // RGBA8 texture has 64 * 4 = 256 bytes per row, already compatible with
    // the default unpack alignment, so no alignment override is required.
    RendererLog("probe.texture.unpack=default-alignment row_bytes=256");
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 64, 64, 0, GL_RGBA, GL_UNSIGNED_BYTE, pixels);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_REPEAT);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_REPEAT);
    if (!checker || !CheckGl("probe.texture")) {
        RendererLog("probe.texture=failed");
        return false;
    }
    RendererLog("probe.texture=ok");
    glGenVertexArrays(1, &hudVao); glGenBuffers(1, &hudVbo);
    glBindVertexArray(0);
    RendererLog("probe.mesh vertices=28 indices=42 stride=24 color_offset=12 uv_offset=16 floor_index_byte_offset=72");
    const bool ok = hudVao && hudVbo && CheckGl("probe.mesh.objects");
    RendererLog(ok ? "probe.mesh.objects=ok" : "probe.mesh.objects=failed");
    return ok;
}

static void BindVertices(GLuint vao, GLuint vbo, bool textured) {
    glBindVertexArray(vao); glBindBuffer(GL_ARRAY_BUFFER, vbo);
    glEnableVertexAttribArray(0); glEnableVertexAttribArray(1);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex),
                         reinterpret_cast<const void *>(offsetof(Vertex, xyz)));
    glVertexAttribPointer(1, 4, GL_UNSIGNED_BYTE, GL_TRUE, sizeof(Vertex),
                         reinterpret_cast<const void *>(offsetof(Vertex, color)));
    if (textured) {
        glEnableVertexAttribArray(5);
        glVertexAttribPointer(5, 2, GL_FLOAT, GL_FALSE, sizeof(Vertex),
                             reinterpret_cast<const void *>(offsetof(Vertex, st)));
    } else glDisableVertexAttribArray(5);
}

static void DrawMesh(const Matrix &mvp, int first, int count, bool depthOnly) {
    glUseProgram(depthOnly ? smokeProgram : material);
    glUniformMatrix4fv(depthOnly ? smokeMvpUniform : materialMvp, 1, GL_FALSE, mvp.data());
    BindVertices(meshVao, meshVbo, !depthOnly);
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, meshIbo);
    glDrawElements(GL_TRIANGLES, count, GL_UNSIGNED_SHORT,
                   reinterpret_cast<const void *>(static_cast<uintptr_t>(first * sizeof(std::uint16_t))));
}

static void DrawScene(float angle) {
    // Reuse the identical matrix bytes in both programs, as the engine's
    // depth-EQUAL path requires. Never recompute a camera between the passes.
    const Matrix floor = Projection(), cube = Multiply(floor, CubeModel(angle));
    glViewport(0, 0, 960, 544);
    glDisable(GL_SCISSOR_TEST); glDisable(GL_CULL_FACE);
    glDisable(GL_BLEND); glDisable(GL_STENCIL_TEST);
    glEnable(GL_DEPTH_TEST); glDepthMask(GL_TRUE);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    glActiveTexture(GL_TEXTURE0); glBindTexture(GL_TEXTURE_2D, checker);
    if (mode != 0) {
        glColorMask(GL_FALSE, GL_FALSE, GL_FALSE, GL_FALSE);
        glDepthFunc(GL_LESS);
        DrawMesh(cube, 0, CubeIndexCount, true);
        DrawMesh(floor, FloorFirstIndex, FloorIndexCount, true);
        glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
        glDepthMask(GL_FALSE);
    }
    glDepthFunc(mode == 1 ? GL_EQUAL : GL_LEQUAL);
    // Draw the cube first and the floor last: a missing depth test must be
    // visible rather than concealed by back-to-front submission.
    DrawMesh(cube, 0, CubeIndexCount, false);
    DrawMesh(floor, FloorFirstIndex, FloorIndexCount, false);
    glDepthMask(GL_TRUE);
}

// Tiny procedural font; no game assets or framebuffer-console ownership.
static const unsigned char font[36][7] = {
 {14,17,17,31,17,17,17},{30,17,17,30,17,17,30},{14,17,16,16,16,17,14},
 {30,17,17,17,17,17,30},{31,16,16,30,16,16,31},{31,16,16,30,16,16,16},
 {14,17,16,23,17,17,15},{17,17,17,31,17,17,17},{14,4,4,4,4,4,14},
 {7,2,2,2,18,18,12},{17,18,20,24,20,18,17},{16,16,16,16,16,16,31},
 {17,27,21,21,17,17,17},{17,25,21,19,17,17,17},{14,17,17,17,17,17,14},
 {30,17,17,30,16,16,16},{14,17,17,17,21,18,13},{30,17,17,30,20,18,17},
 {15,16,16,14,1,1,30},{31,4,4,4,4,4,4},{17,17,17,17,17,17,14},
 {17,17,17,17,17,10,4},{17,17,17,21,21,21,10},{17,17,10,4,10,17,17},
 {17,17,10,4,4,4,4},{31,1,2,4,8,16,31},
 {14,17,19,21,25,17,14},{4,12,4,4,4,4,14},{14,17,1,2,4,8,31},
 {30,1,1,14,1,1,30},{2,6,10,18,31,2,2},{31,16,16,30,1,1,30},
 {14,16,16,30,17,17,14},{31,1,2,4,8,8,8},{14,17,17,14,17,17,14},
 {14,17,17,15,1,1,14}
};
static void Text(std::vector<Vertex> &out, const char *text, int x, int y, bool ok = true) {
    for (; *text; ++text, x += 12) {
        int glyph = *text >= 'A' && *text <= 'Z' ? *text - 'A' :
                    (*text >= '0' && *text <= '9' ? *text - '0' + 26 : -1);
        if (glyph < 0) continue;
        for (int r = 0; r < 7; ++r) for (int c = 0; c < 5; ++c) {
            if (!(font[glyph][r] & (1 << (4-c)))) continue;
            const float left = 2.0f * (x+c*2) / 960.0f - 1.0f;
            const float top = 1.0f - 2.0f * (y+r*2) / 544.0f;
            const float right = left + 4.0f/960.0f, bottom = top - 4.0f/544.0f;
            const float xy[6][2] = {{left,top},{left,bottom},{right,bottom},{left,top},{right,bottom},{right,top}};
            for (int k = 0; k < 6; ++k) {
                Vertex v = {{xy[k][0],xy[k][1],0},{255,255,255,255},{0,0}};
                if (!ok) { v.color[1] = 75; v.color[2] = 75; }
                out.push_back(v);
            }
        }
    }
}
static void UpdateHud() {
    std::vector<Vertex> data;
    Text(data, "VITA OPENQ4 PRUEBA DE RENDER", 20, 18);
    Text(data, modeNames[mode], 20, 40);
    Text(data, "X MODO  TRIANGULO PAUSA  CUADRADO LOG", 20, 62);
    Text(data, sceneReady ? "SHADERS Y GEOMETRIA CARGADOS" : "ERROR DE SHADER O GEOMETRIA", 20, 84, sceneReady);
    if (!lastGlOk) Text(data, "ERROR GL VER RENDERER PROBE LOG", 20, 106, false);
    BindVertices(hudVao, hudVbo, false);
    glBufferData(GL_ARRAY_BUFFER, data.size()*sizeof(Vertex), data.data(), GL_STATIC_DRAW);
    hudCount = static_cast<GLsizei>(data.size());
}
static void DrawHud() {
    glDisable(GL_DEPTH_TEST); glDisable(GL_CULL_FACE); glDisable(GL_BLEND);
    glUseProgram(smokeProgram);
    const Matrix identity = Identity();
    glUniformMatrix4fv(smokeMvpUniform, 1, GL_FALSE, identity.data());
    if (smokeColorUniform >= 0) glUniform4f(smokeColorUniform, 1, 1, 1, 1);
    if (smokeAlphaTestUniform >= 0) glUniform1f(smokeAlphaTestUniform, -1);
    BindVertices(hudVao, hudVbo, false);
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0);
    glDrawArrays(GL_TRIANGLES, 0, hudCount);
}
static void SamplePixels() {
    const int points[3][2] = {{480,272},{480,90},{20,272}};
    glFinish();
    for (int i = 0; i < 3; ++i) {
        unsigned char rgba[4] = {};
        glReadPixels(points[i][0], points[i][1], 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, rgba);
        char line[192];
        sceClibSnprintf(line, sizeof(line), "probe.sample mode=%d point=%d xy=%d,%d rgba=%u,%u,%u,%u",
                        mode,i,points[i][0],points[i][1],rgba[0],rgba[1],rgba[2],rgba[3]);
        RendererLog(line);
    }
    // These are observations, not an automatic image-correctness verdict.
    CheckGl("probe.readback");
}
}

int main() {
    sceIoMkdir("ux0:data/Vita-OpenQ4", 0777);
    sceIoMkdir("ux0:data/Vita-OpenQ4/logs", 0777);
    kRendererLog = "ux0:data/Vita-OpenQ4/logs/renderer-probe.log";
    // Keep each test run self-contained instead of appending checkpoints from
    // older VPKs to the same file.
    sceIoRemove(kRendererLog);
    RendererLog("probe.build=" PROBE_BUILD_SHA);
    RendererLog("probe.kind=isolated-production-shaders-not-full-game");
    sceCtrlSetSamplingMode(SCE_CTRL_MODE_ANALOG);
    if (!VitaRendererSmoke_Init()) {
        RendererLog("probe.bootstrap.failed");
        for (;;) sceKernelDelayThread(100000);
    }
    const bool gpu = Probe::CreateSceneGpu();
    if (!gpu) Probe::RendererLog("probe.scene.gpu=failed");
    const bool materialOk = gpu ? Probe::CreateMaterial() : false;
    if (gpu && !materialOk) Probe::RendererLog("probe.scene.material=failed");
    Probe::sceneReady = gpu && materialOk;
    Probe::RendererLog(Probe::sceneReady ? "probe.scene.ready=1" : "probe.scene.ready=0");
    if (!Probe::hudVao || !Probe::hudVbo) {
        RendererLog("probe.hud.allocation_failed");
        VitaRendererSmoke_Run();
    }
    Probe::UpdateHud();
    unsigned int previousButtons = 0;
    float angle = 0.25f;
    unsigned int frame = 0;
    bool capture = true;
    for (;;) {
        SceCtrlData pad = {};
        if (sceCtrlPeekBufferPositive(0, &pad, 1) > 0) {
            const unsigned int pressed = pad.buttons & ~previousButtons;
            previousButtons = pad.buttons;
            if (pressed & SCE_CTRL_CROSS) {
                Probe::mode = (Probe::mode + 1) % 3;
                RendererLog(Probe::modeNames[Probe::mode]);
                Probe::UpdateHud(); capture = true;
            }
            if (pressed & SCE_CTRL_TRIANGLE) Probe::paused = !Probe::paused;
            if (pressed & SCE_CTRL_SQUARE) capture = true;
        }
        glViewport(0, 0, 960, 544); glDisable(GL_SCISSOR_TEST);
        glColorMask(GL_TRUE,GL_TRUE,GL_TRUE,GL_TRUE); glDepthMask(GL_TRUE);
        glClearColor(0.025f, 0.035f, 0.065f, 1);
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT);
        if (Probe::sceneReady) Probe::DrawScene(angle);
        if (capture) {
            Probe::lastGlOk = CheckGl("probe.scene");
            Probe::SamplePixels(); Probe::UpdateHud(); capture = false;
        }
        Probe::DrawHud();
        if (frame == 0) CheckGl("probe.hud");
        vglSwapBuffers(GL_FALSE);
        if (!Probe::paused) angle += 0.009f;
        if (++frame == 60) RendererLog("probe.presented_60_frames=1");
    }
}
