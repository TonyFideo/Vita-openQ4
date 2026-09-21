#include "vita_safe_printf.h"
#include "../../idlib/precompiled.h"
#include "vita_public.h"

#include <psp2/io/fcntl.h>
#include <psp2/io/stat.h>
#include <psp2/kernel/clib.h>
#include <psp2/kernel/processmgr.h>
#include <psp2/kernel/rng.h>
#include <psp2/kernel/sysmem.h>
#include <psp2/kernel/threadmgr/thread.h>
#include <psp2/power.h>

#include <sys/stat.h>
#include <unistd.h>

#include <stdint.h>
#include <stdio.h>
#include <string.h>

namespace {

const char *VITA_DATA_ROOT = VITA_OPENQ4_WRITABLE_ROOT;
const char *VITA_PACKAGE_ROOT = "app0:";
const char *VITA_EBOOT_PATH = "app0:/eboot.bin";

uint64_t vitaTimeBaseUsec = 0;
int vitaLastMilliseconds = 0;

// Keep warnings/fatal messages independently of Vita3K's buffered host log.
// This is a diagnostic sink only: it never calls the engine filesystem/logger.
static void VitaPrintText( const char *text, bool persist = false ) {
	sceClibPrintf( "%s", text );
	if ( !persist && strstr( text, "WARNING" ) == NULL &&
		 strstr( text, "ERROR" ) == NULL && strstr( text, "FATAL" ) == NULL ) {
		return;
	}
	const SceUID fd = sceIoOpen( VITA_OPENQ4_WRITABLE_ROOT "/logs/errors.log",
		SCE_O_WRONLY | SCE_O_CREAT | SCE_O_APPEND, 0666 );
	if ( fd >= 0 ) {
		const SceSize size = static_cast<SceSize>( sceClibStrnlen( text, 4096 ) );
		SceSize offset = 0;
		while ( offset < size ) {
			const int written = sceIoWrite( fd, text + offset, size - offset );
			if ( written <= 0 ) break;
			offset += static_cast<SceSize>( written );
		}
		sceIoClose( fd );
	}
}

static void VitaPrintV( const char *format, va_list args ) {
	if ( format == NULL ) return;
	char text[4096];
	VitaFormatPrint( text, sizeof( text ), format, args );
	VitaPrintText( text );
}

static int Vita_BytesToMegabytes( uint64_t bytes ) {
	const uint64_t megabytes = bytes >> 20;
	const uint64_t maxInt = 0x7fffffffULL;
	return megabytes > maxInt ? 0x7fffffff : static_cast<int>( megabytes );
}

static void Vita_CopyPath( char *destination, int destinationSize, const char *source ) {
	if ( destination == NULL || destinationSize <= 0 ) {
		return;
	}
	const char *safeSource = source != NULL ? source : "";
	sceClibStrncpy( destination, safeSource, static_cast<SceSize>( destinationSize - 1 ) );
	destination[destinationSize - 1] = '\0';
}

}

extern "C" {
int _newlib_heap_size_user = 300 * 1024 * 1024;
}

void Sys_Init( void ) {
	sceIoMkdir( "ux0:data", 0777 );
	sceIoMkdir( VITA_DATA_ROOT, 0777 );
	sceIoMkdir( "ux0:data/Vita-OpenQ4/q4base", 0777 );
	sceIoMkdir( "ux0:data/Vita-OpenQ4/baseoq4", 0777 );
	sceIoMkdir( "ux0:data/Vita-OpenQ4/savegames", 0777 );
	sceIoMkdir( "ux0:data/Vita-OpenQ4/config", 0777 );
	sceIoMkdir( "ux0:data/Vita-OpenQ4/cache", 0777 );
	sceIoMkdir( "ux0:data/Vita-OpenQ4/logs", 0777 );
	sceIoRemove( VITA_OPENQ4_WRITABLE_ROOT "/logs/errors.log" );
	Vita_InitThreads();
	Sys_Milliseconds();
}

void Sys_Shutdown( void ) {
	Vita_StopAsyncTimer();
	Vita_ShutdownThreads();
}

void Sys_Quit( void ) {
	Sys_Shutdown();
	sceKernelExitProcess( 0 );
}

void Sys_Error( const char *error, ... ) {
	char text[4096];
	va_list args;
	va_start( args, error );
	VitaFormatPrint( text, sizeof( text ), error != NULL ? error : "Unknown error", args );
	va_end( args );

	VitaPrintText( "[openQ4] FATAL: ", true );
	VitaPrintText( text, true );
	VitaPrintText( "\n", true );
	Sys_Shutdown();
	sceKernelExitProcess( -1 );
}

