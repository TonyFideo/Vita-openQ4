#include "../../idlib/precompiled.h"
#pragma hdrstop

#include "../../framework/BuildVersion.h"
#include "vita_debug_screen.h"
#include "vita_loading_hud.h"
#include "vita_public.h"

#include <psp2/io/fcntl.h>
#include <psp2/io/stat.h>
#include <psp2/kernel/clib.h>
#include <psp2/kernel/threadmgr.h>

#include <stdarg.h>
#include <stdio.h>
#include <string.h>

namespace {

static const char *kLoadingLog = VITA_OPENQ4_WRITABLE_ROOT "/logs/loading.log";
static const char *kBuildStamp = "app0:/build.txt";
static const uint64_t kNativeRefreshUsec = 80000;

struct vitaLoadingHudState_t {
	bool initialized;
	bool nativeReady;
	bool rendererInitialized;
	bool rendererHandoffComplete;
	SceUID logFd;
	uint64_t lastNativeDrawUsec;
	char lastLoggedGuiAsset[128];
	char lastPhaseAsset[128];
	char lastPhaseName[64];
	vitaLoadingHudSnapshot_t snapshot;
};

static vitaLoadingHudState_t hud;

static void HudCopy( char *dest, int destSize, const char *source ) {
	if ( dest == NULL || destSize <= 0 ) {
		return;
	}
	if ( source == NULL ) {
		source = "";
	}
	sceClibStrncpy( dest, source, static_cast<SceSize>( destSize - 1 ) );
	dest[ destSize - 1 ] = '\0';
}

static char HudLower( char c ) {
	if ( c >= 'A' && c <= 'Z' ) {
		return static_cast<char>( c - 'A' + 'a' );
	}
	return c;
}

static bool HudEqualsIgnoreCase( const char *a, const char *b ) {
	if ( a == NULL || b == NULL ) {
		return false;
	}
	while ( *a && *b ) {
		if ( HudLower( *a ) != HudLower( *b ) ) {
			return false;
		}
		++a;
		++b;
	}
	return *a == '\0' && *b == '\0';
}

static bool HudStartsWithIgnoreCase( const char *text, const char *prefix ) {
	if ( text == NULL || prefix == NULL ) {
		return false;
	}
	while ( *prefix ) {
		if ( *text == '\0' || HudLower( *text ) != HudLower( *prefix ) ) {
			return false;
		}
		++text;
		++prefix;
	}
	return true;
}

static bool HudEndsWithIgnoreCase( const char *text, const char *suffix ) {
	if ( text == NULL || suffix == NULL ) {
		return false;
	}
	const int textLength = static_cast<int>( strlen( text ) );
	const int suffixLength = static_cast<int>( strlen( suffix ) );
	if ( suffixLength > textLength ) {
		return false;
	}
	return HudEqualsIgnoreCase( text + textLength - suffixLength, suffix );
}

static bool HudContainsIgnoreCase( const char *text, const char *needle ) {
	if ( text == NULL || needle == NULL || needle[0] == '\0' ) {
		return false;
	}
	for ( const char *scan = text; *scan; ++scan ) {
		if ( HudStartsWithIgnoreCase( scan, needle ) ) {
			return true;
		}
	}
	return false;
}

static vitaLoadingStage_t HudAssetStage( const char *path ) {
	if ( path == NULL || path[0] == '\0' ) {
		return VITA_LOAD_STAGE_COUNT;
	}

	if ( HudStartsWithIgnoreCase( path, "guis/" ) ||
		 HudStartsWithIgnoreCase( path, "gfx/guis/" ) ||
		 HudContainsIgnoreCase( path, "/guis/" ) ||
		 HudEndsWithIgnoreCase( path, ".gui" ) ) {
		return VITA_LOAD_GUI;
	}
	if ( HudStartsWithIgnoreCase( path, "materials/" ) ||
		 HudEndsWithIgnoreCase( path, ".mtr" ) ) {
		return VITA_LOAD_MATERIALS;
	}
	if ( HudStartsWithIgnoreCase( path, "sound/" ) ||
		 HudEndsWithIgnoreCase( path, ".wav" ) ||
		 HudEndsWithIgnoreCase( path, ".ogg" ) ) {
		return VITA_LOAD_SOUND;
	}
	if ( HudStartsWithIgnoreCase( path, "dds/" ) ||
		 HudEndsWithIgnoreCase( path, ".dds" ) ||
		 HudEndsWithIgnoreCase( path, ".tga" ) ||
		 HudEndsWithIgnoreCase( path, ".jpg" ) ||
		 HudEndsWithIgnoreCase( path, ".jpeg" ) ||
		 HudEndsWithIgnoreCase( path, ".png" ) ) {
		return VITA_LOAD_IMAGES;
	}
	return VITA_LOAD_STAGE_COUNT;
}

static vitaLoadingStage_t HudPakStage( const char *gameDir ) {
	if ( HudEqualsIgnoreCase( gameDir, "q4base" ) ) {
		return VITA_LOAD_Q4_PAKS;
	}
	if ( HudEqualsIgnoreCase( gameDir, "baseoq4" ) ) {
		return VITA_LOAD_OPENQ4_PAKS;
	}
	return VITA_LOAD_STAGE_COUNT;
}

static const char *HudLogPrefix( vitaLoadingLogColor_t color ) {
	switch ( color ) {
		case VITA_LOAD_LOG_OK: return "OK";
		case VITA_LOAD_LOG_WARN: return "WARN";
		case VITA_LOAD_LOG_ERROR: return "ERROR";
		case VITA_LOAD_LOG_INFO:
		default: return "INFO";
	}
}

static vitaDiagColor_t HudDiagColor( vitaLoadingLogColor_t color ) {
	switch ( color ) {
		case VITA_LOAD_LOG_OK: return VITA_DIAG_OK;
		case VITA_LOAD_LOG_WARN: return VITA_DIAG_WARN;
		case VITA_LOAD_LOG_ERROR: return VITA_DIAG_ERROR;
		case VITA_LOAD_LOG_INFO:
		default: return VITA_DIAG_INFO;
	}
}

static void HudWritePersistentLine( vitaLoadingLogColor_t color, const char *text ) {
	if ( hud.logFd < 0 || text == NULL ) {
		return;
	}

	char line[192];
	sceClibSnprintf( line, sizeof( line ), "[%s] %s\n", HudLogPrefix( color ), text );
	const SceSize length = static_cast<SceSize>( sceClibStrnlen( line, sizeof( line ) ) );
	if ( length > 0 ) {
		sceIoWrite( hud.logFd, line, length );
	}
}

static void HudPushLogText( vitaLoadingLogColor_t color, const char *text ) {
	if ( !hud.initialized || text == NULL || text[0] == '\0' ) {
		return;
	}

	if ( hud.snapshot.logCount < VITA_LOADING_HUD_MAX_LOG_LINES ) {
		const int index = hud.snapshot.logCount++;
		hud.snapshot.logs[ index ].color = color;
		HudCopy( hud.snapshot.logs[ index ].text, sizeof( hud.snapshot.logs[ index ].text ), text );
	} else {
		for ( int i = 1; i < VITA_LOADING_HUD_MAX_LOG_LINES; ++i ) {
			hud.snapshot.logs[ i - 1 ] = hud.snapshot.logs[ i ];
		}
		vitaLoadingLogSnapshot_t &entry = hud.snapshot.logs[ VITA_LOADING_HUD_MAX_LOG_LINES - 1 ];
		entry.color = color;
		HudCopy( entry.text, sizeof( entry.text ), text );
	}

	sceClibPrintf( "[VOQ4][load][%s] %s\n", HudLogPrefix( color ), text );
	HudWritePersistentLine( color, text );
}

static void HudLogV( vitaLoadingLogColor_t color, const char *fmt, va_list args ) {
	if ( fmt == NULL ) {
		return;
	}
	char text[160];
	idStr::vsnPrintf( text, sizeof( text ), fmt, args );
	text[ sizeof( text ) - 1 ] = '\0';
	HudPushLogText( color, text );
	VitaLoadingHud_TickNative( false );
}

static void HudInitStage( vitaLoadingStage_t stage, const char *label, int total ) {
	vitaLoadingStageSnapshot_t &entry = hud.snapshot.stages[ stage ];
	memset( &entry, 0, sizeof( entry ) );
	HudCopy( entry.label, sizeof( entry.label ), label );
	entry.total = total;
}

static void HudReadBuildStamp( void ) {
	char action[24] = "?";
	char commit[48] = OPENQ4_VERSION_GIT_SHA;
	char buffer[256] = {};

	SceUID fd = sceIoOpen( kBuildStamp, SCE_O_RDONLY, 0 );
	if ( fd >= 0 ) {
		const int readBytes = sceIoRead( fd, buffer, sizeof( buffer ) - 1 );
		sceIoClose( fd );
		if ( readBytes > 0 ) {
			buffer[ readBytes ] = '\0';
			char *line = buffer;
			while ( line != NULL && *line ) {
				char *next = strchr( line, '\n' );
				if ( next != NULL ) {
					*next = '\0';
					++next;
				}
				if ( HudStartsWithIgnoreCase( line, "action=" ) ) {
					HudCopy( action, sizeof( action ), line + 7 );
				} else if ( HudStartsWithIgnoreCase( line, "commit=" ) ) {
					HudCopy( commit, sizeof( commit ), line + 7 );
				}
				line = next;
			}
		}
	}

	char shortCommit[12] = {};
	if ( commit[0] != '\0' ) {
		for ( int i = 0; i < 8 && commit[i] != '\0'; ++i ) {
			shortCommit[i] = commit[i];
		}
	}
	if ( shortCommit[0] == '\0' ) {
		HudCopy( shortCommit, sizeof( shortCommit ), "unknown" );
	}

	sceClibSnprintf(
		hud.snapshot.buildLabel,
		sizeof( hud.snapshot.buildLabel ),
		"Vita-OpenQ4 #%s %s",
		action,
		shortCommit );

	char fullBuild[160];
	sceClibSnprintf( fullBuild, sizeof( fullBuild ), "build action=%s commit=%s", action, commit[0] ? commit : "unknown" );
	HudPushLogText( VITA_LOAD_LOG_INFO, fullBuild );
}

static void HudDrawNative( void ) {
	if ( !hud.nativeReady || hud.rendererHandoffComplete ) {
		return;
	}

	VitaDiagScreen_Clear();
	VitaDiagScreen_DrawText( 8, 8, VITA_DIAG_INFO, hud.snapshot.buildLabel );
	VitaDiagScreen_DrawText( 8, 30, VITA_DIAG_INFO, "CARGANDO DATOS..." );
	VitaDiagScreen_DrawText( 8, 50, VITA_DIAG_INFO, hud.snapshot.status );

	int y = 78;
	for ( int i = 0; i < VITA_LOAD_STAGE_COUNT; ++i ) {
		const vitaLoadingStageSnapshot_t &stage = hud.snapshot.stages[i];
		char line[160];
		if ( stage.total > 0 ) {
			sceClibSnprintf( line, sizeof( line ), "%s %d/%d %s", stage.label, stage.done, stage.total, stage.detail );
		} else {
			sceClibSnprintf( line, sizeof( line ), "%s %d/? %s", stage.label, stage.done, stage.detail );
		}
		const bool complete = stage.total > 0 && stage.done >= stage.total;
		VitaDiagScreen_DrawText( 12, y, complete ? VITA_DIAG_OK : VITA_DIAG_INFO, line );
		y += 20;
	}

	char line[180];
	sceClibSnprintf( line, sizeof( line ), "ETAPA: %s", hud.snapshot.lastStage );
	VitaDiagScreen_DrawText( 8, 244, VITA_DIAG_INFO, line );
	sceClibSnprintf( line, sizeof( line ), "ASSET: %s", hud.snapshot.lastAsset );
	VitaDiagScreen_DrawText( 8, 264, VITA_DIAG_INFO, line );
	sceClibSnprintf( line, sizeof( line ), "PK4: %s", hud.snapshot.lastPak );
	VitaDiagScreen_DrawText( 8, 284, VITA_DIAG_INFO, line );

	VitaDiagScreen_DrawText( 8, 316, VITA_DIAG_OK, "LOGGING..." );
	y = 338;
	for ( int i = 0; i < hud.snapshot.logCount; ++i ) {
		VitaDiagScreen_DrawText(
			12,
			y,
			HudDiagColor( hud.snapshot.logs[i].color ),
			hud.snapshot.logs[i].text );
		y += 18;
	}

	VitaDiagScreen_Present();
}

}

