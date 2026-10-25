/* See ragdoll.h. A body is 12 points (pelvis, shoulders, head, elbows, hands, knees, feet) held
   together by 14 sticks, stepped once a frame with that frame's ticks, position-based: each point
   moves, is pushed out of the city, the sticks pull back to length (twice), and its velocity is
   where it got to. A point that comes down hard bounces back up (RESTITUTION), so a body thrown
   high bounces two or three times, each lower, then slides and settles. The city here is the one
   the car stands on: floors, roofs, ramps, bridge decks, walls and railings (physics.c), and the
   water, where a body floats. Thumb in ROM: a moving body costs a few thousand cycles a frame, one
   at rest none but its drawing. */
#include "ragdoll.h"
#include "world.h"
#include "render.h"
#include "palette.h"

Rag rags[RAG_N];
u8 rag_grav_k = 4, rag_bounce;     /* GAME SETTINGS: gravity in quarters; restitution /16, 0 as below */
u8 rag_on, rag_wacky, rag_fall, rag_unlock;      /* (off until the cheat: see README) */
const Body *rag_car;

enum { P_PELVIS, P_LS, P_RS, P_HEAD, P_LE, P_LW, P_RE, P_RW, P_LK, P_LF, P_RK, P_RF };

/* standing (units: feet at 0, facing +z, +x the right hand), as the person models stand */
static const s16 pose[RAG_P][3] = {
    {0, 100, 0}, {-34, 176, 0}, {34, 176, 0}, {0, 206, 0}, {-40, 140, -2}, {-40, 102, 4},
    {40, 140, -2}, {40, 102, 4}, {-15, 52, 3}, {-15, 6, -2}, {15, 52, 3}, {15, 6, -2},
};
/* ... and floating: arms out and a little forward, the legs apart and bent back (spacewalk.c) */
static const s16 pose_float[RAG_P][3] = {
    {0, 100, 0}, {-34, 176, 0}, {34, 176, 0}, {0, 206, 0}, {-67, 189, 7}, {-104, 197, 15},
    {67, 189, 7}, {104, 197, 15}, {-24, 55, -5}, {-45, 16, -17}, {24, 55, -5}, {45, 16, -17},
};
/* how far out each point's surface is (units): what touches the ground first */
static const u8 radius[RAG_P] = {14, 12, 12, 16, 7, 6, 7, 6, 8, 5, 8, 5};

/* a stick: its ends (hip 1 or 2: a is that hip, a point a fifth of the shoulders' width out from
   the pelvis), its length squared ((units * 8)^2) and 2^26 / that */
typedef struct { u8 a, b, hip; s32 l2; s16 inv; } Stick;
static const Stick sticks[] = {
    {P_PELVIS, P_LS, 0, 443648, 151}, {P_PELVIS, P_RS, 0, 443648, 151}, {P_LS, P_RS, 0, 295936, 226},
    {P_HEAD, P_LS, 0, 131584, 510}, {P_HEAD, P_RS, 0, 131584, 510}, {P_HEAD, P_PELVIS, 0, 719104, 93},
    {P_LS, P_LE, 0, 85504, 784}, {P_LE, P_LW, 0, 94720, 708}, {P_RS, P_RE, 0, 85504, 784},
    {P_RE, P_RW, 0, 94720, 708}, {P_PELVIS, P_LK, 1, 148032, 453}, {P_LK, P_LF, 0, 137024, 489},
    {P_PELVIS, P_RK, 2, 148032, 453}, {P_RK, P_RF, 0, 137024, 489},
};
#define NSTICK (sizeof sticks / sizeof sticks[0])

#define SH 3                       /* points are in units << SH */
#define VBOUNCE (3 << SH)          /* coming down slower than this (units a tick) it does not bounce */
#define VQUIET 10                  /* (units << SH a tick) moving less than this a body is settling */
#define FALL (52 << SH)            /* falling no faster than this (units a tick; a fall of under three cells
                                      gets there): it comes down on a floor a part at a time, never all of it
                                      flat at once */

static s32 iabs(s32 v) { return v < 0 ? -v : v; }
/* (160 units a tick: never across more than one cell in a step) */
static s32 clampv(s32 v) { return v > 1280 ? 1280 : v < -1280 ? -1280 : v; }

static int keep(s32 *P, s32 ox, s32 oz, s32 ax, s32 az, s32 ya, s32 yb, int r);
static s32 floor_at(s32 x, s32 z, s32 y0, int *shape, s32 *ceil);

s32 rag_floor(s32 x, s32 z, s32 y)
{
    int sh;
    s32 ce;
    return floor_at(x, z, y, &sh, &ce);
}

V3 rag_pelvis(const Rag *r)
{
    return v3(r->o[0] + (r->x[0][0] >> SH), r->o[1] + (r->x[0][1] >> SH), r->o[2] + (r->x[0][2] >> SH));
}

void rag_pose(Rag *r, const M3 *m, V3 at, int s)
{
    for (int i = 0; i < RAG_P; i++) {
        V3 l = mlocal(m, v3(pose[i][0] + (pose_float[i][0] - pose[i][0]) * s / 16,
                            pose[i][1] - pose[0][1] + (pose_float[i][1] - pose[i][1]) * s / 16,
                            pose[i][2] + (pose_float[i][2] - pose[i][2]) * s / 16));
        r->x[i][0] = l.x << SH, r->x[i][1] = l.y << SH, r->x[i][2] = l.z << SH;
        r->v[i][0] = r->v[i][1] = r->v[i][2] = 0;
    }
    r->o[0] = at.x, r->o[1] = at.y, r->o[2] = at.z;
    r->state = RAG_UP;
    r->age = 1;                                    /* (RAG_UP, aged: the figure is not 'just stood up') */
    r->quiet = r->bounces = r->land = r->held = r->due = 0;
}