bool Sys_AlreadyRunning( void ) {
	return false;
}

char *Sys_GetClipboardData( void ) {
	return NULL;
}

void Sys_SetClipboardData( const char *string ) {
	(void)string;
}

void Sys_Printf( const char *msg, ... ) {
	va_list args;
	va_start( args, msg );
	VitaPrintV( msg, args );
	va_end( args );
}

void Sys_DebugPrintf( const char *fmt, ... ) {
	va_list args;
	va_start( args, fmt );
	VitaPrintV( fmt, args );
	va_end( args );
}

void Sys_DebugVPrintf( const char *fmt, va_list arg ) {
	VitaPrintV( fmt, arg );
}

void Sys_Sleep( int msec ) {
	if ( msec <= 0 ) {
		return;
	}

	uint64_t delayUsec = static_cast<uint64_t>( msec ) * 1000ULL;
	while ( delayUsec > 0 ) {
		const SceUInt chunk = delayUsec > 0xffffffffULL
			? 0xffffffffU
			: static_cast<SceUInt>( delayUsec );
		sceKernelDelayThread( chunk );
		delayUsec -= chunk;
	}
}

int Sys_Milliseconds( void ) {
	const uint64_t nowUsec = static_cast<uint64_t>( sceKernelGetSystemTimeWide() );
	if ( vitaTimeBaseUsec == 0 ) {
		vitaTimeBaseUsec = nowUsec;
		vitaLastMilliseconds = 0;
		return 0;
	}

	vitaLastMilliseconds = static_cast<int>( ( nowUsec - vitaTimeBaseUsec ) / 1000ULL );
	return vitaLastMilliseconds;
}

bool Sys_GetSecureRandomBytes( void *buffer, int bytes ) {
	if ( bytes < 0 || ( bytes > 0 && buffer == NULL ) ) {
		return false;
	}
	if ( bytes == 0 ) {
		return true;
	}
	return sceKernelGetRandomNumber( buffer, static_cast<SceSize>( bytes ) ) >= 0;
}

double Sys_GetClockTicks( void ) {
	return static_cast<double>( sceKernelGetSystemTimeWide() );
}

double Sys_ClockTicksPerSecond( void ) {
	return 1000000.0;
}

double Sys_GetApproximateProcessorFrequencyHz( void ) {
	const int megahertz = scePowerGetArmClockFrequency();
	return megahertz > 0 ? static_cast<double>( megahertz ) * 1000000.0 : 0.0;
}

cpuid_t Sys_GetProcessorId( void ) {
	return CPUID_GENERIC;
}

const char *Sys_GetProcessorString( void ) {
	return "ARM Cortex-A9 (PlayStation Vita)";
}

bool Sys_FPU_StackIsEmpty( void ) {
	return true;
}

void Sys_FPU_ClearStack( void ) {
}

const char *Sys_FPU_GetState( void ) {
	return "";
}

void Sys_FPU_EnableExceptions( int exceptions ) {
	(void)exceptions;
}

void Sys_FPU_SetPrecision( int precision ) {
	(void)precision;
}

void Sys_FPU_SetRounding( int rounding ) {
	(void)rounding;
}

void Sys_FPU_SetFTZ( bool enable ) {
	(void)enable;
}

void Sys_FPU_SetDAZ( bool enable ) {
	(void)enable;
}

int Sys_GetSystemRam( void ) {
	return _newlib_heap_size_user / ( 1024 * 1024 );
}

int Sys_GetVideoRam( void ) {
	return 128;
}

bool Sys_GetDesktopResolution( int *width, int *height ) {
	if ( width != NULL ) {
		*width = 960;
	}
	if ( height != NULL ) {
		*height = 544;
	}
	return width != NULL && height != NULL;
}

