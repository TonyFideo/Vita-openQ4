#include "../../idlib/precompiled.h"
#pragma hdrstop

#include "../../renderer/tr_local.h"
#include "../../renderer/RenderModuleAPI.h"
#include "vita_public.h"
#include "vita_loading_hud.h"
#include "vita_runtime_audit.h"
#include <psp2/kernel/processmgr.h>

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

static void VitaGLimp_PrimeImagePolicy( void ) {
	// ImageManager::Init runs before the user's configs are applied. The first
	// upload after this context initialization already uses those config values;
	// leaving their modified bits set makes the first BeginFrame reload all
	// images again. Prime only at context initialization/restart, never per frame,
	// so later console/config changes continue to trigger CheckCvars normally.
	if ( globalImages != NULL ) {
		globalImages->PrimeCvars();
		VitaLoadingHud_SetCheckpoint( "IMAGE policy primed before upload" );
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


#ifndef GL_READ_BUFFER
#define GL_READ_BUFFER 0x0C02
#endif

// BEGIN VITA CLEAR AUDIT
// A bounded observer, not a replacement glClear or an alternative renderer.
// Readbacks serialize GXM and can affect timing; the log is evidence about the
// observed frame only. The untouched frames between samples remain essential.
extern "C" void __real_glClear(GLbitfield mask);
static bool vitaClearAuditStarted = false;
static unsigned vitaClearAuditSamples = 0;
static uint64_t vitaClearAuditNext = 0;
static bool vitaClearAuditPresent = false;

void VitaRuntimeAudit_Start() {
    vitaClearAuditStarted = true;
    vitaClearAuditSamples = 0;
    vitaClearAuditNext = 0;
}

bool VitaRuntimeAudit_GpuFree(size_t freeBytes[3]) {
    if (!vitaGLReady) return false;
    freeBytes[0] = vglMemFree(VGL_MEM_RAM);
    freeBytes[1] = vglMemFree(VGL_MEM_VRAM);
    freeBytes[2] = vglMemFree(VGL_MEM_PHYCONT);
    return true;
}

static void VitaClearAuditPixels(const char *phase, unsigned sample) {
    // Only called for the default RGBA8 framebuffer. VitaGL's half-float
    // readback path has different restrictions; do not probe it as RGBA8.
    GLint previousRead = 0, displayReadBuffer = GL_BACK;
    glGetIntegerv(GL_READ_FRAMEBUFFER_BINDING, &previousRead);
    glBindFramebuffer(GL_READ_FRAMEBUFFER, 0);
    glGetIntegerv(GL_READ_BUFFER, &displayReadBuffer);
    glReadBuffer(GL_BACK);
    const int x[5] = {48, 480, 912, 48, 912};
    const int y[5] = {272, 272, 272, 490, 54};
    GLubyte pixel[5][4] = {};
    for (int i = 0; i < 5; ++i)
        glReadPixels(x[i], y[i], 1, 1, GL_RGBA, GL_UNSIGNED_BYTE, pixel[i]);
    glReadBuffer((GLenum)displayReadBuffer);
    glBindFramebuffer(GL_READ_FRAMEBUFFER, (GLuint)previousRead);
    sceClibPrintf("[VOQ4][clear-audit] sample=%u phase=%s "
        "L=%u,%u,%u,%u C=%u,%u,%u,%u R=%u,%u,%u,%u "
        "TL=%u,%u,%u,%u BR=%u,%u,%u,%u\n", sample, phase,
        pixel[0][0],pixel[0][1],pixel[0][2],pixel[0][3],
        pixel[1][0],pixel[1][1],pixel[1][2],pixel[1][3],
        pixel[2][0],pixel[2][1],pixel[2][2],pixel[2][3],
        pixel[3][0],pixel[3][1],pixel[3][2],pixel[3][3],
        pixel[4][0],pixel[4][1],pixel[4][2],pixel[4][3]);
}

extern "C" void __wrap_glClear(GLbitfield mask) {
    if (!vitaClearAuditStarted || vitaClearAuditSamples >= 12 ||
        !(mask & GL_COLOR_BUFFER_BIT)) {
        __real_glClear(mask);
        return;
    }
    const uint64_t now = sceKernelGetProcessTimeWide();
    GLint drawFbo = 0;
    glGetIntegerv(GL_FRAMEBUFFER_BINDING, &drawFbo);
    if (drawFbo != 0 || now < vitaClearAuditNext) {
        __real_glClear(mask);
        return;
    }
    const unsigned sample = ++vitaClearAuditSamples;
    vitaClearAuditNext = now + 5000000u;
    GLboolean writeMask[4] = {};
    GLfloat clearColor[4] = {};
    GLint scissor[4] = {};
    glGetBooleanv(GL_COLOR_WRITEMASK, writeMask);
    glGetFloatv(GL_COLOR_CLEAR_VALUE, clearColor);
    glGetIntegerv(GL_SCISSOR_BOX, scissor);
    sceClibPrintf("[VOQ4][clear-audit] sample=%u drawFbo=%d mask=0x%x "
        "rgba=%.3f,%.3f,%.3f,%.3f writes=%u%u%u%u scissor=%d box=%d,%d,%d,%d\n",
        sample, drawFbo, (unsigned)mask, (double)clearColor[0],
        (double)clearColor[1], (double)clearColor[2], (double)clearColor[3],
        writeMask[0],writeMask[1],writeMask[2],writeMask[3],
        glIsEnabled(GL_SCISSOR_TEST) != GL_FALSE,
        scissor[0],scissor[1],scissor[2],scissor[3]);
    // Alternate before+after and after-only to expose readback-induced changes.
    if (sample & 1u) VitaClearAuditPixels("before", sample);
    __real_glClear(mask);
    VitaClearAuditPixels("after", sample);
    vitaClearAuditPresent = true;
}

static void VitaClearAuditBeforePresent() {
    if (!vitaClearAuditPresent) return;
    vitaClearAuditPresent = false;
    VitaClearAuditPixels("present", vitaClearAuditSamples);
}
// END VITA CLEAR AUDIT

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
		VitaGLimp_PrimeImagePolicy();
		return true;
	}

	VitaGLimp_Log( "initializing VitaGL context 960x544" );

	// Match the validated prerender handoff: stop CPU writes to the native
	// diagnostic framebuffer before GXM/VitaGL initialization, but retain its
	// CDRAM backing until VitaGL has presented its first replacement frame.
	VitaLoadingHud_BeginRendererHandoff();

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

	const bool rendererValid = glGetString( GL_VERSION ) != NULL;
	if ( rendererValid ) {
		VitaGLimp_PrimeImagePolicy();
		VitaLoadingHud_RendererInitialized();
	} else {
		VitaLoadingHud_LogError( "VitaGL no devolvio GL_VERSION" );
	}
	return rendererValid;
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
		VitaClearAuditBeforePresent();
		vglSwapBuffers( GL_FALSE );
		if ( !VitaLoadingHud_RendererHandoffComplete() ) {
			// Retry until SceDisplay itself confirms that the old diagnostic
			// framebuffer is no longer current.  This is an ownership check, not
			// a timing delay, and is equally valid on hardware and Vita3K.
			VitaLoadingHud_EndRendererHandoff();
		}
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


/*
===================
Sys_GetRenderWindowServices

Vita uses a single native VitaGL display and has no detachable desktop window
service table. This matches the native Win32/Linux/macOS backends: the static
renderer receives NULL and keeps ownership in the platform GLimp layer.
===================
*/
const renderWindowServices_t *Sys_GetRenderWindowServices( void ) {
	return NULL;
}
