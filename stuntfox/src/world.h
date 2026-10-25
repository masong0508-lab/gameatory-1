/* The city: built at build time from Payback's city layout (tools/mkworld.py). */
#ifndef WORLD_H
#define WORLD_H
#include "fx.h"

#define CELL 1024
#define CITY 128

/* a building, or (base above or below 0, units / 64) a deck spanning over open air: a bridge */
typedef struct { u8 x0, z0, x1, z1; s16 h; u8 mat; s8 base; } Box;
typedef struct { u8 x0, z0, x1, z1, mat; } Lot;
typedef struct { u8 x0, z0, x1, z1; s16 h0, h1; u8 dir, mat; } Ramp;
typedef struct { s32 x, z; u8 dir, pad; s16 r, w; s16 pad2; } Loop;
typedef struct { s16 lo, hi; u8 shape, mat; } Cell;
/* a Cell's shape for Payback's water, which people and cars go into and sink: its surface at hi
   (drawn, and what world_ground gives), solid to the physics only at lo, far under it */
#define SHAPE_WATER 6
typedef struct { u8 at, from, to, dir; } Line;      /* dir: 0 along z, 1 along x; | crossings << 1 */
/* x, z in units / 4, height in units / 8 (see draw_tree), base in units / 64 (TREE_BASE), and
   the radius (units / 4) cars are stopped at (car.c, car_posts), 0 for none; a railing (kind 2
   + edge) has its bottom in units / 32 in h, with base its high byte (RAIL_BASE) */
typedef struct { u16 x, z; u8 h, kind; s8 base; u8 r; } Tree;
/* a ladder up a bank too high to climb out of the water at: its cell, edge (-z, +x, +z, -x), bottom
   and top (units) */
typedef struct { u8 x, z, edge, pad; s16 lo, hi; } Ladder;
#define TREE_BASE(t) ((t)->base << 6)
#define RAIL_BASE(t) ((((t)->base << 8) | (t)->h) << 5)
/* deck and wall heights are stored in units / 64 less HBIAS: -2560 .. 10688 (a raised park,
   a railway's roof) */
#define HBIAS 40

typedef struct {
    int nbox, nlot, nramp, nloop, nitem, nline, ntree;
    const Box *box;
    const Lot *lot;
    const Ramp *ramp;
    const Loop *loop;
    const u16 *sector;        /* 256 x (start, count) */
    const u16 *item;
    const Cell *cell;         /* 128 x 128, index x * 128 + z */
    const u16 *far;           /* 256 x (material, height) */
    const Line *line;
    const Tree *tree;
    const u16 *ctex;          /* 128 x 128: Payback tile id of each cell's top, 0xffff none */
    const u16 *btex;          /* per box: 4 sides (-z, +x, +z, -x) x 4 cells, tile ids */
    const s8 *deck;           /* 128 x 128 x (bottom, top, top's low end, shape), units / 64 - HBIAS */
    const u8 *wall;           /* 128 x 128 edge bits (-z, +x, +z, -x), then 128 x 128 x (bottom, top) */
    const s8 *deck2;          /* a second deck over the first, as deck */
    const u16 *dtex;          /* 128 x 128: Payback tile id of the top of the deck over each cell (the
                                 higher of two), 0xffff none */
    const u8 *swim;           /* 128 x 128: a swimmer's ways out of a water cell, bits 0..3 the edges he
                                 climbs out across, 4 one in reach, 5 a ladder, 6..7 the edge to swim
                                 across for the nearest onto the streets (mkworld.py) */
    int nladder;
    const Ladder *ladder;
    s32 yoff;                 /* added to Payback's heights: its streets are at 0x100 on all maps but one */
} World;

extern World world;

#ifdef MERGE
#define NWORLD 11             /* one for each of Payback's level grids */
extern u16 prop_k;            /* GAME SETTINGS' trees and lamps: out to this much of what follows, 256 = all */
#define TREE_FAR (6000 * prop_k >> 8)         /* citydraw.c draws trees nearer than this (units, each way and deep), */
#define PROP_FAR (4500 * prop_k >> 8)         /* ... benches and lamps nearer than this (each way) */
void world_select(int grid);
extern u8 world_grid;         /* ... and the one loaded now */
/* props.c: is one of the street objects it draws still in the cell under (x, z) (units) on
   Payback's live map (a crate opened, a pickup taken: not) */
int prop_live(s32 x, s32 z);
/* props.c: a bolt's step (its whole tick), from p - step to p, meets one of Payback's street
   objects drawn: 1, and p is moved to the point met (a crate hit is opened by props_send, after
   our frame) */
int prop_hit(V3 *p, V3 step);
void props_send(void);
#else
void world_init(void);
#endif
void world_draw(void);
/* how far round the camera world_draw draws the city's sectors (units), 0 for none */
int world_view(void);
/* the ground (units) under (x, z) as drawn: the top of a block, of a floor, of water */
s32 world_ground(s32 x, s32 z);
/* Payback's water under (x, z): 1 with its surface (units) */
int world_water(s32 x, s32 z, s32 *surface);
const Cell *world_cell(s32 x, s32 z);
/* surface normal of the ground at (x, z), 1.14 */
V3 world_normal(s32 x, s32 z);
/* deck k (0, or 1 for a second one over it) spanning over the cell under (x, z) (units): its
   bottom and its top there, and 1, or the shape (2..5, as a Cell's) of a sloped top; 0 for none */
int world_deck(s32 x, s32 z, int k, s32 *bottom, s32 *top);
V3 world_deck_normal(s32 x, s32 z, int k);
/* Payback's walls on the edges of the cell under (x, z): edge bits (-z, +x, +z, -x), with the
   bottom and top (units) they stand between; 0 for none */
int world_wall(s32 x, s32 z, s32 *bottom, s32 *top);
int world_rails(s32 x, s32 z);     /* the edges of that cell with a railing drawn along them (as world_wall's) */

#endif
