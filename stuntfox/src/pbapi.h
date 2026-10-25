/* The one place stage 2 touches Payback (Europe): every address it uses has a name here, and no
   stage-2 .c file may write a raw 0x02.. / 0x03.. / 0x08.. address (tools/pbapi_check.py fails the
   build on one). A port to another machine supplies its own copy of this file and nothing else.

   PBA_x: the address. Each is checked against the player's ROM by tools/pbapi_check.py at build time:
   fn   a function (the Thumb bit is set where it is called): its first instruction is a push or a
        known prologue
   rom  data in the ROM: it is read, never written
   ram  a word of Payback's RAM: Payback's own code names it as a literal (lit=0x.. when it only
        names a neighbour)
   Facts marked [measured] were seen in the emulator, [disasm] were read from the code.

   Banned in stage-2 code (tools/lint_text.py): the phone ticker (0x08039871 is deliberately not here),
   a write to the level's target 0x02001df8 (display only) or 0x020000c0 (read only at init), and any
   persistent data of ours in 0x02006c30..0x020075a8 (Payback's mission state). */
#ifndef PBAPI_H
#define PBAPI_H
#include "gba.h"

/* ---- goals and the command queue ----
   A goal is 0x24 bytes: +0 id, +4 kind, +8 a, +0xc b, +0x10 floor, +0x14 marker byte (non-zero: the
   arrow round-robins over it), +0x18..0x1f spare (-1), +0x20 phone slot. Kinds seen: 0 the level's
   score target (a = score), 1 and 7 a ringing phone (green, red; a, b = x, y at 2048 a cell), 4 go
   to a cell, 9 kill a tagged one. The count is the number of goals (cap 100).
   A command is 0x28 bytes, its fields 4 later than a goal's and +0 the kind of command (0 add a
   goal, 1 remove the goal with id +4). The index is the LAST one (-1 empty), the queue is applied in
   the tick it is pushed (0x0807a918, called from the arrow code 0x0807aa3c) [disasm]. */
#define PBA_GOALS        0x0201a7e0   /*ram*/
#define PBA_NGOALS       0x0201a7d8   /*ram*/
#define PBA_CMDQ         0x0201b5f0   /*ram*/
#define PBA_NCMD         0x0201a7dc   /*ram*/
#define PB_NGOAL_MAX     100
#define PB_GOAL_SIZE     0x24
#define PB_CMD_SIZE      0x28
#define PB_GOALS         ((const s32 *)PBA_GOALS)               /* 9 words a goal (read; write through pb_goal_u8) */
#define PB_NGOALS        (*(volatile s16 *)PBA_NGOALS)
#define PB_CMDQ          ((const s32 *)PBA_CMDQ)                /* 10 words a command */
#define PB_NCMD          (*(volatile s16 *)PBA_NCMD)
enum { PBG_LEVEL = 0, PBG_PHONE = 1, PBG_GOTO = 4, PBG_PHONE_RED = 7, PBG_HIDDEN_PICKUP = 47 };
#define PBG_ID 0
#define PBG_KIND 1
#define PBG_A 2
#define PBG_B 3
#define PBG_FLOOR 4
#define PBG_MARKER_BYTE 0x14

/* goal i's byte at offset off (the marker byte is PBG_MARKER_BYTE) */
static inline volatile u8 *pb_goal_u8(int i, int off) { return (volatile u8 *)PBA_GOALS + PB_GOAL_SIZE * i + off; }
static inline volatile s32 *pb_goal_w(int i, int k) { return (volatile s32 *)PBA_GOALS + 9 * i + k; }

/* push the command that adds a goal; Payback's own calls pass -1 for the fields they do not use.
   Applied the same tick, so the goal exists from the next. id: ours are 0x5000 + (a slot) [stage 2] */
