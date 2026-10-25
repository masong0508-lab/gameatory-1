/* See spacewalk.h. Out of the Arwing high up he is a figure of his own, not the ragdoll (whose
   floor, walls and 52-unit fall are the city's): one point with a velocity, drawn as the ragdoll's
   body posed (ragdoll.c, rag_pose). Gravity and drag fade out between SPACE_LO and SPACE_HI as the
   Arwing's do, so a fall from up there is long and slow; under SPACE_LO he is the ragdoll again
   (merge.c) and comes down as he always did. Out in the dark there are the moon (a polyhedron:
   its skin is exact, so walking on it and standing on it need no search), a few more rocks and
   four beacons. Thumb in ROM; state is a few dozen bytes (keep is short). */
#include "spacewalk.h"
#include "stage2.h"
#include "ragdoll.h"
#include "render.h"
#include "model.h"
#include "palette.h"
#include "draw2d.h"
#include "spacegame.h"
#include "world.h"

u16 sw_pack_k = 256;
static u8 props;                   /* the rocks and rings are to be drawn this frame (sw_draw3d decides, s2_draw3d calls them: not from under sw_draw3d, a frame less on the deepest chain) */
u8 sw_moon_near;                   /* physics.c's space_hit asks the moon only while this is set (draw sets it: the camera is by it) */

#define MOON_R 2400                /* units, corner to middle (the faces are 5% nearer) */
#define MOON_G 26                  /* its pull, fine units a tick squared: 0.1 unit, a fifth of the city's */
#define MOON_REACH 1500            /* it fades out this far above the skin */
#define BELT_BOX 6000              /* no rock reaches further from the moon's middle than this along an axis (the quick tests start here) */
#define SW_MOON_X (-17000)         /* its middle, from the station's */
#define SW_MOON_Y 2500
#define SW_MOON_Z 13000
#define MOON_FULL 4500             /* drawn with all 80 faces (the ones he stands on) inside this, with 20 inside MOON_MID, as one disc to MOON_FAR */
#define MOON_MID 9000
#define MOON_DISC 9500             /* the disc is its true size to this far, then shrinks with the square of the distance (see moon_draw) */
#define MOON_FAR 35000             /* (the camera space the polygons take is good to 40000) */
#define SW_NEAR 7000               /* the rocks and rings are drawn inside this, not beyond (the HUD points to the ring wanted); the moon alone, 14000 off or more, costs no more than its disc */
#define PROP_R 6800                /* they all lie within this of the moon's middle (the farthest ring: 6746) */
#define PELV 100                   /* pelvis over feet */
#define TURN 600                   /* a turn in 1.8 s */
#define FALL_CAP (52 << FX)        /* as the ragdoll falls */
#define WALK_MAX (3 << FX)
#define PACK_MAX (14 << FX)
#define A_FWD 77                   /* the pack's push, fine units a tick squared: 0.3 unit forward, 0.8 up */
#define A_UP 205
#define A_FLOOR 5734               /* ... a third of that at SPACE_LO, all of it at SPACE_HI (1.14) */

/* the moon: 42 corners at radius 256 and 80 faces, each with its outward normal, its plane's
   distance from the middle (1.14 of the radius) and 2^29 / that (tools/moon.py) */
