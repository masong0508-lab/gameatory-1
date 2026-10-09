/* The city: built at build time from Payback's Freedom City layout (tools/mkworld.py). */
#ifndef WORLD_H
#define WORLD_H
#include "fx.h"

#define CELL 1024
#define CITY 128

typedef struct { u8 x0, z0, x1, z1; s16 h; u8 mat, pad; } Box;
typedef struct { u8 x0, z0, x1, z1, mat; } Lot;
typedef struct { u8 x0, z0, x1, z1; s16 h0, h1; u8 dir, mat; } Ramp;
typedef struct { s32 x, z; u8 dir, pad; s16 r, w; s16 pad2; } Loop;
typedef struct { s16 lo, hi; u8 shape, mat; } Cell;

typedef struct {
    int nbox, nlot, nramp, nloop, nitem;
    const Box *box;
    const Lot *lot;
    const Ramp *ramp;
    const Loop *loop;
    const u16 *sector;        /* 256 x (start, count) */
    const u16 *item;
    const Cell *cell;         /* 128 x 128, index x * 128 + z */
    const u16 *far;           /* 256 x (material, height) */
} World;

extern World world;

void world_init(void);
void world_draw(void);
/* collision: ground height (units) under (x, z) and whether it is a wall at height y */
s32 world_ground(s32 x, s32 z);
const Cell *world_cell(s32 x, s32 z);
/* surface normal of the ground at (x, z), 1.14 */
V3 world_normal(s32 x, s32 z);

#endif
