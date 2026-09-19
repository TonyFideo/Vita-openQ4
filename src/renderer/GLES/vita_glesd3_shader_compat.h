#ifndef __VITA_GLESD3_SHADER_COMPAT_H__
#define __VITA_GLESD3_SHADER_COMPAT_H__

#include <string>

#if defined(VITA) || defined(__vita__)
#include <vitaGL.h>

// Converts the GLES 3.0 declaration syntax used by OpenQ4's Android GLES_D3
// shaders into the GLSL form understood by VitaGL's GLSL-to-Cg translator.
// Shader math, uniforms, varyings and material logic remain unchanged.
std::string Vita_GLESD3_NormalizeShaderSource( const char *source, GLenum stage );
#endif

#endif
