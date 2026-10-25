/* Stage 2: what the packages share. s2core.c (F) owns the frame state, the events and the hook
   dispatch; every other package's entry point has a weak stub there, so any package builds and runs
   alone on top of F, and they merge in any order.

   Per frame (merge.c, sf_draw):
     choose_mode, step, s2_tick, camera, [room view], world, entities, car, ship, s2_draw3d,
     flush, hud, s2_hud
   Elsewhere: s2_level_enter (a level was entered), s2_menu (first statement of sf_menu), s2_keys
   (after every keypad read), s2_ev (an event, from the sites below). */
#ifndef STAGE2_H
#define STAGE2_H
#include "gba.h"
#include "fx.h"
#include "pbapi.h"

enum { FOOT, DRIVE, FLY };         /* who moves the player: Payback (walking, its helicopter), our car, the Arwing */

/* ---- the frame ---- */
typedef struct {
    V3 pos;                        /* the player (man, car or ship), world units */
    s32 speed;                     /* units a second */
    u16 heading;                   /* 65536 a turn */
    u8 mode;                       /* FOOT, DRIVE, FLY */
    u8 docked;                     /* mode == FLY and the Arwing is in the hangar */
    u8 paused;                     /* Payback's game did not tick since our last frame (its pause menu), or a fade is on */
    u8 map, sub, story;            /* the map whose world is loaded (not PB_MAP, which is the rampage's), PB_SUB, !PB_RAMPAGE */
    u8 airborne;                   /* car: no wheel down; ship: no gear down */
    u8 sgstate;                    /* SG_* of the space game */
    u8 walk;                       /* W: SWK_* of spacewalk.h, 0 while he is not out in space */
    u8 pad;
    u16 veh;                       /* when driving, Payback's vehicle type (descriptor number) */
    u32 ticks;                     /* our frames since the game started (60 a second) */
    u32 clock;                     /* PB_CLOCK */
    void *me;                      /* Payback's record of the player (the man, or the car he drives) */
} S2Frame;                         /* 44 bytes, in keep */
extern S2Frame s2f;
extern u16 s2_phones;              /* Payback's own "Mission complete!" banners shown (the veneer counts them) */

/* ---- events: s2_ev(ev, a, b) from an existing site, delivered to ms_ev, cp_ev, st_ev in that order ---- */
enum {
    EV_NONE,
    EV_STUNT,                      /* F, car_stunts: a points, b kind (STUNT_*) */
    EV_KILL,                       /* F, ent_hurt: a Payback tag (+0x14c, -1 none), b type (descriptor number); a crate or box
                                      broken: a cell (x * 128 + z), b EVK_BOX. Payback tags entities too (2000..2003 on
                                      map 0): a package's own tags stay clear of that range, and -1 means untagged */
    EV_LAND,                       /* F, a car or the Arwing set down: a airborne distance in 1/8 cells, b 1 on a roof or deck */
    EV_MODE,                       /* F, mode changed: a new, b old */
    EV_DEATH,                      /* F, the player died or was arrested (Payback's respawn countdown started) */
    EV_SPACE,                      /* F, the Arwing crossed the edge of space: a 1 up, 0 down */
    EV_DOCK, EV_LAUNCH,            /* K */
    EV_FOE_DOWN,                   /* K: a foe tag, b kind */
    EV_ARWING_DOWN,                /* K */
    EV_PICKUP,                     /* K: a pod tag */
    EV_TALK,                       /* S: a crew, b node */
    EV_MENU,                       /* S: a item, b arg */
    EV_MIS_DONE, EV_MIS_FAIL,      /* E: a mission, b seconds (cp_ev) */
    EV_WALK,                       /* W (spacewalk.c): a 1 he bailed out above SPACE_LO (b his altitude / 16), 2 he reached the moon, 3 a beacon
                                      (b which, 0..3), 0 it ended (b 1 aboard the Arwing, 2 down under SPACE_LO: the ragdoll's) */
    EV_N
};
enum { STUNT_FRONT_FLIP = 1, STUNT_BACK_FLIP, STUNT_BARREL, STUNT_SPIN, STUNT_HUGE_AIR, STUNT_BIG_AIR, STUNT_LOOP };
#define EVK_BOX 0xffff
void s2_ev(int ev, int a, int b);

/* ---- hooks, called by merge.c ---- */
void s2_tick(void);                /* once a frame, after the game's step: fills s2f, the debug mailbox, the packages' ticks */
void s2_draw3d(void);              /* in the 3D scene, before the Arwing and the flush */
void s2_hud(void);                 /* over the finished picture */
void s2_level_enter(int map);      /* a level was entered (or restarted): the map's world is selected */
int s2_menu(int arg);              /* sf_menu's first statement: the next level (map * 2 + sub), or -1 for the usual */
void s2_keys(void);                /* after Payback's keypad read, whatever else sf_keys did */
int s2_room_view(void);            /* 0 a normal frame, 1 a station room, 2 reuse the last picture. A room (1) or a reuse (2)
                                      skips the world, s2_draw3d and the HUD's selection, tiles, radio and options lines
                                      (st_hud draws the room's own HUD), so S's room owns SELECT and the radio skip then */
