/* The car radio: Payback's songs 1, 2 and 4 and our remixes of them (radio.c, radiodec.s). */
#ifndef RADIO_H
#define RADIO_H
#include "gba.h"

enum { RADIO_ALL, RADIO_ORIGINALS, RADIO_REMIXES };

/* at 0x0203ffec (merge.ld): 20 bytes, all there is above STATE and the progress copy after it.
   radiodec.s knows p, a, b and on by their offsets. The boot clears it: mode RADIO_ALL. */
struct radio {
    const u8 *p;                   /* the next segment of the remix playing */
    s32 a, b;                      /* the decoder's last two samples, times vol + 1 */
    u16 left;                      /* segments to go */
    u8 on;                         /* 1-3: that remix plays (the interrupt's switch); 0x80 + n: a
                                      skip fades Payback's own song n; 0x40: Payback's own song
                                      cuts in on a remix; 0: Payback's own */
    u8 vol;                        /* what a and b are multiplied by, less 1 (volume 1-256) */
    u8 fade;                       /* 1: fade out in the next segment, 2: faded out, 3: fade in */
    u8 mode;                       /* RADIO_ALL / _ORIGINALS / _REMIXES, + 0x80: the player
                                      skipped, so the next pick is another song */
    u8 keys;                       /* how many interrupts (20 ms) SELECT (low 4 bits) and R (high
                                      4 bits) have been held, up to 15: only the interrupt writes it */
    u8 now;                        /* low 3 bits: the song playing, 1-3 Payback's songs 1, 2, 4, 4-6
                                      their remixes; + 8 for every song the radio starts */
};
extern struct radio radio;

void sf_play(int n);               /* Payback's radio's play (the build redirects its two calls) */
void radio_skip(void);             /* the next song, now (SELECT and R together in a car) */
int radio_chord(void);             /* SELECT and R went down within 0.1 s of each other */
int radio_mode(void);
void radio_set_mode(int m);
const char *radio_mode_name(int m);
void radio_hud(int driving, int ticks, int start);   /* the song's name for 2 s when one starts in a car */

#endif