static const s16 moon_v[42][3] = {
    {-135, 218, 0}, {135, 218, 0}, {-135, -218, 0}, {135, -218, 0}, {0, -135, 218}, {0, 135, 218},
    {0, -135, -218}, {0, 135, -218}, {218, 0, -135}, {218, 0, 135}, {-218, 0, -135}, {-218, 0, 135},
    {-207, 128, 79}, {-128, 79, 207}, {-79, 207, 128}, {79, 207, 128}, {0, 256, 0}, {79, 207, -128},
    {-79, 207, -128}, {-128, 79, -207}, {-207, 128, -79}, {-256, 0, 0}, {128, 79, 207}, {207, 128, 79},
    {-128, -79, 207}, {0, 0, 256}, {-207, -128, -79}, {-207, -128, 79}, {0, 0, -256}, {-128, -79, -207},
    {207, 128, -79}, {128, 79, -207}, {207, -128, 79}, {128, -79, 207}, {79, -207, 128}, {-79, -207, 128},
    {0, -256, 0}, {-79, -207, -128}, {79, -207, -128}, {128, -79, -207}, {207, -128, -79}, {256, 0, 0},
};
/* face: its three corners, its outward normal (1.14) and how far its plane lies from the middle (1.14 of the radius), and 2^29 / that */
static const struct { u8 a, b, c; s16 n[3], d; u16 id; } moon_f[80] = {
    {0, 12, 14, {-9554, 12268, 5162}, 15462, 34722}, {11, 13, 12, {-12268, 5162, 9554}, 15462, 34722}, {5, 14, 13, {-5162, 9554, 12268}, 15462, 34722},
    {12, 13, 14, {-9459, 9459, 9459}, 15297, 35096}, {0, 14, 16, {-4391, 15459, 3191}, 15463, 34720}, {5, 15, 14, {0, 12745, 10296}, 15465, 34715},
    {1, 16, 15, {4391, 15459, 3191}, 15463, 34720}, {14, 15, 16, {0, 15305, 5846}, 15301, 35087}, {0, 16, 18, {-4391, 15459, -3191}, 15463, 34720},
    {1, 17, 16, {4391, 15459, -3191}, 15463, 34720}, {7, 18, 17, {0, 12745, -10296}, 15465, 34715}, {16, 17, 18, {0, 15305, -5846}, 15301, 35087},
    {0, 18, 20, {-9554, 12268, -5162}, 15462, 34722}, {7, 19, 18, {-5162, 9554, -12268}, 15462, 34722}, {10, 20, 19, {-12268, 5162, -9554}, 15462, 34722},
    {18, 19, 20, {-9459, 9459, -9459}, 15297, 35096}, {0, 20, 12, {-12745, 10296, 0}, 15465, 34715}, {10, 21, 20, {-15459, 3191, -4391}, 15463, 34720},
    {11, 12, 21, {-15459, 3191, 4391}, 15463, 34720}, {20, 21, 12, {-15305, 5846, 0}, 15301, 35087}, {1, 15, 23, {9554, 12268, 5162}, 15462, 34722},
    {5, 22, 15, {5162, 9554, 12268}, 15462, 34722}, {9, 23, 22, {12268, 5162, 9554}, 15462, 34722}, {15, 22, 23, {9459, 9459, 9459}, 15297, 35096},
    {5, 13, 25, {-3191, 4391, 15459}, 15463, 34720}, {11, 24, 13, {-10296, 0, 12745}, 15465, 34715}, {4, 25, 24, {-3191, -4391, 15459}, 15463, 34720},
    {13, 24, 25, {-5846, 0, 15305}, 15301, 35087}, {11, 21, 27, {-15459, -3191, 4391}, 15463, 34720}, {10, 26, 21, {-15459, -3191, -4391}, 15463, 34720},
    {2, 27, 26, {-12745, -10296, 0}, 15465, 34715}, {21, 26, 27, {-15305, -5846, 0}, 15301, 35087}, {10, 19, 29, {-10296, 0, -12745}, 15465, 34715},
    {7, 28, 19, {-3191, 4391, -15459}, 15463, 34720}, {6, 29, 28, {-3191, -4391, -15459}, 15463, 34720}, {19, 28, 29, {-5846, 0, -15305}, 15301, 35087},
    {7, 17, 31, {5162, 9554, -12268}, 15462, 34722}, {1, 30, 17, {9554, 12268, -5162}, 15462, 34722}, {8, 31, 30, {12268, 5162, -9554}, 15462, 34722},
    {17, 30, 31, {9459, 9459, -9459}, 15297, 35096}, {3, 32, 34, {9554, -12268, 5162}, 15462, 34722}, {9, 33, 32, {12268, -5162, 9554}, 15462, 34722},
    {4, 34, 33, {5162, -9554, 12268}, 15462, 34722}, {32, 33, 34, {9459, -9459, 9459}, 15297, 35096}, {3, 34, 36, {4391, -15459, 3191}, 15463, 34720},
    {4, 35, 34, {0, -12745, 10296}, 15465, 34715}, {2, 36, 35, {-4391, -15459, 3191}, 15463, 34720}, {34, 35, 36, {0, -15305, 5846}, 15301, 35087},
    {3, 36, 38, {4391, -15459, -3191}, 15463, 34720}, {2, 37, 36, {-4391, -15459, -3191}, 15463, 34720}, {6, 38, 37, {0, -12745, -10296}, 15465, 34715},
    {36, 37, 38, {0, -15305, -5846}, 15301, 35087}, {3, 38, 40, {9554, -12268, -5162}, 15462, 34722}, {6, 39, 38, {5162, -9554, -12268}, 15462, 34722},
    {8, 40, 39, {12268, -5162, -9554}, 15462, 34722}, {38, 39, 40, {9459, -9459, -9459}, 15297, 35096}, {3, 40, 32, {12745, -10296, 0}, 15465, 34715},
    {8, 41, 40, {15459, -3191, -4391}, 15463, 34720}, {9, 32, 41, {15459, -3191, 4391}, 15463, 34720}, {40, 41, 32, {15305, -5846, 0}, 15301, 35087},
    {4, 33, 25, {3191, -4391, 15459}, 15463, 34720}, {9, 22, 33, {10296, 0, 12745}, 15465, 34715}, {5, 25, 22, {3191, 4391, 15459}, 15463, 34720},
    {33, 22, 25, {5846, 0, 15305}, 15301, 35087}, {2, 35, 27, {-9554, -12268, 5162}, 15462, 34722}, {4, 24, 35, {-5162, -9554, 12268}, 15462, 34722},
    {11, 27, 24, {-12268, -5162, 9554}, 15462, 34722}, {35, 24, 27, {-9459, -9459, 9459}, 15297, 35096}, {6, 37, 29, {-5162, -9554, -12268}, 15462, 34722},
    {2, 26, 37, {-9554, -12268, -5162}, 15462, 34722}, {10, 29, 26, {-12268, -5162, -9554}, 15462, 34722}, {37, 26, 29, {-9459, -9459, -9459}, 15297, 35096},
    {8, 39, 31, {10296, 0, -12745}, 15465, 34715}, {6, 28, 39, {3191, -4391, -15459}, 15463, 34720}, {7, 31, 28, {3191, 4391, -15459}, 15463, 34720},
    {39, 28, 31, {5846, 0, -15305}, 15301, 35087}, {9, 41, 23, {15459, 3191, 4391}, 15463, 34720}, {8, 30, 41, {15459, 3191, -4391}, 15463, 34720},
    {1, 23, 30, {12745, 10296, 0}, 15465, 34715}, {41, 30, 23, {15305, 5846, 0}, 15301, 35087},
};

/* the same moon coarse, for the middle distance: its 12 corners (moon_v's first twelve) in 20 faces, each with its outward normal (1.14);
   every face lies 13020 / 16384 of the corner radius from the middle (tools/moon.py) */
static const struct { u8 a, b, c; s16 n[3]; } moon_c20[20] = {
    {0, 11, 5, {-9459, 9459, 9459}}, {0, 5, 1, {0, 15305, 5846}}, {0, 1, 7, {0, 15305, -5846}}, {0, 7, 10, {-9459, 9459, -9459}},
    {0, 10, 11, {-15305, 5846, 0}}, {1, 5, 9, {9459, 9459, 9459}}, {5, 11, 4, {-5846, 0, 15305}}, {11, 10, 2, {-15305, -5846, 0}},
    {10, 7, 6, {-5846, 0, -15305}}, {7, 1, 8, {9459, 9459, -9459}}, {3, 9, 4, {9459, -9459, 9459}}, {3, 4, 2, {0, -15305, 5846}},
    {3, 2, 6, {0, -15305, -5846}}, {3, 6, 8, {9459, -9459, -9459}}, {3, 8, 9, {15305, -5846, 0}}, {4, 9, 5, {5846, 0, 15305}},
    {2, 4, 11, {-9459, -9459, 9459}}, {6, 2, 10, {-9459, -9459, -9459}}, {8, 6, 7, {5846, 0, -15305}}, {9, 8, 1, {15305, 5846, 0}},
};

static const s16 belt[6][4] = {      /* more rocks round the moon: offsets from its middle, and radius */
    {-3600, 1900, 2800, 420}, {2900, -1700, 4300, 360}, {-2200, -2600, -3900, 500},
    {4600, 1800, -1200, 300}, {-5600, -400, 900, 380}, {1200, 3300, -3400, 450},
};
static const s16 bea[3][3] = {{-5200, 800, -3000}, {3800, 2400, -5200}, {6200, -1200, 2400}};   /* rings, from the moon's middle */

static struct {
    V3 p, v;                       /* his pelvis (units << 8) and velocity */
    V3 f, u;                       /* the way he faces and his up (1.14) */
    u16 t, away;                   /* ticks since he jumped; ticks lost (no pack in space) or far from the Arwing */
    s16 lean;                      /* leaning into his flight (1.14 of forward) */
    u8 on, kind, slot, call;       /* call: 1 the Arwing comes and he boards, 2 it comes and waits */
    u8 gnd, board, drop, gone, hint, splay, jump, warp, thr;
} swk;
static Ship *sh;                   /* the empty Arwing */
static u8 obj_n, obj_s;            /* the sample objective under way, and its step */
static const char *msg;            /* the line at the bottom (the steady HUD line's place, never the ticker), and when it goes */
static u32 msg_end;
static void hint(const char *s)
{
    int n = 0;
    while (s[n])
        n++;
    msg = s, msg_end = frame_count + 150 + 4 * n;
}

