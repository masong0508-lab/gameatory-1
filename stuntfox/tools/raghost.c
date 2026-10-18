/* Host build of src/ragdoll.c (the solver that ships) for tools/ragcheck.py, on a world built by
   tools/mkworld.py, with a rigid tumbling body beside it to compare with. Built by ragcheck.py;
   nothing here goes into the ROM. */
#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <time.h>
#include "ragdoll.h"
#include "world.h"
#include "render.h"
#include "palette.h"

u32 world_data[1 << 18];
u32 frame_count;
Camera cam;
int fog_of(int z) { (void)z; return 0; }
void r_poly(const V3 *v, int n, int color, int key, int bg) { (void)v; (void)n; (void)color; (void)key; (void)bg; }

int rh_load(const char *path)
{
    FILE *f = fopen(path, "rb");
    if (!f)
        return 0;
    size_t n = fread(world_data, 1, sizeof world_data, f);
    fclose(f);
    world_init();
    nrocks = 0;
    water_floats = 1;                  /* (rh_surface: a water cell's surface, which a body floats on) */
    station_pos = v3(0, 1 << 30, 0);
    rag_clear();
    return (int)n;
}

void rh_wacky(int w) { rag_wacky = w; }

/* feet (units), yaw, velocity (units / 256 a tick), spin (1.14 rad a tick) */
int rh_throw(int x, int y, int z, int yaw, int vx, int vy, int vz, int sx, int sy, int sz)
{
    rag_clear();
    return rag_throw(v3(x, y, z), yaw, v3(vx, vy, vz), v3(sx, sy, sz), M_CAR, M_ROAD, 0, 0);
}

int rh_throw2(int x, int y, int z, int yaw, int vx, int vy, int vz, int sx, int sy, int sz)
{
    return rag_throw(v3(x, y, z), yaw, v3(vx, vy, vz), v3(sx, sy, sz), M_CAR, M_ROAD, 0, 0);
}

void rh_tick(int ticks) { rag_tick(ticks); }
void rh_rise(int k, int yaw) { rag_rise(&rags[k], yaw); }   /* (a body at rest gets up: the get-up check) */

/* body k: state, bounces, then its 12 points (units * 8, absolute) */
int rh_get(int k, int *out)
{
    const Rag *r = &rags[k];
    for (int i = 0; i < RAG_P; i++)
        for (int a = 0; a < 3; a++)
            out[3 * i + a] = (r->o[a] << 3) + r->x[i][a];
    out[36] = r->bounces;
    return r->state;
}

int rh_ground(int x, int z) { return world_ground(x, z); }
int rh_surface(int x, int y, int z) { return surface_fine(v3(x << FX, y << FX, z << FX)) >> FX; }
int rh_inside(int x, int y, int z) { Hit h; return penetrate(v3(x << FX, y << FX, z << FX), &h) ? h.dist >> FX : 0; }

/* how deep (units) a point is in a building or a bridge deck (not counting Payback's thin
   walls, which tools/ragcheck.py checks are never crossed: rh_wallx) */
int rh_solid(int x, int y, int z)
{
    const Cell *c = world_cell(x, z);
    int d = 0, g = c->shape == SHAPE_WATER ? -99999 : ground_fine(x << FX, z << FX) >> FX;
    if (y < g) d = g - y;
    for (int k = 0; k < 2; k++) {
        s32 b, t;
        if (world_deck(x, z, k, &b, &t) && y > b && y < t) {
            int e = y - b < t - y ? y - b : t - y;
            if (e > d) d = e;
        }
    }
    return d;
}

/* did a point go through a railing from (x0, y0, z0) to (x1, y1, z1) (y its bottom), at the
   height it had where it crossed the edge? */
static int wall_at(int ax, int az, int bx, int bz, int y, int e)
{
    s32 lo, hi;
    int w = world_wall(ax, az, &lo, &hi), n = (w & e) && y > lo - 32 && y < hi;
    w = world_wall(bx, bz, &lo, &hi);
    e = e == 1 ? 4 : e == 4 ? 1 : e == 2 ? 8 : 2;
    return n | ((w & e) && y > lo - 32 && y < hi);
}

int rh_wallx(int x0, int y0, int z0, int x1, int y1, int z1)
{
    int n = 0, cx = (x0 >> 10) != (x1 >> 10), cz = (z0 >> 10) != (z1 >> 10);
    int ex = x1 > x0 ? (x0 | 1023) + 1 : x0 & ~1023, ez = z1 > z0 ? (z0 | 1023) + 1 : z0 & ~1023;
    int yx = cx ? y0 + (y1 - y0) * (ex - x0) / (x1 - x0) : 0, yz = cz ? y0 + (y1 - y0) * (ez - z0) / (z1 - z0) : 0;
    if (cz && (!cx || abs(ez - z0) * abs(x1 - x0) < abs(ex - x0) * abs(z1 - z0))) {   /* (z's edge first) */
        n |= wall_at(x0, z0, x0, z1, yz, z1 > z0 ? 4 : 1);
        if (cx) n |= wall_at(x0, z1, x1, z1, yx, x1 > x0 ? 2 : 8);
    } else {
        if (cx) n |= wall_at(x0, z0, x1, z0, yx, x1 > x0 ? 2 : 8);
        if (cz) n |= wall_at(x1, z0, x1, z1, yz, z1 > z0 ? 4 : 1);
    }
    return n;
}

