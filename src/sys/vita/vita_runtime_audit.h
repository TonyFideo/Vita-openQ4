#ifndef OPENQ4_VITA_RUNTIME_AUDIT_H
#define OPENQ4_VITA_RUNTIME_AUDIT_H
#include <stddef.h>
// Diagnostic-only: never change allocation policy, materials or frame contents.
void VitaRuntimeAudit_Start();
void VitaRuntimeAudit_Memory(const char *reason, size_t count, size_t size,
                            const void *caller, bool failed);
bool VitaRuntimeAudit_GpuFree(size_t freeBytes[3]);
#endif