static s32 iabs(s32 v) { return v < 0 ? -v : v; }
static s32 clampi(s32 v, s32 lo, s32 hi) { return v < lo ? lo : v > hi ? hi : v; }
/* the moon's middle, set from the station's place and kept (sync: the three compares) so a probe costs nothing; it follows the
   station if that is ever moved, and the post on the moon with it */
static V3 st_seen = {0, -1, 0}, mcen, post_at;   /* post_at: the post on the moon (units), 0 till asked */
static void sync(void)
{
    if (st_seen.x == station_pos.x && st_seen.y == station_pos.y && st_seen.z == station_pos.z)
        return;
    st_seen = station_pos;
    mcen = vadd(station_pos, v3(SW_MOON_X, SW_MOON_Y, SW_MOON_Z));
    post_at = v3(0, 0, 0);
}
static V3 moon_c(void) { sync(); return mcen; }
static V3 belt_c(int i) { return vadd(moon_c(), v3(belt[i][0], belt[i][1], belt[i][2])); }
static V3 ctr(V3 a) { return v3(a.x >> FX, a.y >> FX, a.z >> FX); }
static void add(V3 *a, V3 d, s32 k) { a->x += d.x * k >> 14, a->y += d.y * k >> 14, a->z += d.z * k >> 14; }
/* a velocity component slowed by 1 / 2^s, and a fine unit besides (so it comes to rest) */
static s32 dmp(s32 v, int s)
{
    v -= v >= 0 ? v >> s : -(-v >> s);
    return v > 0 ? v - 1 : v < 0 ? v + 1 : 0;
}

/* the skin of the moon along d (units from its middle, length L): how far out it is, the face it
   meets there (the one whose plane the ray from the middle reaches first) and its normal */
static s32 skin(V3 d, s32 L, V3 *nrm, int *face)
{
    V3 dir = v3(d.x * ONE / L, d.y * ONE / L, d.z * ONE / L);
    int best = 0;
    s32 bs = 0, bn = 1;
    for (int i = 0; i < 80; i++) {
        const s16 *n = moon_f[i].n;
        s32 nd = (n[0] * dir.x + n[1] * dir.y + n[2] * dir.z) >> 14;
        if (nd > 0 && nd * moon_f[i].id > bs)
            bs = nd * moon_f[i].id, best = i, bn = nd;
    }
    if (nrm)
        *nrm = v3(moon_f[best].n[0], moon_f[best].n[1], moon_f[best].n[2]);
    if (face)
        *face = best;
    return MOON_R * moon_f[best].d / bn;
}

/* the moon and the new rocks as solid for physics.c's space_hit (the Arwing's hull, p fine units) */
int sw_solid(V3 p, Hit *h)
{
    V3 u = ctr(p), d = vsub(u, moon_c());
    if (iabs(d.x) >= BELT_BOX || iabs(d.y) >= BELT_BOX || iabs(d.z) >= BELT_BOX)
        return 0;                  /* (the moon and every rock lie inside this box) */
    for (int i = 0; i < 6; i++) {
        V3 e = vsub(u, belt_c(i));
        s32 r = belt[i][3];
        if (iabs(e.x) >= r || iabs(e.y) >= r || iabs(e.z) >= r)
            continue;
        s32 l = vlen(e);
        if (l < r && l > 0) {
            h->dist = (r - l) << FX;
            h->n = vnorm(e);
            h->kind = SURF_ROCK;
            return 1;
        }
    }
    if (iabs(d.x) >= MOON_R || iabs(d.y) >= MOON_R || iabs(d.z) >= MOON_R)
        return 0;
    s32 L = vlen(d) | 1;
    V3 n;
    int f;
    if (L >= skin(d, L, &n, &f))
        return 0;
    h->n = n;
    h->dist = ((MOON_R * moon_f[f].d >> 14) - vdot(n, d)) << FX;   /* (down to the plane, along the normal) */
    h->kind = SURF_ROCK;
    return 1;
}

/* ---- the places ---- */
int sw_places(void) { return 4; }
V3 sw_moon(s32 *radius)
{
    if (radius)
        *radius = MOON_R;
    return moon_c();
}
V3 sw_place(int i)
{
    V3 mc = moon_c();
    if (i < 3)
        return vadd(mc, v3(bea[i][0], bea[i][1], bea[i][2]));
    if (!post_at.y) {              /* on the skin near the north, 380 up: its ring stands there */
        V3 d = v3(3, 9, 3), n = vnorm(d);
        s32 s = skin(d, vlen(d), 0, 0);
        post_at = vadd(mc, v3(n.x * (s + 380) >> 14, n.y * (s + 380) >> 14, n.z * (s + 380) >> 14));
    }
    return post_at;
}

int sw_active(void) { return swk.on; }
int sw_on(void) { return swk.on; }
int sw_kind(void) { return swk.on ? swk.kind : SWK_NONE; }
V3 sw_pos(void) { return swk.on ? ctr(swk.p) : v3(0, 0, 0); }
int sw_reach(V3 p, s32 r)
{
    if (!swk.on)
        return 0;
    V3 d = vsub(ctr(swk.p), p);
    return iabs(d.x) < r && iabs(d.y) < r && iabs(d.z) < r && vlen(d) < r;
}
int sw_obj(int *step, int *of)
{
    if (step)
        *step = obj_s;
    if (of)
        *of = obj_n == 3 ? 3 : 1;
    return obj_n;
}

void sw_reset(void)
{
    memset(&swk, 0, sizeof swk);
    sh = 0;
    obj_n = obj_s = 0;
}

/* a body frame for the pose and the pack: facing f, up leaning into the flight */
static void body_m(M3 *m)
{
    m->f = swk.f;
    m->u = vnorm(vadd(swk.u, vscale(swk.f, swk.lean)));
    m->r = swk.u;                    /* (morth sets it) */
    morth(m);
}

static V3 flat(V3 f, V3 u)         /* f in the plane across u, unit; a stand-in if it lies along u */
{
    V3 g = vsub(f, vscale(u, vdot(f, u)));
    if (vlen(g) < 3000) {
        g = vcross(u, iabs(u.x) < 12000 ? v3(ONE, 0, 0) : v3(0, 0, ONE));
        g = vcross(g, u);
    }
    return vnorm(g);
}

int sw_begin(Ship *s, int slot, V3 feet, s32 yaw, int side)
{
    const Body *b = &s->b;
    memset(&swk, 0, sizeof swk);
    swk.on = 1;
    swk.slot = slot;
    sh = s;
    swk.p = v3(feet.x << FX, (feet.y + PELV) << FX, feet.z << FX);
    V3 v = vscale(b->vel, 4096);   /* a quarter of the way it was flying, a push out of its side and a little up */
    s32 l = vlen(v);
    if (l > 20 << FX)
        v = vscale(v, (20 << FX) * ONE / l);
    add(&v, b->m.r, side * 4 << FX);
    v.y += 2 << FX;
    swk.v = v;
    swk.u = v3(0, ONE, 0);
    swk.f = flat(b->m.f, swk.u);
    (void)yaw;
    swk.kind = SWK_FALL;
    swk.splay = 14;
    M3 m;
    body_m(&m);
    rag_pose(&rags[slot], &m, ctr(swk.p), swk.splay);   /* (at once: the ragdoll's step must not move him) */
    rags[slot].own = 1;
    s2_ev(EV_WALK, 1, feet.y >> 4);
    return 1;
}