#define PBA_CMD_PUSH     0x0807be61   /*fn*/
typedef void (*PbCmdPush)(int id, int kind, int a, int b, int floor, int marker, int e0, int e1, int e2);
static inline void pb_goal_add(int id, int kind, int a, int b, int floor, int marker)
{
    ((PbCmdPush)PBA_CMD_PUSH)(id, kind, a, b, floor, marker, -1, -1, -1);
}
/* push the command that removes the goal with this id (910 calls in Payback's own scripts) */
#define PBA_GOAL_REMOVE  0x0807be19   /*fn*/
static inline void pb_goal_remove(int id) { ((void (*)(int))PBA_GOAL_REMOVE)(id); }
/* Payback's "goal reached" for id: its mission scripts. NEVER with our ids [P4: markers use floor 0x7f] */
#define PBA_GOAL_REACHED 0x0806c22d   /*fn*/
/* the phones come back (every ringing one a mission has hidden) */
#define PBA_PHONES_READD 0x0803e739   /*fn*/
static inline void pb_phones_readd(void) { ((void (*)(void))PBA_PHONES_READD)(); }

/* the arrow over the player: its target x, y (2048 a cell), round-robin over the marker goals */
#define PBA_ARROW        0x020025f0   /*ram*/
#define PB_ARROW         ((volatile s32 *)PBA_ARROW)

/* ---- the level ---- */
#define PBA_CUR_MISSION  0x02007134   /*ram*/   /* the phone mission's type: its completion code (case 1..9) clears a slot of its table by it, right after the
                                                    "Mission complete!" banner; 0 at the start of a rampage on map 0 */
#define PBA_LEVEL_END    0x02001e08   /*ram*/   /* 3: the target was reached, 2: game over */
#define PBA_CLOCK        0x02001e00   /*ram*/   /* the level's clock, 30 a second, 0 at a level's start */
#define PBA_LIVES        0x02001e4e   /*ram*/
#define PBA_MAP          0x02001d40   /*ram*/   /* the map rampage plays, 0..10 */
#define PBA_DIFF         0x02001d3c   /*ram*/
#define PBA_RAMPAGE      0x02001d39   /*ram*/   /* 1: rampage, 0: story */
#define PBA_WAS_RAMPAGE  0x02001d3a   /*ram*/   /* set as a rampage ends */
#define PBA_CITY         0x02003ef2   /*ram*/   /* the city (map) loaded */
#define PBA_SUB          0x02003ef4   /*ram*/   /* the story sub-level */
#define PBA_TROPHIES     0x020026d2   /*ram*/   /* 6 x s16 */
#define PBA_MULT         0x02001df0   /*ram*/   /* the score multiplier, 1..4 */
#define PBA_RESPAWN      0x02001e0c   /*ram*/   /* the player's respawn countdown: from 80 at a death or arrest, 0 alive */
#define PBA_SAVED_SCORE  0x02001e1c   /*ram*/   /* the score while he is dead (pb_get_score) */
#define PB_CUR_MISSION   (*(volatile s16 *)PBA_CUR_MISSION)
#define PB_LEVEL_END     (*(volatile s16 *)PBA_LEVEL_END)
#define PB_CLOCK         (*(volatile u32 *)PBA_CLOCK)
#define PB_LIVES         (*(volatile s16 *)PBA_LIVES)
#define PB_MAP           (*(volatile s16 *)PBA_MAP)
#define PB_DIFF          (*(volatile u8 *)PBA_DIFF)
#define PB_RAMPAGE       (*(volatile u8 *)PBA_RAMPAGE)
#define PB_WAS_RAMPAGE   (*(volatile u8 *)PBA_WAS_RAMPAGE)
#define PB_CITY          (*(volatile s16 *)PBA_CITY)
#define PB_SUB           (*(volatile s16 *)PBA_SUB)
#define PB_TROPHIES      ((volatile s16 *)PBA_TROPHIES)
#define PB_MULT          (*(volatile s16 *)PBA_MULT)
#define PB_RESPAWN       (*(volatile s16 *)PBA_RESPAWN)

