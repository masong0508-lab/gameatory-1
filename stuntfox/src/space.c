#include "space.h"
#include "physics.h"
#include "render.h"
#include "palette.h"
#include "model.h"
#include "world.h"
#ifdef MERGE
#include "planet.h"
#endif

#define NSTARS 40
/* The stars, and each asteroid's first turn and spin, come from a small random series. Inside Payback (RAM is
   short) it ran at build time, on this computer (tools/mkconst.py, the host build marked NORMALS_HOST): they
   are ROM const there, bit for bit what space_init gives. rock_m turns every frame, so it stays in RAM. */
#if defined(MERGE) && !defined(NORMALS_HOST)
#define CONST_TABLES
extern const V3 gen_stars[NSTARS], gen_rock_w[NROCK];
extern const u16 gen_rock_yaw[NROCK];
#define stars gen_stars
#define rock_w gen_rock_w
#else
#ifdef NORMALS_HOST
#define HOST_VISIBLE               /* (the dump program reads them) */
#else
#define HOST_VISIBLE static
#endif
HOST_VISIBLE V3 stars[NSTARS] EWRAM_BSS;
HOST_VISIBLE V3 rock_w[NROCK] EWRAM_BSS;
HOST_VISIBLE u16 rock_yaw[NROCK];
#endif
static M3 rock_m[NROCK] EWRAM_BSS;
static M3 ring_m;
static s32 ring_a;
static int sky_step = -1, sky_pending = -1;

#ifndef CONST_TABLES
static u32 seed = 0x5f0c2b1d;
static s32 rnd(s32 lo, s32 hi)
{
    seed = seed * 1664525 + 1013904223;
    return lo + (s32)((seed >> 8) % (u32)(hi - lo + 1));
}
#endif

/* Where the station hangs, by map (stage2.md 7.1): cells x 2, so a half cell fits; 34000 up. Map 0 is where it always was. */
static const u8 hang[11][2] = {
    {124, 60}, {224, 200}, {60, 60}, {139, 149}, {192, 204}, {90, 40}, {120, 140}, {226, 112}, {128, 128}, {128, 132}, {180, 104},
};
V3 station_at(int map)
{
    if ((unsigned)map >= 11)
        map = 0;
    return v3(hang[map][0] * (CELL / 2), 34000, hang[map][1] * (CELL / 2));
}

u8 sp_map;                                 /* the level's map (planet.c's pl_set) */
/* the one place the station is set, for the planet too (map -1: this level's) */
V3 pl_station(int map)
{
    return station_at(map < 0 ? sp_map : map);
}

/* the asteroids' places round the station */
static const s16 spots[12][4] = {
    {-9000, 2500, 7000, 900}, {8000, -1500, 9000, 1300}, {14000, 3000, -6000, 700},
    {-15000, -2000, -9000, 1500}, {3000, 5000, -15000, 1000}, {-4000, -4000, 16000, 800},
    {20000, 1000, 12000, 1600}, {-21000, 4000, 3000, 1100}, {11000, 6000, 21000, 900},
    {-12000, 7000, -20000, 1400}, {24000, -3000, -18000, 1200}, {0, 9000, 26000, 1500},
};

/* the station, and the asteroids with it, over this map */
void space_station(int map)
{
    station_pos = station_at(map);
    nrocks = NROCK;
    for (int i = 0; i < nrocks; i++) {
        rocks[i].c = vadd(station_pos, v3(spots[i][0], spots[i][1], spots[i][2]));
        rocks[i].r = spots[i][3];
    }
}

void space_init(void)
{
#if defined(MERGE) && !defined(NORMALS_HOST)
    space_station(world_grid);
#else
    space_station(0);
#endif
#ifndef CONST_TABLES
    for (int i = 0; i < NSTARS; i++)
        stars[i] = vnorm(v3(rnd(-1000, 1000), rnd(60, 1000), rnd(-1000, 1000)));
#endif
    for (int i = 0; i < nrocks; i++) {
#ifdef CONST_TABLES
        myaw(&rock_m[i], gen_rock_yaw[i]);
#else
        myaw(&rock_m[i], rock_yaw[i] = rnd(0, 65535));
        rock_w[i] = v3(rnd(-60, 60), rnd(-60, 60), rnd(-60, 60));
#endif
    }
    myaw(&ring_m, 0);
}

void space_tick(void)
{
    ring_a += 24;
    myaw(&ring_m, ring_a);
}

static u8 lerp8(int a, int b, int t) { return a + (b - a) * t / 16; }

#ifdef MERGE
/* Inside Payback the sky is drawn in Payback's own blues: its palette has a ramp from pale
   sky to the black of night, so the palette never has to change. Higher up, each band steps
   down the ramp, one shade at a time. */
static const u8 sky_ramp[22] = {193, 194, 195, 196, 197, 198, 199, 200, 201, 202, 203, 204, 205, 206, 207,
                                240, 241, 242, 243, 244, 245, 246};
