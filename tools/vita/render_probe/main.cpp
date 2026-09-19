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
static GLuint material = 0, interaction = 0, meshVao = 0, meshVbo = 0, meshIbo = 0;
static GLuint checker = 0, flatNormal = 0, whiteTex = 0, specTable = 0;
static GLuint hudVao = 0, hudVbo = 0;
static GLint materialMvp = -1, interactionMvp = -1;
static GLint interactionLightOrigin = -1, interactionViewOrigin = -1;
static GLsizei hudCount = 0;
static bool sceneReady = false, paused = false, lastGlOk = true;
static int mode = 0;
static unsigned int modeFrame = 0;
static const char *modeNames[] = {
    "0 MATERIAL LEQUAL",
    "1 MATERIAL PREPASADA EQUAL",
    "2 INTERACCION EQUAL RAW",
    "3 INTERACCION EQUAL ADD",
    "4 INTERACCION LEQUAL ADD"
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


static bool CreateInteraction() {
    RendererLog("probe.interaction.begin");
    const std::string vp = Vita_GLESD3_NormalizeShaderSource(glesInteractionShaderVP, GL_VERTEX_SHADER);
    const std::string fp = Vita_GLESD3_NormalizeShaderSource(glesInteractionShaderFP, GL_FRAGMENT_SHADER);
    const GLchar *vs = vp.c_str(), *fs = fp.c_str();
    const GLuint v = glCreateShader(GL_VERTEX_SHADER), f = glCreateShader(GL_FRAGMENT_SHADER);
    if (!v || !f) {
        if (v) glDeleteShader(v);
        if (f) glDeleteShader(f);
        return false;
    }
    glShaderSource(v, 1, &vs, NULL); glCompileShader(v);
    glShaderSource(f, 1, &fs, NULL); glCompileShader(f);
    if (!CheckShader(v, "interaction-vertex") || !CheckShader(f, "interaction-fragment")) {
        glDeleteShader(v); glDeleteShader(f); return false;
    }
    interaction = glCreateProgram();
    if (!interaction) { glDeleteShader(v); glDeleteShader(f); return false; }
    glAttachShader(interaction, v); glAttachShader(interaction, f);
    glBindAttribLocation(interaction, 0, "inPosition");
    glBindAttribLocation(interaction, 1, "inColor");
    glBindAttribLocation(interaction, 2, "inNormal");
    glBindAttribLocation(interaction, 3, "inTangent");
    glBindAttribLocation(interaction, 4, "inBitangent");
    glBindAttribLocation(interaction, 5, "inTexCoord");
    glLinkProgram(interaction);
    const bool linked = CheckProgram(interaction);
    glDeleteShader(v); glDeleteShader(f);
    if (!linked) { glDeleteProgram(interaction); interaction = 0; return false; }

    glUseProgram(interaction);
    RendererLog("probe.interaction.linked");
    interactionMvp = glGetUniformLocation(interaction, "uMVP");
    interactionLightOrigin = glGetUniformLocation(interaction, "uLocalLightOrigin");
    interactionViewOrigin = glGetUniformLocation(interaction, "uLocalViewOrigin");
    const char *samplers[6] = {
        "uSpecularTableMap", "uBumpMap", "uLightFalloffMap",
        "uLightProjectionMap", "uDiffuseMap", "uSpecularMap"
    };
    for (int i = 0; i < 6; ++i) {
        const GLint loc = glGetUniformLocation(interaction, samplers[i]);
        if (loc < 0) { RendererLog("probe.interaction.sampler_missing"); return false; }
        glUniform1i(loc, i);
    }
    const char *vec4Names[] = {
        "uLightProjectionS","uLightProjectionT","uLightProjectionQ","uLightFalloffS",
        "uBumpMatrixS","uBumpMatrixT","uDiffuseMatrixS","uDiffuseMatrixT",
        "uSpecularMatrixS","uSpecularMatrixT","uDiffuseColor","uSpecularColor","uVertexColor"
    };
    const float values[][4] = {
        {0,0,0,0.5f},{0,0,0,0.5f},{0,0,0,1},{0,0,0,0.5f},
        {1,0,0,0},{0,1,0,0},{1,0,0,0},{0,1,0,0},
        {1,0,0,0},{0,1,0,0},{1,1,1,1},{0.35f,0.35f,0.35f,1},{1,0,1,0}
    };
    for (int i = 0; i < 13; ++i) {
        const GLint loc = glGetUniformLocation(interaction, vec4Names[i]);
        if (loc < 0) { RendererLog("probe.interaction.uniform_missing"); return false; }
        glUniform4fv(loc, 1, values[i]);
    }
    if (interactionMvp < 0 || interactionLightOrigin < 0 || interactionViewOrigin < 0) {
        RendererLog("probe.interaction.required_uniform_missing");
        return false;
    }
    const bool ok = CheckGl("probe.interaction");
    RendererLog(ok ? "probe.interaction.ok" : "probe.interaction.gl-error");
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

    const unsigned char normalPixel[4] = {128, 128, 255, 128};
    const unsigned char whitePixel[4] = {255, 255, 255, 255};
    unsigned char specPixels[64 * 4];
    for (int x = 0; x < 64; ++x) {
        const float t = static_cast<float>(x) / 63.0f;
        const unsigned char v = static_cast<unsigned char>(255.0f * t * t * t * t);
        specPixels[x*4+0] = v; specPixels[x*4+1] = v;
        specPixels[x*4+2] = v; specPixels[x*4+3] = 255;
    }
    glGenTextures(1, &flatNormal); glBindTexture(GL_TEXTURE_2D, flatNormal);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 1, 1, 0, GL_RGBA, GL_UNSIGNED_BYTE, normalPixel);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glGenTextures(1, &whiteTex); glBindTexture(GL_TEXTURE_2D, whiteTex);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 1, 1, 0, GL_RGBA, GL_UNSIGNED_BYTE, whitePixel);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST);
    glGenTextures(1, &specTable); glBindTexture(GL_TEXTURE_2D, specTable);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, 64, 1, 0, GL_RGBA, GL_UNSIGNED_BYTE, specPixels);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR);

    if (!checker || !flatNormal || !whiteTex || !specTable || !CheckGl("probe.texture")) {
        RendererLog("probe.texture=failed");
        return false;
    }
    RendererLog("probe.texture=ok");
    glGenVertexArrays(1, &hudVao); glGenBuffers(1, &hudVbo);
    glBindVertexArray(0);
    RendererLog("probe.mesh vertices=28 indices=42 stride=60 color=12 normal=16 tangent=28 bitangent=40 uv=52 floor_index_byte_offset=72");
    const bool ok = hudVao && hudVbo && CheckGl("probe.mesh.objects");
    RendererLog(ok ? "probe.mesh.objects=ok" : "probe.mesh.objects=failed");
    return ok;
}

