#include "space.h"
#include "physics.h"
#include "render.h"
#include "palette.h"
#include "model.h"

#define NSTARS 40
static V3 stars[NSTARS] EWRAM_BSS;
static M3 rock_m[16] EWRAM_BSS;
static V3 rock_w[16] EWRAM_BSS;
static M3 ring_m;
static s32 ring_a;
static int sky_step = -1, sky_pending = -1;

static u32 seed = 0x5f0c2b1d;
static s32 rnd(s32 lo, s32 hi)
{
    seed = seed * 1664525 + 1013904223;
    return lo + (s32)((seed >> 8) % (u32)(hi - lo + 1));
}

void space_init(void)
{
    station_pos = v3(62 * 1024, 34000, 30 * 1024);
    for (int i = 0; i < NSTARS; i++)
        stars[i] = vnorm(v3(rnd(-1000, 1000), rnd(60, 1000), rnd(-1000, 1000)));
    static const s16 spots[12][4] = {
        {-9000, 2500, 7000, 900}, {8000, -1500, 9000, 1300}, {14000, 3000, -6000, 700},
        {-15000, -2000, -9000, 1500}, {3000, 5000, -15000, 1000}, {-4000, -4000, 16000, 800},
        {20000, 1000, 12000, 1600}, {-21000, 4000, 3000, 1100}, {11000, 6000, 21000, 900},
        {-12000, 7000, -20000, 1400}, {24000, -3000, -18000, 1200}, {0, 9000, 26000, 1500},
    };
    nrocks = 12;
    for (int i = 0; i < nrocks; i++) {
        rocks[i].c = vadd(station_pos, v3(spots[i][0], spots[i][1], spots[i][2]));
        rocks[i].r = spots[i][3];
        myaw(&rock_m[i], rnd(0, 65535));
        rock_w[i] = v3(rnd(-60, 60), rnd(-60, 60), rnd(-60, 60));
    }
    myaw(&ring_m, 0);
}

void space_tick(void)
{
    ring_a += 24;
    myaw(&ring_m, ring_a);
}

static u8 lerp8(int a, int b, int t) { return a + (b - a) * t / 16; }

void sky_draw(s32 alt)
{
    int t = alt <= 3000 ? 0 : alt >= 24000 ? 16 : (alt - 3000) * 16 / 21000;
    if (t != sky_step) {
        sky_step = t;
        sky_pending = t;
    }
    static const u8 cols[] = {0, 3, 7, 11, 15, COLOR(M_GLASS, 1, 3), COLOR(M_GLASS, 1, 2), COLOR(M_GLASS, 1, 1),
                              COLOR(M_GLASS, 1, 0)};
    static const s32 bounds[] = {9000, 5000, 2500, 800, 0, -300, -1200, -3000};
    r_sky(cols, bounds, 9);
}

void palette_commit(void)
{
    if (sky_pending < 0)
        return;
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
    if (model_place(&pl, station_pos, &still, 256, far, mdl_hub.radius))
        model_draw(&mdl_hub, &pl);
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