static const u8 sky_day[5] = {6, 5, 4, 2, 1}, sky_space[5] = {21, 19, 15, 12, 9};   /* zenith .. horizon */
#endif

void sky_draw(s32 alt)
{
    /* how far toward space the sky is, 0..16, with 300 units of slack either way so that
       hovering at the edge of a step does not switch it back and forth */
    int up = (alt - 3300) * 16 / 21000, down = (alt - 2700) * 16 / 21000;
    if (up > 16) up = 16;
    if (down < 0) down = 0;
    int t = sky_step < 0 ? (up > 0 ? up : 0) : sky_step < up ? up : sky_step > down ? down : sky_step;
    if (t != sky_step) {
        sky_step = t;
        sky_pending = t;
    }
#ifdef MERGE
    u16 cols[9];
    for (int k = 0; k < 5; k++)
        cols[k] = 0x100 | sky_ramp[sky_day[k] + (sky_space[k] - sky_day[k]) * t / 16];
    for (int f = 3; f >= 0; f--)
        cols[8 - f] = COLOR(M_GLASS, 1, f);
#else
    static const u16 cols[] = {0, 3, 7, 11, 15, COLOR(M_GLASS, 1, 3), COLOR(M_GLASS, 1, 2), COLOR(M_GLASS, 1, 1),
                               COLOR(M_GLASS, 1, 0)};
#endif
    static const s32 bounds[] = {9000, 5000, 2500, 800, 0, -300, -1200, -3000};
    /* All of the bands, every frame, also the ones the city should cover: wherever it does not
       (past the draw distance, a gap between two faces) the page would otherwise still show
       what was drawn there two frames ago, smeared copies of old frames */
#ifdef MERGE
    /* from a few thousand units up the planet takes over below the horizon: the sky above it, the
       planet's rings (planet.c) over that, the whole screen covered by one or the other */
    if (pl_begin(alt)) {
        pl_draw(cols, bounds);
        return;
    }
#endif
    r_sky(cols, bounds, 9, 9);
}

int palette_commit(void)
{
#ifdef MERGE
    return 0;                      /* (inside Payback the palette is Payback's, never changed) */
#endif
    if (sky_pending < 0)
        return 0;
    int t = sky_pending;
    sky_pending = -1;
    static const u8 zd[3] = {6, 12, 26}, hd[3] = {22, 26, 30}, fd[3] = {22, 26, 30};
    static const u8 zs[3] = {0, 0, 2}, hs[3] = {5, 8, 20}, fs[3] = {9, 11, 20};
    u8 z[3], h[3], f[3];
    for (int k = 0; k < 3; k++) {
        z[k] = lerp8(zd[k], zs[k], t);
        h[k] = lerp8(hd[k], hs[k], t);
        f[k] = lerp8(fd[k], fs[k], t);
    }
    palette_set(z, h, f);
    return 1;
}

void stars_draw(s32 alt)
{
    if (alt < 9000)
        return;
    int lim = alt > 20000 ? NSTARS : NSTARS * (alt - 9000) / 11000;
    for (int i = 0; i < lim; i++) {
        V3 d = stars[i];
        s32 z = vdot(cam.m.f, d);
        if (z < 3000)
            continue;
        s32 x = vdot(cam.m.r, d), y = vdot(cam.m.u, d);
        int sx = 120 + FOCAL * x / z, sy = 80 - FOCAL * y / z;
        int c = i & 3 ? COLOR(M_SHIP, 3, 0) : COLOR(M_ACCENT, 3, 0);
        r_pixel(sx, sy, c);
        r_pixel(sx + 1, sy, c);
    }
}

void space_draw(void)
{
    if (cam.pos.y < 6000)
        return;
    static M3 still = {{ONE, 0, 0}, {0, ONE, 0}, {0, 0, ONE}};
    Place pl;
    V3 d = vsub(station_pos, cam.pos);
    s32 far = (d.x > 40000 || d.x < -40000 || d.y > 40000 || d.y < -40000 || d.z > 40000 || d.z < -40000) ? 2 : 0;
    if (model_place(&pl, station_pos, &still, 256, far, mdl_hub.radius)) {
        model_draw(&mdl_hub, &pl);
        if (!far)
            model_draw(&mdl_bay, &pl);                 /* the hangar, seen through its mouth */
    }
    if (model_place(&pl, station_pos, &ring_m, 256, far, mdl_ring.radius))
        model_draw(&mdl_ring, &pl);
    for (int i = 0; i < nrocks; i++) {
        V3 e = vsub(rocks[i].c, cam.pos);
        if (e.x > 30000 || e.x < -30000 || e.y > 30000 || e.y < -30000 || e.z > 30000 || e.z < -30000)
            continue;
        mrotate(&rock_m[i], rock_w[i]);
        if (model_place(&pl, rocks[i].c, &rock_m[i], rocks[i].r, 0, mdl_rock.radius))
            model_draw(&mdl_rock, &pl);
    }
}
