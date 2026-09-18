#include "vita_renderer_smoke.h"

#include <vitaGL.h>

#include <psp2/kernel/clib.h>
#include <psp2/io/fcntl.h>
#include <psp2/kernel/threadmgr/thread.h>

#include <stdint.h>

namespace {

const char *kRendererLog = "ux0:data/Vita-OpenQ4/logs/prerender.log";
uint64_t rendererFrame = 0;

static void RendererLog( const char *text ) {
	if ( text == NULL ) {
		return;
	}
	SceUID fd = sceIoOpen( kRendererLog, SCE_O_WRONLY | SCE_O_CREAT | SCE_O_APPEND, 0666 );
	if ( fd < 0 ) {
		return;
	}
	const SceSize length = static_cast<SceSize>( sceClibStrnlen( text, 1024 ) );
	if ( length > 0 ) {
		sceIoWrite( fd, text, length );
	}
	sceIoWrite( fd, "\n", 1 );
	sceIoClose( fd );
}

static bool CheckGl( const char *stage ) {
	const GLenum error = glGetError();
	if ( error == GL_NO_ERROR ) {
		return true;
	}
	char line[160];
	sceClibSnprintf(
		line,
		sizeof( line ),
		"renderer.gl_error stage=%s code=0x%04x",
		stage != NULL ? stage : "unknown",
		static_cast<unsigned int>( error ) );
	RendererLog( line );
	return false;
}

static void DrawMovingQuad( float offset ) {
	glBegin( GL_QUADS );
		glColor3f( 0.10f, 0.45f, 1.00f );
		glVertex3f( 260.0f + offset, 170.0f, 0.0f );

		glColor3f( 0.10f, 1.00f, 0.45f );
		glVertex3f( 700.0f + offset, 170.0f, 0.0f );

		glColor3f( 1.00f, 0.85f, 0.10f );
		glVertex3f( 700.0f + offset, 374.0f, 0.0f );

		glColor3f( 0.95f, 0.15f, 0.55f );
		glVertex3f( 260.0f + offset, 374.0f, 0.0f );
	glEnd();
}

static void DrawScissorProbe( int x, int y, float r, float g, float b ) {
	glEnable( GL_SCISSOR_TEST );
	glScissor( x, y, 48, 48 );
	glClearColor( r, g, b, 1.0f );
	glClear( GL_COLOR_BUFFER_BIT );
	glDisable( GL_SCISSOR_TEST );
}

}

bool VitaRendererSmoke_Init( void ) {
	RendererLog( "renderer.stage=vitagl-init-begin" );

	// Keep the first renderer bring-up deliberately minimal: no legacy immediate
	// pool reservation and no MSAA. This avoids exercising extra GXM resources
	// before we know the base context/present path is stable on hardware/Vita3K.
	const GLboolean vglReady = vglInitExtended(
		0,
		960,
		544,
		8 * 1024 * 1024,
		SCE_GXM_MULTISAMPLE_NONE );
	if ( vglReady != GL_TRUE ) {
		RendererLog( "renderer.stage=vitagl-init-returned-false" );
		return false;
	}
	RendererLog( "renderer.stage=vitagl-context-created" );

	glViewport( 0, 0, 960, 544 );
	glDisable( GL_DEPTH_TEST );
	glDisable( GL_STENCIL_TEST );
	glDisable( GL_CULL_FACE );
	glDisable( GL_BLEND );

	glMatrixMode( GL_PROJECTION );
	glLoadIdentity();
	glOrtho( 0.0, 960.0, 544.0, 0.0, -1.0, 1.0 );
	glMatrixMode( GL_MODELVIEW );
	glLoadIdentity();

	glClearColor( 0.015f, 0.020f, 0.040f, 1.0f );
	glClear( GL_COLOR_BUFFER_BIT );

	if ( !CheckGl( "init" ) ) {
		RendererLog( "renderer.stage=vitagl-init-failed" );
		return false;
	}

	vglSwapBuffers( GL_FALSE );
	RendererLog( "renderer.stage=vitagl-init-ok" );
	RendererLog( "renderer.test=immediate-quad+scissor+swap" );
	return true;
}

void VitaRendererSmoke_Run( void ) {
	RendererLog( "renderer.stage=frame-loop-enter" );

	for ( ;; ) {
		const int phase = static_cast<int>( rendererFrame % 240ULL );
		const float triangular =
			phase < 120 ? static_cast<float>( phase ) : static_cast<float>( 240 - phase );
		const float offset = ( triangular - 60.0f ) * 0.45f;

		glViewport( 0, 0, 960, 544 );
		glDisable( GL_SCISSOR_TEST );
		glClearColor( 0.015f, 0.020f, 0.040f, 1.0f );
		glClear( GL_COLOR_BUFFER_BIT );

		glMatrixMode( GL_MODELVIEW );
		glLoadIdentity();
		DrawMovingQuad( offset );

		// Four small clears validate scissor coordinates independently from the
		// immediate-mode geometry path.
		DrawScissorProbe( 16, 16, 0.85f, 0.10f, 0.10f );
		DrawScissorProbe( 896, 16, 0.10f, 0.85f, 0.10f );
		DrawScissorProbe( 16, 480, 0.10f, 0.25f, 0.95f );
		DrawScissorProbe( 896, 480, 0.95f, 0.80f, 0.10f );

		if ( rendererFrame == 0 ) {
			const bool firstFrameOk = CheckGl( "first-frame" );
			RendererLog( firstFrameOk ? "renderer.first_frame=ok" : "renderer.first_frame=error" );
		}

		vglSwapBuffers( GL_FALSE );
		++rendererFrame;

		if ( rendererFrame == 60 ) {
			RendererLog( "renderer.presented_60_frames=1" );
		}
	}
}