static void BindVertices(GLuint vao, GLuint vbo, bool textured, bool interactionLayout = false) {
    glBindVertexArray(vao); glBindBuffer(GL_ARRAY_BUFFER, vbo);
    glEnableVertexAttribArray(0); glEnableVertexAttribArray(1);
    glVertexAttribPointer(0, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex),
                         reinterpret_cast<const void *>(offsetof(Vertex, xyz)));
    glVertexAttribPointer(1, 4, GL_UNSIGNED_BYTE, GL_TRUE, sizeof(Vertex),
                         reinterpret_cast<const void *>(offsetof(Vertex, color)));
    if (interactionLayout) {
        glEnableVertexAttribArray(2); glEnableVertexAttribArray(3); glEnableVertexAttribArray(4);
        glVertexAttribPointer(2, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex),
                             reinterpret_cast<const void *>(offsetof(Vertex, normal)));
        glVertexAttribPointer(3, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex),
                             reinterpret_cast<const void *>(offsetof(Vertex, tangent)));
        glVertexAttribPointer(4, 3, GL_FLOAT, GL_FALSE, sizeof(Vertex),
                             reinterpret_cast<const void *>(offsetof(Vertex, bitangent)));
    } else {
        glDisableVertexAttribArray(2); glDisableVertexAttribArray(3); glDisableVertexAttribArray(4);
    }
    if (textured) {
        glEnableVertexAttribArray(5);
        glVertexAttribPointer(5, 2, GL_FLOAT, GL_FALSE, sizeof(Vertex),
                             reinterpret_cast<const void *>(offsetof(Vertex, st)));
    } else glDisableVertexAttribArray(5);
}

