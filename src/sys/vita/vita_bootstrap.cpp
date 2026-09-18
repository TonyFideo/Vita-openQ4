#include "../sys_public.h"
#include "vita_public.h"
#include "vita_debug_screen.h"

#include <psp2/io/fcntl.h>
#include <psp2/io/stat.h>
#include <psp2/kernel/clib.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/kernel/sysmem.h>
#include <psp2/kernel/threadmgr/thread.h>

#include <stdint.h>
#include <string.h>

namespace {

const char *kPreRenderLog = VITA_OPENQ4_WRITABLE_ROOT "/logs/prerender.log";
int vitaDiagnosticErrors = 0;
bool vitaScreenReady = false;

struct VitaMemorySnapshot {
	bool valid;
	uint64_t freeUserBytes;
	uint64_t freeCdramBytes;
	uint64_t freePhycontBytes;
};

struct VitaProfileMark {
	uint64_t wallUsec;
	uint64_t processClockUsec;
	uint64_t mainThreadRunClocks;
	bool threadClockValid;
};

static void Vita_ResetLog( void ) {
	SceUID fd = sceIoOpen(
		kPreRenderLog,
		SCE_O_WRONLY | SCE_O_CREAT | SCE_O_TRUNC,
		0666 );
	if ( fd >= 0 ) {
		sceIoClose( fd );
	}
}

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

static void Vita_WriteLogU64( const char *key, uint64_t value ) {
	char line[192];
	sceClibSnprintf(
		line,
		sizeof( line ),
		"%s=%llu",
		key != NULL ? key : "value",
		static_cast<unsigned long long>( value ) );
	Vita_WriteLogLine( line );
}

static void Vita_Info( const char *text ) {
	Vita_WriteLogLine( text );
	if ( vitaScreenReady ) {
		VitaDiagScreen_PrintLine( VITA_DIAG_INFO, text );
	}
}

static void Vita_ReportStatus( const char *name, bool ok, const char *detail ) {
	char line[256];
	const char *safeName = name != NULL ? name : "ETAPA";
	const char *safeDetail = detail != NULL ? detail : "";
	if ( safeDetail[0] != '\0' ) {
		sceClibSnprintf(
			line,
			sizeof( line ),
			"[%s] %s - %s",
			ok ? "OK" : "ERROR",
			safeName,
			safeDetail );
	} else {
		sceClibSnprintf(
			line,
			sizeof( line ),
			"[%s] %s",
			ok ? "OK" : "ERROR",
			safeName );
	}
	Vita_WriteLogLine( line );
	if ( vitaScreenReady ) {
		VitaDiagScreen_PrintLine( ok ? VITA_DIAG_OK : VITA_DIAG_ERROR, line );
	}
	if ( !ok ) {
		++vitaDiagnosticErrors;
	}
}

static VitaMemorySnapshot Vita_ReadMemorySnapshot( void ) {
	VitaMemorySnapshot snapshot;
	memset( &snapshot, 0, sizeof( snapshot ) );

	SceKernelFreeMemorySizeInfo info;
	memset( &info, 0, sizeof( info ) );
	info.size = sizeof( info );
	if ( sceKernelGetFreeMemorySize( &info ) < 0 ) {
		return snapshot;
	}

	snapshot.valid = true;
	snapshot.freeUserBytes = static_cast<uint64_t>( info.size_user );
	snapshot.freeCdramBytes = static_cast<uint64_t>( info.size_cdram );
	snapshot.freePhycontBytes = static_cast<uint64_t>( info.size_phycont );
	return snapshot;
}

static uint64_t Vita_TotalFreeBytes( const VitaMemorySnapshot &snapshot ) {
	if ( !snapshot.valid ) {
		return 0;
	}
	return snapshot.freeUserBytes + snapshot.freeCdramBytes + snapshot.freePhycontBytes;
}

static void Vita_LogMemorySnapshot( const char *label, const VitaMemorySnapshot &snapshot ) {
	char key[128];
	if ( label == NULL ) {
		label = "memory";
	}
	if ( !snapshot.valid ) {
		sceClibSnprintf( key, sizeof( key ), "ram.%s.error", label );
		Vita_WriteLogLine( key );
		return;
	}

	sceClibSnprintf( key, sizeof( key ), "ram.%s.free_user_kb", label );
	Vita_WriteLogU64( key, snapshot.freeUserBytes >> 10 );
	sceClibSnprintf( key, sizeof( key ), "ram.%s.free_cdram_kb", label );
	Vita_WriteLogU64( key, snapshot.freeCdramBytes >> 10 );
	sceClibSnprintf( key, sizeof( key ), "ram.%s.free_phycont_kb", label );
	Vita_WriteLogU64( key, snapshot.freePhycontBytes >> 10 );
	sceClibSnprintf( key, sizeof( key ), "ram.%s.total_free_kb", label );
	Vita_WriteLogU64( key, Vita_TotalFreeBytes( snapshot ) >> 10 );
}

static uint64_t Vita_ReadMainThreadRunClocks( bool &valid ) {
	SceKernelThreadInfo info;
	memset( &info, 0, sizeof( info ) );
	info.size = sizeof( info );
	if ( sceKernelGetThreadInfo( SCE_KERNEL_THREAD_ID_SELF, &info ) < 0 ) {
		valid = false;
		return 0;
	}
	valid = true;
	return static_cast<uint64_t>( info.runClocks );
}

static VitaProfileMark Vita_ProfileMarkNow( void ) {
	VitaProfileMark mark;
	mark.wallUsec = static_cast<uint64_t>( sceKernelGetSystemTimeWide() );
	mark.processClockUsec = static_cast<uint64_t>( sceKernelGetProcessTimeWide() );
	mark.mainThreadRunClocks = Vita_ReadMainThreadRunClocks( mark.threadClockValid );
	return mark;
}

static void Vita_LogProfileStage(
	const char *name,
	const VitaProfileMark &start,
	const VitaProfileMark &end ) {
	char key[160];
	const char *safeName = name != NULL ? name : "stage";

	sceClibSnprintf( key, sizeof( key ), "profile.%s.elapsed_us", safeName );
	Vita_WriteLogU64( key, end.wallUsec - start.wallUsec );

	sceClibSnprintf( key, sizeof( key ), "profile.%s.process_clock_delta_us", safeName );
	Vita_WriteLogU64( key, end.processClockUsec - start.processClockUsec );

	if ( start.threadClockValid && end.threadClockValid ) {
		sceClibSnprintf( key, sizeof( key ), "profile.%s.main_thread_run_clocks", safeName );
		Vita_WriteLogU64( key, end.mainThreadRunClocks - start.mainThreadRunClocks );
	}
}

static bool Vita_FindQ4DataRoot( char *root, int rootSize ) {
	if ( root == NULL || rootSize <= 0 ) {
		return false;
	}

	const char *candidates[] = {
		VITA_OPENQ4_DATA_ROOT_UX0,
		VITA_OPENQ4_DATA_ROOT_UMA0,
		VITA_OPENQ4_DATA_ROOT_UR0
	};

	for ( unsigned int i = 0; i < sizeof( candidates ) / sizeof( candidates[0] ); ++i ) {
		char pakPath[256];
		sceClibSnprintf(
			pakPath,
			sizeof( pakPath ),
			"%s/q4base/pak001.pk4",
			candidates[i] );

		SceIoStat statInfo;
		memset( &statInfo, 0, sizeof( statInfo ) );
		if ( sceIoGetstat( pakPath, &statInfo ) >= 0 ) {
			sceClibStrncpy( root, candidates[i], static_cast<SceSize>( rootSize - 1 ) );
			root[rootSize - 1] = '\0';
			return true;
		}
	}

	root[0] = '\0';
	return false;
}

}

