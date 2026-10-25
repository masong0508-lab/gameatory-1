/* The city data: built at build time from the player's Payback ROM (tools/mkworld.py). */
#include "world.h"

World world;

static void world_load(const u32 *h)
{
    const u8 *base = (const u8 *)h;
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
    world.ctex = (const u16 *)(base + h[19]);
    world.btex = (const u16 *)(base + h[20]);
    world.deck = (const s8 *)(base + h[21]);
    world.yoff = (s32)h[8];
    world.wall = base + h[22];
    world.deck2 = (const s8 *)(base + h[23]);
    world.dtex = (const u16 *)(base + h[24]);
    world.swim = base + h[25];
    world.nladder = *(const u16 *)(world.swim + CITY * CITY);
    world.ladder = (const Ladder *)(world.swim + CITY * CITY + 4);
}

#ifdef MERGE
/* every map's world, placed above Payback's own 8 MiB by build.py (gen/merge_sig.c) */
extern const u32 *const world_table[NWORLD];

u8 world_grid;                     /* the grid whose world is loaded (the station hangs over it: space.c) */

void world_select(int grid)
{
    world_load(world_table[world_grid = grid]);
}
#else
extern const u32 world_data[];

void world_init(void)
{
    world_load(world_data);
}
#endif

int world_deck(s32 x, s32 z, int k, s32 *bottom, s32 *top)
{
    if (x < 0 || z < 0 || x >= CITY * CELL || z >= CITY * CELL)
        return 0;
    const s8 *d = &(k ? world.deck2 : world.deck)[4 * ((x >> 10) * CITY + (z >> 10))];
    if (!(d[0] | d[1]))
        return 0;
    *bottom = (d[0] + HBIAS) * 64;
    s32 hi = (d[1] + HBIAS) * 64, lo = (d[2] + HBIAS) * 64, fx = x & 1023, fz = z & 1023;
    switch ((u8)d[3]) {                 /* a sloped deck: a ramp up onto a bridge */
    case 2: *top = lo + (((hi - lo) * fz) >> 10); break;
    case 3: *top = lo + (((hi - lo) * fx) >> 10); break;
    case 4: *top = lo + (((hi - lo) * (1024 - fz)) >> 10); break;
    case 5: *top = lo + (((hi - lo) * (1024 - fx)) >> 10); break;
    default: *top = hi;
    }
    return d[3] < 2 ? 1 : d[3];
}

int world_wall(s32 x, s32 z, s32 *bottom, s32 *top)
{
    if (x < 0 || z < 0 || x >= CITY * CELL || z >= CITY * CELL)
        return 0;
    int i = (x >> 10) * CITY + (z >> 10), b = world.wall[i] & 15;
    if (b) {
        const s8 *r = (const s8 *)world.wall + CITY * CITY + 2 * i;
        *bottom = (r[0] + HBIAS) * 64;
        *top = (r[1] + HBIAS) * 64;
    }
    return b;
}

int world_rails(s32 x, s32 z)
{
    if (x < 0 || z < 0 || x >= CITY * CELL || z >= CITY * CELL)
        return 0;
    return world.wall[(x >> 10) * CITY + (z >> 10)] >> 4;
}

int world_water(s32 x, s32 z, s32 *surface)
{
    const Cell *c = world_cell(x, z);
    if (c->shape != SHAPE_WATER)
        return 0;
    *surface = c->hi;
    return 1;
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

/* normal (1.14) of a top of shape 2..5 (as a Cell's) rising d units over the cell */
static V3 shape_normal(int shape, s32 d)
{
    switch (shape) {
    case 2: return vnorm(v3(0, 1024, -d));
    case 3: return vnorm(v3(-d, 1024, 0));
    case 4: return vnorm(v3(0, 1024, d));
    case 5: return vnorm(v3(d, 1024, 0));
    default: return v3(0, ONE, 0);
    }
}

V3 world_normal(s32 x, s32 z)
{
    const Cell *c = world_cell(x, z);
    return shape_normal(c->shape, c->hi - c->lo);
}

V3 world_deck_normal(s32 x, s32 z, int k)
{
    if (x < 0 || z < 0 || x >= CITY * CELL || z >= CITY * CELL)
        return v3(0, ONE, 0);
    const s8 *d = &(k ? world.deck2 : world.deck)[4 * ((x >> 10) * CITY + (z >> 10))];
    return shape_normal((u8)d[3], (d[1] - d[2]) * 64);
}
