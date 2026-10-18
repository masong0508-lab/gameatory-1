/* Host build of the game's own collision (src/physics.c, src/world.c, src/car.c) for
   tools/colcheck.py: the functions that ship, called through ctypes on a world built by
   tools/mkworld.py. Built by colcheck.py; nothing here goes into the ROM. */
#include <stdio.h>
#include <string.h>
#include "car.h"
#include "world.h"
#include "gba.h"

u32 world_data[1 << 18];
u32 frame_count;
static const Tree *trees;
static Tree bare[8192];

int col_load(const char *path)
{
    FILE *f = fopen(path, "rb");
    if (!f)
        return 0;
    size_t n = fread(world_data, 1, sizeof world_data, f);
    fclose(f);
    world_init();
    ramp_grip = 1;                         /* (as merge.c has it) */
    trees = world.tree;
    nrocks = 0;
    station_pos = v3(0, 1 << 30, 0);       /* (far away: the city alone) */
    return (int)n;
}

/* ground under (x, z) units, in units */
int col_ground(int x, int z) { return ground_fine(x << FX, z << FX) >> FX; }

/* what physics stands a point at height y on (a deck's top or the ground), units */
int col_surface(int x, int y, int z) { return surface_fine(v3(x << FX, y << FX, z << FX)) >> FX; }

/* penetrate() at a point (units): 1 when inside, out = depth (units), normal (1.14) */
int col_penetrate(int x, int y, int z, int *out)
{
    Hit h;
    if (!penetrate(v3(x << FX, y << FX, z << FX), &h))
        return 0;
    out[0] = h.dist >> FX;
    out[1] = h.n.x;
    out[2] = h.n.y;
    out[3] = h.n.z;
    return 1;
}

/* deck k over the cell at (x, z): 1 with bottom, top (units) */
int col_deck(int x, int z, int k, int *out) { return world_deck(x, z, k, &out[0], &out[1]); }

/* street objects on (1) or off (0) for what follows: the same world without their circles */
void col_posts(int on)
{
    world.tree = trees;
    if (on)
        return;
    for (int i = 0; i < world.ntree && i < 8192; i++)
        bare[i] = trees[i], bare[i].r = 0;
    world.tree = bare;
}

/* Drive the stunt car from (x, y, z) units, heading (65536 a turn, 0 = +z), at speed v
   (units/tick) with the throttle held, for up to ticks ticks or until it has gone `reach`
   units along its heading. out: final x, y, z (units), the furthest it got along the heading,
   wheels on the ground at the end, hardest impact. */
int col_drive(int x, int y, int z, int heading, int v, int ticks, int reach, int *out)
{
    Car c;
    car_reset(&c, v3(x, y, z), heading);
    c.b.vel = vscale(c.b.m.f, v << FX);
    V3 f = c.b.m.f;
    s32 best = 0, imp = 0;
    int t;
    for (t = 0; t < ticks; t++) {
        car_update(&c, KEY_A);
        if (c.impact > imp)
            imp = c.impact;
        s32 along = (((c.b.pos.x >> FX) - x) * f.x + ((c.b.pos.z >> FX) - z) * f.z) >> 14;
        if (along > best)
            best = along;
        if (best >= reach)
            break;
    }
    out[0] = c.b.pos.x >> FX;
    out[1] = c.b.pos.y >> FX;
    out[2] = c.b.pos.z >> FX;
    out[3] = best;
    out[4] = c.wheels;
    out[5] = imp;
    return t;
}
