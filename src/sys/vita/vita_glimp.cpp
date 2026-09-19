#include "../../idlib/precompiled.h"
#pragma hdrstop

#include "../../renderer/tr_local.h"
#include "vita_public.h"

#include <vitaGL.h>

#include <psp2/gxm.h>
#include <psp2/kernel/clib.h>
#include <psp2/kernel/sysmem.h>

namespace {

static bool vitaGLReady = false;
static bool vitaGLLogging = false;

static void VitaGLimp_Log( const char *message ) {
	if ( message == NULL ) {
		return;
	}
	sceClibPrintf( "[VOQ4][glimp] %s\n", message );
	if ( common != NULL ) {
		common->Printf( "VitaGL: %s\n", message );
	}
}

static int VitaGLimp_FreeCdramBytes( void ) {
	SceKernelFreeMemorySizeInfo freeMemory = {};
	freeMemory.size = sizeof( freeMemory );
	if ( sceKernelGetFreeMemorySize( &freeMemory ) < 0 ) {
		return 128 * 1024 * 1024;
	}
	return static_cast<int>( freeMemory.size_cdram );
}

}

/*
===================
GLimp_Init

The Vita renderer owns one process-wide VitaGL/GXM context. During bring-up we
keep it alive across renderer restarts instead of trying to tear down and
reinitialize GXM, which vitaGL does not expose as a supported lifecycle.
===================
*/
bool GLimp_Init( glimpParms_t parms ) {
	(void)parms;

	if ( vitaGLReady ) {
		glConfig.vidWidth = 960;
		glConfig.vidHeight = 544;
		glConfig.isFullscreen = true;
		engineWindowState.vidWidth = 960;
		engineWindowState.vidHeight = 544;
		VitaGLimp_Log( "reusing existing VitaGL context" );
		return true;
	}

	VitaGLimp_Log( "initializing VitaGL context 960x544" );

	// Match the stable smoke-test configuration and the transient-pool sizing
	// used by the Vita idTech 4 reference path.
	vglSetCircularPoolSize( 3 * 1024 * 1024 );
	vglSetParamBufferSize( 14 * 1024 * 1024 );

	const int ramThreshold = 10 * 1024 * 1024;
	const int cdramThreshold = VitaGLimp_FreeCdramBytes();
	const int phycontThreshold = 0;
	const int commonDialogThreshold = 0x8C6000;

	// vitaGL returns whether it had to fall back from the requested resolution;
	// GL_FALSE is the normal success value when 960x544 was accepted.
	const GLboolean resolutionFallback = vglInitWithCustomThreshold(
		0,
		960,
		544,
		ramThreshold,
		cdramThreshold,
		phycontThreshold,
		commonDialogThreshold,
		SCE_GXM_MULTISAMPLE_NONE );

	vitaGLReady = true;
	vglWaitVblankStart( GL_TRUE );

	glConfig.vidWidth = 960;
	glConfig.vidHeight = 544;
	glConfig.isFullscreen = true;
	engineWindowState.vidWidth = 960;
	engineWindowState.vidHeight = 544;

	if ( resolutionFallback == GL_TRUE ) {
		VitaGLimp_Log( "VitaGL reported a resolution fallback" );
	} else {
		VitaGLimp_Log( "VitaGL initialized at requested resolution" );
	}

	return glGetString( GL_VERSION ) != NULL;
}

bool GLimp_SetScreenParms( glimpParms_t parms ) {
	(void)parms;
	// Vita has one native display mode. Keep renderer-visible state pinned to it.
	glConfig.vidWidth = 960;
	glConfig.vidHeight = 544;
	glConfig.isFullscreen = true;
	engineWindowState.vidWidth = 960;
	engineWindowState.vidHeight = 544;
	return vitaGLReady;
}

void GLimp_Shutdown( void ) {
	if ( !vitaGLReady ) {
		return;
	}

	// vitaGL currently has no public context-destruction counterpart to vglInit.
	// Synchronize outstanding work and intentionally keep the context alive so a
	// same-process vid_restart can reuse it safely.
	glFinish();
	sceGxmDisplayQueueFinish();
	VitaGLimp_Log( "renderer shutdown synchronized; VitaGL context retained" );
}

void GLimp_PreserveWindowOnShutdown( bool preserve ) {
	(void)preserve;
}

void GLimp_SwapBuffers( void ) {
	if ( vitaGLReady ) {
		vglSwapBuffers( GL_FALSE );
	}
}

void GLimp_SetGamma( unsigned short red[256], unsigned short green[256], unsigned short blue[256] ) {
	(void)red;
	(void)green;
	(void)blue;
}

bool GLimp_UseNativeGammaRamps( void ) {
	return false;
}

bool GLimp_SpawnRenderThread( void (*function)( void ) ) {
	(void)function;
	// Keep GL submission on the main thread until the complete renderer is stable.
	return false;
}

void *GLimp_BackEndSleep( void ) {
	return NULL;
}

void GLimp_FrontEndSleep( void ) {
}

void GLimp_WakeBackEnd( void *data ) {
	(void)data;
}

void GLimp_ActivateContext( void ) {
}

bool GLimp_EnsureActiveContext( const char *operation ) {
	if ( !vitaGLReady ) {
		if ( common != NULL ) {
			common->Printf( "VitaGL: no active context for %s\n", operation != NULL ? operation : "operation" );
		}
		return false;
	}
	return true;
}

void GLimp_DeactivateContext( void ) {
	// VitaGL exposes a single process-wide context; there is no make-current
	// transition to perform for the single-threaded Vita renderer.
}

void GLimp_EnableLogging( bool enable ) {
	vitaGLLogging = enable;
	(void)vitaGLLogging;
}

void *GLimp_ExtensionPointer( const char *name ) {
	return name != NULL ? vglGetProcAddress( name ) : NULL;
}
