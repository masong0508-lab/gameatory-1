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

void sg_level_enter(void);         /* Payback loaded a level: what was out there goes, progress stays */
void sg_save(u32 *w);              /* the progress (credits, upgrades, paint, medals, jobs) as 4 words */
void sg_load(const u32 *w);
void sg_sane(void);                /* each of those back in its range */

void sg_crash(V3 p);               /* the empty Arwing comes down at p (bailing out): fire, pieces, smoke */
void sg_fx_tick(void);             /* the fire and smoke go on, a tick, while the Arwing is not out */
void sg_note(const char *s);       /* a few seconds of news on our HUD, not on Payback's ticker */
void sg_banner(void);              /* draws it, when the Arwing is not out (sg_hud does then) */
/* merge.c: the Arwing's shots into Payback's city */
int city_near(V3 lo, V3 hi, u32 *near);   /* who stands where shots fly this tick (lo..hi): bits of near[2] */
int city_hit(V3 p, int dmg, const u32 *near);   /* a shot at p into those of them: the person it is in,
                                      else the nearest vehicle, takes dmg; its index + 1 if it hit one */
void city_blast(V3 p, int dmg, s32 r, int skip);   /* a missile's splash: dmg x (1 - d / r) off everyone
                                      within r that the city does not shield, but record skip */
/* one pass over its people and vehicles: how far along dir from `from` the line first meets one
   (*ray, len if none within len), and auto-aim's candidates, the CITY_CANDS nearest the line inside
   the cone (cos over lim / ONE) within range, people first: their records' indices (cand[], best
   first) and how far along (at[]); how many */
#define CITY_CANDS 3
int city_scan(V3 from, V3 dir, s32 len, s32 lim, s32 range, s32 *ray, u8 *cand, s32 *at);
int city_tag(int i);               /* which record is at index i now, as a byte (0 none) */
int city_target_at(int i, V3 *p, V3 *v);   /* record i now: 1 with its middle and velocity (units a tick) */
int shot_blocked(V3 a, V3 b);      /* spacegame.c: does a shot's step a -> b run into the ground, a deck or a railing */

#endif