void Sys_GetCurrentMemoryStatus( sysMemoryStats_t &stats ) {
	memset( &stats, 0, sizeof( stats ) );

	SceKernelFreeMemorySizeInfo freeInfo;
	memset( &freeInfo, 0, sizeof( freeInfo ) );
	freeInfo.size = sizeof( freeInfo );

	const uint64_t totalBytes = static_cast<uint64_t>( _newlib_heap_size_user );
	uint64_t freeBytes = 0;
	if ( sceKernelGetFreeMemorySize( &freeInfo ) >= 0 ) {
		freeBytes =
			static_cast<uint64_t>( freeInfo.size_user ) +
			static_cast<uint64_t>( freeInfo.size_phycont );
		if ( freeBytes > totalBytes ) {
			freeBytes = totalBytes;
		}
	}

	stats.totalPhysical = Vita_BytesToMegabytes( totalBytes );
	stats.availPhysical = Vita_BytesToMegabytes( freeBytes );
	stats.totalPageFile = stats.totalPhysical;
	stats.availPageFile = stats.availPhysical;
	stats.totalVirtual = stats.totalPhysical;
	stats.availVirtual = stats.availPhysical;
	stats.availExtendedVirtual = 0;
	if ( totalBytes > 0 ) {
		stats.memoryLoad = 100 - static_cast<int>( ( freeBytes * 100ULL ) / totalBytes );
	}
}

void Sys_GetExeLaunchMemoryStatus( sysMemoryStats_t &stats ) {
	Sys_GetCurrentMemoryStatus( stats );
}

bool Sys_LockMemory( void *ptr, int bytes ) {
	(void)ptr;
	(void)bytes;
	return false;
}

bool Sys_UnlockMemory( void *ptr, int bytes ) {
	(void)ptr;
	(void)bytes;
	return false;
}

void Sys_SetPhysicalWorkMemory( int minBytes, int maxBytes ) {
	(void)minBytes;
	(void)maxBytes;
}

void Sys_FlushCacheMemory( void *base, int bytes ) {
	(void)base;
	(void)bytes;
}

void Sys_GetCallStack( address_t *callStack, const int callStackSize ) {
	if ( callStack != NULL && callStackSize > 0 ) {
		memset( callStack, 0, static_cast<size_t>( callStackSize ) * sizeof( callStack[0] ) );
	}
}

const char *Sys_GetCallStackStr( const address_t *callStack, const int callStackSize ) {
	(void)callStack;
	(void)callStackSize;
	return "";
}

const char *Sys_GetCallStackCurStr( int depth ) {
	(void)depth;
	return "";
}

const char *Sys_GetCallStackCurAddressStr( int depth ) {
	(void)depth;
	return "";
}

void Sys_ShutdownSymbols( void ) {
}

intptr_t Sys_DLL_Load( const char *dllName ) {
	if ( dllName != NULL && dllName[0] != '\0' ) {
		Sys_Printf( "Vita: dynamic module loading disabled during monolithic bring-up: %s\n", dllName );
	}
	return 0;
}

void *Sys_DLL_GetProcAddress( intptr_t dllHandle, const char *procName ) {
	(void)dllHandle;
	(void)procName;
	return NULL;
}

void Sys_DLL_Unload( intptr_t dllHandle ) {
	(void)dllHandle;
}

void Sys_Mkdir( const char *path ) {
	if ( path != NULL && path[0] != '\0' ) {
		sceIoMkdir( path, 0777 );
	}
}

ID_TIME_T Sys_FileTimeStamp( FILE *fp ) {
	// VitaSDK's newlib FILE implementation does not expose a portable fileno()
	// entry point. Engine-owned files use the idFileSystem path/stat layer, so
	// keep the legacy FILE* timestamp helper conservative during bring-up.
	(void)fp;
	return static_cast<ID_TIME_T>( -1 );
}

const char *Sys_DefaultCDPath( void ) {
	// Engine-owned runtime support files live inside the installed VPK.
	// Retail Quake 4 media remains in the writable data root selected as
	// fs_basepath, while fs_cdpath provides app0:/baseoq4 as the immutable
	// openQ4 runtime layer.
	return VITA_PACKAGE_ROOT;
}

const char *Sys_DefaultBasePath( void ) {
	return VITA_DATA_ROOT;
}

const char *Sys_DefaultSavePath( void ) {
	return VITA_DATA_ROOT;
}

const char *Sys_EXEPath( void ) {
	return VITA_EBOOT_PATH;
}

bool Sys_GetPackageRootDirectory( char *packageRoot, int packageRootSize ) {
	Vita_CopyPath( packageRoot, packageRootSize, VITA_PACKAGE_ROOT );
	return packageRoot != NULL && packageRootSize > 0;
}

bool Sys_GetGameModuleRootDirectory( char *moduleRoot, int moduleRootSize ) {
	Vita_CopyPath( moduleRoot, moduleRootSize, "" );
	return false;
}