void rag_clear(void)
{
    for (int i = 0; i < RAG_N; i++)
        rags[i].state = RAG_FREE, rags[i].rec = 0;
    rag_car = 0;
}

Rag *rag_of(const u8 *rec)
{
    for (int i = 0; i < RAG_N; i++)
        if (rags[i].state && rags[i].rec == rec)
            return &rags[i];
    return 0;
}


int rag_throw(V3 feet, s32 yaw, V3 vel, V3 spin, int body, int legs, int hero, const u8 *rec)
{
    int k = rags[0].own;
    for (int i = 0; i < RAG_N; i++) {              /* a free slot, else the one thrown longest ago (never
                                                      the player bailing out) */
        if (!rags[i].state) { k = i; break; }
        if (!rags[i].own && rags[i].age > rags[k].age) k = i;
    }
    int sh;
    s32 ce;
    if (floor_at(feet.x, feet.z, feet.y + 40, &sh, &ce) > feet.y + 160)
        return -1;                                 /* standing where our city is solid (a floor Payback has that
                                                      ours has not, Little Chicago's walkways): no body, it would
                                                      come out on the roof */
    Rag *r = &rags[k];
    M3 m;
    myaw(&m, yaw);
    r->o[0] = feet.x, r->o[1] = feet.y, r->o[2] = feet.z;
    if (rag_wacky)                                 /* (further and spinning; not far higher, or a chase camera
                                                      sees only a speck going up out of the picture) */
        vel = v3(vel.x + (vel.x >> 1), vel.y + (vel.y >> 3), vel.z + (vel.z >> 1)), spin = vadd(spin, spin);
    for (int i = 0; i < RAG_P; i++) {
        V3 p = mlocal(&m, v3(pose[i][0], pose[i][1], pose[i][2]));
        V3 w = vcross(spin, v3(p.x, p.y - pose[0][1], p.z));   /* (units a tick, about the pelvis) */
        s32 P[3] = {p.x << SH, p.y << SH, p.z << SH};
        s32 y = feet.y + p.y - radius[i];
        keep(P, feet.x, feet.z, feet.x, feet.z, y, y, radius[i]);   /* (a hand by a wall) */
        r->x[i][0] = P[0], r->x[i][1] = P[1], r->x[i][2] = P[2];
        r->v[i][0] = (vel.x >> (FX - SH)) + (w.x << SH);
        r->v[i][1] = (vel.y >> (FX - SH)) + (w.y << SH);
        r->v[i][2] = (vel.z >> (FX - SH)) + (w.z << SH);
    }
    r->rec = rec;
    r->kx = feet.x, r->kz = feet.z;
    r->body = body, r->legs = legs, r->hero = hero;
    r->state = RAG_FLY;
    r->quiet = r->bounces = r->own = r->land = r->held = r->far = r->due = 0;
    r->fine = 1;
    r->age = 0;
    return k;
}

/* ---- the city, as a point sees it ---- */

/* the floor under (x, z) (units) for a point that was at height y0: a bridge deck it was over,
   else the ground (a water cell's surface: it floats); *n: 0 flat, else the ramp's shape */
static s32 floor_at(s32 x, s32 z, s32 y0, int *shape, s32 *ceil)
{
    const Cell *c = &world.cell[(x >> 10) * CITY + (z >> 10)];
    s32 g = c->hi, fx = x & 1023, fz = z & 1023, d = c->hi - c->lo;
    *shape = 0;
    *ceil = 0x7fffffff;
    switch (c->shape) {
    case 2: g = c->lo + ((d * fz) >> 10); *shape = 2; break;
    case 3: g = c->lo + ((d * fx) >> 10); *shape = 3; break;
    case 4: g = c->lo + ((d * (1024 - fz)) >> 10); *shape = 4; break;
    case 5: g = c->lo + ((d * (1024 - fx)) >> 10); *shape = 5; break;
    case SHAPE_WATER: g -= 14; *shape = 1; break;  /* (floats, low in the water) */
    }
    const s8 *dk = &world.deck[4 * ((x >> 10) * CITY + (z >> 10))];
    if (dk[0] | dk[1]) {
        for (int k = 0; k < 2; k++) {
            s32 b, t;
            if (!world_deck(x, z, k, &b, &t))
                break;
            if (y0 >= ((b + t) >> 1))
                g = t, *shape = 0;                 /* on it (a sloped one: flat enough) */
            else if (*ceil > b)
                *ceil = b;                         /* under it */
        }
    }
    return g;
}

/* can a point at height y (units, its bottom) go from cell (ax, az) into the next one at (bx, bz)
   (just over the edge)? Not into a floor higher than it was there (a building's side, a ramp's
   side or top end), nor into a bridge deck's side, nor through Payback's railing on that edge */
static int blocked(s32 ax, s32 az, s32 bx, s32 bz, s32 y)
{
    int sh;
    s32 ce, g = floor_at(bx, bz, y, &sh, &ce);
    if (g > y + 24 || y + 24 > ce)
        return 1;                                  /* (a kerb's step it goes over) */
    s32 lo, hi;
    int w = world_wall(ax, az, &lo, &hi), e;
    e = bx != ax ? (bx > ax ? 2 : 8) : (bz > az ? 4 : 1);  /* edge bits -z 1, +x 2, +z 4, -x 8 */
    if ((w & e) && y > lo - 32 && y < hi)
        return 1;
    w = world_wall(bx, bz, &lo, &hi);
    e = e == 1 ? 4 : e == 4 ? 1 : e == 2 ? 8 : 2;
    return (w & e) && y > lo - 32 && y < hi;
}

/* point P (units << SH from o) going from (ax, az) (units) to where it is, its bottom from ya to
   yb (units), r its radius: over each cell edge it crossed (the one it reached first first, at
   the height it had there) unless that is blocked, else back to it. Returns 3 if it was stopped
   going along x, 4 along z, else 0 */
