#ifndef OPENQ4_VITA_SAFE_PRINTF_H
#define OPENQ4_VITA_SAFE_PRINTF_H

// Include before idlib's legacy C-string poison macros. Format with the
// toolchain's own va_list consumer, not Vita3K's sceClibVprintf HLE bridge.
#include <stdarg.h>
#include <stddef.h>
#include <stdio.h>

static inline void VitaFormatPrint(char *text, size_t capacity,
                                  const char *format, va_list args) {
    if (text == NULL || capacity == 0) return;
    text[0] = '\0';
    if (format == NULL) return;
    va_list copy;
    va_copy(copy, args);
    const int result = vsnprintf(text, capacity, format, copy);
    va_end(copy);
    if (result < 0) text[0] = '\0';
    text[capacity - 1] = '\0';
}
#endif