static void DrawMaterial(const Matrix &mvp, int first, int count) {
    glUseProgram(material);
    glUniformMatrix4fv(materialMvp, 1, GL_FALSE, mvp.data());
    BindVertices(meshVao, meshVbo, true, false);
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, meshIbo);
    glDrawElements(GL_TRIANGLES, count, GL_UNSIGNED_SHORT,
                   reinterpret_cast<const void *>(static_cast<uintptr_t>(first * sizeof(std::uint16_t))));
}

static void BindInteractionTextures() {
    glActiveTexture(GL_TEXTURE0 + 0); glBindTexture(GL_TEXTURE_2D, specTable);
    glActiveTexture(GL_TEXTURE0 + 1); glBindTexture(GL_TEXTURE_2D, flatNormal);
    glActiveTexture(GL_TEXTURE0 + 2); glBindTexture(GL_TEXTURE_2D, whiteTex);
    glActiveTexture(GL_TEXTURE0 + 3); glBindTexture(GL_TEXTURE_2D, whiteTex);
    glActiveTexture(GL_TEXTURE0 + 4); glBindTexture(GL_TEXTURE_2D, checker);
    glActiveTexture(GL_TEXTURE0 + 5); glBindTexture(GL_TEXTURE_2D, whiteTex);
}

static void ReloadInteractionUniforms() {
    // Mirror GLESD3_DrawInteraction: vitaGL's custom-program path is safest
    // when all per-draw uniforms are refreshed after switching away to the
    // material program for the depth prepass.
    const char *samplers[6] = {
        "uSpecularTableMap", "uBumpMap", "uLightFalloffMap",
        "uLightProjectionMap", "uDiffuseMap", "uSpecularMap"
    };
    for (int i = 0; i < 6; ++i) {
        const GLint loc = glGetUniformLocation(interaction, samplers[i]);
        if (loc >= 0) glUniform1i(loc, i);
    }
    const char *vec4Names[] = {
        "uLightProjectionS","uLightProjectionT","uLightProjectionQ","uLightFalloffS",
        "uBumpMatrixS","uBumpMatrixT","uDiffuseMatrixS","uDiffuseMatrixT",
        "uSpecularMatrixS","uSpecularMatrixT","uDiffuseColor","uSpecularColor","uVertexColor"
    };
    const float values[][4] = {
        {0,0,0,0.5f},{0,0,0,0.5f},{0,0,0,1},{0,0,0,0.5f},
        {1,0,0,0},{0,1,0,0},{1,0,0,0},{0,1,0,0},
        {1,0,0,0},{0,1,0,0},{1,1,1,1},{0.35f,0.35f,0.35f,1},{1,0,1,0}
    };
    for (int i = 0; i < 13; ++i) {
        const GLint loc = glGetUniformLocation(interaction, vec4Names[i]);
        if (loc >= 0) glUniform4fv(loc, 1, values[i]);
    }
    glUniform4f(interactionLightOrigin, 2.5f, 3.5f, 2.5f, 0.0f);
    glUniform4f(interactionViewOrigin, 0.0f, 1.0f, 4.0f, 1.0f);
}

static void DrawInteraction(const Matrix &mvp, int first, int count) {
    glUseProgram(interaction);
    ReloadInteractionUniforms();
    glUniformMatrix4fv(interactionMvp, 1, GL_FALSE, mvp.data());
    BindInteractionTextures();
    BindVertices(meshVao, meshVbo, true, true);
    glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, meshIbo);
    glDrawElements(GL_TRIANGLES, count, GL_UNSIGNED_SHORT,
                   reinterpret_cast<const void *>(static_cast<uintptr_t>(first * sizeof(std::uint16_t))));
}