static int keep(s32 *P, s32 ox, s32 oz, s32 ax, s32 az, s32 ya, s32 yb, int r)
{
    s32 bx = ox + (P[0] >> SH), bz = oz + (P[2] >> SH);
    int cx = (ax ^ bx) >> 10 != 0, cz = (az ^ bz) >> 10 != 0, t = 0;
    if (!(cx | cz))
        return 0;
    s32 ex = bx > ax ? (ax | 1023) + 1 : ax & ~1023, ez = bz > az ? (az | 1023) + 1 : az & ~1023;   /* the edges */
    s32 tx = bx > ax ? ex : ex - 1, tz = bz > az ? ez : ez - 1;   /* just over them */
    s32 yx = yb, yz = yb;                          /* how high it was where it went over each */
    if (ya != yb) {
        if (cx) yx = ya + (yb - ya) * (ex - ax) / (bx - ax);
        if (cz) yz = ya + (yb - ya) * (ez - az) / (bz - az);
    }
    if (cz && (!cx || iabs(ez - az) * iabs(bx - ax) < iabs(ex - ax) * iabs(bz - az))) {
        if (blocked(ax, az, ax, tz, yz))
            bz = bz > az ? ez - 1 - r : ez + r, P[2] = (bz - oz) << SH, t = 4;
        if (cx && blocked(ax, bz, tx, bz, yx))
            bx = bx > ax ? ex - 1 - r : ex + r, P[0] = (bx - ox) << SH, t = 3;
    } else {
        if (blocked(ax, az, tx, az, yx))
            bx = bx > ax ? ex - 1 - r : ex + r, P[0] = (bx - ox) << SH, t = 3;
        if (cz && blocked(bx, az, bx, tz, yz))
            bz = bz > az ? ez - 1 - r : ez + r, P[2] = (bz - oz) << SH, t = 4;
    }
    return t;
}

/* ---- one step ---- */

static const u16 recip[9] = {0, 65535, 32768, 21845, 16384, 13107, 10923, 9362, 8192};

/* what a stick's ends each move, as a part of it (1.14), for a stretch u = |d|^2 / l^2 - 1 from
   -1 on in sixteenths: (1 - l / |d|) / 2, so that one pass puts a stick far out back to length
   (near its length, u / 4 - 3 u^2 / 16 is close enough and smooth) */
static const s16 pull_by[80] = {
    -8192, -8192, -8192, -8192, -7255, -5780, -4661, -3773, -3047, -2439, -1920, -1471, -1076, -726, -413, -131,
    125, 359, 574, 772, 955, 1125, 1284, 1432, 1572, 1703, 1827, 1943, 2054, 2159, 2259, 2354,
    2444, 2531, 2613, 2692, 2768, 2841, 2911, 2978, 3043, 3105, 3166, 3224, 3280, 3334, 3387, 3438,
    3487, 3535, 3581, 3626, 3670, 3712, 3753, 3794, 3833, 3871, 3908, 3944, 3979, 4014, 4047, 4080,
    4112, 4143, 4174, 4204, 4233, 4261, 4289, 4317, 4344, 4370, 4396, 4421, 4446, 4470, 4494, 4517,
};

/* the sticks back to length, the knees and elbows bending only their own way; returns the
   worst stretch it found (1.14, either way). (Not inlined: Thumb has eight registers to work
   with, and inside step every value of this went to the stack and back.) */
static __attribute__((noinline)) s32 pull(s32 (*X)[3])
{
    s32 worst = 0;
    s32 O[3][3];                                   /* where each stick's a end is from point a */
    O[0][0] = O[0][1] = O[0][2] = 0;
    O[1][0] = (X[P_LS][0] - X[P_RS][0]) * 7 >> 5, O[1][1] = (X[P_LS][1] - X[P_RS][1]) * 7 >> 5,
    O[1][2] = (X[P_LS][2] - X[P_RS][2]) * 7 >> 5;  /* (the hips, out toward each shoulder) */
    O[2][0] = -O[1][0], O[2][1] = -O[1][1], O[2][2] = -O[1][2];
    for (const Stick *s = sticks; s < sticks + NSTICK; s++) {
        s32 *A = X[s->a], *B = X[s->b];
        const s32 *o = O[s->hip];
        s32 dx = B[0] - A[0] - o[0], dy = B[1] - A[1] - o[1], dz = B[2] - A[2] - o[2];
        s32 d2 = dx * dx + dy * dy + dz * dz, l2 = s->l2, u, f;
        if (d2 > 8 * l2)
            d2 = 8 * l2;
        u = ((d2 - l2) * s->inv) >> 12;            /* 1.14 */
        if (u < 0) {
            if (-u > worst) worst = -u;
        } else if (u > worst) {
            worst = u;
        }
        if (u > -4096 && u < 4096)
            f = (u * (8192 - ((u * 6144) >> 14))) >> 15;
        else
            f = pull_by[u >= 65536 ? 79 : (u + 16384) >> 10];
        dx = (dx * f) >> 14, dy = (dy * f) >> 14, dz = (dz * f) >> 14;
        A[0] += dx, A[1] += dy, A[2] += dz;
        B[0] -= dx, B[1] -= dy, B[2] -= dz;
    }
    /* which way the chest faces: (right shoulder - left) x (shoulders - pelvis), near 1.14 */
    s32 sx = X[P_RS][0] - X[P_LS][0], sy = X[P_RS][1] - X[P_LS][1], sz = X[P_RS][2] - X[P_LS][2];
    s32 ux = ((X[P_RS][0] + X[P_LS][0]) >> 1) - X[0][0], uy = ((X[P_RS][1] + X[P_LS][1]) >> 1) - X[0][1],
        uz = ((X[P_RS][2] + X[P_LS][2]) >> 1) - X[0][2];
    s32 fx = (sy * uz - sz * uy) >> 4, fy = (sz * ux - sx * uz) >> 4, fz = (sx * uy - sy * ux) >> 4;
    fx = fx * 3246 >> 12, fy = fy * 3246 >> 12, fz = fz * 3246 >> 12;
    static const u8 joint[4][3] = {{P_LK, P_PELVIS, P_LF}, {P_RK, P_PELVIS, P_RF}, {P_LE, P_LS, P_LW}, {P_RE, P_RS, P_RW}};
    for (int j = 0; j < 4; j++) {
        s32 *J = X[joint[j][0]], *a = X[joint[j][1]], *b = X[joint[j][2]];
        s32 d = ((J[0] - ((a[0] + b[0]) >> 1)) * fx + (J[1] - ((a[1] + b[1]) >> 1)) * fy +
                 (J[2] - ((a[2] + b[2]) >> 1)) * fz) >> 14;
        if (j < 2 ? d < 0 : d > 0)                 /* a knee bent backwards, an elbow forwards */
            J[0] -= (fx * d) >> 14, J[1] -= (fy * d) >> 14, J[2] -= (fz * d) >> 14;
    }
    return worst;
}

