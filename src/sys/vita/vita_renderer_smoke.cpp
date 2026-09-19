#include "vita_renderer_smoke.h"

#include <vitaGL.h>

#include <psp2/io/fcntl.h>
#include <psp2/kernel/clib.h>
#include <psp2/kernel/sysmem.h>

#include <stdint.h>

namespace {

const char *kRendererLog = "ux0:data/Vita-OpenQ4/logs/prerender.log";

uint64_t rendererFrame = 0;
GLuint smokeProgram = 0;
GLuint smokePositionBuffer = 0;
GLuint smokeFullScreenPositionBuffer = 0;
GLuint smokeColorBuffer = 0;

static void RendererLog( const char *text ) {
	if ( text == NULL ) {
		return;
	}

	// Mirror renderer checkpoints to stdout so Vita3K logs contain the actual
	// stage names instead of only sceIoWrite sizes.
	sceClibPrintf( "[VOQ4][renderer] %s\n", text );

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

static void RendererLogVitaGLMemory( const char *label ) {
	char line[192];
	sceClibSnprintf(
		line,
		sizeof( line ),
		"renderer.vitagl.mem.%s ram_free_kb=%llu vram_free_kb=%llu phycont_free_kb=%llu",
		label != NULL ? label : "unknown",
		static_cast<unsigned long long>( vglMemFree( VGL_MEM_RAM ) >> 10 ),
		static_cast<unsigned long long>( vglMemFree( VGL_MEM_VRAM ) >> 10 ),
		static_cast<unsigned long long>( vglMemFree( VGL_MEM_PHYCONT ) >> 10 ) );
	RendererLog( line );
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

static bool CheckShader( GLuint shader, const char *name ) {
	GLint status = GL_FALSE;
	glGetShaderiv( shader, GL_COMPILE_STATUS, &status );

	if ( status == GL_TRUE ) {
		char line[160];
		sceClibSnprintf(
			line,
			sizeof( line ),
			"renderer.shader.%s=compiled",
			name != NULL ? name : "unknown" );
		RendererLog( line );
		return true;
	}

	char line[160];
	sceClibSnprintf(
		line,
		sizeof( line ),
		"renderer.shader.%s=compile-failed",
		name != NULL ? name : "unknown" );
	RendererLog( line );

	GLchar infoLog[512] = {};
	GLsizei infoLength = 0;
	glGetShaderInfoLog( shader, sizeof( infoLog ) - 1, &infoLength, infoLog );
	if ( infoLength > 0 ) {
		infoLog[sizeof( infoLog ) - 1] = '\0';
		RendererLog( infoLog );
	}
	return false;
}

static bool CheckProgram( GLuint program ) {
	GLint status = GL_FALSE;
	glGetProgramiv( program, GL_LINK_STATUS, &status );
	if ( status == GL_TRUE ) {
		RendererLog( "renderer.program=linked" );
		return true;
	}

	RendererLog( "renderer.program=link-failed" );
	GLchar infoLog[512] = {};
	GLsizei infoLength = 0;
	glGetProgramInfoLog( program, sizeof( infoLog ) - 1, &infoLength, infoLog );
	if ( infoLength > 0 ) {
		infoLog[sizeof( infoLog ) - 1] = '\0';
		RendererLog( infoLog );
	}
	return false;
}

static bool CreateSmokeProgram( void ) {
	RendererLog( "renderer.stage=shader-create-begin" );

	static const GLchar *vertexSource =
		"float4 out vColor : TEXCOORD0; "
		"float4 out gl_Position : POSITION; "
		"void main(float2 VertexPosition, float4 VertexColor) { "
		"    vColor = VertexColor; "
		"    gl_Position = float4(VertexPosition, 0.0, 1.0); "
		"}";

	static const GLchar *fragmentSource =
		"float4 in vColor : TEXCOORD0; "
		"float4 main() : COLOR { "
		"    return vColor; "
		"}";

	const GLuint vertexShader = glCreateShader( GL_CG_VERTEX_SHADER_EXT );
	const GLuint fragmentShader = glCreateShader( GL_CG_FRAGMENT_SHADER_EXT );
	if ( vertexShader == 0 || fragmentShader == 0 ) {
		RendererLog( "renderer.stage=shader-handle-failed" );
		return false;
	}

	glShaderSource( vertexShader, 1, &vertexSource, NULL );
	glCompileShader( vertexShader );
	if ( !CheckShader( vertexShader, "vertex" ) ) {
		return false;
	}

	glShaderSource( fragmentShader, 1, &fragmentSource, NULL );
	glCompileShader( fragmentShader );
	if ( !CheckShader( fragmentShader, "fragment" ) ) {
		return false;
	}

	smokeProgram = glCreateProgram();
	if ( smokeProgram == 0 ) {
		RendererLog( "renderer.stage=program-handle-failed" );
		return false;
	}

	glAttachShader( smokeProgram, vertexShader );
	glAttachShader( smokeProgram, fragmentShader );
	glBindAttribLocation( smokeProgram, 0, "VertexPosition" );
	glBindAttribLocation( smokeProgram, 1, "VertexColor" );
	glLinkProgram( smokeProgram );
	if ( !CheckProgram( smokeProgram ) ) {
		return false;
	}

	glUseProgram( smokeProgram );
	glDeleteShader( vertexShader );
	glDeleteShader( fragmentShader );

	RendererLog( "renderer.stage=shader-create-ok" );
	return CheckGl( "shader-create" );
}

static bool CreateSmokeGeometry( void ) {
	RendererLog( "renderer.stage=geometry-create-begin" );

	// Two triangles in normalized device coordinates. This deliberately follows
	// the VBO + vertex-attrib path used by the GLES_D3 renderer instead of
	// VitaGL's legacy immediate mode.
	static const GLfloat positions[] = {
		-0.62f, -0.48f,
		 0.62f, -0.48f,
		 0.62f,  0.48f,
		-0.62f, -0.48f,
		 0.62f,  0.48f,
		-0.62f,  0.48f
	};

	static const GLfloat fullScreenPositions[] = {
		-1.0f, -1.0f,
		 1.0f, -1.0f,
		 1.0f,  1.0f,
		-1.0f, -1.0f,
		 1.0f,  1.0f,
		-1.0f,  1.0f
	};

	static const GLfloat colors[] = {
		0.10f, 0.45f, 1.00f, 1.00f,
		0.10f, 1.00f, 0.45f, 1.00f,
		1.00f, 0.85f, 0.10f, 1.00f,
		0.10f, 0.45f, 1.00f, 1.00f,
		1.00f, 0.85f, 0.10f, 1.00f,
		0.95f, 0.15f, 0.55f, 1.00f
	};

	glGenBuffers( 1, &smokePositionBuffer );
	glBindBuffer( GL_ARRAY_BUFFER, smokePositionBuffer );
	glBufferData( GL_ARRAY_BUFFER, sizeof( positions ), positions, GL_STATIC_DRAW );

	glGenBuffers( 1, &smokeFullScreenPositionBuffer );
	glBindBuffer( GL_ARRAY_BUFFER, smokeFullScreenPositionBuffer );
	glBufferData( GL_ARRAY_BUFFER, sizeof( fullScreenPositions ), fullScreenPositions, GL_STATIC_DRAW );

	glGenBuffers( 1, &smokeColorBuffer );
	glBindBuffer( GL_ARRAY_BUFFER, smokeColorBuffer );
	glBufferData( GL_ARRAY_BUFFER, sizeof( colors ), colors, GL_STATIC_DRAW );

	glBindBuffer( GL_ARRAY_BUFFER, 0 );

	if ( smokePositionBuffer == 0 || smokeFullScreenPositionBuffer == 0 || smokeColorBuffer == 0 ) {
		RendererLog( "renderer.stage=geometry-buffer-failed" );
		return false;
	}

	RendererLog( "renderer.stage=geometry-create-ok" );
	return CheckGl( "geometry-create" );
}

static void DrawSmokeGeometry( void ) {
	glUseProgram( smokeProgram );

	glEnableVertexAttribArray( 0 );
	glBindBuffer( GL_ARRAY_BUFFER, smokePositionBuffer );
	glVertexAttribPointer( 0, 2, GL_FLOAT, GL_FALSE, 0, reinterpret_cast<const GLvoid *>( 0 ) );

	glEnableVertexAttribArray( 1 );
	glBindBuffer( GL_ARRAY_BUFFER, smokeColorBuffer );
	glVertexAttribPointer( 1, 4, GL_FLOAT, GL_FALSE, 0, reinterpret_cast<const GLvoid *>( 0 ) );

	glDrawArrays( GL_TRIANGLES, 0, 6 );

	glDisableVertexAttribArray( 0 );
	glDisableVertexAttribArray( 1 );
	glBindBuffer( GL_ARRAY_BUFFER, 0 );
}

static void DrawScissorProbe( int x, int y ) {
	// Do not use glClear for this validation. On VitaGL the clear path has its
	// own internal shader/state handling; OpenQ4 primarily needs scissor to
	// constrain normal surface draws. A fullscreen draw clipped to a 64x64 box
	// tests that exact path.
	glEnable( GL_SCISSOR_TEST );
	glScissor( x, y, 64, 64 );

	glUseProgram( smokeProgram );

	glEnableVertexAttribArray( 0 );
	glBindBuffer( GL_ARRAY_BUFFER, smokeFullScreenPositionBuffer );
	glVertexAttribPointer( 0, 2, GL_FLOAT, GL_FALSE, 0, reinterpret_cast<const GLvoid *>( 0 ) );

	glEnableVertexAttribArray( 1 );
	glBindBuffer( GL_ARRAY_BUFFER, smokeColorBuffer );
	glVertexAttribPointer( 1, 4, GL_FLOAT, GL_FALSE, 0, reinterpret_cast<const GLvoid *>( 0 ) );

	glDrawArrays( GL_TRIANGLES, 0, 6 );

	glDisableVertexAttribArray( 0 );
	glDisableVertexAttribArray( 1 );
	glBindBuffer( GL_ARRAY_BUFFER, 0 );
	glDisable( GL_SCISSOR_TEST );
}

}

bool VitaRendererSmoke_Init( void ) {
	RendererLog( "renderer.stage=vitagl-init-begin" );

	// Vita3K reserves guest CDRAM at 0x60000000. The failing traces die while
	// vitaGL creates its CDRAM heap, before vglInit* returns. For the emulator
	// bring-up path, reserve more CDRAM than a retail Vita exposes so vitaGL
	// deliberately creates no VGL_MEM_VRAM pool. GPU-visible allocations then
	// fall back to normal/phycont RAM. This trades performance for a deterministic
	// renderer bootstrap and can be relaxed once real-hardware validation starts.
	const int kRamReserveBytes = 10 * 1024 * 1024;
	const int kDisableCdramThresholdBytes = 128 * 1024 * 1024;

	// Match the proven idTech 4 Vita configuration for the transient command
	// pools while keeping MSAA disabled for the smoke renderer.
	vglSetCircularPoolSize( 3 * 1024 * 1024 );
	vglSetParamBufferSize( 14 * 1024 * 1024 );

	RendererLog( "renderer.vitagl.profile=vita3k-safe-no-cdram" );
	RendererLog( "renderer.vitagl.gc=single-threaded" );
	RendererLog( "renderer.vitagl.heap=custom" );
	RendererLog( "renderer.vitagl.shader_compiler=compat-simple" );

	// The return value reports resolution fallback, not success/failure.
	const GLboolean resolutionFallback = vglInitWithCustomThreshold(
		0,
		960,
		544,
		kRamReserveBytes,
		kDisableCdramThresholdBytes,
		0,
		SCE_KERNEL_MAX_MAIN_CDIALOG_MEM_SIZE,
		SCE_GXM_MULTISAMPLE_NONE );

	RendererLog(
		resolutionFallback == GL_TRUE
			? "renderer.vitagl.resolution_fallback=1"
			: "renderer.vitagl.resolution_fallback=0" );
	RendererLog( "renderer.stage=vitagl-context-created" );
	RendererLogVitaGLMemory( "after-init" );

	vglWaitVblankStart( GL_TRUE );

	glViewport( 0, 0, 960, 544 );
	glDisable( GL_DEPTH_TEST );
	glDisable( GL_STENCIL_TEST );
	glDisable( GL_CULL_FACE );
	glDisable( GL_BLEND );
	glDisable( GL_SCISSOR_TEST );

	// First prove that a plain display clear can be presented before touching
	// shader compilation or geometry.
	glClearColor( 0.035f, 0.070f, 0.150f, 1.0f );
	glClear( GL_COLOR_BUFFER_BIT );
	if ( !CheckGl( "baseline-clear" ) ) {
		RendererLog( "renderer.stage=baseline-clear-failed" );
		return false;
	}

	vglSwapBuffers( GL_FALSE );
	RendererLog( "renderer.stage=baseline-presented" );

	if ( !CreateSmokeProgram() ) {
		RendererLog( "renderer.stage=shader-create-failed" );
		return false;
	}

	if ( !CreateSmokeGeometry() ) {
		RendererLog( "renderer.stage=geometry-create-failed" );
		return false;
	}

	RendererLog( "renderer.stage=vitagl-init-ok" );
	RendererLog( "renderer.test=vbo+shader+scissor-draw+swap" );
	RendererLog( "renderer.note=scissor-clear-path-deferred" );
	return true;
}

void VitaRendererSmoke_Run( void ) {
	RendererLog( "renderer.stage=frame-loop-enter" );

	for ( ;; ) {
		glViewport( 0, 0, 960, 544 );
		glDisable( GL_SCISSOR_TEST );
		glClearColor( 0.015f, 0.020f, 0.040f, 1.0f );
		glClear( GL_COLOR_BUFFER_BIT );

		DrawSmokeGeometry();

		// Validate scissor on the regular shader/VBO draw path. Each call draws a
		// fullscreen gradient but should expose only a 64x64 corner region.
		DrawScissorProbe( 16, 16 );
		DrawScissorProbe( 880, 16 );
		DrawScissorProbe( 16, 464 );
		DrawScissorProbe( 880, 464 );

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
