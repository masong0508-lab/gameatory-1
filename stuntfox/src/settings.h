/* GAME SETTINGS (MERGE build): the hangar's second options page, in Payback's own menu letters.
   Rampage's target and time limit, Payback's difficulty, wanted stars, lives and the damage he
   takes, our car, the Arwing, the ragdolls and our ticker lines. Each kept in spare bits of the
   progress words (sg_save), stored as its distance from its default, so 0 everywhere (a copy
   from before these) is the game as it was. */
#ifndef SETTINGS_H
#define SETTINGS_H
#include "gba.h"

extern u8 opt_tex;                 /* Payback's tiles on */
extern u8 opt_planet;              /* the planet from up high (planet.c) */
extern u16 cam_dflt;               /* the chase camera settles at this distance (256 as built) */
extern u8 opt_ticker;              /* 0: our hint lines stay off Payback's ticker */

void opt_save(u32 *w);             /* ORs the settings into sg_save's words 1..3 */
void opt_load(const u32 *w);       /* and back, each in its range, applied */
int opt_x_bad(void);               /* the extras' copy (XM) is good and they are not what it holds */
void opt_x_keep(void);             /* store them there */
void opt_level_enter(void);        /* a level starts: its clock from 0, the lives */
/* each frame, after Payback's tick: the target, the clock, difficulty, wanted, lives, damage.
   me: the record he controls (or 0), ticks: game ticks since the last frame (0 paused) */
void opt_frame(u8 *me, int ticks);
void opt_hud(int paused);          /* the time left, over the picture (none on Payback's pause menu) */
void opt_open(void);               /* the page comes up */
int opt_input(u16 hit, u16 keys);  /* a tick on the page (true D-pad sides): 1 when B leaves it */
void opt_draw(void);
#endif
