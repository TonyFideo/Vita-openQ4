#pragma once
#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>

namespace Probe {
struct Vertex {
    float xyz[3];
    unsigned char color[4];
    float normal[3];
    float tangent[3];
    float bitangent[3];
    float st[2];
};
static_assert(sizeof(Vertex) == 60, "Unexpected probe vertex stride");
static_assert(offsetof(Vertex, color) == 12 &&
              offsetof(Vertex, normal) == 16 &&
              offsetof(Vertex, tangent) == 28 &&
              offsetof(Vertex, bitangent) == 40 &&
              offsetof(Vertex, st) == 52,
              "Unexpected probe attribute offsets");
using Matrix = std::array<float, 16>;
inline Matrix Identity() {
    return {{1,0,0,0, 0,1,0,0, 0,0,1,0, 0,0,0,1}};
}
inline Matrix Multiply(const Matrix &a, const Matrix &b) {
    Matrix out{};
    for (int c = 0; c < 4; ++c)
        for (int r = 0; r < 4; ++r)
            for (int k = 0; k < 4; ++k)
                out[c*4+r] += a[k*4+r] * b[c*4+k];
    return out;
}
inline Matrix Projection() {
    const float f = 1.0f / std::tan(0.55f), n = 0.1f, z = 32.0f;
    Matrix m{};
    m[0] = f / (960.0f / 544.0f); m[5] = f;
    m[10] = (z+n)/(n-z); m[11] = -1.0f; m[14] = 2*z*n/(n-z);
    return m;
}
inline Matrix CubeModel(float angle) {
    Matrix m = Identity();
    m[0] = m[10] = std::cos(angle);
    m[2] = -std::sin(angle); m[8] = std::sin(angle);
    m[13] = -0.25f; m[14] = -4.2f;
    return m;
}
struct Scene {
    std::array<Vertex, 28> vertices{};
    std::array<std::uint16_t, 42> indices{};
};
constexpr int CubeIndexCount = 36;
constexpr int FloorFirstIndex = 36;
constexpr int FloorIndexCount = 6;
inline Scene MakeScene() {
    const float h = 0.75f;
    const float p[7][4][3] = {
        {{-h,-h,h},{h,-h,h},{h,h,h},{-h,h,h}},
        {{h,-h,-h},{-h,-h,-h},{-h,h,-h},{h,h,-h}},
        {{h,-h,h},{h,-h,-h},{h,h,-h},{h,h,h}},
        {{-h,-h,-h},{-h,-h,h},{-h,h,h},{-h,h,-h}},
        {{-h,h,h},{h,h,h},{h,h,-h},{-h,h,-h}},
        {{-h,-h,-h},{h,-h,-h},{h,-h,h},{-h,-h,h}},
        {{-4,-1.1f,-2},{4,-1.1f,-2},{4,-1.1f,-16},{-4,-1.1f,-16}}
    };
    const unsigned char colors[7][3] = {
        {245,140,65},{80,180,245},{240,195,65},{80,225,140},
        {195,115,250},{90,155,190},{220,225,235}
    };
    const float normals[7][3] = {
        {0,0,1},{0,0,-1},{1,0,0},{-1,0,0},{0,1,0},{0,-1,0},{0,1,0}
    };
    const float tangents[7][3] = {
        {1,0,0},{-1,0,0},{0,0,-1},{0,0,1},{1,0,0},{1,0,0},{1,0,0}
    };
    const float bitangents[7][3] = {
        {0,1,0},{0,1,0},{0,1,0},{0,1,0},{0,0,-1},{0,0,1},{0,0,-1}
    };
    const float uv[4][2] = {{0,0},{1,0},{1,1},{0,1}};
    const int local[6] = {0,1,2,0,2,3};
    Scene result;
    for (int face = 0; face < 7; ++face) {
        for (int v = 0; v < 4; ++v) {
            Vertex &out = result.vertices[face*4+v];
            for (int c = 0; c < 3; ++c) {
                out.xyz[c] = p[face][v][c];
                out.color[c] = colors[face][c];
                out.normal[c] = normals[face][c];
                out.tangent[c] = tangents[face][c];
                out.bitangent[c] = bitangents[face][c];
            }
            out.color[3] = 255;
            out.st[0] = uv[v][0] * (face == 6 ? 8.0f : 1.0f);
            out.st[1] = uv[v][1] * (face == 6 ? 16.0f : 1.0f);
        }
        for (int i = 0; i < 6; ++i)
            result.indices[face*6+i] = static_cast<std::uint16_t>(face*4+local[i]);
    }
    return result;
}
}