/* the Arwing comes: from behind him, a few thousand units off (never through the moon) */
static V3 warp_spot(void)
{
    V3 me = ctr(swk.p), a = vadd(me, vadd(vscale(swk.f, -2800), vscale(swk.u, 400)));
    Hit h;
    if (penetrate(v3(a.x << FX, a.y << FX, a.z << FX), &h))
        a = vadd(me, vadd(vscale(swk.u, 2800), vscale(swk.f, -400)));
    return a;
}

void sw_call(void)
{
    if (!swk.on)
        return;
    if (sh && !swk.gone) {
        V3 d = vsub(ctr(sh->b.pos), ctr(swk.p));
        if (iabs(d.x) < 900 && iabs(d.y) < 900 && iabs(d.z) < 900) {
            swk.board = 1;
            return;
        }
    }
    if (swk.call != 1)
        hint("Your Arwing is on its way."), swk.call = 1;
}

void sw_ship_gone(void) { swk.gone = 1; }

/* the empty Arwing, a tick: out here it keeps on, levels out and stops by itself; called, it
   flies in to him and waits at his side (or he is aboard) */
int sw_flies(Ship *s)
{
    if (!swk.on || s != sh)
        return 0;
    Body *b = &s->b;
    V3 pu = ctr(b->pos), me = ctr(swk.p);
    if (!swk.call && pu.y < SPACE_LO + 400)
        return 0;                  /* (down in the air it falls and crashes as an empty Arwing does) */
    s32 air = ONE - space_factor(pu.y);
    V3 want = flat(b->m.f, v3(0, ONE, 0));
    if (swk.call) {
        V3 d = vsub(vadd(me, vscale(vcross(swk.u, swk.f), 420)), pu);
        if (!swk.warp && (iabs(d.x) > 5000 || iabs(d.y) > 5000 || iabs(d.z) > 5000)) {
            swk.warp = 1;
            V3 a = warp_spot();
            b->pos = v3(a.x << FX, a.y << FX, a.z << FX);
            d = vsub(vadd(me, vscale(vcross(swk.u, swk.f), 420)), a);
        }
        s32 len = vlen(d), sp = len / 12 + 8;
        if (sp > 70)
            sp = 70;
        V3 u = vnorm(d);
        b->vel = len < 40 ? v3(0, 0, 0) : v3(u.x * sp >> 6, u.y * sp >> 6, u.z * sp >> 6);
        b->pos = vadd(b->pos, b->vel);
        b->m.f = vnorm(vadd(b->m.f, vshr(vsub(len > 300 ? u : swk.f, b->m.f), 3)));
        b->m.u = vnorm(vadd(b->m.u, vshr(vsub(swk.u, b->m.u), 3)));
        morth(&b->m);
        b->w = v3(0, 0, 0);
        if (len < 260 && swk.call == 1)
            swk.board = 1;           /* (in reach: he climbs aboard) */
        return 1;
    }
    b->vel.y -= (G_ACC * air) >> 14;
    int s_ = air > ONE / 2 ? 8 : 4;                  /* (no air to slow it: its own brakes) */
    b->vel = v3(dmp(b->vel.x, s_), dmp(b->vel.y, s_), dmp(b->vel.z, s_));
    b->pos = vadd(b->pos, b->vel);
    b->m.f = vnorm(vadd(b->m.f, vshr(vsub(want, b->m.f), 4)));
    b->m.u = vnorm(vadd(b->m.u, vshr(vsub(v3(0, ONE, 0), b->m.u), 4)));
    morth(&b->m);
    b->w = v3(0, 0, 0);
    ship_settle(s);                // (off the moon and the rocks)
    return 1;
}

