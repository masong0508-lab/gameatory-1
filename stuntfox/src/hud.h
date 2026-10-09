/* On-screen text, drawn with hardware sprites over the 3D view. */
#ifndef HUD_H
#define HUD_H
#include "gba.h"

enum { HUD_WHITE, HUD_YELLOW, HUD_RED, HUD_CYAN, HUD_GREEN };

void hud_init(void);
void hud_begin(void);
void hud_text(int x, int y, const char *s, int pal);
void hud_big(int x, int y, const char *s, int pal);     /* double size, 16 pixels a letter */
void hud_end(void);
void hud_commit(void);                                  /* during vblank */
/* writes v as decimal into buf, returns the end */
char *hud_num(char *buf, int v);

#endif
