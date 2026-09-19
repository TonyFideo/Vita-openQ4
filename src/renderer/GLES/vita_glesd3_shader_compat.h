#ifndef __VITA_GLESD3_SHADER_COMPAT_H__
#define __VITA_GLESD3_SHADER_COMPAT_H__

#include <string>

// Converts the GLES 3.0 declaration/sampling syntax used by OpenQ4's GLES_D3
// shaders into the GLSL form understood by VitaGL's GLSL-to-Cg translator.
// Kept platform-neutral so the transformation can be regression-tested on host.
std::string Vita_GLESD3_NormalizeShaderSource( const char *source, unsigned int stage );

#endif