/* one tick of him (k: the keys as held, hit: as pressed) */
void sw_tick(u16 k, u16 hit)
{
    if (!swk.on)
        return;
    (void)hit;
    if (swk.t < 0xffff)
        swk.t++;
    V3 pu = ctr(swk.p), mc = moon_c(), dm = vsub(pu, mc), dir = v3(0, ONE, 0);
    s32 sp = space_factor(pu.y), air = ONE - sp, hgt = 1 << 20;
    int near = 0, pack = sw_pack != 0;
    if (iabs(dm.x) < MOON_R + MOON_REACH + 300 && iabs(dm.y) < MOON_R + MOON_REACH + 300 && iabs(dm.z) < MOON_R + MOON_REACH + 300) {
        s32 L = vlen(dm) | 1;
        hgt = L - skin(dm, L, 0, 0);
        dir = v3(dm.x * ONE / L, dm.y * ONE / L, dm.z * ONE / L);
        near = hgt < MOON_REACH;
    }
    /* his up follows the moon's, or the world's */
    swk.u = vnorm(vadd(swk.u, vshr(vsub(near ? dir : v3(0, ONE, 0), swk.u), near ? 3 : 4)));
    swk.f = flat(swk.f, swk.u);
    if (k & (KEY_LEFT | KEY_RIGHT)) {
        s32 a = k & KEY_LEFT ? TURN : -TURN;
        swk.f = flat(vadd(vscale(swk.f, fcos(a)), vscale(vcross(swk.u, swk.f), fsin(a))), swk.u);
    }
    /* what he does with the pad: walk on the moon, jump; with the pack, fly (in the thin air less) */
    V3 acc = v3(0, 0, 0);
    s32 str = pack ? (A_FLOOR + ((ONE - A_FLOOR) * sp >> 14)) * sw_pack_k >> 8 : 0;
    int thr = 0;
    if (swk.jump)
        swk.jump--;
    if (swk.gnd) {
        if (k & KEY_UP)
            add(&acc, swk.f, 45);
        if (k & KEY_DOWN)
            add(&acc, swk.f, -45);
        if ((k & KEY_A) && !swk.jump) {
            add(&swk.v, dir, 5 << FX);
            swk.jump = 30;
            swk.gnd = 0;
        }
    } else if (pack) {
        s32 af = A_FWD * str >> 14, au = A_UP * str >> 14;
        if (k & KEY_UP)
            add(&acc, swk.f, af), thr = 1;
        if (k & KEY_DOWN)
            add(&acc, swk.f, -af), thr = 1;
        if (k & KEY_A)
            add(&acc, swk.u, au), thr = 1;
        if (k & KEY_B)
            add(&acc, swk.u, -au), thr = 1;
    }
    swk.thr = thr;
    if (near) {
        s32 gk = hgt <= 0 ? ONE : (MOON_REACH - hgt) * ONE / MOON_REACH;
        add(&acc, dir, -(MOON_G * gk >> 14));
    } else {
        acc.y -= (G_ACC * air) >> 14;
        s32 w = 6 * air >> 14;       /* a breeze in the thin air, back toward the city if he has drifted out over the sea (none in space) */
        if (w) {
            acc.x += pu.x < 2 * CELL ? w : pu.x > (CITY - 2) * CELL ? -w : 0;
            acc.z += pu.z < 2 * CELL ? w : pu.z > (CITY - 2) * CELL ? -w : 0;
        }
        if (pu.y > 58000)
            acc.y -= (pu.y - 58000) >> 2;           /* (the edge of space pushes back, as on the Arwing) */
    }
    swk.v = vadd(swk.v, acc);
    if (swk.gnd) {                   /* on foot: friction, a walking pace */
        s32 vr = vdot(swk.v, dir);
        V3 vt = vsub(swk.v, vscale(dir, vr));
        int s = k & (KEY_UP | KEY_DOWN) ? 4 : 1;
        vt = v3(dmp(vt.x, s), dmp(vt.y, s), dmp(vt.z, s));
        s32 l = vlen(vt);
        if (l > WALK_MAX)
            vt = vscale(vt, WALK_MAX * ONE / l);
        swk.v = vadd(vt, vscale(dir, vr));
    } else {
        int s = k & KEY_L ? 3 : pack && !thr ? 6 : 8;   /* L brakes; the pack steadies him; else a drift */
        swk.v = v3(dmp(swk.v.x, s), dmp(swk.v.y, s), dmp(swk.v.z, s));
        s32 cap = pack ? PACK_MAX * sw_pack_k >> 8 : 40 << FX, l = vlen(swk.v);
        if (l > cap && (pack || !near))
            swk.v = vsub(swk.v, vshr(vsub(swk.v, vscale(swk.v, cap * ONE / l)), 2));   /* (eased down to the pace) */
        if (!near && swk.v.y < -FALL_CAP)
            swk.v.y = -FALL_CAP;
    }
    swk.p = vadd(swk.p, swk.v);
    /* the moon under his feet, and the rocks, the station and the rest all round him */
    pu = ctr(swk.p);
    dm = vsub(pu, mc);
    int ground = 0;
    swk.gnd = 0;
    if (iabs(dm.x) < MOON_R + 300 && iabs(dm.y) < MOON_R + 300 && iabs(dm.z) < MOON_R + 300) {
        s32 L = vlen(dm) | 1, s = skin(dm, L, 0, 0);
        V3 n = v3(dm.x * ONE / L, dm.y * ONE / L, dm.z * ONE / L);
        s32 vr = vdot(swk.v, n);
        if (L - s - PELV < 2 && vr <= 0) {   /* (not while he is leaving it) */
            swk.p = v3((mc.x << FX) + ((s + PELV) * n.x >> (14 - FX)), (mc.y << FX) + ((s + PELV) * n.y >> (14 - FX)),
                     (mc.z << FX) + ((s + PELV) * n.z >> (14 - FX)));
            swk.v = vsub(swk.v, vscale(n, vr));
            swk.gnd = ground = 1;
            near = 1;
        }
    }
    for (int i = 0; i < 3; i++) {
        V3 q = vadd(swk.p, vscale(swk.u, (i - 1) * (PELV << FX)));
        Hit h;
        if (!penetrate(q, &h))
            continue;
        s32 d = h.dist > 8192 ? 8192 : h.dist;
        swk.p = vadd(swk.p, vscale(h.n, d));
        s32 vn = vdot(swk.v, h.n);
        if (vn < 0)
            swk.v = vsub(swk.v, vscale(h.n, vn));
    }
    pu = ctr(swk.p);
    int fwdv = vdot(swk.v, swk.f) >> 5;     /* he leans into his flight (steady: no more than a fifth of a turn) */
    swk.lean += ((swk.gnd ? 0 : fwdv > 5000 ? 5000 : fwdv < -2500 ? -2500 : fwdv) - swk.lean) >> 3;
    int ts = swk.gnd ? 0 : swk.kind == SWK_FLOAT && !pack ? 12 : pack ? (thr ? 3 : 6) : 14;
    swk.splay += swk.splay < ts ? (swk.t & 1) : -(swk.splay > ts && (swk.t & 1));
    swk.kind = near || ground ? SWK_MOON : pu.y > SPACE_HI ? SWK_FLOAT : SWK_FALL;
    if (!near && pu.y < SPACE_LO)
        swk.drop = 1;
    /* helpless out here with no pack, or far from the Arwing: it comes after a while */
    int far = sh && !swk.gone && (iabs(ctr(sh->b.pos).x - pu.x) + iabs(ctr(sh->b.pos).z - pu.z) > 20000);
    int help = !pack && swk.kind == SWK_FLOAT;
    if ((help || far) && !swk.call) {
        if (++swk.away == (help ? 480 : 900)) {
            sw_call();
            swk.call = help ? 1 : 2;
            if (help)
                hint("No jet pack! Fox Station sells one.");
        }
    } else if (!help && !far) {
        swk.away = 0;
    }
    /* hints, once each */
    if (swk.t == 45 && pu.y > SPACE_HI + 200)
        hint(pack ? "Jet pack: D-pad flies, A up, B down." : "Hold SELECT to call your Arwing.");
    if (swk.kind == SWK_MOON && !(swk.hint & 1)) {
        swk.hint |= 1;
        hint("The moon: D-pad walks, A jumps.");
        s2_ev(EV_WALK, 2, 0);
    }
    /* the sample objectives (the mailbox starts them) */
    if (obj_n) {
        int ok = 0;
        if (obj_n == 1)
            ok = sw_reach(sw_place(0), 900);
        else if (obj_n == 2)
            ok = swk.gnd && sw_reach(sw_place(3), 700);
        else if (obj_s < 2)
            ok = sw_reach(sw_place(1 + obj_s), 900);
        if (ok) {
            s2_ev(EV_WALK, 3, obj_n == 2 ? 3 : obj_n == 1 ? 0 : 1 + obj_s);
            if (obj_n == 3 && ++obj_s < 3) {
                hint("Beacon reached! On to the next.");
            } else if (obj_n < 3) {
                sg_credit(obj_n == 1 ? 150 : 300);
                hint(obj_n == 1 ? "Beacon reached! +150 CR" : "Moon landing! +300 CR");
                obj_n = obj_s = 0;
            }
        }
    }
}