void VitaLoadingHud_Init( void ) {
	if ( hud.initialized ) {
		return;
	}

	memset( &hud, 0, sizeof( hud ) );
	hud.logFd = -1;
	hud.initialized = true;
	hud.snapshot.active = true;
	HudCopy( hud.snapshot.status, sizeof( hud.snapshot.status ), "Preparando motor..." );
	HudCopy( hud.snapshot.lastStage, sizeof( hud.snapshot.lastStage ), "ENTRY" );
	HudCopy( hud.snapshot.lastAsset, sizeof( hud.snapshot.lastAsset ), "-" );
	HudCopy( hud.snapshot.lastPak, sizeof( hud.snapshot.lastPak ), "-" );

	HudInitStage( VITA_LOAD_ENGINE, "MOTOR", 11 );
	HudInitStage( VITA_LOAD_Q4_PAKS, "PK4 QUAKE4", 0 );
	HudInitStage( VITA_LOAD_OPENQ4_PAKS, "PK4 OPENQ4", 0 );
	HudInitStage( VITA_LOAD_MATERIALS, "MATERIALES", 0 );
	HudInitStage( VITA_LOAD_IMAGES, "IMAGENES/DDS", 0 );
	HudInitStage( VITA_LOAD_GUI, "GUI", 0 );
	HudInitStage( VITA_LOAD_SOUND, "SONIDO", 0 );
	HudInitStage( VITA_LOAD_SESSION, "SESION", 2 );

	sceIoMkdir( VITA_OPENQ4_WRITABLE_ROOT, 0777 );
	sceIoMkdir( VITA_OPENQ4_WRITABLE_ROOT "/logs", 0777 );
	hud.logFd = sceIoOpen( kLoadingLog, SCE_O_WRONLY | SCE_O_CREAT | SCE_O_TRUNC, 0666 );

	hud.nativeReady = VitaDiagScreen_Init();
	HudReadBuildStamp();
	HudPushLogText( VITA_LOAD_LOG_OK, hud.nativeReady ? "HUD nativo listo" : "HUD nativo no disponible" );
	HudDrawNative();
}

