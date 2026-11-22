
#include <stdarg.h>
#include <stdio.h>
static FILE *f;
void shim_open(const char *p) { f = fopen(p, "w"); if (f) setvbuf(f, 0, _IOLBF, 0); }
void shim_log(int level, const char *fmt, ...) { va_list a; if (!f) return; fprintf(f, "[%d] ", level); va_start(a, fmt); vfprintf(f, fmt, a); va_end(a); }
