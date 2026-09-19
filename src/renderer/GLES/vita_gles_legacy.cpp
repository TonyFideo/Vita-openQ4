// Copyright (C) 2026
//
// Link-time compatibility for the shared idTech 4 GL front end on VitaGL.

#ifdef OPENQ4_RENDERER_GLES_MODULE

#include "../../idlib/precompiled.h"
#pragma hdrstop

#include "qgl_vita.h"

PFN_VITA_LEGACY_VOID glProgramStringARB = NULL;
PFN_VITA_LEGACY_VOID glBindProgramARB = NULL;
PFN_VITA_LEGACY_VOID glProgramEnvParameter4fvARB = NULL;
PFN_VITA_LEGACY_VOID glProgramLocalParameter4fvARB = NULL;
PFN_VITA_LEGACY_VOID glGetObjectParameterivARB = NULL;
PFN_VITA_LEGACY_VOID glGetInfoLogARB = NULL;

PFN_VITA_COMPRESSED_TEX_SUB_IMAGE_2D glCompressedTexSubImage2DARB = NULL;

GLboolean glewExperimental = GL_FALSE;

GLenum glewInit( void ) {
	// There is no desktop loader on Vita. vitaGL's exported functions are
	// linked directly, while unsupported legacy entry points above remain NULL.
	return GLEW_OK;
}

const GLubyte *glewGetErrorString( GLenum error ) {
	(void)error;
	return reinterpret_cast<const GLubyte *>( "vitaGL static dispatch" );
}

void GL_APIENTRY glDeleteObjectARB( GLhandleARB obj ) {
	(void)obj;
}

void GL_APIENTRY glDetachObjectARB( GLhandleARB containerObj, GLhandleARB attachedObj ) {
	(void)containerObj;
	(void)attachedObj;
}

void Vita_GLES_DrawBuffer( GLenum buffer ) {
	// VitaGL currently exposes one colour output per framebuffer. The default
	// backbuffer and COLOR_ATTACHMENT0 require no routing call. GL_NONE is
	// likewise represented by the pass state rather than an MRT draw mask.
	// Multi-attachment rendering stays disabled via GLEW_ARB_draw_buffers=0.
	(void)buffer;
}

#endif
