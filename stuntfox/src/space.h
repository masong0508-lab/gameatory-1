/* The sky by altitude, the stars, and what is up there: the station and the asteroids. */
#ifndef SPACE_H
#define SPACE_H
#include "fx.h"

void space_init(void);
void space_tick(void);
void sky_draw(s32 alt);            /* sky and sea bands (background); sets the palette */
void stars_draw(s32 alt);          /* after the background is drawn */
void space_draw(void);             /* the station and the asteroids */
void palette_commit(void);         /* during vblank: apply a pending sky palette */

#endif