/* the score: the controlled record's +0x90 (the saved one while he is dead) [disasm 0x080258e0: P13] */
#define PBA_GET_SCORE    0x080258e1   /*fn*/
static inline int pb_get_score(void) { return ((int (*)(void))PBA_GET_SCORE)(); }
/* score += n x the multiplier */
#define PBA_ADD_SCORE    0x080256dd   /*fn*/
static inline void pb_add_score(int n) { ((void (*)(int))PBA_ADD_SCORE)(n); }

/* ---- text: titles are Payback's raw banner (the ticker stays quiet) ----
   pb_banner_raw(0, s) copies s (strcpy, 20 bytes a slot: 19 letters and the 0) into banner slot 0
   and starts the flying letters [disasm 0x08039bc8]; tools/lint_text.py holds every literal to 19.
   pb_banner_idx(i) shows Payback's own line i: 0x7e6 "Mission complete!" (it raises the
   multiplier too), 0x7ec "Mission failed!". Payback's calls to it all go through the veneer in
   s2core.c, which counts 0x7e6 (s2_phones); a direct call (this one) is not counted. */
#define PBA_BANNER_RAW   0x08039bc9   /*fn*/
#define PBA_BANNER_IDX   0x0807a685   /*fn*/
#define PBA_BANNER_IDX_FN 0x0807a684  /*fn*/   /* (the bl target of Payback's 72 calls) */
#define PB_BANNER_COMPLETE 0x7e6
#define PB_BANNER_FAILED   0x7ec
#define PB_BANNER_LEN 19
static inline void pb_banner_raw(int slot, const char *s) { ((void (*)(int, const char *))PBA_BANNER_RAW)(slot, s); }
static inline void pb_banner_idx(int i) { ((void (*)(int))PBA_BANNER_IDX)(i); }

/* ---- entities ----
   The list: pointers at PB_ENTITY, PB_NENTITY the LAST index. Records: +4 x, +8 y (s32, 2048 a
   cell), +0xc z (u16: 19904 at street level, 16 a step), +0x12 heading (5760 a turn), +0x1c descriptor
   (vehicles 0x08354af4 + k x 0x3c), +0x10f state, +0x68 health, +0x90 score (the player's) */
#define PBA_ENTITY       0x03000c60   /*ram*/
#define PBA_NENTITY      0x0300000c   /*ram*/
#define PBA_CONTROLLED   0x02001db8   /*ram*/
#define PBA_GRID         0x03000d60   /*ram*/
#define PBA_DESC0        0x08354af4   /*rom*/   /* the descriptor table: vehicles k = 0.., then the people's animations */
#define PB_ENTITY        ((u8 *const volatile *)PBA_ENTITY)
#define PB_NENTITY       (*(volatile s16 *)PBA_NENTITY)
#define PB_CONTROLLED    (*(volatile s16 *)PBA_CONTROLLED)
#define PB_GRID          (*(const u32 *volatile *)PBA_GRID)
/* the column of cell (cx, cz), 0..127: a pointer, into the ROM while nothing has changed the cell, else into a copy in EWRAM */
static inline u32 pb_col(int cx, int cz) { const u32 *g = PB_GRID; return g ? g[(cx << 7) + cz] : 0; }
#define PB_IN_ROM(p) ((u32)(p) >= 0x08000000u)
#define PBE_X 4
#define PBE_Y 8
#define PBE_Z 0xc
#define PBE_HEAD 0x12
#define PBE_DESC 0x1c
#define PBE_HEALTH 0x68
#define PBE_SCORE 0x90
#define PBE_WANTED 0x5a               /* s8: the wanted stars, in the controlled record (the HUD's stars follow it) [measured: P10] */
#define PBE_STATE 0x10f
#define PBE_TAG 0x14c                 /* s32: the tag pb_spawn_tagged gave it (-1 after pb_kill) */
static inline int pb_wanted(const u8 *me) { return me ? *(const s8 *)(me + PBE_WANTED) : 0; }
#define PB_DESC_SIZE 0x3c
#define PB_DESC_K(d) (((u32)(d) - PBA_DESC0) / PB_DESC_SIZE)   /* a record's descriptor as Payback's own number */

