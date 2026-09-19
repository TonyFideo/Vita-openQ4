// Copyright (C) 2026
//
// VitaGL dispatch bridge for the OpenQ4 GLES_D3 backend.
//
// The shared idTech 4 front end still speaks a mixture of core GL, ARB-era
// spellings and GLEW capability variables. VitaGL already implements most of
// the useful compatibility surface, so this header aliases those calls to
// VitaGL and deliberately reports the obsolete ARB2/ATI program paths absent.

#ifndef __QGL_VITA_H__
#define __QGL_VITA_H__

#include <vitaGL.h>
#include <stddef.h>

#ifdef __cplusplus
extern "C" {
#endif

#ifndef GL_APIENTRY
#define GL_APIENTRY
#endif
#ifndef GLAPIENTRY
#define GLAPIENTRY GL_APIENTRY
#endif
#ifndef APIENTRY
#define APIENTRY GL_APIENTRY
#endif

typedef unsigned int GLhandleARB;
typedef char GLcharARB;
typedef ptrdiff_t GLsizeiptrARB;
typedef ptrdiff_t GLintptrARB;

#ifndef GLEW_OK
#define GLEW_OK 0
#endif

/*
===============================================================================
	GLEW feature predicates used by the shared renderer.

	These describe the VitaGL API contract, not a desktop driver version.
===============================================================================
*/
#define GLEW_ARB_vertex_buffer_object 1
#define GLEW_ARB_framebuffer_object 1
#define GLEW_EXT_framebuffer_object 1
#define GLEW_EXT_framebuffer_blit 1
// VitaGL exposes a single colour attachment today. Keep MRT disabled rather
// than query GL_MAX_DRAW_BUFFERS, which VitaGL does not expose.
#define GLEW_ARB_draw_buffers 0
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

/*
===============================================================================
	Enum compatibility.
===============================================================================
*/
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
#ifndef GL_STREAM_READ_ARB
#define GL_STREAM_READ_ARB GL_STREAM_READ
#endif
#ifndef GL_PIXEL_PACK_BUFFER_ARB
#define GL_PIXEL_PACK_BUFFER_ARB GL_PIXEL_PACK_BUFFER
#endif
#ifndef GL_TEXTURE0_ARB
#define GL_TEXTURE0_ARB GL_TEXTURE0
#endif
#ifndef GL_MAX_TEXTURE_UNITS_ARB
#define GL_MAX_TEXTURE_UNITS_ARB 0x84E2
#endif
#ifndef GL_MAX_TEXTURE_COORDS_ARB
#define GL_MAX_TEXTURE_COORDS_ARB GL_MAX_TEXTURE_COORDS
#endif
#ifndef GL_MAX_TEXTURE_IMAGE_UNITS_ARB
#define GL_MAX_TEXTURE_IMAGE_UNITS_ARB GL_MAX_TEXTURE_IMAGE_UNITS
#endif
#ifndef GL_MAX_DRAW_BUFFERS_ARB
#define GL_MAX_DRAW_BUFFERS_ARB 0x8824
#endif
#ifndef GL_MAX_COLOR_ATTACHMENTS_EXT
#define GL_MAX_COLOR_ATTACHMENTS_EXT GL_MAX_COLOR_ATTACHMENTS
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
#ifndef GL_VERTEX_PROGRAM_ARB
#define GL_VERTEX_PROGRAM_ARB 0x8620
#endif
#ifndef GL_FRAGMENT_PROGRAM_ARB
#define GL_FRAGMENT_PROGRAM_ARB 0x8804
#endif
#ifndef GL_TEXTURE_CUBE_MAP_SEAMLESS
#define GL_TEXTURE_CUBE_MAP_SEAMLESS 0x884F
#endif
#ifndef GL_STENCIL_INDEX
#define GL_STENCIL_INDEX 0x1901
#endif

#ifndef GL_CONTEXT_FLAGS
#define GL_CONTEXT_FLAGS 0x821E
#endif
#ifndef GL_CONTEXT_PROFILE_MASK
#define GL_CONTEXT_PROFILE_MASK 0x9126
#endif
#ifndef GL_CONTEXT_CORE_PROFILE_BIT
#define GL_CONTEXT_CORE_PROFILE_BIT 0x00000001
#endif
#ifndef GL_CONTEXT_COMPATIBILITY_PROFILE_BIT
#define GL_CONTEXT_COMPATIBILITY_PROFILE_BIT 0x00000002
#endif
#ifndef GL_CONTEXT_FLAG_FORWARD_COMPATIBLE_BIT
#define GL_CONTEXT_FLAG_FORWARD_COMPATIBLE_BIT 0x00000001
#endif
#ifndef GL_CONTEXT_FLAG_DEBUG_BIT
#define GL_CONTEXT_FLAG_DEBUG_BIT 0x00000002
#endif

/*
===============================================================================
	ARB spellings that map directly to VitaGL.
===============================================================================
*/
#define glActiveTextureARB glActiveTexture
#define glAttachObjectARB glAttachShader
#define glBindAttribLocationARB glBindAttribLocation
#define glBindBufferARB glBindBuffer
#define glBufferDataARB glBufferData
#define glBufferSubDataARB glBufferSubData
#define glCompileShaderARB glCompileShader
#define glCompressedTexImage2DARB glCompressedTexImage2D
#define glCreateProgramObjectARB glCreateProgram
#define glCreateShaderObjectARB glCreateShader
#define glDeleteBuffersARB glDeleteBuffers
#define glDisableVertexAttribArrayARB glDisableVertexAttribArray
#define glEnableVertexAttribArrayARB glEnableVertexAttribArray
#define glGenBuffersARB glGenBuffers
#define glGetUniformLocationARB glGetUniformLocation
#define glLinkProgramARB glLinkProgram
#define glMapBufferARB glMapBuffer
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

// VitaGL implements these fixed-function compatibility calls directly.
#define glClientActiveTextureARB glClientActiveTexture
#define glMultiTexCoord2fARB glMultiTexCoord2f

/*
===============================================================================
	Unavailable API expressed as NULL pointers.

	RenderSystem_init.cpp probes these with != NULL. A non-NULL no-op would
	falsely advertise ARB2 or legacy GLSL and make the renderer choose a path
	that VitaGL must never execute.
===============================================================================
*/
typedef void ( GL_APIENTRY *PFN_VITA_LEGACY_VOID )( void );

extern PFN_VITA_LEGACY_VOID glProgramStringARB;
extern PFN_VITA_LEGACY_VOID glBindProgramARB;
extern PFN_VITA_LEGACY_VOID glProgramEnvParameter4fvARB;
extern PFN_VITA_LEGACY_VOID glProgramLocalParameter4fvARB;
extern PFN_VITA_LEGACY_VOID glGetObjectParameterivARB;
extern PFN_VITA_LEGACY_VOID glGetInfoLogARB;

typedef void ( GL_APIENTRY *PFN_VITA_COMPRESSED_TEX_SUB_IMAGE_2D )(
	GLenum target, GLint level, GLint xoffset, GLint yoffset,
	GLsizei width, GLsizei height, GLenum format,
	GLsizei imageSize, const void *data );
extern PFN_VITA_COMPRESSED_TEX_SUB_IMAGE_2D glCompressedTexSubImage2DARB;

// ARB shader objects do not map cleanly onto VitaGL's separate shader/program
// namespaces. They are only part of the disabled legacy probe.
void GL_APIENTRY glDeleteObjectARB( GLhandleARB obj );
void GL_APIENTRY glDetachObjectARB( GLhandleARB containerObj, GLhandleARB attachedObj );

/*
===============================================================================
	Small front-end shims.
===============================================================================
*/
void Vita_GLES_DrawBuffer( GLenum buffer );
#define glDrawBuffer Vita_GLES_DrawBuffer

extern GLboolean glewExperimental;
GLenum glewInit( void );
const GLubyte *glewGetErrorString( GLenum error );

#ifdef __cplusplus
}
#endif

#endif