void VitaLoadingHud_Shutdown( void ) {
	if ( !hud.initialized ) {
		return;
	}
	if ( hud.logFd >= 0 ) {
		sceIoClose( hud.logFd );
		hud.logFd = -1;
	}
	hud.snapshot.active = false;
	hud.initialized = false;
}

void VitaLoadingHud_SetCheckpoint( const char *text ) {
	if ( !hud.initialized || text == NULL || text[0] == '\0' ) {
		return;
	}
	HudCopy( hud.snapshot.status, sizeof( hud.snapshot.status ), text );
	HudCopy( hud.snapshot.lastStage, sizeof( hud.snapshot.lastStage ), text );
	HudPushLogText( VITA_LOAD_LOG_INFO, text );
	VitaLoadingHud_TickNative( false );
}

void VitaLoadingHud_SetEngineProgress( int done, int total, const char *detail, bool completed ) {
	VitaLoadingHud_SetStageProgress( VITA_LOAD_ENGINE, done, total, detail );
	if ( detail != NULL && detail[0] != '\0' ) {
		HudCopy( hud.snapshot.lastStage, sizeof( hud.snapshot.lastStage ), detail );
		if ( completed ) {
			VitaLoadingHud_LogOk( "%s completado", detail );
		}
	}
}

void VitaLoadingHud_SetStageProgress( vitaLoadingStage_t stage, int done, int total, const char *detail ) {
	if ( !hud.initialized || stage < 0 || stage >= VITA_LOAD_STAGE_COUNT ) {
		return;
	}
	vitaLoadingStageSnapshot_t &entry = hud.snapshot.stages[ stage ];
	entry.done = done < 0 ? 0 : done;
	if ( total >= 0 ) {
		entry.total = total;
	}
	if ( entry.total > 0 && entry.done > entry.total ) {
		entry.total = entry.done;
	}
	if ( detail != NULL ) {
		HudCopy( entry.detail, sizeof( entry.detail ), detail );
	}
	VitaLoadingHud_TickNative( false );
}