/* nanoseconds a step of the bodies in flight (n frames of `ticks`, all slots re-thrown each time) */
double rh_time(int ticks, int n)
{
    struct timespec a, b;
    Rag save[RAG_N];
    memcpy(save, rags, sizeof save);
    clock_gettime(CLOCK_MONOTONIC, &a);
    for (int i = 0; i < n; i++) {
        if (!(i & 31))
            memcpy(rags, save, sizeof save);
        rag_tick(ticks);
    }
    clock_gettime(CLOCK_MONOTONIC, &b);
    memcpy(rags, save, sizeof save);
    return ((b.tv_sec - a.tv_sec) * 1e9 + (b.tv_nsec - a.tv_nsec)) / n;
}

/* ---- the other way, to compare: the body as one rigid figure tumbling (the standing pose
   turned and moved as a whole), bouncing off the ground at the point that touches it ---- */
static Body rb;
static const s16 rpose[12][3] = {
    {0, 100, 0}, {-34, 176, 0}, {34, 176, 0}, {0, 206, 0}, {-40, 140, -2}, {-40, 102, 4},
    {40, 140, -2}, {40, 102, 4}, {-15, 52, 3}, {-15, 6, -2}, {15, 52, 3}, {15, 6, -2},
};
static int rb_bounces;

void rb_throw(int x, int y, int z, int yaw, int vx, int vy, int vz, int sx, int sy, int sz)
{
    memset(&rb, 0, sizeof rb);
    myaw(&rb.m, yaw);
    rb.pos = v3(x << FX, (y + 110) << FX, z << FX);
    rb.vel = v3(vx, vy, vz);
    rb.w = v3(sx, sy, sz);
    for (int i = 0; i < 3; i++)
        rb.inv_i[i] = (1 << 24) / 9000;            /* (a stick 200 long: m l^2 / 12, about) */
    rb_bounces = 0;
}

void rb_tick(int ticks)
{
    for (int t = 0; t < ticks; t++) {
        rb.vel.y -= G_ACC;
        rb.pos = vadd(rb.pos, rb.vel);
        if (rb.w.x | rb.w.y | rb.w.z)
            mrotate(&rb.m, rb.w);
        /* the lowest of its points under the ground: out, and bounce there */
        int lo = -1;
        s32 depth = 0;
        V3 lr = v3(0, 0, 0);
        for (int i = 0; i < 12; i++) {
            V3 r = mlocal(&rb.m, v3(rpose[i][0], rpose[i][1] - 110, rpose[i][2]));
            V3 p = vadd(vshr(rb.pos, FX), r);
            s32 d = world_ground(p.x, p.z) + 6 - p.y;
            if (d > depth)
                depth = d, lo = i, lr = r;
        }
        if (lo >= 0) {
            rb.pos.y += depth << FX;
            Hit h = {0, v3(0, ONE, 0), SURF_GROUND, 0, 0};
            s32 vin = body_point_vel(&rb, lr).y;
            body_contact(&rb, lr, &h, vin < -(3 << FX) ? 9 * 16 : 0, 64);
            rb_bounces += vin < -(3 << FX) && lo < 3;
            rb.w = vscale(rb.w, 15000);
        }
    }
}

int rb_get(int *out)
{
    for (int i = 0; i < 12; i++) {
        V3 r = mlocal(&rb.m, v3(rpose[i][0], rpose[i][1] - 110, rpose[i][2]));
        out[3 * i] = (rb.pos.x >> (FX - 3)) + (r.x << 3);
        out[3 * i + 1] = (rb.pos.y >> (FX - 3)) + (r.y << 3);
        out[3 * i + 2] = (rb.pos.z >> (FX - 3)) + (r.z << 3);
    }
    out[36] = rb_bounces;
    return 1;
}

double rb_time(int ticks, int n)
{
    struct timespec a, b;
    Body save = rb;
    clock_gettime(CLOCK_MONOTONIC, &a);
    for (int i = 0; i < n; i++) {
        if (!(i & 31))
            rb = save;
        rb_tick(ticks);
    }
    clock_gettime(CLOCK_MONOTONIC, &b);
    rb = save;
    return ((b.tv_sec - a.tv_sec) * 1e9 + (b.tv_nsec - a.tv_nsec)) / n;
}

int rh_wall(int x, int z, int *lohi) { s32 lo = 0, hi = 0; int w = world_wall(x, z, &lo, &hi); lohi[0] = lo; lohi[1] = hi; return w; }
int rh_deck(int x, int z, int k, int *bt) { s32 b = 0, t = 0; int s = world_deck(x, z, k, &b, &t); bt[0] = b; bt[1] = t; return s; }
int rh_shape(int x, int z) { return world_cell(x, z)->shape; }

extern unsigned rag_pulls, rag_steps;
unsigned rh_pulls(void) { return rag_pulls; }
unsigned rh_steps(void) { return rag_steps; }