/* once a frame: his body posed; what the glue is to do (SWF_*) */
int sw_frame(int ticks, V3 *at, V3 *vel, s32 *yaw)
{
    (void)ticks;
    if (!swk.on)
        return SWF_KEEP;
    M3 m;
    body_m(&m);
    Rag *r = &rags[swk.slot];
    rag_pose(r, &m, ctr(swk.p), swk.splay);
    r->own = 1;
    *at = ctr(swk.p);
    *vel = swk.v;
    *yaw = fatan2(swk.f.x, swk.f.z);
    if (swk.board) {
        s2_ev(EV_WALK, 0, 1);
        if (obj_n == 3 && obj_s == 2) {
            sg_credit(500);
            hint("Beacon tour done! +500 CR");
            obj_n = obj_s = 0;
        }
        swk.on = 0;
        return SWF_BOARD;
    }
    if (swk.drop) {
        s2_ev(EV_WALK, 0, 2);
        swk.on = 0;
        return SWF_DROP;
    }
    if (swk.gone && swk.call) {
        swk.gone = 0;
        *at = warp_spot();
        return SWF_NEWSHIP;
    }
    return SWF_KEEP;
}

int sw_land_at(V3 p)
{
    if (!swk.on)
        return 0;
    V3 mc = moon_c(), d = vsub(p, mc);
    s32 L = vlen(d) | 1, s = 0;
    if (L < MOON_R + 3000) {       /* on the moon: down on its skin, wherever that is along the line from its middle */
        s = skin(d, L, 0, 0) + PELV;
        p = vadd(mc, v3(d.x * s / L, d.y * s / L, d.z * s / L));
        swk.gnd = 1;
    } else {
        p.y += PELV;
    }
    swk.p = v3(p.x << FX, p.y << FX, p.z << FX);
    swk.v = v3(0, 0, 0);
    return 1;
}

void sw_view(V3 *p, V3 *fwd, V3 *up)
{
    *p = vsub(ctr(swk.p), vscale(swk.u, PELV));
    *fwd = swk.f;
    *up = swk.u;
}

/* the camera stays out of the moon and the rocks */
void sw_cam_clear(V3 *pos)
{
    if (!swk.on)
        return;
    V3 mc = moon_c(), d = vsub(*pos, mc);
    if (iabs(d.x) < MOON_R + 200 && iabs(d.y) < MOON_R + 200 && iabs(d.z) < MOON_R + 200) {
        s32 L = vlen(d) | 1, s = skin(d, L, 0, 0) + 120;
        if (L < s)
            *pos = vadd(mc, v3(d.x * s / L, d.y * s / L, d.z * s / L));
    }
    for (int i = 0; i < 6 + nrocks; i++) {
        V3 c = i < 6 ? belt_c(i) : rocks[i - 6].c, e = vsub(*pos, c);
        s32 r = (i < 6 ? belt[i][3] : rocks[i - 6].r) + 120;
        if (iabs(e.x) < r && iabs(e.y) < r && iabs(e.z) < r) {
            s32 l = vlen(e) | 1;
            if (l < r)
                *pos = vadd(c, v3(e.x * r / l, e.y * r / l, e.z * r / l));
        }
    }
}

/* ---- drawing ---- */

/* a sphere of radius r at c (camera space) that is at least partly in the view */
static int in_view(V3 c, s32 r)
{
    return c.z >= -r && c.z * 121 - c.x * FOCAL >= -r * FRX && c.z * 121 + c.x * FOCAL >= -r * FRX
        && c.z * 81 - c.y * FOCAL >= -r * FRX && c.z * 81 + c.y * FOCAL >= -r * FRX;
}

/* the moon as it is seen: all 80 faces close up, 20 at the middle distance, one disc far off. What a polygon costs is mostly its
   pixels, so the disc is only as large as it can be afforded: its true size to MOON_DISC, then its radius falls with the square of
   the distance, to a speck of 3 pixels (a moon at the far end of a flight is a dot, not 20 pixels of fill a frame). c is its middle in
   camera space, q its distance squared over 16. Not inlined
   into sw_draw3d: that is on the deepest call chain, and the 42 corners here may be on the stack only while this draws, not while the
   rocks and rings do (inlined, the stack ran into what lies below it and the game stopped). */
__attribute__((noinline)) static void moon_draw(V3 c, s32 q)
{
    s32 rr = MOON_R + MOON_R / 16;          /* (the coarse one's corners lie a little out to keep its size) */
    if (!in_view(c, rr))
        return;                             /* (out of sight: none of the rest) */
    static const u8 mat[8] = {M_CONCRETE, M_CONCRETE, M_STEEL, M_CONCRETE, M_ROAD, M_CONCRETE, M_STEEL, M_CONCRETE};
    if (q >= (MOON_MID / 4) * (MOON_MID / 4)) {      /* a flat disc facing the camera */
        static const s8 hx[6] = {32, 16, -16, -32, -16, 16}, hy[6] = {0, 28, 28, 0, -28, -28};
        s32 z = c.z, w = 70, ir = (1 << 28) / z;                          /* (w: the radius over 32: 2240, a little inside its edge; ir: 1 / z, the one division) */
        if (z < NEAR)
            return;
        if (z > MOON_DISC) {
            s32 s = MOON_DISC * ir >> 14;
            w = w * (s * s >> 14) >> 14;
        }
        if (w * 32 * FOCAL < 3 * z)
            w = ((3 * z * 482 >> 16) + 31) >> 5;                          /* (a speck: 3 pixels; 482 / 65536 is 1 / FOCAL) */
        if (w * 32 * FOCAL <= 8 * z) {      /* 8 pixels or less: put on the screen directly, none of the clipping and projecting of the corners */
            static const s8 dx[4] = {36, 0, -36, 0}, dy[4] = {0, 36, 0, -36};
            s32 k = FOCAL * 16, px = 1920 + (s32)((s64)(c.x * k) * ir >> 28), py = 1280 - (s32)((s64)(c.y * k) * ir >> 28);   /* (28.4) */
            s32 u = (s32)((s64)(w * k << 8) * ir >> 28), xy[12];                                                              /* (a corner's step, 8 bits finer) */
            int n = w * 32 * FOCAL <= 4 * z ? 4 : 6;                     /* (4 pixels or less: a diamond, it is a dot) */
            for (int i = 0; i < n; i++) {
                s32 ox = n == 4 ? dx[i] : hx[i], oy = n == 4 ? dy[i] : hy[i];
                xy[2 * i] = clampi(px + (ox * u >> 8), 0, 3840);
                xy[2 * i + 1] = clampi(py - (oy * u >> 8), 0, 2560);
            }
            r_poly2d(xy, n, COLOR(M_CONCRETE, 2, fog_of(z)), z, 0);
            return;
        }
        V3 d[6];
        for (int i = 0; i < 6; i++)
            d[i] = v3(c.x + hx[i] * w, c.y + hy[i] * w, z);
        r_poly(d, 6, COLOR(M_CONCRETE, 2, fog_of(z)), -2, 0);
        return;
    }
    V3 mc = moon_c(), cp = vsub(cam.pos, mc);
    V3 cv[42];
    if (q < (MOON_FULL / 4) * (MOON_FULL / 4)) {
        for (int i = 0; i < 42; i++)
            cv[i] = r_cam(v3(mc.x + (moon_v[i][0] * MOON_R >> 8), mc.y + (moon_v[i][1] * MOON_R >> 8), mc.z + (moon_v[i][2] * MOON_R >> 8)));
        for (int f = 0; f < 80; f++) {
            const s16 *n = moon_f[f].n;
            if (((n[0] * (cp.x >> 2) + n[1] * (cp.y >> 2) + n[2] * (cp.z >> 2)) >> 12) <= (MOON_R * moon_f[f].d >> 14))
                continue;              /* (turned away) */
            s32 l = (n[0] * 6553 + n[1] * 13107 + n[2] * 7372) >> 14;
            int lv = (l + 16384) >> 13;
            V3 t[3] = {cv[moon_f[f].a], cv[moon_f[f].b], cv[moon_f[f].c]};
            r_poly(t, 3, COLOR(mat[(f * 5 + f / 3) & 7], lv > 3 ? 3 : lv, fog_of((t[0].z + t[1].z + t[2].z) / 3)), -2, 0);
        }
        return;
    }
    for (int i = 0; i < 12; i++)
        cv[i] = r_cam(v3(mc.x + (moon_v[i][0] * rr >> 8), mc.y + (moon_v[i][1] * rr >> 8), mc.z + (moon_v[i][2] * rr >> 8)));
    for (int f = 0; f < 20; f++) {
        const s16 *n = moon_c20[f].n;
        if (((n[0] * (cp.x >> 2) + n[1] * (cp.y >> 2) + n[2] * (cp.z >> 2)) >> 12) <= (rr * 13020 >> 14))
            continue;
        s32 l = (n[0] * 6553 + n[1] * 13107 + n[2] * 7372) >> 14;
        int lv = (l + 16384) >> 13;
        V3 t[3] = {cv[moon_c20[f].a], cv[moon_c20[f].b], cv[moon_c20[f].c]};
        r_poly(t, 3, COLOR(mat[f & 7], lv > 3 ? 3 : lv, fog_of((t[0].z + t[1].z + t[2].z) / 3)), -2, 0);
    }
}