int main( int argc, char **argv ) {
	(void)argc;
	(void)argv;

	const VitaMemorySnapshot memoryBeforeInit = Vita_ReadMemorySnapshot();
	const VitaProfileMark totalStart = Vita_ProfileMarkNow();

	Sys_Init();
	Vita_ResetLog();

	vitaScreenReady = VitaDiagScreen_Init();
	Vita_Info( "VITA OPENQ4 PRE-RENDER" );
	Vita_Info( "DIAGNOSTICO DE ARRANQUE" );
	Vita_Info( "" );

	Vita_ReportStatus( "PANTALLA", vitaScreenReady, vitaScreenReady ? "FRAMEBUFFER NATIVO" : "NO DISPONIBLE" );
	Vita_ReportStatus( "SISTEMA", true, BUILD_STRING );

	const VitaProfileMark networkStart = Vita_ProfileMarkNow();
	Sys_InitNetworking();
	const VitaProfileMark networkEnd = Vita_ProfileMarkNow();
	Vita_LogProfileStage( "network", networkStart, networkEnd );
	Vita_ReportStatus( "RED SP", true, "API STUB LISTA" );

	const VitaMemorySnapshot memoryAfterInit = Vita_ReadMemorySnapshot();
	Vita_LogMemorySnapshot( "before_init", memoryBeforeInit );
	Vita_LogMemorySnapshot( "after_init", memoryAfterInit );
	Vita_WriteLogU64( "ram.heap_configured_kb", static_cast<uint64_t>( Sys_GetSystemRam() ) * 1024ULL );

	if ( memoryAfterInit.valid ) {
		char memoryLine[192];
		sceClibSnprintf(
			memoryLine,
			sizeof( memoryLine ),
			"USER %llu MB CDRAM %llu MB PHY %llu MB LIBRES",
			static_cast<unsigned long long>( memoryAfterInit.freeUserBytes >> 20 ),
			static_cast<unsigned long long>( memoryAfterInit.freeCdramBytes >> 20 ),
			static_cast<unsigned long long>( memoryAfterInit.freePhycontBytes >> 20 ) );
		Vita_ReportStatus( "RAM", true, memoryLine );
	} else {
		Vita_ReportStatus( "RAM", false, "NO SE PUDO MEDIR" );
	}

	const VitaProfileMark rngStart = Vita_ProfileMarkNow();
	uint8_t randomBytes[16] = {};
	const bool rngOk = Sys_GetSecureRandomBytes( randomBytes, sizeof( randomBytes ) );
	const VitaProfileMark rngEnd = Vita_ProfileMarkNow();
	Vita_LogProfileStage( "rng", rngStart, rngEnd );
	Vita_ReportStatus( "RNG", rngOk, rngOk ? "OK" : "FALLO" );

	const VitaProfileMark clockStart = Vita_ProfileMarkNow();
	const int before = Sys_Milliseconds();
	Sys_Sleep( 10 );
	const int after = Sys_Milliseconds();
	const bool clockOk = after >= before;
	const VitaProfileMark clockEnd = Vita_ProfileMarkNow();
	Vita_LogProfileStage( "clock", clockStart, clockEnd );
	Vita_ReportStatus( "RELOJ", clockOk, clockOk ? "MONOTONICO" : "FALLO" );

	const VitaProfileMark threadStart = Vita_ProfileMarkNow();
	Sys_EnterCriticalSection();
	Sys_LeaveCriticalSection();
	const VitaProfileMark threadEnd = Vita_ProfileMarkNow();
	Vita_LogProfileStage( "threading", threadStart, threadEnd );
	Vita_ReportStatus( "HILOS", true, "SINCRONIZACION OK" );

	const VitaProfileMark dataStart = Vita_ProfileMarkNow();
	char q4DataRoot[128];
	const bool dataFound = Vita_FindQ4DataRoot( q4DataRoot, sizeof( q4DataRoot ) );
	const VitaProfileMark dataEnd = Vita_ProfileMarkNow();
	Vita_LogProfileStage( "data_scan", dataStart, dataEnd );
	if ( dataFound ) {
		char detail[192];
		sceClibSnprintf( detail, sizeof( detail ), "%s/q4base", q4DataRoot );
		Vita_ReportStatus( "DATOS Q4", true, detail );
		Vita_WriteLogLine( "data.q4.found=1" );
		char rootLine[192];
		sceClibSnprintf( rootLine, sizeof( rootLine ), "data.q4.root=%s", q4DataRoot );
		Vita_WriteLogLine( rootLine );
	} else {
		Vita_ReportStatus( "DATOS Q4", false, "PAK001.PK4 NO ENCONTRADO" );
		Vita_WriteLogLine( "data.q4.found=0" );
	}

	const int driveFreeMb = Sys_GetDriveFreeSpace( Sys_DefaultSavePath() );
	char filesystemDetail[160];
	sceClibSnprintf(
		filesystemDetail,
		sizeof( filesystemDetail ),
		"UX0 LIBRE %d MB",
		driveFreeMb );
	Vita_ReportStatus( "FILESYSTEM", driveFreeMb > 0, filesystemDetail );

	bool cpuProfilerValid = false;
	Vita_ReadMainThreadRunClocks( cpuProfilerValid );
	Vita_ReportStatus(
		"CPU PROFILER",
		cpuProfilerValid,
		cpuProfilerValid ? "TIMINGS GUARDADOS EN LOG" : "RUN CLOCKS NO DISPONIBLES" );

	const VitaMemorySnapshot memoryFinal = Vita_ReadMemorySnapshot();
	Vita_LogMemorySnapshot( "final", memoryFinal );
	if ( memoryBeforeInit.valid && memoryFinal.valid ) {
		const uint64_t beforeFree = Vita_TotalFreeBytes( memoryBeforeInit );
		const uint64_t finalFree = Vita_TotalFreeBytes( memoryFinal );
		const uint64_t usedApproxBytes = beforeFree > finalFree ? beforeFree - finalFree : 0;
		Vita_WriteLogU64( "ram.delta_used_kb_approx", usedApproxBytes >> 10 );

		char ramDelta[160];
		sceClibSnprintf(
			ramDelta,
			sizeof( ramDelta ),
			"DELTA APROX %llu KB",
			static_cast<unsigned long long>( usedApproxBytes >> 10 ) );
		Vita_Info( ramDelta );
	}

	Vita_ReportStatus( "PRE-RENDER", true, "LISTO PARA RENDERER" );

	const VitaProfileMark totalEnd = Vita_ProfileMarkNow();
	Vita_LogProfileStage( "total", totalStart, totalEnd );

	Vita_Info( "" );
	if ( vitaDiagnosticErrors == 0 ) {
		VitaDiagScreen_PrintLine( VITA_DIAG_OK, "TERMINADO" );
		Vita_WriteLogLine( "result=success" );
	} else {
		VitaDiagScreen_PrintLine( VITA_DIAG_ERROR, "TERMINADO - CON ERRORES" );
		Vita_WriteLogLine( "result=errors" );
	}
	Vita_WriteLogLine( "next=renderer-bring-up" );

	// Keep the final diagnostic screen visible long enough to read on hardware.
	sceKernelDelayThread( 5 * 1000 * 1000 );

	Sys_ShutdownNetworking();
	VitaDiagScreen_Finish();
	Sys_Shutdown();

	const int exitCode = vitaDiagnosticErrors == 0 ? 0 : 1;
	sceKernelExitProcess( exitCode );
	return exitCode;
}