/* point i's floor and ceiling where P is (units << SH from o; y its bottom, units), and the
   place they are of; returns the floor's shape (floor_at) */
static int floor_of(const s32 *P, s32 ox, s32 oy, s32 oz, s32 y, int i, s32 *fl, s32 *ce, s32 *hx, s32 *hz)
{
    int sh;
    s32 c, g;
    *hx = ox + (P[0] >> SH), *hz = oz + (P[2] >> SH);
    g = floor_at(*hx, *hz, y, &sh, &c) + radius[i];
    *fl = (g - oy) << SH;
    *ce = c < 0x40000 ? (c - radius[i] - oy) << SH : 0x7fffffff;
    if (*ce < *fl)
        *ce = *fl;
    return sh;
}

#ifdef RAG_HOST
unsigned rag_pulls, rag_steps;
#endif
#ifndef RAG_TOL
#define RAG_TOL 1500               /* (1.14: sticks within about 5% of their length) */
#endif
#ifndef RAG_FINE
#define RAG_FINE 2                 /* steps a frame coming down fast on something */
#endif
#ifndef RAG_AIR
#define RAG_AIR 1                  /* (0: the host check, as it was without the shortcut) */
#endif
#ifndef RAG_ITS
#define RAG_ITS 12                 /* passes at most (a step): three on an ordinary step, all of them on a hard
                                      landing on a corner, where fewer left a stick half as long again for a frame */
#endif

/* the points back on their side of the city and over their floors after a pull: each in its
   own cell, the rest on the pelvis' side of any wall (so a body is never wrapped round a corner
   or hung over a railing). (Not inlined, as pull.) */
static __attribute__((noinline)) void settle(s32 (*X)[3], s32 ox, s32 oy, s32 oz, s32 *fl, s32 *ce,
                                             s32 *hx, s32 *hz, u8 *ramp)
{
    s32 px = ox + (X[0][0] >> SH), pz = oz + (X[0][2] >> SH);
    for (int i = 0; i < RAG_P; i++) {
        s32 x = ox + (X[i][0] >> SH), z = oz + (X[i][2] >> SH), y = oy + (X[i][1] >> SH) - radius[i];
        if (((x ^ hx[i]) | (z ^ hz[i])) >> 10) {   /* (out of its own cell) */
            keep(X[i], ox, oz, hx[i], hz[i], y, y, radius[i]);
            x = ox + (X[i][0] >> SH), z = oz + (X[i][2] >> SH);
        }
        if (!i)
            px = x, pz = z;
        else if (((x ^ px) | (z ^ pz)) >> 10) {   /* (not in the pelvis' cell) */
            keep(X[i], ox, oz, px, pz, y, y, radius[i]);
            x = ox + (X[i][0] >> SH), z = oz + (X[i][2] >> SH);
        }
        if (ramp[i] || ((x ^ hx[i]) | (z ^ hz[i])) >> 10)   /* (its floor where it is now) */
            ramp[i] = floor_of(X[i], ox, oy, oz, y, i, &fl[i], &ce[i], &hx[i], &hz[i]) >= 2;
        if (X[i][1] < fl[i])
            X[i][1] = fl[i];
        else if (X[i][1] > ce[i])
            X[i][1] = ce[i];
    }
}

/* our car runs into it (points X, units << SH from (ox, oy, oz), its fastest moving most):
   knocked on, at the car's speed (and a little up); never the player bailing out of it, nor by a
   car crawling or parked on it (it would never come to rest), nor when it already goes as fast as
   the car. 1 if it was. (Not inlined, as pull.) */