/* a thing at d from the camera, radius r: near enough and large enough on the screen (8 pixels across or more) to draw */
static int worth(V3 d, s32 r)
{
    if (iabs(d.x) > SW_NEAR || iabs(d.y) > SW_NEAR || iabs(d.z) > SW_NEAR || (d.x >> 2) * (d.x >> 2) + (d.y >> 2) * (d.y >> 2) + (d.z >> 2) * (d.z >> 2) > (SW_NEAR / 4) * (SW_NEAR / 4))
        return 0;
    s32 z = vdot(cam.m.f, d);
    return z > -r && FOCAL * r >= 4 * z;
}

/* what a rock or a ring is placed with: static, not on the stack. sw_draw3d, the one that draws it and model_draw and poly under it
   are the deepest call chain there is; 130 bytes less on it is what keeps it above Payback's own code that lies below the stack. */
static Place pp;
static M3 pm;

__attribute__((noinline)) void sw_rocks_draw(void)
{
    if (!props)
        return;
    V3 mc = moon_c();
    for (int i = 0; i < 6; i++) {
        V3 c = vadd(mc, v3(belt[i][0], belt[i][1], belt[i][2]));
        if (!worth(vsub(c, cam.pos), belt[i][3]))
            continue;
        myaw(&pm, i * 9000 + 3000);
        if (model_place(&pp, c, &pm, belt[i][3], 0, mdl_rock.radius))
            model_draw(&mdl_rock, &pp);
    }
}

/* the rings and the post: gates, steady in colour and light; the one an objective wants is bright */
static V3 target(void)
{
    return obj_n == 1 ? sw_place(0) : obj_n == 2 ? sw_place(3) : obj_s < 2 ? sw_place(1 + obj_s) : sh ? ctr(sh->b.pos) : v3(0, 0, 0);
}

/* the post stands on the moon: its up is out from the middle (a call of its own: its temporaries are not on the stack while it draws) */
__attribute__((noinline)) static void post_up(V3 c)
{
    V3 u = vnorm(vsub(c, moon_c()));
    pm.u = u;
    pm.f = flat(v3(0, 0, ONE), u);
    pm.r = u;
    morth(&pm);
}

__attribute__((noinline)) void sw_rings_draw(void)
{
    if (!props)
        return;
    V3 mc = moon_c(), tg = obj_n ? target() : v3(0, -1, 0);
    for (int i = 0; i < 4; i++) {
        V3 c = i < 3 ? vadd(mc, v3(bea[i][0], bea[i][1], bea[i][2])) : mc;
        if (i == 3 && !worth(vsub(c, cam.pos), 4000))
            continue;              /* (the post stands on the moon: when the moon is too far off to draw it, so is it) */
        if (i == 3)
            c = sw_place(3);
        if (!worth(vsub(c, cam.pos), i < 3 ? 768 : 256))
            continue;
        if (i < 3)
            myaw(&pm, 7000 + i * 18000);
        else
            post_up(c);
        model_body = c.x == tg.x && c.y == tg.y && c.z == tg.z ? M_ACCENT : M_STEEL;
        if (model_place(&pp, c, &pm, i < 3 ? 768 : 256, 0, mdl_gate.radius))
            model_draw(&mdl_gate, &pp);
    }
    model_body = M_CAR;
}

/* the pack on his back, and its flame while it pushes (two steady cones, not a flicker) */
__attribute__((noinline)) static void pack_draw(void)
{
    if (!swk.on || !sw_pack)
        return;
    static const MVert a[8] = {{-20, -10, -17}, {20, -10, -17}, {20, 70, -17}, {-20, 70, -17},
                               {-20, -10, -37}, {20, -10, -37}, {20, 70, -37}, {-20, 70, -37}};
    static const u8 face[5][4] = {{4, 5, 6, 7}, {3, 2, 6, 7}, {0, 3, 7, 4}, {1, 2, 6, 5}, {0, 1, 5, 4}};
    M3 m;
    Place pl;
    body_m(&m);
    if (!model_place(&pl, ctr(swk.p), &m, 256, 0, 200))
        return;
    for (int i = 0; i < 5; i++) {
        MVert q[4] = {a[face[i][0]], a[face[i][1]], a[face[i][2]], a[face[i][3]]};
        model_poly(&pl, q, 4, COLOR(M_STEEL, i ? 2 : 1, 0));
    }
    if (swk.thr)
        for (int s = -1; s <= 1; s += 2) {
            MVert q[3] = {{s * 14, -10, -27}, {s * 6, -10, -27}, {s * 10, -58, -27}};
            model_poly(&pl, q, 3, COLOR(M_STUNT, 3, 0));
        }
}

