/* The mission data blob (stage 2): chapters, missions, objectives, places and text, as the compiler
   (tools/content) writes them and mission.c reads them straight from the ROM. Little-endian, every
   record aligned to its own size, no pointers (offsets from the blob's start): nothing here names a GBA
   address or a byte of Payback's, so another machine's build reads the same file.

   World units everywhere (a cell is 1024): a MsPlace is in 1/8 cell, its height and radius in units, and
   the build's mkdemo.py and the content compiler both write this layout. A blob of 8 zero bytes is "no
   content" (s2build.py hands that out when no builder is present). */
#ifndef MISDATA_H
#define MISDATA_H
#include "gba.h"

#define S2_MAGIC 0x31433253                  /* 'S2C1' */
#define S2_VER 1

typedef struct {                             /* blob header, 56 bytes */
    u32 magic;
    u16 ver, nchap;
    u16 nmis, nobj;
    u16 nplace, ntext;
    u32 off_chap, off_mis, off_obj, off_place, off_text, off_name, off_spare;
    u32 size, crc;                           /* crc32 of the bytes after the header */
    u32 flags;                               /* (0) */
} S2Head;

enum { CH_STORY = 1, CH_DROP = 2, CH_FINAL = 4, CH_RESERVED = 8 };
typedef struct {                             /* 16 bytes */
    u8 map, flags;                           /* CH_* */
    u8 nact, split;                          /* acts; the acts in Payback's first level of the map (3 story, 6 rampage) */
    u16 mis0, nmis;                          /* this chapter's MisDef range (the acts first, in order) */
    u16 title, brief;                        /* text ids */
    u8 hx2, hy2;                             /* where the station hovers, in half cells */
    u16 next;                                /* the next chapter, 0xffff none */
} Chapter;

enum { MK_ACT, MK_CONTRACT, MK_CHAL, MK_MEDAL };
/* fail rules (flags, low byte) */
enum { FF_TIME = 0x01, FF_DEATH = 0x02, FF_VEHLOST = 0x04, FF_ZONE = 0x08, FF_CEIL = 0x10, FF_ESCORT = 0x20,
       MF_PHONE = 0x40 };                    /* MF_PHONE: runs alongside Payback's phone missions (it counts them) */
/* start rules (flags, high byte) */
enum { MS_FOOT = 0x100, MS_DRIVE = 0x200, MS_FLY = 0x400, MS_SPACE = 0x800, MS_AFTER = 0x1000, MS_REPEAT = 0x2000 };
#define NOPLACE 0xffff
typedef struct {                             /* 24 bytes */
    u16 id;                                  /* stable (ids.lock) */
    u8 map, kind;                            /* MK_* */
    u8 act, tier;                            /* act 1..6 (0 otherwise); 0..3 */
    u16 flags;                               /* FF_* | MF_* | MS_* */
    u16 title, brief;                        /* text ids; the title is at most 19 letters (a banner) */
    u16 obj0;
    u8 nobj, giver;                          /* its MisObj range; the crew member */
    u16 start;                               /* the MsPlace of the start beacon, NOPLACE: started from the Ops board or a talk */
    u16 par;                                 /* seconds: the par for medals and the ghost, or the time limit with FF_TIME */
    u16 pay;                                 /* credits */
    u16 score;                               /* Payback score / 100 */
} MisDef;

