/* Space walks (MERGE build): he bails out of the Arwing at any height. Under SPACE_LO that is the
   ragdoll's fall as ever; from SPACE_LO up he is a figure of his own that falls as slowly as the air
   is thin (gravity and the air fade out together up to SPACE_HI), floats above it, and with the
   jet pack (bought at the shipyard) flies: D-pad forward and back and turn, A up, B down, L brake.
   Lower than SPACE_LO again he is the ragdoll once more and lands with its bounce. SELECT held
   calls the Arwing (it flies to him) or, near it, gets him aboard. A small moon to walk on, a few
   asteroids and four beacons are out there for the missions (stage2.h's mailbox has three samples). */
#ifndef SPACEWALK_H
#define SPACEWALK_H
#include "ship.h"

extern u8 sw_pack;                 /* the jet pack is bought (spacegame.c keeps it with the other upgrades) */
extern u16 sw_pack_k;              /* GAME SETTINGS: its strength, 256 = as built */

/* ---- for the missions (E, C): where the spacewalker is, and the places out there ---- */
enum { SWK_NONE, SWK_FALL, SWK_FLOAT, SWK_MOON };   /* what he is doing: out of the Arwing under SPACE_HI, above it, on the moon */
int sw_active(void);               /* the man is out of the Arwing high over the city (a figure, not a ragdoll) */
int sw_kind(void);                 /* SWK_* */
V3 sw_pos(void);                   /* his pelvis (units) */
int sw_reach(V3 p, s32 r);         /* a walk is on and he is within r (units) of p */
int sw_land_at(V3 p);              /* a mission puts him down at p (units; on the moon's skin if p is within its reach): 1 if it did */
V3 sw_moon(s32 *radius);           /* the moon's middle (units) and its radius */
int sw_places(void);               /* how many of the beacons are out there */
V3 sw_place(int i);                /* beacon i (units): 0..2 rings in space, 3 a post on the moon's skin */
int sw_obj(int *step, int *of);    /* the sample objective under way (1..3, 0 none), its step and how many steps */

/* ---- merge.c ---- */
int sw_begin(Ship *s, int slot, V3 feet, s32 yaw, int side);   /* he has jumped out of s (his body is rags[slot]) from above SPACE_LO, out of its side (-1 or 1): 1 if the walk began */
int sw_on(void);
void sw_reset(void);               /* a level was entered, or the walk ends with nobody left */
void sw_tick(u16 keys, u16 hit);   /* one tick of him (keys as held; steering as the player pressed it) */
int sw_flies(Ship *s);             /* one tick of the empty Arwing on its way to him: 1 if it moved it */
void sw_call(void);                /* SELECT held: it comes, or he climbs aboard if it is by */
enum { SWF_KEEP, SWF_BOARD, SWF_DROP, SWF_NEWSHIP };
int sw_frame(int ticks, V3 *at, V3 *vel, s32 *yaw);   /* once a frame: SWF_BOARD (get aboard), SWF_DROP (under SPACE_LO: the ragdoll takes him), SWF_NEWSHIP (an Arwing is wanted) */
void sw_ship_gone(void);           /* once a frame while the walk is on and there is no Arwing (it crashed): a new one comes when he calls */
void sw_view(V3 *p, V3 *fwd, V3 *up);   /* the camera's: where he is, which way he faces, his up */
void sw_cam_clear(V3 *pos);        /* keeps the camera out of the moon and the rocks */
void sw_draw3d(void);              /* the moon, his pack, and whether the rocks and rings are to be drawn (stage2.h's s2_draw3d) */
void sw_rocks_draw(void);          /* the rocks and the rings round the moon: drawn after sw_draw3d, not from it (the stack is tight) */
void sw_rings_draw(void);
void sw_hud(void);                 /* his altitude, the beacon, the hints (s2_hud) */
int sw_solid(V3 p, Hit *h);        /* physics.c's space_hit: the moon and the rocks (p fine units) */
int sw_dbg(int cmd, int arg);      /* the mailbox, commands 80..95 */

#endif
