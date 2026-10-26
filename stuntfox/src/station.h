/* Fox Station (stage 2, S): the rooms the Arwing's pilot walks through while docked. station.c is the walker, the cameras, the
   talk and the terminals; stationdraw.c draws a room. The rooms, the crew's talk and the messages are ROM data (st_blob, built by
   tools/content/station.py from tools/content/stgeo.py): its layout is below, and the two files must agree on every number here
   (tests/s2/station.py reads this header for the enums). The hangar (room 0) is the docked view as it always was; every other room is
   drawn here, in flat shades, with no Payback tiles, and takes the keys the hangar's menu would. */
#ifndef STATION_H
#define STATION_H
#include "gba.h"
#include "fx.h"
#include "model.h"

enum { R_HANGAR, R_HUB, R_OPS, R_WORKSHOP, R_NAV, R_LOUNGE, R_TROPHY, R_COMMS, R_QUARTERS, R_N };
enum { U_NONE, U_DOOR, U_TALK, U_TERM, U_PAD };                       /* what a place in a room is for */
enum { T_NONE, T_BRIEF, T_CONTRACT, T_TRAVEL, T_SHOP, T_PAINT, T_MAP, T_TROPHY, T_COMMS, T_MSGS, T_RECAP, T_LOG, T_QUICK, T_N };
enum { E_REPEAT = 1, E_MSG = 2, E_LOG = 4 };                          /* a talk entry's flags */
enum { A_NONE, A_UNLOCK, A_SET, A_START, A_OPEN };                    /* a node's act (low 3 bits; its argument above) */

#define ST_MAGIC 0x314e5453        /* 'STN1' */
#define ST_VER 1

typedef struct {                   /* 40 bytes */
    u32 magic;
    u16 ver, nroom, nnode, nent, ntext, pad;
    u32 off_room, off_node, off_ent, off_text, size, crc;
} StHead;
typedef struct {                   /* 48 bytes: room 0 (the hangar) is all zeros */
    u8 nparts, nbox, ncam, nuse, ncrew, ceilc, floorc, pad;
    s16 hx, hz, zmin;              /* the walls (half the room's width and depth) and the nearest the walker comes: the floor under that is off the picture */
    u16 title;                     /* a text id */
    u32 off_parts, off_box, off_cam, off_use, off_crew;
    u8 spare[12];
} StRoom;
typedef struct { u8 nv, nf; u16 pad; u32 off_v, off_f, off_n; } StPart;       /* a part: at most 56 points (model_draw's stack) */
typedef struct { s16 px, py, pz, ty, tz, x0, x1, z0, z1, pad; } StCam;        /* a camera node: it looks along +z from (px, py, pz) at height ty, depth tz; the walker's region */
typedef struct { s16 x, z, sx, sz; u8 r4, kind, arg, flags; s16 ly; u16 label; } StUse;   /* a door, a place to use: r4 a quarter of its reach; where one arrives (sx, sz); the label's height */
typedef struct { s16 x, z; u16 yaw; u8 crew, model, body, legs; u8 fur, fpart; } StCrew;   /* fur: bit 0 ears, 1 tail, 2 muzzle; fpart: 1 + the part (after the room's own) that is the fur, 0 none */
typedef struct { u8 speaker, flags; u16 text, next; u8 cond, act; } StNode;
typedef struct { u8 crew, cond, flags, pad; u16 node, id; } StEnt;
#ifdef __arm__
_Static_assert(sizeof(StHead) == 40 && sizeof(StRoom) == 48 && sizeof(StPart) == 16 && sizeof(StCam) == 20 && sizeof(StUse) == 16 &&
               sizeof(StCrew) == 12 && sizeof(StNode) == 8 && sizeof(StEnt) == 8 && sizeof(MFace) == 9, "the station blob's records");
#endif

/* the walker and what he is doing: 60 bytes in keep (memguard keeps the headroom) */
typedef struct {
    s16 x, z;                      /* the walker, in the room's units */
    u16 yaw;
    s16 bx, by, bz, bty, btz;      /* the camera now (it glides to its node) */
    u8 room, node;                 /* R_*; the camera node in use */
    u8 dwell, cd;                  /* ticks before the camera may cut again; before a door may be taken again */
    u8 phase, moving;              /* the walk cycle; he moved this tick */
    u8 term, cur, top, page;       /* the terminal on screen (T_*), its line, first line shown, its page */
    u8 confirm, near;              /* "A again" asked; what is in reach: a U_* kind << 5 | its index + 1 (0 none) */
    u16 dnode, dent;               /* the talk on: its node and its entry's id (0 none) */
    u8 dcrew, chat;                /* who is speaking; the chatter's turn */
    u8 hid, same;                  /* Payback's sprites are off; frames drawn alike (2: both pages hold the picture) */
    u8 sway, idle;                 /* the hangar camera's sway (0..256 >> 1) and the frames its menu has been as it is */
    u8 pan, pad2;                  /* ticks a full-screen page is held as it is (no flashing); spare */
    u32 heard[2];                  /* the entries (ids under 64) the crew have said */
    u32 sig;                       /* the picture as last drawn (a hash); in the hangar, the menu's */
    const char *msg;               /* a line of news (ROM text) and when it goes */
    u32 msg_end;
} StState;
extern StState stw;

/* ---- station.c, for stationdraw.c ---- */
extern const u8 st_blob[];
int st_ok(void);                                        /* the blob is good */
const StHead *st_head(void);
const StRoom *st_room(int r);
const StCam *st_cams(const StRoom *rm);
const StUse *st_uses(const StRoom *rm);
const StCrew *st_crews(const StRoom *rm);
const char *st_text(int id);
extern const char *const st_crew_name[9];                /* ROOK PIP NOVA DUSTY QUILL JUNO KESTREL SABLE, by crew number */
u32 st_sig(void);                                       /* a hash of everything the picture of a room shows */

/* ---- stationdraw.c ---- */
void st_draw_room(void);                                /* the room, its crew and the walker in 3D, over a two-colour clear */
void st_draw_labels(void);                              /* the names over the doors and places, in 2D */

/* ---- for the hangar and the quick menu (spacegame.c, campaign.c) ---- */
int st_enter(void);                                     /* out of the hangar into the hub: 1, or 0 with no station data */
int st_tick(u16 hit, u16 keys);                         /* the hangar's tick while docked: 1 when the walker is outside it and has the keys */
int st_sway(void);                                      /* the hangar camera's sway, 0..256: it settles when nothing moves (the view can then be reused) */
#endif
