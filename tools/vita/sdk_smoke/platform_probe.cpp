#include "../../../src/sys/sys_public.h"

#if !defined(__vita__)
#error "VitaSDK must define __vita__ for the Vita platform probe"
#endif

static_assert(sizeof(void *) == 4, "PlayStation Vita must use a 32-bit pointer ABI");
static_assert(sizeof(int) == 4, "PlayStation Vita must use a 32-bit int ABI");
static_assert(sizeof(long) == 4, "PlayStation Vita must use ILP32");
static_assert(BUILD_OS_ID == 3, "Unexpected Vita BUILD_OS_ID");

int VitaPlatformProbe() {
    ALIGN16(int alignedValue) = 16;
    return alignedValue + CPU_EASYARGS + (BUILD_STRING[0] == 'v' ? 1 : 0);
}
