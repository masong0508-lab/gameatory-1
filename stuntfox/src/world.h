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
typedef struct { u8 at, from, to, dir; } Line;      /* dir: 0 along z, 1 along x; | crossings << 1 */
typedef struct { u16 x, z; u8 h, kind; } Tree;      /* x, z in units / 4, height in units / 8 */

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
    const s8 *deck;           /* 128 x 128 x (bottom, top), units / 64, of a deck over the cell */
} World;

extern World world;

void world_init(void);
void world_draw(void);
/* collision: ground height (units) under (x, z) and whether it is a wall at height y */
s32 world_ground(s32 x, s32 z);
const Cell *world_cell(s32 x, s32 z);
/* surface normal of the ground at (x, z), 1.14 */
V3 world_normal(s32 x, s32 z);
/* a deck spanning over the cell under (x, z) (units): 1 with its bottom and top, else 0 */
int world_deck(s32 x, s32 z, s32 *bottom, s32 *top);

#endif
