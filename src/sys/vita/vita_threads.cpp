#include "../../idlib/precompiled.h"
#include "vita_public.h"

#include <psp2/kernel/threadmgr/cond.h>
#include <psp2/kernel/threadmgr/mutex.h>
#include <psp2/kernel/threadmgr/thread.h>
#include <psp2/kernel/clib.h>

#include <stdint.h>
#include <string.h>
#include <atomic>

namespace {

const int MAX_LOCAL_CRITICAL_SECTIONS = MAX_CRITICAL_SECTIONS + 1;
const SceSize VITA_THREAD_STACK_SIZE = 2 * 1024 * 1024;

SceUID vitaMutexes[MAX_LOCAL_CRITICAL_SECTIONS] = {};
bool vitaMutexReady[MAX_LOCAL_CRITICAL_SECTIONS] = {};
SceUID vitaConditions[MAX_TRIGGER_EVENTS] = {};
bool vitaConditionReady[MAX_TRIGGER_EVENTS] = {};
bool vitaSignaled[MAX_TRIGGER_EVENTS] = {};
bool vitaWaiting[MAX_TRIGGER_EVENTS] = {};
bool vitaThreadsReady = false;
SceUID vitaAsyncThread = 0;
std::atomic<bool> vitaAsyncStop( false );

static uint32_t Vita_NextAsyncIntervalUsec( uint32_t &remainder ) {
	const uint32_t wholeUsec = 1000000u / USERCMD_HZ;
	const uint32_t fractionalUsec = 1000000u % USERCMD_HZ;
	uint32_t intervalUsec = wholeUsec;

	remainder += fractionalUsec;
	if ( remainder >= USERCMD_HZ ) {
		remainder -= USERCMD_HZ;
		++intervalUsec;
	}
	return intervalUsec;
}

static int Vita_AsyncTimerThread( SceSize argsSize, void *argsData ) {
	(void)argsSize;
	(void)argsData;

	uint32_t fractionalRemainder = 0;
	uint64_t nextWakeUsec = static_cast<uint64_t>( sceKernelGetSystemTimeWide() );
	unsigned int callbackCount = 0;

	while ( !vitaAsyncStop.load( std::memory_order_acquire ) ) {
		// idCommonLocal::Async owns the precise/catch-up policy and advances
		// com_ticNumber. The platform timer only supplies the periodic wakeup,
		// matching idTech's desktop/SDL async timer contract.
		common->Async();
		Sys_TriggerEvent( TRIGGER_EVENT_ONE );
		++callbackCount;

		if ( callbackCount <= 600 && ( callbackCount % USERCMD_HZ ) == 0 ) {
			sceClibPrintf( "[VOQ4][async] callbacks=%u tic=%d time=%d\n",
				callbackCount, com_ticNumber, Sys_Milliseconds() );
		}

		const uint32_t intervalUsec = Vita_NextAsyncIntervalUsec( fractionalRemainder );
		const uint64_t nowUsec = static_cast<uint64_t>( sceKernelGetSystemTimeWide() );
		// Async() already catches the simulation up to wall time. If scheduling
		// made us late, restart the platform deadline from 'now' instead of
		// spinning through stale timer callbacks.
		if ( nextWakeUsec < nowUsec ) {
			nextWakeUsec = nowUsec;
		}
		nextWakeUsec += intervalUsec;

		while ( !vitaAsyncStop.load( std::memory_order_acquire ) ) {
			const uint64_t currentUsec = static_cast<uint64_t>( sceKernelGetSystemTimeWide() );
			if ( currentUsec >= nextWakeUsec ) {
				break;
			}
			const uint64_t remainingUsec = nextWakeUsec - currentUsec;
			sceKernelDelayThread( static_cast<SceUInt>( remainingUsec ) );
		}
	}

	return 0;
}

struct VitaThreadStartArgs {
	xthread_t function;
	void *parms;
};

static SceUID Vita_HandleToThread( uintptr_t handle ) {
	return static_cast<SceUID>( static_cast<uint32_t>( handle ) );
}

static uintptr_t Vita_ThreadToHandle( SceUID thread ) {
	return static_cast<uintptr_t>( static_cast<uint32_t>( thread ) );
}

static int Vita_ThreadPriority( xthreadPriority priority ) {
	switch ( priority ) {
		case THREAD_ABOVE_NORMAL:
			return 0x38;
		case THREAD_HIGHEST:
			return 0x30;
		case THREAD_NORMAL:
		default:
			return 0x40;
	}
}

static int Vita_ThreadEntry( SceSize argsSize, void *argsData ) {
	if ( argsData == NULL || argsSize < sizeof( VitaThreadStartArgs ) ) {
		return -1;
	}

	VitaThreadStartArgs args;
	memcpy( &args, argsData, sizeof( args ) );
	if ( args.function == NULL ) {
		return -1;
	}

	return static_cast<int>( args.function( args.parms ) );
}

static bool Vita_IsCriticalSectionValid( int index ) {
	return index >= 0 && index < MAX_LOCAL_CRITICAL_SECTIONS;
}

static bool Vita_IsTriggerEventValid( int index ) {
	return index >= 0 && index < MAX_TRIGGER_EVENTS;
}

static void Vita_RemoveThreadInfo( xthreadInfo &info ) {
	Sys_EnterCriticalSection();
	for ( int i = 0; i < g_thread_count; ++i ) {
		if ( g_threads[i] != &info ) {
			continue;
		}
		for ( int j = i + 1; j < g_thread_count; ++j ) {
			g_threads[j - 1] = g_threads[j];
		}
		g_threads[g_thread_count - 1] = NULL;
		--g_thread_count;
		break;
	}
	Sys_LeaveCriticalSection();
}

}