void sw_draw3d(void)
{
    if (swk.on)
        pack_draw();
    sw_moon_near = props = 0;
    if (cam.pos.y < 14000)
        return;
    s32 x = station_pos.x + SW_MOON_X - cam.pos.x, y = station_pos.y + SW_MOON_Y - cam.pos.y, z = station_pos.z + SW_MOON_Z - cam.pos.z;
    sw_moon_near = iabs(x) < BELT_BOX + 4000 && iabs(y) < BELT_BOX + 4000 && iabs(z) < BELT_BOX + 4000;   /* (what he or the Arwing probes is within 4000 of the camera) */
    if ((u32)(y + MOON_FAR) > 2 * MOON_FAR || (u32)(x + MOON_FAR) > 2 * MOON_FAR || (u32)(z + MOON_FAR) > 2 * MOON_FAR)
        return;                    /* (the rocks and rings lie round it: none in sight either) */
    s32 q = (x >> 2) * (x >> 2) + (y >> 2) * (y >> 2) + (z >> 2) * (z >> 2);   /* its distance squared, over 16 */
    if (q > (MOON_FAR / 4) * (MOON_FAR / 4))
        return;
    V3 mc = moon_c(), c = r_cam(mc);
    moon_draw(c, q);
    if (q < ((SW_NEAR + PROP_R) / 4) * ((SW_NEAR + PROP_R) / 4) && in_view(c, PROP_R + 800)) {   /* (the rocks and rings lie within PROP_R of its middle, and are as large as 770) */
        props = 1;
    }
}

/* ---- the HUD: where he is, the pack, the objective ---- */
#define INK COLOR(M_CREAM, 3, 0)
#define HI COLOR(M_ACCENT, 3, 0)
#define PANEL COLOR(M_ROAD, 0, 0)

static void mark(V3 p, int c)
{
    V3 d = vsub(p, cam.pos);
    while (iabs(d.x) > 30000 || iabs(d.y) > 30000 || iabs(d.z) > 30000)
        d = vshr(d, 1);
    s32 z = vdot(cam.m.f, d), rx = vdot(cam.m.r, d), ry = vdot(cam.m.u, d);
    int x, y;
    if (z > 64 && (x = 120 + FOCAL * rx / z) > 6 && x < 234 && (y = 80 - FOCAL * ry / z) > 6 && y < 154) {
        d_hline(x - 4, x + 4, y, c);
        d_vline(x, y - 4, y + 4, c);
        return;
    }
    s32 big = iabs(rx) > iabs(ry) ? iabs(rx) : iabs(ry);
    if (!big)
        return;
    x = 120 + (z > 0 ? rx : -rx) * 100 / big, y = 80 - (z > 0 ? ry : -ry) * 64 / big;   /* (on the edge, toward it) */
    d_hline(x - 3, x + 3, y, c);
    d_vline(x, y - 3, y + 3, c);
}

void sw_hud(void)
{
    if (s2f.paused || PB_LEVEL_END == 3)
        return;
    char b[40], *p;
    int y = 66;                                   /* (below Payback's own two-line banner) */
    if (msg && frame_count < msg_end) {
        int n = 0;
        while (msg[n])
            n++;
        y = 128;                                  /* (under the steady line at y117 and the space HUD's) */
        d_fill(0, y - 2, n * TEXT_W + 8, 11, PANEL);
        d_text(4, y, msg, HI);
        y = 66;
    }
    if (!swk.on && !obj_n)
        return;
    if (swk.on) {
        p = d_cat(b, swk.kind == SWK_MOON ? "MOON " : swk.kind == SWK_FLOAT ? "SPACE " : "FALLING ");
        p = d_cat(p, "ALT ");
        p = d_num(p, ctr(swk.p).y);
        d_fill(4, y - 2, (p - b) * TEXT_W + 8, 10, PANEL);
        d_text(8, y, b, INK);
        y += 10;
        p = d_cat(b, swk.call ? "ARWING COMING" : sw_pack ? "JET PACK" : "NO JET PACK");
        d_fill(4, y - 2, (p - b) * TEXT_W + 8, 10, PANEL);
        d_text(8, y, b, swk.call || sw_pack ? INK : HI);
        y += 10;
    }
    if (obj_n) {
        static const char *const what[] = {"", "REACH BEACON A", "LAND ON THE MOON", "BEACON B", "BEACON C", "BOARD THE ARWING"};
        V3 t = target(), d = vsub(t, s2f.pos);
        p = d_cat(b, what[obj_n == 3 ? 3 + obj_s : obj_n]);
        p = d_cat(p, " ");
        p = d_num(p, vlen(vshr(d, 1)) * 2);
        d_fill(4, y - 2, (p - b) * TEXT_W + 8, 10, PANEL);
        d_text(8, y, b, HI);
        mark(t, HI);
    }
}

/* ---- the mailbox: 80..95 (stage2.h) ---- */
int sw_dbg(int cmd, int arg)
{
    switch (cmd) {
    case 80:                       /* start a sample objective (1..3), 0 none */
        obj_n = arg > 3 ? 0 : arg, obj_s = 0;
        return obj_n;
    case 81:                       /* what is going on: on, kind, on the ground, pack, called, objective and step */
        return swk.on | swk.kind << 1 | swk.gnd << 4 | (sw_pack != 0) << 5 | swk.call << 6 | obj_n << 8 | obj_s << 12 | swk.t << 16;
    case 82:
        sw_pack = arg == 2 ? !sw_pack : arg;
        return sw_pack;
    case 83: {                     /* the Arwing to altitude arg * 16, still */
        V3 p = s2f.pos;
        p.y = arg * 16;
        return s2_put_player(p, s2f.heading, FLY) ? p.y : -1;
    }
    case 84:
        return swk.on ? ctr(swk.p).y : -1;
    case 85:                       /* put him down on the moon's north */
        return sw_land_at(vadd(moon_c(), v3(0, MOON_R, 0)));
    case 86:
        return swk.t;
    case 87:
        return swk.v.y;
    case 88:                       /* to place arg (just short of it), with no speed */
        if (!swk.on || arg < 0 || arg > 3)
            return 0;
        swk.v = v3(0, 0, 0);
        V3 q = sw_place(arg);
        if (arg < 3)
            return sw_land_at(vadd(q, v3(0, -PELV - 200, 0)));
        return sw_land_at(q);
    case 89:
        return sg_credit(arg * 100);
    case 90:
        sw_call();
        return swk.on;
    case 91:                       /* the Arwing arg * 64 units away along x */
        if (!sh)
            return 0;
        sh->b.pos.x += arg * 64 << FX;
        return 1;
    case 92:
        return swk.on ? ctr(sh->b.pos).y : -1;
    case 93:
        return swk.on ? vlen(swk.v) : -1;
    case 94:
        return swk.u.y;
    case 95:                       /* how far from the moon's middle (units) */
        return swk.on ? vlen(vsub(ctr(swk.p), moon_c())) : -1;
    }
    return -1;
}
