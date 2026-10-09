/* The city data: built at build time from the player's Payback ROM (tools/mkworld.py). */
#include "world.h"

extern const u32 world_data[];
World world;

void world_init(void)
{
    const u32 *h = world_data;
    const u8 *base = (const u8 *)world_data;
    world.nbox = h[1];
    world.nlot = h[2];
    world.nramp = h[3];
    world.nloop = h[4];
    world.nitem = h[5];
    world.nline = h[6];
    world.ntree = h[7];
    world.box = (const Box *)(base + h[9]);
    world.lot = (const Lot *)(base + h[10]);
    world.ramp = (const Ramp *)(base + h[11]);
    world.loop = (const Loop *)(base + h[12]);
    world.sector = (const u16 *)(base + h[13]);
    world.item = (const u16 *)(base + h[14]);
    world.cell = (const Cell *)(base + h[15]);
    world.far = (const u16 *)(base + h[16]);
    world.line = (const Line *)(base + h[17]);
    world.tree = (const Tree *)(base + h[18]);
}

const Cell *world_cell(s32 x, s32 z)
{
    int cx = x >> 10, cz = z >> 10;
    if (cx < 0) cx = 0;
    if (cz < 0) cz = 0;
    if (cx > 127) cx = 127;
    if (cz > 127) cz = 127;
    return &world.cell[cx * CITY + cz];
}

s32 world_ground(s32 x, s32 z)
{
    if (x < 0 || z < 0 || x >= CITY * CELL || z >= CITY * CELL)
        return 0;
    const Cell *c = &world.cell[(x >> 10) * CITY + (z >> 10)];
    s32 fx = x & 1023, fz = z & 1023, d = c->hi - c->lo;
    switch (c->shape) {
    case 2: return c->lo + ((d * fz) >> 10);
    case 3: return c->lo + ((d * fx) >> 10);
    case 4: return c->lo + ((d * (1024 - fz)) >> 10);
    case 5: return c->lo + ((d * (1024 - fx)) >> 10);
    default: return c->hi;
    }
}

V3 world_normal(s32 x, s32 z)
{
    const Cell *c = world_cell(x, z);
    s32 d = c->hi - c->lo;          /* rise over one cell (1024) */
    switch (c->shape) {
    case 2: return vnorm(v3(0, 1024, -d));
    case 3: return vnorm(v3(-d, 1024, 0));
    case 4: return vnorm(v3(0, 1024, d));
    case 5: return vnorm(v3(d, 1024, 0));
    default: return v3(0, ONE, 0);
    }
}