void VitaLoadingHud_AddStageTotal( vitaLoadingStage_t stage, int amount ) {
	if ( !hud.initialized || stage < 0 || stage >= VITA_LOAD_STAGE_COUNT || amount <= 0 ) {
		return;
	}
	hud.snapshot.stages[ stage ].total += amount;
}

void VitaLoadingHud_AdvanceStage( vitaLoadingStage_t stage, int amount, const char *detail ) {
	if ( !hud.initialized || stage < 0 || stage >= VITA_LOAD_STAGE_COUNT || amount <= 0 ) {
		return;
	}
	vitaLoadingStageSnapshot_t &entry = hud.snapshot.stages[ stage ];
	entry.done += amount;
	if ( entry.total > 0 && entry.done > entry.total ) {
		entry.total = entry.done;
	}
	if ( detail != NULL ) {
		HudCopy( entry.detail, sizeof( entry.detail ), detail );
	}
	VitaLoadingHud_TickNative( false );
}

void VitaLoadingHud_PakDirectoryDiscovered( const char *gameDir, int count ) {
	const vitaLoadingStage_t stage = HudPakStage( gameDir );
	if ( stage == VITA_LOAD_STAGE_COUNT || count <= 0 ) {
		return;
	}
	VitaLoadingHud_AddStageTotal( stage, count );
	VitaLoadingHud_TickNative( true );
}