static __attribute__((noinline)) int car_knock(Rag *r, s32 (*X)[3], s32 ox, s32 oy, s32 oz, s32 most)
{
    V3 c = vshr(rag_car->pos, FX);
    V3 cv = vshr(rag_car->vel, FX - SH);
    s32 px = ox + (X[0][0] >> SH), pz = oz + (X[0][2] >> SH), cs = iabs(cv.x) + iabs(cv.z);
    if (cs <= 4 << SH || most >= cs || iabs(px - c.x) >= 500 || iabs(pz - c.z) >= 500)
        return 0;
    const M3 *m = &rag_car->m;
    int hit = 0;
    s32 wide = r->due && r->age < 240 ? 420 : 100;   /* (one Payback knocked down as the car came: struck by
                                                        its corner or its side, as Payback had it; its reach is
                                                        wider than our car, a third of a cell off its side) */
    for (int i = 0; i < RAG_P && !hit; i++) {
        V3 l = mworld(m, v3(ox + (X[i][0] >> SH) - c.x, oy + (X[i][1] >> SH) - c.y, oz + (X[i][2] >> SH) - c.z));
        hit = iabs(l.x) < wide && iabs(l.z) < 240 && l.y > -96 && l.y < 80;   /* (down to the street: the
                                                      car's centre rides 76 up, and one lying there is under that) */
    }
    if (!hit)
        return 0;
    /* (all of it as one: a limb alone would stretch; up a storey or two and on a little slower than
       the car, as a hit throws one: over its roof if it keeps going, ahead if it brakes) */
    V3 lp = mworld(m, v3(px - c.x, 0, pz - c.z));
    s32 sd = lp.x < 0 ? -1 : 1;                    /* (off the side of the car it was nearer: seen across from
                                                      behind it, not end on) */
    s32 k = rag_wacky ? 8 : 7, vx = (cv.x * k >> 3) - sd * (cv.z >> 2), vz = (cv.z * k >> 3) + sd * (cv.x >> 2);
    s32 vy = cv.y + (6 << SH) + cs / 4;
    for (int i = 0; i < RAG_P; i++) {              /* (the legs swept on and out more than the head: it
                                                      cartwheels) */
        s32 dy = (X[0][1] - X[i][1]) >> SH;
        r->v[i][0] = vx + (cv.x * dy >> 9) - sd * (cv.z * dy / 400);
        r->v[i][1] = vy;
        r->v[i][2] = vz + (cv.z * dy >> 9) + sd * (cv.x * dy / 400);
    }
    r->state = RAG_FLY;
    r->due = r->quiet = 0;
    return 1;
}

