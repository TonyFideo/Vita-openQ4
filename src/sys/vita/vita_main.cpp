#include "../../idlib/precompiled.h"
#pragma hdrstop

#include "vita_public.h"
#include "vita_loading_hud.h"

#include <psp2/kernel/clib.h>
#include <psp2/kernel/sysmem.h>
#include <psp2/io/fcntl.h>
#include <malloc.h>
#include <errno.h>
#include <stdint.h>
#include "vita_runtime_audit.h"



// BEGIN VITA ALLOCATION AUDIT
// GNU ld wrapping preserves newlib's allocator and every original failure.
// No engine logger, strings, filesystem objects, retries or fallback heaps are
// used here: failure reporting must also work when the engine cannot allocate.
extern "C" void *__real_malloc(size_t);
extern "C" void *__real_calloc(size_t, size_t);
extern "C" void *__real_realloc(void *, size_t);
extern "C" void *__real_memalign(size_t, size_t);

static volatile unsigned vitaAuditRequested = 0;
static volatile int vitaAuditReporting = 0;
static unsigned vitaAuditSnapshots = 0;

void VitaRuntimeAudit_Memory(const char *reason, size_t count, size_t size,
                            const void *caller, bool failed) {
    const int savedErrno = errno;
    if (__sync_lock_test_and_set(&vitaAuditReporting, 1)) return;
    const bool trafficSnapshot = reason != NULL && strcmp(reason, "allocation-traffic") == 0;
    if (!failed && trafficSnapshot && vitaAuditSnapshots >= 96) {
        __sync_lock_release(&vitaAuditReporting);
        return;
    }
    if (!failed && trafficSnapshot) ++vitaAuditSnapshots;
    const struct mallinfo heap = mallinfo();
    SceKernelFreeMemorySizeInfo kernel = {};
    kernel.size = sizeof(kernel);
    const int kernelResult = sceKernelGetFreeMemorySize(&kernel);
    size_t gpu[3] = {};
    const bool gpuReady = VitaRuntimeAudit_GpuFree(gpu);
    const bool overflow = size != 0 && count > SIZE_MAX / size;
    char line[768];
    const int length = sceClibSnprintf(line, sizeof(line),
        "[VOQ4][memory] %s failed=%d count=%u size=%u overflow=%d caller=%p "
        "heapArena=%u heapUsed=%u heapFree=%u heapTop=%u "
        "kernelResult=%d kernelUser=%u kernelPhy=%u kernelCdram=%u "
        "gpuReady=%d gpuRamFree=%u gpuCdramFree=%u gpuPhyFree=%u\n",
        reason, failed ? 1 : 0, (unsigned)count, (unsigned)size,
        overflow ? 1 : 0, caller,
        (unsigned)heap.arena, (unsigned)heap.uordblks,
        (unsigned)heap.fordblks, (unsigned)heap.keepcost,
        kernelResult, (unsigned)kernel.size_user,
        (unsigned)kernel.size_phycont, (unsigned)kernel.size_cdram,
        gpuReady ? 1 : 0, (unsigned)gpu[0], (unsigned)gpu[1], (unsigned)gpu[2]);
    if (length > 0) {
        line[sizeof(line)-1] = '\0';
        sceClibPrintf("%s", line);
        // Persist failed reservations separately from the allocating FatalError
        // path. Successful checkpoints remain in the emulator/console log.
        if (failed) {
            const SceUID fd = sceIoOpen(VITA_OPENQ4_WRITABLE_ROOT "/logs/errors.log",
                SCE_O_WRONLY | SCE_O_CREAT | SCE_O_APPEND, 0666);
            if (fd >= 0) {
                const size_t bytes = (size_t)length < sizeof(line) ?
                    (size_t)length : sizeof(line)-1;
                size_t offset = 0;
                while (offset < bytes) {
                    const int written = sceIoWrite(fd, line + offset, bytes - offset);
                    if (written <= 0) break;
                    offset += (size_t)written;
                }
                sceIoClose(fd);
            }
        }
    }
    __sync_lock_release(&vitaAuditReporting);
    errno = savedErrno;
}

static void VitaAuditAllocation(void *result, const char *kind, size_t count,
                                size_t size, const void *caller) {
    if (count == 0 || size == 0) return; // zero-sized allocations may return NULL
    if (!result) {
        VitaRuntimeAudit_Memory(kind, count, size, caller, true);
        return;
    }
    // Traffic, NOT live memory: every 32 MiB of successful allocation requests
    // samples the real heap counters. This also runs during blocking map loads.
    const unsigned bytes = (unsigned)(count * size);
    const unsigned before = __sync_fetch_and_add(&vitaAuditRequested, bytes);
    if ((before >> 25) != ((before + bytes) >> 25))
        VitaRuntimeAudit_Memory("allocation-traffic", count, size, caller, false);
}

extern "C" void *__wrap_malloc(size_t size) {
    void *result = __real_malloc(size);
    VitaAuditAllocation(result, "malloc", 1, size, __builtin_return_address(0));
    return result;
}
extern "C" void *__wrap_calloc(size_t count, size_t size) {
    void *result = __real_calloc(count, size);
    VitaAuditAllocation(result, "calloc", count, size, __builtin_return_address(0));
    return result;
}
extern "C" void *__wrap_realloc(void *ptr, size_t size) {
    void *result = __real_realloc(ptr, size);
    VitaAuditAllocation(result, "realloc", 1, size, __builtin_return_address(0));
    return result;
}
extern "C" void *__wrap_memalign(size_t alignment, size_t size) {
    void *result = __real_memalign(alignment, size);
    VitaAuditAllocation(result, "memalign", 1, size, __builtin_return_address(0));
    return result;
}
// END VITA ALLOCATION AUDIT

/*
================
main

Vita owns no desktop message pump. idCommonLocal::Init performs Sys_Init()
itself, then the normal idTech 4 frame loop drives session/game/rendering.
Keeping this entry point intentionally small makes the Vita executable follow
the same engine lifecycle as the desktop builds.
================
*/
int main( int argc, char **argv ) {
	sceClibPrintf( "[VOQ4] engine entry\n" );
	VitaLoadingHud_Init();
	VitaLoadingHud_SetEngineProgress( 0, 11, "Entrada del motor", false );

	const char **engineArgv = const_cast<const char **>( argv );
	if ( argc > 1 ) {
		common->Init( argc - 1, engineArgv + 1, NULL );
	} else {
		common->Init( 0, NULL, NULL );
	}

	VitaLoadingHud_SetEngineProgress( 11, 11, "Inicializacion completa", true );
	if ( !Vita_StartAsyncTimer() ) {
		Sys_Error( "No se pudo iniciar el temporizador asincrono de 60 Hz" );
	}
	VitaLoadingHud_LogOk( "Entrando al bucle principal" );

	VitaRuntimeAudit_Start();
	VitaRuntimeAudit_Memory("main-loop", 0, 0, NULL, false);
	for ( ;; ) {
		common->Frame();
	}

	return 0;
}
