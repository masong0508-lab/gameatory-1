/* The one steady HUD line of stage 2 (mission.c sets it, s2core.c's s2_hud draws it): the objective at the left, at
   most 18 letters, a space and the status after it, at most 7 ("0:42", "3/8", "HP 7", "NE 34"). It is a band the
   height of the letters at y 117, clear of Payback's ticker below and its HUD on the right, as wide as its text.
   Cards are two lines of up to 38 letters at y 100 and 108 for three seconds, after a title banner has gone (it is up
   for 220 ticks). Colours are steady: white, the whole line turning amber once at 10 s left; nothing blinks. Nothing
   is drawn in Payback's pause menu, at a level's end, in the hangar or while the man is being brought back.
   The picture is page-redrawn every frame, so the text is inked once into bit strips (one bit a pixel, when its
   words or status change: ~700 cycles a letter then) and each frame only expanded onto the page a word at a
   time (~12 cycles a word: ~3.5k a frame for the line, ~13k with a card), not drawn letter by letter. The font's
   shadow is the panel's own colour, so on the panel a letter is its ink alone. */
#ifndef HUDLINE_H
#define HUDLINE_H
#include "gba.h"

#define HL_Y 117                   /* K's sg_hud line is on this row too: it gives way while hl_up() */
#define HL_LEFT_MAX 18
#define HL_STAT_MAX 7
#define HL_CARD_TICKS 90           /* Payback's clock: 30 a second */
enum { HLS_NONE, HLS_TIME, HLS_COUNT, HLS_HP, HLS_BEAR };   /* the status: a seconds; a of b; a hp; compass a (0 N, 2 E ..), b cells */

void hl_text(const char *s);                /* the left text (not copied: ROM text; "" or 0 clears it) */
void hl_stat(int kind, int a, int b);       /* the status; formatted only when it changes */
void hl_card(const char *s, int delay);     /* two lines, split at a newline, three seconds, after delay ticks (a title banner is up first) */
void hl_clear(void);                        /* line and card off */
void hl_off(void);                          /* the line off, a card left to run out */
const char *hl_status(void);                /* the status text now (for the debug mailbox and the tests) */
int hl_up(void);                            /* a line or a card is up */
#endif