xthreadInfo *g_threads[MAX_THREADS] = {};
int g_thread_count = 0;

void Vita_InitThreads( void ) {
	if ( vitaThreadsReady ) {
		return;
	}

	for ( int i = 0; i < MAX_LOCAL_CRITICAL_SECTIONS; ++i ) {
		char name[32];
		sceClibSnprintf( name, sizeof( name ), "openq4-mutex-%d", i );
		vitaMutexes[i] = sceKernelCreateMutex( name, 0, 0, NULL );
		if ( vitaMutexes[i] < 0 ) {
			Sys_Printf( "Vita_InitThreads: sceKernelCreateMutex(%d) failed: 0x%08X\n", i, vitaMutexes[i] );
			continue;
		}
		vitaMutexReady[i] = true;
	}

	const int eventMutex = MAX_LOCAL_CRITICAL_SECTIONS - 1;
	if ( vitaMutexReady[eventMutex] ) {
		for ( int i = 0; i < MAX_TRIGGER_EVENTS; ++i ) {
			char name[32];
			sceClibSnprintf( name, sizeof( name ), "openq4-cond-%d", i );
			vitaConditions[i] = sceKernelCreateCond( name, 0, vitaMutexes[eventMutex], NULL );
			if ( vitaConditions[i] < 0 ) {
				Sys_Printf( "Vita_InitThreads: sceKernelCreateCond(%d) failed: 0x%08X\n", i, vitaConditions[i] );
				continue;
			}
			vitaConditionReady[i] = true;
		}
	}

	for ( int i = 0; i < MAX_THREADS; ++i ) {
		g_threads[i] = NULL;
	}
	g_thread_count = 0;
	vitaThreadsReady = true;
}


bool Vita_StartAsyncTimer( void ) {
	if ( vitaAsyncThread > 0 ) {
		return true;
	}
	if ( !vitaThreadsReady ) {
		Vita_InitThreads();
	}

	vitaAsyncStop.store( false, std::memory_order_release );
	vitaAsyncThread = sceKernelCreateThread(
		"openq4-async",
		Vita_AsyncTimerThread,
		Vita_ThreadPriority( THREAD_ABOVE_NORMAL ),
		512 * 1024,
		0,
		SCE_KERNEL_THREAD_CPU_AFFINITY_MASK_DEFAULT,
		NULL );
	if ( vitaAsyncThread < 0 ) {
		Sys_Printf( "Vita_StartAsyncTimer: sceKernelCreateThread failed: 0x%08X\n", vitaAsyncThread );
		vitaAsyncThread = 0;
		return false;
	}

	const int startResult = sceKernelStartThread( vitaAsyncThread, 0, NULL );
	if ( startResult < 0 ) {
		Sys_Printf( "Vita_StartAsyncTimer: sceKernelStartThread failed: 0x%08X\n", startResult );
		sceKernelDeleteThread( vitaAsyncThread );
		vitaAsyncThread = 0;
		return false;
	}

	Sys_Printf( "Vita async timer: %d Hz, thread=0x%08X\n", USERCMD_HZ, vitaAsyncThread );
	return true;
}