static void step(Rag *r, int dt)
{
#ifdef RAG_HOST
    rag_steps++;
#endif
    s32 X[RAG_P][3], X0[RAG_P][3];
    s32 fl[RAG_P], ce[RAG_P];                      /* each point's floor and ceiling (units << SH, from o) */
    s16 vin[RAG_P];                                /* how fast it came into what it touched */
    u8 touch[RAG_P];                               /* what: 0 nothing, 1 floor, 2 ramp, 3 wall x, 4 wall z, 5 ceiling, 6 water */
    const s32 ox = r->o[0], oy = r->o[1], oz = r->o[2];
    const s32 grav = ((rag_wacky ? 3 : 4) * rag_grav_k + 3) >> 2;            /* (units << SH a tick each tick: G_ACC, 0.5 units) */
    const s32 lo = (2 * CELL - ox) << SH, hi = ((CITY - 2) * CELL - ox) << SH;
    const s32 loz = (2 * CELL - oz) << SH, hiz = ((CITY - 2) * CELL - oz) << SH;
    s32 fall = 0;                                  /* the body's own speed up (x 12), coming in */
    for (int i = 0; i < RAG_P; i++) {
        s32 vx = clampv(r->v[i][0]), vy = r->v[i][1] - grav * dt, vz = clampv(r->v[i][2]);
        if (vy < -FALL) vy = -FALL;                /* (as fast as a body falls through the air) */
        if (vy > 1280) vy = 1280;
        fall += vy;
        vx -= (vx * dt) >> 8, vy -= (vy * dt) >> 8, vz -= (vz * dt) >> 8;   /* (air) */
        X0[i][0] = r->x[i][0], X0[i][1] = r->x[i][1], X0[i][2] = r->x[i][2];
        X[i][0] = X0[i][0] + vx * dt;
        X[i][1] = X0[i][1] + vy * dt;
        X[i][2] = X0[i][2] + vz * dt;
        if (X[i][0] < lo) X[i][0] = lo;
        if (X[i][0] > hi) X[i][0] = hi;
        if (X[i][2] < loz) X[i][2] = loz;
        if (X[i][2] > hiz) X[i][2] = hiz;
        touch[i] = 0;
        vin[i] = 0;
    }
    /* out of the city: walls first (back to its own side of a cell's edge), then the floor */
    s32 hx[RAG_P], hz[RAG_P];                      /* the cell each point's floor is of (units) */
    u8 ramp[RAG_P];
    for (int i = 0; i < RAG_P; i++) {
        s32 y0 = oy + (X0[i][1] >> SH) - radius[i];
        s32 ax = ox + (X0[i][0] >> SH), az = oz + (X0[i][2] >> SH);
        int t = keep(X[i], ox, oz, ax, az, y0, oy + (X[i][1] >> SH) - radius[i], radius[i]);
        if (t)
            touch[i] = t, vin[i] = r->v[i][t - 3 ? 2 : 0];
        int sh = floor_of(X[i], ox, oy, oz, y0, i, &fl[i], &ce[i], &hx[i], &hz[i]);
        ramp[i] = sh >= 2;
        if (X[i][1] < fl[i]) {
            if (!touch[i])
                touch[i] = sh == 1 ? 6 : sh >= 2 ? 2 : 1, vin[i] = r->v[i][1] - grav * dt;
            X[i][1] = fl[i];
        } else if (X[i][1] > ce[i]) {
            X[i][1] = ce[i];
            if (!touch[i])
                touch[i] = 5, vin[i] = r->v[i][1];
        }
    }
    /* in the air (nothing touched, all of it in the pelvis' cell and clear of its floor by more
       than the step took): the sticks alone, no putting back (a third of the step's cost) */
    int air = RAG_AIR;
    for (int i = 0; i < RAG_P && air; i++)
        air = !touch[i] && !((hx[i] ^ hx[0]) | (hz[i] ^ hz[0])) >> 10 && X[i][1] - fl[i] > (X0[i][1] - X[i][1]) + (24 << SH)
              && X[i][1] < ce[i] - (24 << SH);
    /* the sticks, each time with the points put back (settle); until none is out by more than
       3% (about 6% of its length), or RAG_ITS times */
    for (int it = 0; it < RAG_ITS; it++) {
        s32 w = pull(X);
#ifdef RAG_HOST
        rag_pulls++;
#endif
        if (!air)
            settle(X, ox, oy, oz, fl, ce, hx, hz, ramp);
        if (w < RAG_TOL)
            break;
    }
    /* how fast each point went, and what bounced */
    s32 e = rag_bounce ? rag_bounce : rag_wacky ? 12 : 9, rub = rag_wacky ? 2 : 6;   /* restitution and friction, / 16 */
    const s32 upmost = rag_wacky ? 26 << SH : 14 << SH;    /* no bounce faster up than this (units a tick): off a
                                                              roof a body hops 200 units, not 800 */
    s32 most = 0, rise = 0;
    u32 rd = recip[dt];
    int hard = 0, down = 0;
    for (int i = 0; i < RAG_P; i++) {
        s32 vx = ((X[i][0] - X0[i][0]) * (s32)rd) >> 16, vy = ((X[i][1] - X0[i][1]) * (s32)rd) >> 16,
            vz = ((X[i][2] - X0[i][2]) * (s32)rd) >> 16;
        if (touch[i]) {
            s32 in = vin[i];
            down |= touch[i] <= 2 || touch[i] == 6;
            if (touch[i] <= 2) {                   /* floor or ramp: up is out */
                if (vy > 40 << SH)
                    vy = 40 << SH;                 /* (put out of a floor it was deep in: not a launch) */
                if (in < -VBOUNCE) {               /* (the limb itself a little; the body below) */
                    s32 up = (-in * e) >> 5;
                    if (up > upmost >> 1) up = upmost >> 1;
                    if (vy < up) vy = up;
                    hard = 1;
                }
                vx -= (vx * rub) >> 4, vz -= (vz * rub) >> 4;
            } else if (touch[i] == 3) {
                if (iabs(in) > VBOUNCE) vx = -(in * e) >> 4;
            } else if (touch[i] == 4) {
                if (iabs(in) > VBOUNCE) vz = -(in * e) >> 4;
            } else if (touch[i] == 6) {
                vx -= vx >> 2, vy -= vy >> 1, vz -= vz >> 2;   /* (water: no bounce, a slow drift) */
            } else if (vy > 0) {
                vy = -(vy * e) >> 4;
            }
        }
        r->v[i][0] = vx, r->v[i][1] = vy, r->v[i][2] = vz;
        rise += vy;
        s32 m = iabs(vx) + iabs(vy) + iabs(vz);
        if (m > most) most = m;
    }
    /* the bounce: come down hard, the whole body goes back up at e of the speed it came down
       at (as one, turning as it was), so it hops two or three times, each lower */
    fall = fall * 2731 >> 15, rise = rise * 2731 >> 15;   /* (/ 12) */
    if (hard && fall < -VBOUNCE * 2) {
        if (-fall >> SH > r->land)
            r->land = -fall >> SH;                 /* (how hard: fall damage, merge.c) */
        if ((fall = ((-fall * e) >> 4) - rise) > 0) {
            if (fall > upmost - rise)
                fall = upmost - rise;
            for (int i = 0; i < RAG_P; i++)
                r->v[i][1] += fall;
            r->bounces++;
            most += fall;
        }
    }
    if (rag_car && !r->own && car_knock(r, X, ox, oy, oz, most))
        most = 99;
    /* settling: down and slow it slows more (no shivering on a slope), and lying still for half
       a second it is at rest (or down at all after twelve seconds) */
    if (down && most < 3 * VQUIET)
        for (int i = 0; i < RAG_P; i++)
            r->v[i][0] -= r->v[i][0] >> 2, r->v[i][1] -= r->v[i][1] >> 2, r->v[i][2] -= r->v[i][2] >> 2;
    if (most < 2 * VQUIET && down)
        r->quiet += dt;
    else
        r->quiet = 0;
    r->age += dt;
    if (r->age > 2400) {                           /* (never seen: a minute in the air) */
        r->state = RAG_FREE, r->rec = 0;
        return;
    }
    if (r->quiet > 30 || (r->age > 720 && down && most < 4 * VQUIET)) {   /* (not in the moment a car
                                                                              knocks it on: it would lie as it
                                                                              was that step, a stick out long) */
        r->state = RAG_REST;
        for (int i = 0; i < RAG_P; i++)
            r->v[i][0] = r->v[i][1] = r->v[i][2] = 0;
    }
    /* fast and near a floor (or a wall it hit): the next steps a tick at a time, so it comes
       down on it a part at a time rather than all of it flat at once */
    s32 gap = 0x7fffffff, sink = 0;
    for (int i = 0; i < RAG_P; i++) {
        s32 g = X[i][1] - fl[i], s = -r->v[i][1];
        if (touch[i] == 3 || touch[i] == 4)
            g = 0, s = iabs(r->v[i][touch[i] == 3 ? 0 : 2]);
        if (g < gap) gap = g;
        if (s > sink) sink = s;
    }
    r->fine = sink > 16 << SH && gap < sink * 4 + (64 << SH);
    /* the body's place follows its pelvis, so its points stay small numbers */
    s32 kx = X[0][0] >> SH, ky = X[0][1] >> SH, kz = X[0][2] >> SH;
    r->o[0] = ox + kx, r->o[1] = oy + ky, r->o[2] = oz + kz;
    for (int i = 0; i < RAG_P; i++) {
        s32 x = X[i][0] - (kx << SH), y = X[i][1] - (ky << SH), z = X[i][2] - (kz << SH);
        if (iabs(x) > 4000 || iabs(y) > 4000 || iabs(z) > 4000) {
            r->state = RAG_FREE;                   /* (never seen: a body pulled apart goes) */
            r->rec = 0;
            return;
        }
        r->x[i][0] = x, r->x[i][1] = y, r->x[i][2] = z;
    }
}

/* ---- getting up ---- */