void VitaLoadingHud_PakProcessed( const char *gameDir, const char *pakName, bool loaded, bool skipped ) {
	const vitaLoadingStage_t stage = HudPakStage( gameDir );
	if ( stage == VITA_LOAD_STAGE_COUNT ) {
		return;
	}
	VitaLoadingHud_AdvanceStage( stage, 1, pakName != NULL ? pakName : "pk4" );
	if ( skipped ) {
		VitaLoadingHud_LogInfo( "PK4 omitido: %s", pakName != NULL ? pakName : "?" );
	} else if ( loaded ) {
		VitaLoadingHud_LogOk( "PK4 listo: %s", pakName != NULL ? pakName : "?" );
	} else {
		VitaLoadingHud_LogError( "PK4 fallo: %s", pakName != NULL ? pakName : "?" );
	}
}

void VitaLoadingHud_IndexAsset( const char *relativePath ) {
	const vitaLoadingStage_t stage = HudAssetStage( relativePath );
	if ( stage == VITA_LOAD_STAGE_COUNT ) {
		return;
	}
	VitaLoadingHud_AddStageTotal( stage, 1 );
}

void VitaLoadingHud_SetAssetContext( const char *relativePath, const char *pakPath ) {
	if ( !hud.initialized ) {
		return;
	}
	HudCopy( hud.snapshot.lastAsset, sizeof( hud.snapshot.lastAsset ), relativePath != NULL ? relativePath : "?" );
	HudCopy( hud.snapshot.lastPak, sizeof( hud.snapshot.lastPak ), pakPath != NULL ? pakPath : "?" );

	if ( HudAssetStage( relativePath ) == VITA_LOAD_GUI &&
		 !HudEqualsIgnoreCase( hud.lastLoggedGuiAsset, relativePath != NULL ? relativePath : "" ) ) {
		HudCopy( hud.lastLoggedGuiAsset, sizeof( hud.lastLoggedGuiAsset ), relativePath );
		VitaLoadingHud_LogInfo( "GUI abre: %s", relativePath != NULL ? relativePath : "?" );
	} else {
		VitaLoadingHud_TickNative( false );
	}
}

void VitaLoadingHud_SetAssetPhase( const char *relativePath, const char *phase ) {
	if ( !hud.initialized ) {
		return;
	}

	if ( relativePath != NULL && relativePath[0] != '\0' ) {
		HudCopy( hud.snapshot.lastAsset, sizeof( hud.snapshot.lastAsset ), relativePath );
	}
	if ( phase != NULL && phase[0] != '\0' ) {
		HudCopy( hud.snapshot.lastStage, sizeof( hud.snapshot.lastStage ), phase );
		char status[128];
		sceClibSnprintf( status, sizeof( status ), "%s: %s",
			phase, relativePath != NULL ? relativePath : "?" );
		HudCopy( hud.snapshot.status, sizeof( hud.snapshot.status ), status );
	}

	const bool diagnosticAsset = HudAssetStage( relativePath ) == VITA_LOAD_GUI ||
		HudContainsIgnoreCase( relativePath, "mainmenu" );
	const bool phaseChanged =
		!HudEqualsIgnoreCase( hud.lastPhaseAsset, relativePath != NULL ? relativePath : "" ) ||
		!HudEqualsIgnoreCase( hud.lastPhaseName, phase != NULL ? phase : "" );
	if ( diagnosticAsset && phaseChanged ) {
		HudCopy( hud.lastPhaseAsset, sizeof( hud.lastPhaseAsset ), relativePath );
		HudCopy( hud.lastPhaseName, sizeof( hud.lastPhaseName ), phase );
		VitaLoadingHud_LogInfo( "%s: %s",
			phase != NULL ? phase : "ASSET",
			relativePath != NULL ? relativePath : "?" );
	} else {
		VitaLoadingHud_TickNative( false );
	}
}

