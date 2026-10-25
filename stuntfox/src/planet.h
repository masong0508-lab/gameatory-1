/* The planet under the map (MERGE build): from a few thousand units up the horizon curves, the air thins into
   a lit rim, and from 12000 up the map is a patch on a planet wearing its own colours, with the station in
   orbit over it. Everything is drawn as background polygons, in Payback's own palette (no palette change).
   The sphere is tangent to the street plane under the camera, so the world below needs no change: it
   only has to be left out where the patch stands in for it (pl_cover). */
#ifndef PLANET_H
#define PLANET_H
#include "fx.h"

#define PL_COVER_ON 9000           /* the patch stands in for the island and the far patches from this height up ... */
#define PL_COVER_OFF 8200          /* ... until this one on the way down (a hair of height must not flip it) */
#define PL_CITY_OFF 12000          /* the city's own view (world_draw) shrinks from pl_on to nothing here: under the patch, so no hole */

void pl_set(int map);              /* a level's planet look: when its world is selected */
int pl_begin(s32 alt);             /* each frame, before the sky: 0 no planet in sight (the flat sky as ever), 1 sky and planet */
void pl_draw(const u16 *cols, const s32 *bounds);   /* the sky (its 5 bands' colours and bounds, as r_sky takes them), the
                                      atmosphere, the planet, its patch and clouds (background polygons) */
extern u8 pl_hide;                 /* set by the frame: nothing of the planet is in sight (inside the station's hangar): pl_begin gives 0 */
extern u16 pl_on;                  /* the height the patch starts at on this map: Real Park, whose city costs least to draw, a little later */
extern u8 pl_cover;                /* the patch stands in for the city's island and far patches: world_draw leaves them out */

/* For the campaign's orbital drop and Fox Station (packages P and S): the station over a map, and the way down.
   pl_station: where the station hangs over map (world units; y 34000). pl_drop_alt: the descent's height for
   t = 0 (docked in orbit) .. 256 (on the pad), slow at the ends and quick through the air, so the planet grows
   and the sky changes at a pace that reads; the rest of the picture follows from the height alone. */
V3 pl_station(int map);            /* (map -1: this level's) */
s32 pl_drop_alt(int t, s32 pad_alt);

#endif