void Vita_StopAsyncTimer( void ) {
	if ( vitaAsyncThread <= 0 ) {
		return;
	}

	vitaAsyncStop.store( true, std::memory_order_release );
	int status = 0;
	const int waitResult = sceKernelWaitThreadEnd( vitaAsyncThread, &status, NULL );
	if ( waitResult < 0 ) {
		Sys_Printf( "Vita_StopAsyncTimer: wait failed: 0x%08X\n", waitResult );
	}
	const int deleteResult = sceKernelDeleteThread( vitaAsyncThread );
	if ( deleteResult < 0 ) {
		Sys_Printf( "Vita_StopAsyncTimer: delete failed: 0x%08X\n", deleteResult );
	}
	vitaAsyncThread = 0;
}

void Vita_ShutdownThreads( void ) {
	if ( !vitaThreadsReady ) {
		return;
	}

	for ( int i = 0; i < MAX_TRIGGER_EVENTS; ++i ) {
		if ( vitaConditionReady[i] ) {
			sceKernelDeleteCond( vitaConditions[i] );
			vitaConditionReady[i] = false;
		}
		vitaConditions[i] = 0;
		vitaSignaled[i] = false;
		vitaWaiting[i] = false;
	}

	for ( int i = 0; i < MAX_LOCAL_CRITICAL_SECTIONS; ++i ) {
		if ( vitaMutexReady[i] ) {
			sceKernelDeleteMutex( vitaMutexes[i] );
			vitaMutexReady[i] = false;
		}
		vitaMutexes[i] = 0;
	}

	vitaThreadsReady = false;
}

void Sys_EnterCriticalSection( int index ) {
	assert( Vita_IsCriticalSectionValid( index ) );
	if ( !Vita_IsCriticalSectionValid( index ) || !vitaMutexReady[index] ) {
		return;
	}
	const int result = sceKernelLockMutex( vitaMutexes[index], 1, NULL );
	if ( result < 0 ) {
		Sys_Printf( "Sys_EnterCriticalSection: lock %d failed: 0x%08X\n", index, result );
	}
}

void Sys_LeaveCriticalSection( int index ) {
	assert( Vita_IsCriticalSectionValid( index ) );
	if ( !Vita_IsCriticalSectionValid( index ) || !vitaMutexReady[index] ) {
		return;
	}
	const int result = sceKernelUnlockMutex( vitaMutexes[index], 1 );
	if ( result < 0 ) {
		Sys_Printf( "Sys_LeaveCriticalSection: unlock %d failed: 0x%08X\n", index, result );
	}
}

void Sys_WaitForEvent( int index ) {
	assert( Vita_IsTriggerEventValid( index ) );
	if ( !Vita_IsTriggerEventValid( index ) || !vitaConditionReady[index] ) {
		return;
	}

	const int eventMutex = MAX_LOCAL_CRITICAL_SECTIONS - 1;
	Sys_EnterCriticalSection( eventMutex );
	assert( !vitaWaiting[index] );
	if ( vitaSignaled[index] ) {
		vitaSignaled[index] = false;
	} else {
		vitaWaiting[index] = true;
		const int result = sceKernelWaitCond( vitaConditions[index], NULL );
		if ( result < 0 ) {
			Sys_Printf( "Sys_WaitForEvent: wait %d failed: 0x%08X\n", index, result );
		}
		vitaWaiting[index] = false;
	}
	Sys_LeaveCriticalSection( eventMutex );
}

void Sys_TriggerEvent( int index ) {
	assert( Vita_IsTriggerEventValid( index ) );
	if ( !Vita_IsTriggerEventValid( index ) || !vitaConditionReady[index] ) {
		return;
	}

	const int eventMutex = MAX_LOCAL_CRITICAL_SECTIONS - 1;
	Sys_EnterCriticalSection( eventMutex );
	if ( vitaWaiting[index] ) {
		const int result = sceKernelSignalCond( vitaConditions[index] );
		if ( result < 0 ) {
			Sys_Printf( "Sys_TriggerEvent: signal %d failed: 0x%08X\n", index, result );
		}
	} else {
		vitaSignaled[index] = true;
	}
	Sys_LeaveCriticalSection( eventMutex );
}