s32 rag_yaw(const Rag *r)
{
    const s16 (*x)[3] = r->x;
    s32 sx = x[P_RS][0] - x[P_LS][0], sz = x[P_RS][2] - x[P_LS][2];
    s32 ux = ((x[P_RS][0] + x[P_LS][0]) >> 1) - x[0][0], uy = ((x[P_RS][1] + x[P_LS][1]) >> 1) - x[0][1],
        uz = ((x[P_RS][2] + x[P_LS][2]) >> 1) - x[0][2];
    s32 sy = x[P_RS][1] - x[P_LS][1];
    s32 fx = sy * uz - sz * uy, fz = sx * uy - sy * ux;   /* the chest's way (as pull has it) */
    if (iabs(uy) > iabs(ux) + iabs(uz))
        return fatan2(fx, fz);                     /* upright enough: the way the chest faces */
    return fatan2(-ux, -uz);                       /* lying: sat up, toward the feet */
}

#define RISE 20                    /* ticks to get up */

void rag_rise(Rag *r, s32 yaw)
{
    r->state = RAG_RISE;
    r->age = 0;
    r->kx = yaw;                                   /* (kx holds the yaw while getting up) */
    for (int i = 0; i < RAG_P; i++)
        r->v[i][0] = r->v[i][1] = r->v[i][2] = 0;
}

/* each point a part of the way to where it stands, its feet on the floor under the pelvis */
static void rising(Rag *r, int ticks)
{
    M3 m;
    int sh, left = RISE - r->age;
    s32 ce, fl = floor_at(r->o[0], r->o[2], r->o[1], &sh, &ce) + pose[0][1] - r->o[1];
    myaw(&m, r->kx);
    if (left <= ticks) {
        r->state = RAG_UP;
        left = ticks;
    }
    s32 X[RAG_P][3];                               /* (worked on aside: the body is never seen half done) */
    for (int i = 0; i < RAG_P; i++) {
        V3 p = mlocal(&m, v3(pose[i][0], pose[i][1] - pose[0][1], pose[i][2]));
        s32 t[3] = {p.x << SH, (p.y + fl) << SH, p.z << SH};
        for (int a = 0; a < 3; a++)
            X[i][a] = r->x[i][a] + (t[a] - r->x[i][a]) * ticks / left;
    }
    r->age = r->state == RAG_UP ? 0 : r->age + ticks;   /* (up: counts the frames it has stood) */
    if (r->state == RAG_RISE)                      /* the sticks their own length on the way (the blend alone
                                                      shortens a limb that turns, by a third half way through;
                                                      two passes left one a fifth to two fifths out) */
        for (int it = 0; it < RAG_ITS && pull(X) >= RAG_TOL; it++)
            ;
    for (int i = 0; i < RAG_P; i++)
        r->x[i][0] = X[i][0], r->x[i][1] = X[i][1], r->x[i][2] = X[i][2];
}

void rag_tick(int ticks)
{
    if (!ticks)
        return;
    int flying = 0, full = 0;
    for (int i = 0; i < RAG_N; i++)
        flying += rags[i].state == RAG_FLY;
    for (int i = 0; i < RAG_N; i++) {
        Rag *r = &rags[i];
        if (r->state == RAG_RISE) {
            rising(r, ticks);
        } else if (r->state == RAG_REST || r->state == RAG_UP) {
            if (r->age < 0xff00) r->age += ticks;
            if (r->due && rag_car && r->state == RAG_REST) {   /* (down where Payback knocked them as the car
                                                                  came: thrown when it gets there) */
                s32 X[RAG_P][3];
                for (int j = 0; j < RAG_P; j++)
                    X[j][0] = r->x[j][0], X[j][1] = r->x[j][1], X[j][2] = r->x[j][2];
                if (car_knock(r, X, r->o[0], r->o[1], r->o[2], 0))
                    r->fine = 1;
            }
        } else if (r->state == RAG_FLY) {
            /* every other frame, with the ticks carried over, when it is far off and others are in
               the air, or two bodies have already had their steps this frame (so a crowd thrown at
               once costs about two bodies' worth); never two frames running */
            int t = ticks + r->held;
            int skip = !r->held && t < 8 && ((flying > 1 && r->far) || full >= 2);
            r->held = skip ? t : 0;
            if (skip)
                continue;
            full++;
            for (int d; t > 0 && r->state == RAG_FLY; t -= d) {   /* (a step a frame, never over 6 ticks;
                                                                        two steps of up to 4 coming down
                                                                        fast on something) */
                d = r->fine ? (t + RAG_FINE - 1) / RAG_FINE : t;
                if (d > (r->fine ? 4 : 6))
                    d = r->fine ? 4 : 6;
                step(r, d);
            }
        }
    }
}

#ifndef RAG_HOST
/* ---- drawing ---- */

/* a limb from a to b (camera space), wa and wb wide (units) at each end, as one flat quad
   turned to face the camera */
static void limb(V3 a, V3 b, s32 wa, s32 wb, int color)
{
    s32 dx = b.x - a.x, dy = b.y - a.y, ax = iabs(dx), ay = iabs(dy);
    s32 l = ax > ay ? ax + (ay * 3 >> 3) : ay + (ax * 3 >> 3);
    s32 px = 256, py = 0;                          /* (unit, 8 bits) */
    if (l >= 2) {
        s32 k = 65536 / l;
        px = -dy * k >> 8, py = dx * k >> 8;
    }
    V3 q[4] = {v3(a.x + (px * wa >> 8), a.y + (py * wa >> 8), a.z), v3(b.x + (px * wb >> 8), b.y + (py * wb >> 8), b.z),
               v3(b.x - (px * wb >> 8), b.y - (py * wb >> 8), b.z), v3(a.x - (px * wa >> 8), a.y - (py * wa >> 8), a.z)};
    r_poly(q, 4, color, -1, 0);
}