void VitaLoadingHud_AssetLoaded( const char *relativePath, const char *pakPath, bool firstLoad ) {
	VitaLoadingHud_SetAssetContext( relativePath, pakPath );
	if ( !firstLoad ) {
		return;
	}
	const vitaLoadingStage_t stage = HudAssetStage( relativePath );
	if ( stage != VITA_LOAD_STAGE_COUNT ) {
		VitaLoadingHud_AdvanceStage( stage, 1, relativePath );
		if ( stage == VITA_LOAD_GUI ) {
			VitaLoadingHud_LogOk( "GUI listo: %s", relativePath != NULL ? relativePath : "?" );
		}
	}
}

void VitaLoadingHud_AssetError( const char *relativePath, const char *pakPath, const char *reason ) {
	VitaLoadingHud_SetAssetContext( relativePath, pakPath );
	VitaLoadingHud_LogError(
		"Asset fallo: %s (%s)",
		relativePath != NULL ? relativePath : "?",
		reason != NULL ? reason : "desconocido" );
}

void VitaLoadingHud_LogInfo( const char *fmt, ... ) {
	va_list args;
	va_start( args, fmt );
	HudLogV( VITA_LOAD_LOG_INFO, fmt, args );
	va_end( args );
}

void VitaLoadingHud_LogOk( const char *fmt, ... ) {
	va_list args;
	va_start( args, fmt );
	HudLogV( VITA_LOAD_LOG_OK, fmt, args );
	va_end( args );
}

void VitaLoadingHud_LogWarn( const char *fmt, ... ) {
	va_list args;
	va_start( args, fmt );
	HudLogV( VITA_LOAD_LOG_WARN, fmt, args );
	va_end( args );
}

void VitaLoadingHud_LogError( const char *fmt, ... ) {
	va_list args;
	va_start( args, fmt );
	HudLogV( VITA_LOAD_LOG_ERROR, fmt, args );
	va_end( args );
}

void VitaLoadingHud_TickNative( bool force ) {
	if ( !hud.initialized || !hud.nativeReady || hud.rendererHandoffComplete ) {
		return;
	}
	const uint64_t now = static_cast<uint64_t>( sceKernelGetSystemTimeWide() );
	if ( !force && hud.lastNativeDrawUsec != 0 && now - hud.lastNativeDrawUsec < kNativeRefreshUsec ) {
		return;
	}
	hud.lastNativeDrawUsec = now;
	HudDrawNative();
}

void VitaLoadingHud_RendererInitialized( void ) {
	if ( !hud.initialized ) {
		return;
	}
	hud.rendererInitialized = true;
	VitaLoadingHud_LogOk( "VitaGL inicializado" );
}

void VitaLoadingHud_BeginRendererHandoff( void ) {
	if ( !hud.initialized || hud.rendererHandoffComplete || !hud.nativeReady ) {
		return;
	}
	VitaDiagScreen_Finish();
	hud.nativeReady = false;
}

void VitaLoadingHud_EndRendererHandoff( void ) {
	if ( !hud.initialized || hud.rendererHandoffComplete ) {
		return;
	}
	VitaDiagScreen_ReleaseBacking();
	hud.rendererHandoffComplete = true;
	hud.snapshot.rendererHandoffComplete = true;
	VitaLoadingHud_LogOk( "HUD transferido a VitaGL" );
}

bool VitaLoadingHud_RendererHandoffComplete( void ) {
	return hud.rendererHandoffComplete;
}

void VitaLoadingHud_GetSnapshot( vitaLoadingHudSnapshot_t *snapshot ) {
	if ( snapshot == NULL ) {
		return;
	}
	*snapshot = hud.snapshot;
}
