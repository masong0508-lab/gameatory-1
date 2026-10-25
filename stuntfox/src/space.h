/* The sky by altitude, the stars, and what is up there: the station and the asteroids. */
#ifndef SPACE_H
#define SPACE_H
#include "fx.h"

void space_init(void);
V3 station_at(int map);            /* where the station hangs over a map (units, 34000 up) */
void space_station(int map);       /* ... and put it, and the asteroids round it, there */
void space_tick(void);
void sky_draw(s32 alt);            /* sky and sea bands (background); sets the palette */
void stars_draw(s32 alt);          /* after the background is drawn */
void space_draw(void);             /* the station and the asteroids */
int palette_commit(void);          /* during vblank: apply a pending sky palette (1 if it did) */

#endif