static V3 mid(V3 a, V3 b) { return v3((a.x + b.x) >> 1, (a.y + b.y) >> 1, (a.z + b.z) >> 1); }

static int face_lv;

static void draw_one(Rag *r)
{
    V3 c[RAG_P];
    V3 o = v3(r->o[0], r->o[1], r->o[2]), d = vsub(o, cam.pos);
    r->far = 1;
    if (iabs(d.x) > 20000 || iabs(d.y) > 20000 || iabs(d.z) > 20000)
        return;
    V3 t = r_cam(o);
    if (t.z < -200 || FOCAL * t.x - 121 * t.z > 200 * FRX || -FOCAL * t.x - 121 * t.z > 200 * FRX ||
        FOCAL * t.y - 81 * t.z > 200 * FRY || -FOCAL * t.y - 81 * t.z > 200 * FRY)
        return;
    for (int i = 0; i < RAG_P; i++) {             /* (the camera's axes, like r_cam, on the offsets) */
        s32 x = r->x[i][0], y = r->x[i][1], z = r->x[i][2];
        c[i] = v3(t.x + ((cam.m.r.x * x + cam.m.r.y * y + cam.m.r.z * z) >> (14 + SH)),
                  t.y + ((cam.m.u.x * x + cam.m.u.y * y + cam.m.u.z * z) >> (14 + SH)),
                  t.z + ((cam.m.f.x * x + cam.m.f.y * y + cam.m.f.z * z) >> (14 + SH)));
        if (c[i].z < NEAR)
            return;                                /* (at the camera: not drawn this frame) */
    }
    int fog = fog_of(t.z);
    int body = r->hero ? M_GLOW : r->body, legs = r->hero ? M_GLASS : r->legs;
    int lv = face_lv, cb = COLOR(body, lv, fog), cl = COLOR(legs, lv, fog), skin = COLOR(M_CREAM, lv, fog), hair = COLOR(M_ROAD, lv, fog);
    V3 ls = c[P_LS], rs = c[P_RS], p = c[P_PELVIS];
    V3 side = vsub(rs, ls);
    V3 hl = vadd(p, vscale(side, -3600)), hr = vadd(p, vscale(side, 3600));   /* the hips, as the sticks have them */
    V3 neck = mid(ls, rs), up = vsub(c[P_HEAD], neck);
    /* which way the chest faces (about 16 units long) */
    V3 f = vcross(side, vsub(neck, p));
    f = v3((f.x >> 4) * 13 >> 8, (f.y >> 4) * 13 >> 8, (f.z >> 4) * 13 >> 8);
    int away = (f.x * c[P_HEAD].x + f.y * c[P_HEAD].y + f.z * c[P_HEAD].z) > 0;   /* its face from the camera */
    r->far = t.z > 3500;
    if (r->far) {                                  /* far: a tumbling figure */
        limb(neck, p, 26, 22, cb);
        limb(hl, c[P_LF], 10, 8, cl);
        limb(hr, c[P_RF], 10, 8, cl);
        limb(vsub(c[P_HEAD], vshr(up, 1)), vadd(c[P_HEAD], vshr(up, 1)), 15, 15, away ? hair : skin);
        return;
    }
    limb(hl, c[P_LK], 11, 10, cl);
    limb(c[P_LK], c[P_LF], 10, 8, cl);
    limb(hr, c[P_RK], 11, 10, cl);
    limb(c[P_RK], c[P_RF], 10, 8, cl);
    limb(ls, c[P_LE], 9, 8, cb);
    limb(c[P_LE], c[P_LW], 8, 6, cb);
    limb(rs, c[P_RE], 9, 8, cb);
    limb(c[P_RE], c[P_RW], 8, 6, cb);
    /* the chest: a box from the shoulders to the hips, 32 deep; the faces toward the camera */
    V3 lf = vadd(ls, f), rf = vadd(rs, f), hlf = vadd(hl, f), hrf = vadd(hr, f);
    V3 lb = vsub(ls, f), rb = vsub(rs, f), hlb = vsub(hl, f), hrb = vsub(hr, f);
    V3 q[4];
    int front = (f.x * neck.x + f.y * neck.y + f.z * neck.z) < 0;
    if (front)
        q[0] = lf, q[1] = rf, q[2] = hrf, q[3] = hlf;
    else
        q[0] = lb, q[1] = rb, q[2] = hrb, q[3] = hlb;
    r_poly(q, 4, cb, -1, 0);
    if (side.x * neck.x + side.y * neck.y + side.z * neck.z < 0)
        q[0] = rf, q[1] = rb, q[2] = hrb, q[3] = hrf;
    else
        q[0] = lf, q[1] = lb, q[2] = hlb, q[3] = hlf;
    r_poly(q, 4, COLOR(body, lv ? lv - 1 : 0, fog), -1, 0);
    /* the head: hair over the top (all of it from behind), the face under it */
    V3 top = vadd(c[P_HEAD], vshr(up, 1));
    if (away) {
        limb(vsub(c[P_HEAD], vshr(up, 1)), top, 17, 17, hair);
    } else {
        limb(vadd(c[P_HEAD], vshr(up, 3)), top, 18, 18, hair);    /* (queued first: drawn last) */
        limb(vsub(c[P_HEAD], vshr(up, 1)), top, 16, 16, skin);
    }
}

void rag_draw(void)
{
    /* the faces turned to the camera are lit by the sun as a model's face turned to it is (the
       standing man and the body in the same colours, whichever way the camera looks) */
    s32 l = -((cam.m.f.x * 6553 + cam.m.f.y * 13107 + cam.m.f.z * 7372) >> 14);
    face_lv = (l + 16384) >> 13;
    if (face_lv > 3) face_lv = 3;
    if (face_lv < 0) face_lv = 0;
    for (int i = 0; i < RAG_N; i++)
        if (rags[i].state)
            draw_one(&rags[i]);
}
#endif