static void DrawScene(float angle) {
    const float testAngle = mode == 0 ? angle : 0.65f;
    const Matrix floor = Projection(), cube = Multiply(floor, CubeModel(testAngle));
    glViewport(0, 0, 960, 544);
    glDisable(GL_SCISSOR_TEST); glDisable(GL_CULL_FACE);
    glDisable(GL_STENCIL_TEST);
    glEnable(GL_DEPTH_TEST); glDepthMask(GL_TRUE);
    glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
    glDisable(GL_BLEND);

    if (mode != 0) {
        // Production GLES_D3 depth fill uses the material program itself.
        glColorMask(GL_FALSE, GL_FALSE, GL_FALSE, GL_FALSE);
        glDepthFunc(GL_LESS);
        glActiveTexture(GL_TEXTURE0); glBindTexture(GL_TEXTURE_2D, checker);
        DrawMaterial(cube, 0, CubeIndexCount);
        DrawMaterial(floor, FloorFirstIndex, FloorIndexCount);
        glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE);
        glDepthMask(GL_FALSE);
    }

    if (mode <= 1) {
        glDisable(GL_BLEND);
        glDepthFunc(mode == 1 ? GL_EQUAL : GL_LEQUAL);
        glActiveTexture(GL_TEXTURE0); glBindTexture(GL_TEXTURE_2D, checker);
        DrawMaterial(cube, 0, CubeIndexCount);
        DrawMaterial(floor, FloorFirstIndex, FloorIndexCount);
    } else {
        // Preserve depth but reset destination colour immediately before the
        // light pass. This makes any frame-to-frame additive accumulation
        // measurable rather than conflating it with the prepass.
        glDisable(GL_BLEND);
        glClearColor(0.0f, 0.0f, 0.0f, 1.0f);
        glClear(GL_COLOR_BUFFER_BIT);

        if (mode == 2) {
            // Raw interaction output. If this drifts, the shader/uniform state
            // is changing; blending cannot be responsible.
            glDisable(GL_BLEND);
            glDepthFunc(GL_EQUAL);
        } else {
            glEnable(GL_BLEND);
            glBlendFunc(GL_ONE, GL_ONE);
            glDepthFunc(mode == 3 ? GL_EQUAL : GL_LEQUAL);
        }
        DrawInteraction(cube, 0, CubeIndexCount);
        DrawInteraction(floor, FloorFirstIndex, FloorIndexCount);
        glDisable(GL_BLEND);
    }
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
                Vertex v = {};
                v.xyz[0] = xy[k][0]; v.xyz[1] = xy[k][1]; v.xyz[2] = 0.0f;
                v.color[0] = v.color[1] = v.color[2] = v.color[3] = 255;
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
    BindVertices(hudVao, hudVbo, false, false);
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
    BindVertices(hudVao, hudVbo, false, false);
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
        sceClibSnprintf(line, sizeof(line), "probe.sample mode=%d frame=%u point=%d xy=%d,%d rgba=%u,%u,%u,%u",
                        mode,modeFrame,i,points[i][0],points[i][1],rgba[0],rgba[1],rgba[2],rgba[3]);
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
    if (!gpu) RendererLog("probe.scene.gpu=failed");
    const bool materialOk = gpu ? Probe::CreateMaterial() : false;
    if (gpu && !materialOk) RendererLog("probe.scene.material=failed");
    const bool interactionOk = gpu && materialOk ? Probe::CreateInteraction() : false;
    if (gpu && materialOk && !interactionOk) RendererLog("probe.scene.interaction=failed");
    Probe::sceneReady = gpu && materialOk && interactionOk;
    RendererLog(Probe::sceneReady ? "probe.scene.ready=1" : "probe.scene.ready=0");
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
                Probe::mode = (Probe::mode + 1) % 5;
                Probe::modeFrame = 0;
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
        const bool autoCapture = Probe::mode >= 2 &&
            (Probe::modeFrame == 0 || Probe::modeFrame == 1 || Probe::modeFrame == 2 ||
             Probe::modeFrame == 3 || Probe::modeFrame == 7 || Probe::modeFrame == 15 ||
             Probe::modeFrame == 31 || Probe::modeFrame == 63);
        if (capture || autoCapture) {
            Probe::lastGlOk = CheckGl("probe.scene");
            Probe::SamplePixels(); Probe::UpdateHud(); capture = false;
        }
        Probe::DrawHud();
        if (frame == 0) CheckGl("probe.hud");
        vglSwapBuffers(GL_FALSE);
        if (!Probe::paused && Probe::mode == 0) angle += 0.009f;
        Probe::modeFrame++;
        if (++frame == 60) RendererLog("probe.presented_60_frames=1");
    }
}
