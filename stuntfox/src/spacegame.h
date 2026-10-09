/* The space game around the station (MERGE build): docking, the hangar and its job board,
   shipyard and paint shop, pirates and dogfights, jobs that take you down into Payback's city,
   and fox medals to find. */
#ifndef SPACEGAME_H
#define SPACEGAME_H
#include "ship.h"

enum { SG_FLY, SG_DOCKING, SG_DOCKED, SG_LAUNCH, SG_DEAD };
extern int sg_state;
extern u8 sg_invert;               /* the stick: 0 UP dives (Star Fox), 1 UP climbs */
extern u8 sg_autoaim;              /* 1: lasers bend toward the target in front, 0: straight */

void sg_init(void);
/* one tick of the Arwing being out (FLY mode). keys: as held (steering already mirrored),
   hit: newly pressed (on the first tick of a frame only). Flies the Arwing itself (or docks,
   launches or runs the hangar's menus). */
void sg_tick(Ship *s, u16 keys, u16 hit);
int sg_select(Ship *s);            /* SELECT held while flying: 1 if the space game took it (docking) */
void sg_landed(Ship *s);           /* the Arwing came to rest on the station's deck */
void sg_draw(const Ship *s);       /* 3D: pirates, shots, pods, medals, gates, the hangar's crew */
void sg_hud(const Ship *s);        /* 2D, over the finished picture */
void sg_paint(void);               /* sets model_hull and model_body for the Arwing */
V3 sg_pad(void);                   /* where the Arwing stands in the hangar (units) */
void sg_dock_now(Ship *s);         /* put it in the hangar, on the pad */
int sg_ship_visible(void);

void sg_say(const char *s);        /* merge.c: one line on Payback's ticker */

#endif
