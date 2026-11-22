/* rigshim.c: log sink for ps1game.py (libretro log callback).
   Messages of exactly one character are the guest's TTY (the core prints BIOS putchar one character per log call): they go to tty.log and to a
   ring that Python drains with rs_tty_read().  Everything else is the core's own log: core.log, one "[level] " prefix per line. */
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
static FILE *flog, *ftty;
static int at_bol = 1;
#define RING (1 << 20)
static char ring[RING];
static unsigned long long wr, rd;
void rs_open(const char *logpath, const char *ttypath) {
  if (flog) fclose(flog);
  if (ftty) fclose(ftty);
  flog = fopen(logpath, "w"); ftty = fopen(ttypath, "w");
  if (flog) setvbuf(flog, 0, _IOLBF, 0);
  at_bol = 1; wr = rd = 0;
}
void rs_tty_put(const char *s, unsigned n) {
  for (unsigned i = 0; i < n; i++) { ring[wr % RING] = s[i]; wr++; }
  if (wr - rd > RING) rd = wr - RING;
  if (ftty) { fwrite(s, 1, n, ftty); if (memchr(s, '\n', n)) fflush(ftty); }
}
void rs_log(int level, const char *fmt, ...) {
  char buf[4096]; va_list a; va_start(a, fmt); int n = vsnprintf(buf, sizeof buf, fmt, a); va_end(a);
  if (n < 0) return;
  if (n >= (int)sizeof buf) n = sizeof buf - 1;
  if (n == 1) { rs_tty_put(buf, 1); return; }
  if (!flog) return;
  for (int i = 0; i < n; i++) { if (at_bol) { fprintf(flog, "[%d] ", level); at_bol = 0; } fputc(buf[i], flog); if (buf[i] == '\n') at_bol = 1; }
}
unsigned rs_tty_read(char *dst, unsigned max) {
  unsigned n = 0; while (rd < wr && n < max) { dst[n++] = ring[rd % RING]; rd++; }
  return n;
}
void rs_flush(void) { if (flog) fflush(flog); if (ftty) fflush(ftty); }