void Sys_CreateThread( xthread_t function, void *parms, xthreadPriority priority, xthreadInfo &info, const char *name, xthreadInfo *threads[MAX_THREADS], int *thread_count ) {
	if ( !vitaThreadsReady ) {
		Vita_InitThreads();
	}

	const char *threadName = ( name != NULL && name[0] != '\0' ) ? name : "openq4-thread";
	info.name = threadName;
	info.threadHandle = 0;
	info.threadId = 0;
	info.stopRequested = false;

	if ( function == NULL || threads == NULL || thread_count == NULL ) {
		Sys_Printf( "Sys_CreateThread: invalid arguments for %s\n", threadName );
		return;
	}

	SceUID thread = sceKernelCreateThread(
		threadName,
		Vita_ThreadEntry,
		Vita_ThreadPriority( priority ),
		VITA_THREAD_STACK_SIZE,
		0,
		SCE_KERNEL_THREAD_CPU_AFFINITY_MASK_DEFAULT,
		NULL );
	if ( thread < 0 ) {
		Sys_Printf( "Sys_CreateThread: sceKernelCreateThread(%s) failed: 0x%08X\n", threadName, thread );
		return;
	}

	VitaThreadStartArgs args = { function, parms };
	const int startResult = sceKernelStartThread( thread, sizeof( args ), &args );
	if ( startResult < 0 ) {
		Sys_Printf( "Sys_CreateThread: sceKernelStartThread(%s) failed: 0x%08X\n", threadName, startResult );
		sceKernelDeleteThread( thread );
		return;
	}

	info.threadHandle = Vita_ThreadToHandle( thread );
	info.threadId = static_cast<uint32_t>( thread );

	Sys_EnterCriticalSection();
	if ( *thread_count < MAX_THREADS ) {
		threads[( *thread_count )++] = &info;
	} else {
		Sys_Printf( "Sys_CreateThread: MAX_THREADS reached for %s\n", threadName );
	}
	Sys_LeaveCriticalSection();
}

void Sys_RequestThreadStop( xthreadInfo &info ) {
	if ( vitaThreadsReady ) {
		Sys_EnterCriticalSection();
	}
	info.stopRequested = true;
	if ( vitaThreadsReady ) {
		Sys_LeaveCriticalSection();
		for ( int i = 0; i < MAX_TRIGGER_EVENTS; ++i ) {
			Sys_TriggerEvent( i );
		}
	}
}

bool Sys_IsThreadStopRequested( const xthreadInfo &info ) {
	return info.stopRequested;
}

bool Sys_IsCurrentThreadStopRequested( void ) {
	const SceUID current = sceKernelGetThreadId();
	bool stopRequested = false;

	Sys_EnterCriticalSection();
	for ( int i = 0; i < g_thread_count; ++i ) {
		if ( g_threads[i] != NULL && Vita_HandleToThread( g_threads[i]->threadHandle ) == current ) {
			stopRequested = g_threads[i]->stopRequested;
			break;
		}
	}
	Sys_LeaveCriticalSection();
	return stopRequested;
}

void Sys_DestroyThread( xthreadInfo &info ) {
	if ( info.threadHandle == 0 ) {
		return;
	}

	const SceUID thread = Vita_HandleToThread( info.threadHandle );
	if ( thread == sceKernelGetThreadId() ) {
		Sys_Printf( "Sys_DestroyThread: refusing to join current thread %s\n", info.name != NULL ? info.name : "unnamed" );
		return;
	}

	Sys_RequestThreadStop( info );
	int status = 0;
	const int waitResult = sceKernelWaitThreadEnd( thread, &status, NULL );
	if ( waitResult < 0 ) {
		Sys_Printf( "Sys_DestroyThread: wait for %s failed: 0x%08X\n", info.name != NULL ? info.name : "unnamed", waitResult );
	}
	const int deleteResult = sceKernelDeleteThread( thread );
	if ( deleteResult < 0 ) {
		Sys_Printf( "Sys_DestroyThread: delete %s failed: 0x%08X\n", info.name != NULL ? info.name : "unnamed", deleteResult );
	}

	info.threadHandle = 0;
	info.threadId = 0;
	info.stopRequested = false;
	Vita_RemoveThreadInfo( info );
}

const char *Sys_GetThreadName( int *index ) {
	const SceUID current = sceKernelGetThreadId();
	Sys_EnterCriticalSection();
	for ( int i = 0; i < g_thread_count; ++i ) {
		if ( g_threads[i] != NULL && Vita_HandleToThread( g_threads[i]->threadHandle ) == current ) {
			if ( index != NULL ) {
				*index = i;
			}
			const char *name = g_threads[i]->name;
			Sys_LeaveCriticalSection();
			return name != NULL ? name : "unnamed";
		}
	}
	if ( index != NULL ) {
		*index = -1;
	}
	Sys_LeaveCriticalSection();
	return "main";
}
