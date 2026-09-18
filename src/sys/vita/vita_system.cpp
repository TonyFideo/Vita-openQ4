#include "../../idlib/precompiled.h"
#include "vita_public.h"

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

const char *VITA_DATA_ROOT = "ux0:data/Vita-OpenQ4";
const char *VITA_PACKAGE_ROOT = "app0:";
const char *VITA_EBOOT_PATH = "app0:/eboot.bin";

uint64_t vitaTimeBaseUsec = 0;
int vitaLastMilliseconds = 0;

static int Vita_BytesToMegabytes( uint64_t bytes ) {
	const uint64_t megabytes = bytes >> 20;
	return megabytes > static_cast<uint64_t>( idMath::INT_MAX )
		? idMath::INT_MAX
		: static_cast<int>( megabytes );
}

static void Vita_CopyPath( char *destination, int destinationSize, const char *source ) {
	if ( destination == NULL || destinationSize <= 0 ) {
		return;
	}
	idStr::Copynz( destination, source != NULL ? source : "", destinationSize );
}

}

extern "C" {
int _newlib_heap_size_user = 300 * 1024 * 1024;
}

void Sys_Init( void ) {
	sceIoMkdir( "ux0:data", 0777 );
	sceIoMkdir( VITA_DATA_ROOT, 0777 );
	Vita_InitThreads();
	Sys_Milliseconds();
}

void Sys_Shutdown( void ) {
	Vita_ShutdownThreads();
}

void Sys_Quit( void ) {
	Sys_Shutdown();
	sceKernelExitProcess( 0 );
}

void Sys_Error( const char *error, ... ) {
	char text[4096];
	text[0] = '\0';

	va_list args;
	va_start( args, error );
	vsnprintf( text, sizeof( text ), error != NULL ? error : "Unknown error", args );
	va_end( args );
	text[sizeof( text ) - 1] = '\0';

	sceClibPrintf( "[openQ4] FATAL: %s\n", text );
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
	if ( msg == NULL ) {
		return;
	}
	va_list args;
	va_start( args, msg );
	sceClibVprintf( msg, args );
	va_end( args );
}

void Sys_DebugPrintf( const char *fmt, ... ) {
	if ( fmt == NULL ) {
		return;
	}
	va_list args;
	va_start( args, fmt );
	sceClibVprintf( fmt, args );
	va_end( args );
}

void Sys_DebugVPrintf( const char *fmt, va_list arg ) {
	if ( fmt != NULL ) {
		sceClibVprintf( fmt, arg );
	}
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
	if ( fp == NULL ) {
		return static_cast<ID_TIME_T>( -1 );
	}

	struct stat st;
	if ( fstat( fileno( fp ), &st ) != 0 ) {
		return static_cast<ID_TIME_T>( -1 );
	}
	return st.st_mtime;
}

const char *Sys_DefaultCDPath( void ) {
	return VITA_DATA_ROOT;
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