void s2_room_draw(void);

/* merge.c: move the player. FLY: the ship, anywhere. FOOT or DRIVE: by Payback's record, only for a move of
   under 12 cells (Payback refuses 13 or more). mode must be the mode now. 1 if it moved */
int s2_put_player(V3 p, int heading, int mode);
int s2_ready(void);                /* merge.c: our memory is set up (the veneer may run before the first frame) */
void s2_dock_start(void);          /* merge.c: this level starts with the Arwing docked at the station (a chapter's orbital drop) */
void s2_progress_keep(void);       /* merge.c: the progress now is the one to keep (a save was loaded: not a stray write to undo) */

/* ---- the packages' entry points, all weak in s2core.c (empty, or the value that means "none") ---- */
/* E: the mission engine, hudline */
void ms_tick(void);
void ms_ev(int ev, int a, int b);
void ms_draw3d(void);
void ms_level_enter(int map);
int ms_dbg(int cmd, int arg);
void hl_draw(void);
int s2_hud_owned(void);            /* E: 1 while a HUD line or card is up (K's sg_hud then leaves y117 alone) */
/* P: campaign, saves */
void cp_tick(void);
void cp_ev(int ev, int a, int b);
void cp_level_enter(int map);
int cp_menu(int arg);              /* -1: the usual */
u32 cp_keys(void);                 /* buttons to hold down for Payback this tick, bit i = PB_BTN[i]; bits from B_N up are ignored */
int cp_dbg(int cmd, int arg);
int cp_act_running(void);
void cp_hud(void);                 /* the quick menu, over the picture (s2_hud) */
int cp_dock_keys(u16 hit, u16 keys, int main_ok);   /* the hangar's keys: 1 when the quick menu has them (main_ok: the main menu is up, L opens it) */
u32 cp_sig(void);                  /* changes whenever the quick menu would look different (sg_menu_sig folds it in) */
/* the orbital drop that opens a chapter (the planet package supplies pl_*; weak, so nothing happens without it) */
void pl_drop_begin(int map, int hx2, int hy2);   /* docked at the station over the map: the planet below is drawn from here */
void pl_drop_end(void);                          /* below the edge of space, or act 1 done, or the level left: the city is the world */
int pl_drop_active(void);
/* S: the station */
int st_view(void);
void st_draw(void);
void st_hud(void);
void st_ev(int ev, int a, int b);
int st_dbg(int cmd, int arg);
int st_active(void);
/* K: combat */
int sg_dbg(int cmd, int arg);
int sg_job_active(void);
int sg_foe_spawn(int kind, V3 p, V3 home, int hp, int tag);   /* the slot, or -1 */
int sg_foe_alive(int tag);
void sg_foe_clear(int tag);
void sg_foe_hold(int tag, int on);
int sg_boss_spawn(int boss, V3 p, int tag);
int sg_boss_alive(int tag);
/* stage 3 */
int bigmap_enter(int arg);         /* weak: 0, so stage 2 plays the ending */

/* ---- the debug mailbox (16 bytes, found by symbol s2_dbg): the harness writes cmd and arg, then
   the magic; s2_tick runs the command in the frame, puts the answer in ret, counts seq and clears
   the magic. cmd 1..15 E, 16..31 P, 32..47 S, 48..63 K, 64..79 F, 80..95 W (spacewalk.c, sw_dbg): */
typedef struct { u32 magic; u16 cmd, arg; s32 ret; u32 seq; } S2Dbg;
extern S2Dbg s2_dbg;
#define S2_DBG_MAGIC 0x42443253     /* 'S2DB' */
enum {
    DBG_F_EVENTS = 64,             /* ret = the number of events arg (EV_*) raised */
    DBG_F_HOOK,                    /* ret = the number of calls of hook arg (HK_*) */
    DBG_F_RAISE,                   /* raise event arg with a = b = 0 (ret 0) */
    DBG_F_PUT,                     /* put the player at the middle of cell arg (x << 7 | z), heading 0; ret = s2_put_player's */
    DBG_F_RESET                    /* zero the counters */
};
enum { HK_TICK, HK_DRAW3D, HK_HUD, HK_LEVEL, HK_MENU, HK_KEYS, HK_ROOM, HK_BANNER, HK_N };

/* ---- data the build places above 8 MiB (tools/s2build.py): an 8-byte zero blob when a package has none ---- */
extern const u8 s2_blob[];         /* E and C: the missions, places and chapters */
extern const u8 st_blob[];         /* S: the station's rooms, crew and talk */

#endif