enum {
    OP_NOP,
    OP_GOTO,                                 /* place, mode; a height tolerance (0: 512) */
    OP_CHECK,                                /* place..+n in order, mode; b seconds for all of them (0: none) */
    OP_RINGS,                                /* place..+n (at most 16), flown in order; MO_STRICT: a near miss fails */
    OP_LAND,                                 /* place; a height tolerance (0: 512): set down on it */
    OP_ENTER,                                /* mode; a Payback vehicle type (0 any) */
    OP_DELIVER,                              /* place: the pick-up, then place+1..n-1 the drops; mode: the vehicle (FF_VEHLOST) */
    OP_RACE,                                 /* place..+n checkpoints, mode; b laps (0: 1), against a ghost on the mission's par */
    OP_CHASE,                                /* place; a type; b ticks within r of it (0: 90), or it is destroyed */
    OP_DESTROY,                              /* place..+n the spawn points; a type */
    OP_BLAST,                                /* place, place+1: the zone's corners (PK_BOX0, PK_BOX1); n boxes broken in it */
    OP_FOES,                                 /* place; n foes of kind a with b hp (K's sg_foe_spawn) */
    OP_BOSS,                                 /* place; a boss */
    OP_ESCORT,                               /* place (start), place+1 (end); a type */
    OP_DEFEND,                               /* place; a hp; b seconds */
    OP_COLLECT,                              /* place..+n pickups, any mode */
    OP_CRATES,                               /* place..+n pickups, each carried to the place b */
    OP_STUNT,                                /* a points; b the zone's PK_BOX0 place, -1 anywhere */
    OP_JUMP,                                 /* a airborne distance, in 1/8 cells */
    OP_SCORE,                                /* a x 100 of Payback's score since this step began */
    OP_WANTED,                               /* a stars for b seconds */
    OP_PHONE,                                /* n of Payback's own phone missions done */
    OP_SURVIVE,                              /* b seconds without a death */
    OP_SPACE,                                /* reach space */
    OP_DOCK,                                 /* dock */
    OP_TALK,                                 /* docked: wait for the talk (a crew, b node); in the city: the line `text` as a card */
    OP_BRIEF,                                /* card `text` (and the banner a, a text id, if not 0) */
    OP_TIMER,                                /* a time limit of b seconds from here (until ENDTIMER or the end) */
    OP_ENDTIMER,
    OP_GROUP,                                /* the objectives up to ENDGROUP, in any order (MO_ORDER: in order; at most 16, and
                                                ones that finish within a tick of becoming true: GOTO LAND ENTER STUNT JUMP DOCK
                                                SPACE PHONE SCORE COLLECT of 1) */
    OP_ENDGROUP,
    OP_SPAWNVEH,                             /* place; a Payback vehicle type, with a tag */
    OP_CARD,                                 /* card `text`, 3 s, and on */
    OP_WAIT,                                 /* b ticks (30 a second) */
    OP_CEIL,                                 /* from here to the end: above height a inside the zone at place fails (FF_CEIL) */
    OP_ZONE,                                 /* from here to the end: leaving the zone at place fails (FF_ZONE) */
    OP_GIVE,                                 /* a credits */
    OP_UNLOCK,                               /* a: what */
    OP_SET,                                  /* campaign flag a = b */
    OP_GATEWAY,                              /* bigmap_enter(a): stage 3 */
    OP_FINISH,                               /* award and complete */
    OP_N
};
enum { MO_STRICT = 1, MO_ORDER = 2, MO_HIDDEN = 4, MO_CKPT = 8 };
typedef struct {                             /* 12 bytes */
    u8 op, flags;                            /* OP_*, MO_* */
    u8 mode, n;                              /* the mode it needs (0 any, 1 foot, 2 drive, 3 fly); a count */
    u16 place;                               /* the first MsPlace */
    s16 a, b;                                /* arguments (above) */
    u16 text;                                /* the HUD line, a text id (0: the line stays) */
} MisObj;

enum { PK_POINT, PK_PAD, PK_RING_X, PK_RING_Y, PK_RING_H, PK_BOX0, PK_BOX1, PK_PICK, PK_SPAWN };
typedef struct {                             /* 8 bytes */
    u16 x8, y8;                              /* 1/8 cell (y is Payback's y, our z) */
    u16 h;                                   /* world units */
    u8 r8, kind;                             /* radius in 1/8 cell; PK_*: a ring faces along x, along y (our z) or up */
} MsPlace;

_Static_assert(sizeof(S2Head) == 56 && sizeof(Chapter) == 16 && sizeof(MisDef) == 24 && sizeof(MisObj) == 12 &&
               sizeof(MsPlace) == 8, "the blob's records");

/* Text: a table of u16 offsets (from the table's start, ntext of them) followed by NUL-terminated ASCII in the
   Stunt Fox font; id 0 is "". Titles 19 letters, HUD text 18, a card two lines of 38 split by a newline.
   Names (off_name) are for the host tools; the engine never reads them. */

#endif