/* a tagged entity: Payback's spawn with a tag kept at +0x14c. Seven arguments [disasm 0x0807874c]:
   tag; type (descriptor k, < 1000; negative picks another table); x, y (2048 a cell); then mode
   (0 normal, 1 and 2 shift the height), the turn handed to Payback's spawner, and a byte kept at
   +0xc8. K's probe P12 settles which types exist on which map; until it has, stage 2 calls it
   with (0, 0, 0) for the last three */
#define PBA_SPAWN_TAGGED 0x0807874d   /*fn*/
typedef void (*PbSpawnTagged)(int tag, int type, int x, int y, int mode, int turn, int byte);
static inline void pb_spawn_tagged(int tag, int type, int x, int y)
{
    ((PbSpawnTagged)PBA_SPAWN_TAGGED)(tag, type, x, y, 0, 0, 0);
}
/* every entity with this tag becomes a wreck (state 6, unless it is the man on foot) and loses the tag.
   Nothing in Payback's image calls it (pbapi_check holds its code to what was read by hand), so it is as
   untried as pb_spawn_tagged until K's probe P12 runs them */
#define PBA_KILL         0x0807a4bd   /*fn*/
static inline void pb_kill(int tag) { ((void (*)(int))PBA_KILL)(tag); }
/* the entity with this tag, or 0 */
#define PBA_ENT_BY_TAG   0x08025979   /*fn*/
static inline u8 *pb_ent_by_tag(int tag) { return ((u8 *(*)(int))PBA_ENT_BY_TAG)(tag); }
/* "the player hurt entity i" (wanted stars, kill score, the goals waiting on it) */
#define PBA_HURT         0x0800020d   /*fn*/
static inline void pb_hurt(int i, int by_man) { ((void (*)(int, int))PBA_HURT)(i, by_man); }

/* ---- keys: the buttons Payback decoded this tick, one byte each, 1 = held ---- */
#define PBA_BTN          0x0200c3e4   /*ram*/
#define PB_BTN           ((volatile u8 *)PBA_BTN)
enum { B_UP = 0, B_DOWN = 1, B_SELECT = 2, B_LEFT = 4, B_RIGHT = 5, B_A = 6, B_B = 7, B_R = 8,
       B_START = 9, B_L = 10, B_SELECT2 = 11, B_N = 14 };

/* ---- saves (the EEPROM library; P's) ----
   the config pointer survives the game's start(): 0x087d92e4 is the 64 Kbit chip, 0x087d92d8 4 Kbit */
#define PBA_EEP_READ     0x0807c475   /*fn*/   /* (block, u16 buf[4]) */
#define PBA_EEP_PROG     0x0807c6f1   /*fn*/   /* (block, buf) -> 0 on success */
#define PBA_EEP_CFG      0x03000d64   /*ram*/
#define PBA_EEP_IDENT    0x0807c3ad   /*fn*/   /* (size in Kbit) identify the chip */
#define PBA_EEP_IDENT_SITE 0x08027c76 /*site*/ /* the bl in the boot load, after movs r0, #4 at 0x08027c74 */
#define PB_EEP_CFG       (*(volatile u32 *)PBA_EEP_CFG)

/* ---- the minimap: 64 x 64, 4 bits a pixel, 2 cells a pixel; 0x800 bytes a level ---- */
#define PBA_MINIMAP      0x0834c230   /*rom*/
#define PB_MINIMAP(level) ((const u8 *)(PBA_MINIMAP + 0x800 * (level)))

/* ---- stage 3: where the live grid window starts, in 1/8 cells (Place units), added to every Place
   before it is compared with Payback's coordinates. Nothing slides today. ---- */
static inline void pb_window_origin(s32 *ox8, s32 *oy8) { *ox8 = 0; *oy8 = 0; }

#endif
