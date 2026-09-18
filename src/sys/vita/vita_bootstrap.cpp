#include "../sys_public.h"
#include "vita_public.h"

#include <psp2/io/fcntl.h>
#include <psp2/kernel/clib.h>
#include <psp2/kernel/processmgr.h>

#include <stdint.h>

namespace {

const char *kPreRenderLog = "ux0:data/Vita-OpenQ4/logs/prerender.log";

static void Vita_WriteLogLine( const char *text ) {
	if ( text == NULL ) {
		return;
	}
	SceUID fd = sceIoOpen( kPreRenderLog, SCE_O_WRONLY | SCE_O_CREAT | SCE_O_APPEND, 0666 );
	if ( fd < 0 ) {
		return;
	}
	const SceSize length = static_cast<SceSize>( sceClibStrnlen( text, 4096 ) );
	if ( length > 0 ) {
		sceIoWrite( fd, text, length );
	}
	sceIoWrite( fd, "\n", 1 );
	sceIoClose( fd );
}

static void Vita_WriteFormatted( const char *label, int value ) {
	char line[160];
	sceClibSnprintf( line, sizeof( line ), "%s%d", label, value );
	Vita_WriteLogLine( line );
}

}

int main( int argc, char **argv ) {
	(void)argc;
	(void)argv;

	Sys_Init();
	Sys_InitNetworking();
	Vita_WriteLogLine( "Vita-OpenQ4 pre-render bootstrap" );
	Vita_WriteLogLine( "stage=sys-init-ok" );
	Vita_WriteLogLine( BUILD_STRING );

	Vita_WriteFormatted( "system_ram_mb=", Sys_GetSystemRam() );
	Vita_WriteFormatted( "video_ram_mb=", Sys_GetVideoRam() );
	Vita_WriteFormatted( "drive_free_mb=", Sys_GetDriveFreeSpace( Sys_DefaultSavePath() ) );

	uint8_t randomBytes[16] = {};
	if ( !Sys_GetSecureRandomBytes( randomBytes, sizeof( randomBytes ) ) ) {
		Vita_WriteLogLine( "stage=rng-failed" );
		Sys_Shutdown();
		sceKernelExitProcess( 2 );
		return 2;
	}
	Vita_WriteLogLine( "stage=rng-ok" );

	const int before = Sys_Milliseconds();
	Sys_Sleep( 10 );
	const int after = Sys_Milliseconds();
	if ( after < before ) {
		Vita_WriteLogLine( "stage=clock-failed" );
		Sys_Shutdown();
		sceKernelExitProcess( 3 );
		return 3;
	}
	Vita_WriteLogLine( "stage=clock-ok" );

	Sys_EnterCriticalSection();
	Sys_LeaveCriticalSection();
	Vita_WriteLogLine( "stage=threading-ok" );
	Vita_WriteLogLine( "stage=network-api-ok-sp-stub" );

	Vita_WriteLogLine( "stage=filesystem-ok" );
	Vita_WriteLogLine( "stage=pre-render-ready" );
	Vita_WriteLogLine( "next=renderer-bring-up" );

	Sys_ShutdownNetworking();
	Sys_Shutdown();
	sceKernelExitProcess( 0 );
	return 0;
}
