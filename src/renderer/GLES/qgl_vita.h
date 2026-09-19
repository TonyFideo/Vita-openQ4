// Copyright (C) 2026
//
// VitaGL dispatch bridge for the OpenQ4 GLES_D3 backend.
//
// Android uses Khronos GLES3 headers. Vita exposes the GL-compatible API
// through vitaGL.h, so this header supplies the legacy ARB spellings used by
// the shared idTech 4 renderer without pulling desktop GLEW into the Vita build.

#ifndef __QGL_VITA_H__
#define __QGL_VITA_H__

#include <vitaGL.h>
#include <stddef.h>

#ifndef GL_APIENTRY
#define GL_APIENTRY
#endif
#ifndef GLAPIENTRY
#define GLAPIENTRY
#endif
#ifndef APIENTRY
#define APIENTRY
#endif

typedef unsigned int GLhandleARB;
typedef char GLcharARB;
typedef ptrdiff_t GLsizeiptrARB;
typedef ptrdiff_t GLintptrARB;

#ifndef GLEW_OK
#define GLEW_OK 0
#endif

#define GLEW_ARB_vertex_buffer_object 1
#define GLEW_ARB_framebuffer_object 1
#define GLEW_EXT_framebuffer_object 1
#define GLEW_EXT_framebuffer_blit 1
#define GLEW_ARB_draw_buffers 1
#define GLEW_ARB_pixel_buffer_object 1
#define GLEW_EXT_pixel_buffer_object 1
#define GLEW_EXT_texture_sRGB 1
#define GLEW_VERSION_2_1 1
#define GLEW_VERSION_3_0 1
#define GLEW_VERSION_3_2 0
#define GLEW_ARB_framebuffer_sRGB 0
#define GLEW_EXT_framebuffer_sRGB 0
#define GLEW_ARB_seamless_cube_map 0
#define GLEW_ARB_texture_cube_map_array 0
#define GLEW_ARB_texture_multisample 0
#define GLEW_EXT_direct_state_access 0

#ifndef GL_ARRAY_BUFFER_ARB
#define GL_ARRAY_BUFFER_ARB GL_ARRAY_BUFFER
#endif
#ifndef GL_ELEMENT_ARRAY_BUFFER_ARB
#define GL_ELEMENT_ARRAY_BUFFER_ARB GL_ELEMENT_ARRAY_BUFFER
#endif
#ifndef GL_STATIC_DRAW_ARB
#define GL_STATIC_DRAW_ARB GL_STATIC_DRAW
#endif
#ifndef GL_STREAM_DRAW_ARB
#define GL_STREAM_DRAW_ARB GL_STREAM_DRAW
#endif
#ifndef GL_PIXEL_PACK_BUFFER_ARB
#define GL_PIXEL_PACK_BUFFER_ARB GL_PIXEL_PACK_BUFFER
#endif
#ifndef GL_TEXTURE0_ARB
#define GL_TEXTURE0_ARB GL_TEXTURE0
#endif
#ifndef GL_INCR_WRAP_EXT
#define GL_INCR_WRAP_EXT GL_INCR_WRAP
#endif
#ifndef GL_DECR_WRAP_EXT
#define GL_DECR_WRAP_EXT GL_DECR_WRAP
#endif
#ifndef GL_TEXTURE_CUBE_MAP_EXT
#define GL_TEXTURE_CUBE_MAP_EXT GL_TEXTURE_CUBE_MAP
#endif
#ifndef GL_TEXTURE_CUBE_MAP_POSITIVE_X_EXT
#define GL_TEXTURE_CUBE_MAP_POSITIVE_X_EXT GL_TEXTURE_CUBE_MAP_POSITIVE_X
#endif
#ifndef GL_READ_ONLY_ARB
#define GL_READ_ONLY_ARB 0x88B8
#endif

#define glActiveTextureARB glActiveTexture
#define glAttachObjectARB glAttachShader
#define glBindAttribLocationARB glBindAttribLocation
#define glBindBufferARB glBindBuffer
#define glBufferDataARB glBufferData
#define glBufferSubDataARB glBufferSubData
#define glCompileShaderARB glCompileShader
#define glCompressedTexImage2DARB glCompressedTexImage2D
#define glCompressedTexSubImage2DARB glCompressedTexSubImage2D
#define glCreateProgramObjectARB glCreateProgram
#define glCreateShaderObjectARB glCreateShader
#define glDeleteBuffersARB glDeleteBuffers
#define glDetachObjectARB glDetachShader
#define glDisableVertexAttribArrayARB glDisableVertexAttribArray
#define glEnableVertexAttribArrayARB glEnableVertexAttribArray
#define glGenBuffersARB glGenBuffers
#define glGetUniformLocationARB glGetUniformLocation
#define glLinkProgramARB glLinkProgram
#define glShaderSourceARB glShaderSource
#define glUniform1fARB glUniform1f
#define glUniform1fvARB glUniform1fv
#define glUniform1iARB glUniform1i
#define glUniform2fvARB glUniform2fv
#define glUniform3fvARB glUniform3fv
#define glUniform4fvARB glUniform4fv
#define glUniformMatrix4fvARB glUniformMatrix4fv
#define glUnmapBufferARB glUnmapBuffer
#define glUseProgramObjectARB glUseProgram
#define glVertexAttribPointerARB glVertexAttribPointer

#endif
