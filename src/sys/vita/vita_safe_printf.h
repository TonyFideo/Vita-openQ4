#ifndef OPENQ4_VITA_SAFE_PRINTF_H
#define OPENQ4_VITA_SAFE_PRINTF_H

// The full engine force-includes idlib before this header. Temporarily suspend
// its vsnprintf poison macro only inside this platform adapter, then restore it.
// Consume va_list with the guest toolchain, not Vita3K's Vprintf HLE bridge.
#pragma push_macro("vsnprintf")
#ifdef vsnprintf
#undef vsnprintf
#endif
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
#pragma pop_macro("vsnprintf")
#endif
