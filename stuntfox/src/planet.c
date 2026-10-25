/* The planet under the map: see planet.h.

   The geometry. Under the camera the world is a plane (the streets). Higher up that plane curves away:
   a sphere of radius Re, tangent to it under the camera, centred (cam.x, -Re, cam.z). Re falls from
   infinity (flat, the city as it always was) to 5 << 16 units as the camera climbs from PL_LO to PL_HI, along a
   smooth step, so the curve comes in gradually and the picture never jumps. With u = alt / Re, the
   tangent rays (the limb) leave the nadir at an angle a with sin a = 1 / (1 + u), and an atmosphere
   of height PL_HA reaches out to sin a2 = (1 + u * PL_HA / alt) / (1 + u). The rings are polygons of
   directions (their length does not matter to the projection) round the camera's nadir. */
#include "planet.h"
#include "render.h"
#include "world.h"
#include "physics.h"
#include "settings.h"

#define PL_LO 2500                 /* the curve starts to come in */
#define PL_HI 17500                /* ... and is all there */
#define PL_HA 14000                /* the atmosphere's height */
#define NRING 24
#define ALT_B 8000                 /* below this the limb is a straight edge, one more band of the sky's: the curve in it is a few pixels */
enum { K_NONE, K_BANDS, K_HEMI, K_RINGS };   /* the sky and planet: bands only; the sky's bands down to the horizon, the disc over them
                                                (the atmosphere's cone is a hemisphere while PL_HA is not under us); the full rings */

u8 pl_cover, pl_hide;
u16 pl_on;                         /* this map's cover height (pl_set) */

typedef struct { s16 ca, sa; u16 col; } Layer;
/* what one frame's planet needs, from pl_begin to pl_draw: in the polygon pool (r_scratch), not in the keep, which is nearly full */
typedef struct {
    V3 nd, e1, e2;                 /* the world's down, x and z axes in camera space (1.14) */
    Layer lay[2];
    u8 kind, full;                 /* how the sky and planet are drawn (K_*); 0 / 1 / 2: the screen is not / is wholly inside the disc's / the atmosphere's cone */
    s16 dip;                       /* K_BANDS: the limb's sine of dip (1.14), an edge a little over its middle's */
    s32 alt, kq, qmax;             /* the height; the sag's factor (below); the farthest ground drawn, squared (units / 32) */
    s32 dmax;                      /* ... and not squared (units) */
} Fr;
static Fr *fr;
static struct {
    u8 cover;                      /* the patch stands in for the island (with a hair of hysteresis) */
    u32 t;                         /* frames, for the clouds' drift */
} pl;

static u8 map_now;

extern const u32 rtab[2048];       /* 2^31 / (2048 + i) (tables.c) */
extern const u8 pl_col[11][9][8], pl_ring[11][6], pl_sur[11][25], pl_cld[11][24], pl_rect[][4];
extern const s16 pl_sun[11][3];
extern const s8 pl_jit[11][72];
extern const u16 pl_sb[11][4][65];

extern u8 sp_map;                  /* (space.c: the level's map, for the station) */
void pl_set(int map)
{
    sp_map = map_now = map;
    pl_on = map == 9 ? 10000 : PL_COVER_ON;
}

/* camera-space directions that leave the nadir at the cone (ca = cos, sa = sin of its half angle).
   A corner outside the view's side with both its neighbours is left out: what is cut from the polygon is
   the same without it (the long edge stays outside that plane too), and the rest is far less to clip.
   What is left is mostly few enough for r_poly, which runs from fast RAM */
static void ring(const Layer *l)
{
    V3 v[NPOLYN];                                   /* (the kept corners are packed down in it, and r_polyn cuts in it: the stack is short here) */
    u8 oc[NPOLYN];
    s32 k = l->sa * 16525 >> 14;                  /* (the polygon's sides, not its corners, are on the cone) */
    V3 b = vscale(fr->nd, l->ca), p = vscale(fr->e1, k), q = vscale(fr->e2, k);
    const s32 fl = FOCAL, H = NRING / 2;
    for (int i = 0; i < H; i++) {                 /* (the far half of the ring mirrors the near half through b) */
        s32 c = fcos(i * (ANG_TURN / NRING)), s = fsin(i * (ANG_TURN / NRING));
        s32 ux = (p.x * c + q.x * s) >> 14, uy = (p.y * c + q.y * s) >> 14, uz = (p.z * c + q.z * s) >> 14;
        v[i] = v3(b.x + ux, b.y + uy, b.z + uz);
        v[i + H] = v3(b.x - ux, b.y - uy, b.z - uz);
    }
    int all = 0x1f;
    for (int i = 0; i < NRING; i++)
        all &= oc[i] = r_ocode(&v[i], fl);
    if (all)
        return;                                   /* (all of it outside one plane) */
    int n = 1, last = 0;
    for (int i = 1; i < NRING; i++) {
        if (i < NRING - 1 && (oc[last] & oc[i] & oc[i + 1]))
            continue;
        oc[n] = oc[i];
        v[n++] = v[i];
        last = i;
    }
    if (n < 10)
        r_poly(v, n, 0x100 | l->col, 0, 1);
    else
        r_polyn(v, oc, n, 0x100 | l->col, 1);
}

/* is the whole screen inside the cone? (its four corner rays are) */
static int covers(const V3 *nd, s16 ca)
{
    s32 f = FOCAL, len = (s32)isqrt(120 * 120 + 80 * 80 + f * f);
    s32 lim = (ca + 300) * len;
    for (int i = 0; i < 4; i++) {
        s32 x = i & 1 ? 120 : -120, y = i & 2 ? 80 : -80;
        if (nd->x * x + nd->y * y + nd->z * f < lim)
            return 0;
    }
    return 1;
}

int pl_begin(s32 alt)
{
    fr = 0;
    pl_cover = 0;
    if (pl_hide || !opt_planet)
        return 0;
    if (alt < pl_on - (PL_COVER_ON - PL_COVER_OFF))
        pl.cover = 0;
    else if (alt >= pl_on)
        pl.cover = 1;
    pl_cover = pl.cover;                                    /* (also looking away: nothing of the ground is in view then) */
    s32 x = alt <= PL_LO ? 0 : alt >= PL_HI ? 1024 : (alt - PL_LO) * 1024 / (PL_HI - PL_LO);
    s32 w = (s32)((u32)x * x * (3072 - 2 * x) >> 20);       /* how far the curve is in, 0 .. 1024: a smooth step */
    if (w < 12)
        return 0;                                           /* (a degree of dip: the city hides it) */
    s32 U = alt * w / 5120, UH = PL_HA * w / 5120;
    if (U > 25000) U = 25000;                               /* (U * (131072 + U) below must fit 32 bits) */
    s32 sa = (1 << 30) / (65536 + U);                       /* sin of the limb's angle from the nadir, 1.14 */
    s32 ca = (s32)((u32)isqrt((u32)U * (131072 + U)) * sa >> 16);
    s32 sa2 = (sa * (65536 + UH)) >> 16, ca2 = 0;
    if (sa2 >= ONE)
        sa2 = ONE;
    else
        ca2 = (s32)isqrt(ONE * ONE - sa2 * sa2);
    V3 nd = v3(-cam.m.r.y, -cam.m.u.y, -cam.m.f.y);
    /* in sight at all? the nadir is within the atmosphere's angle plus the view's half diagonal (47 degrees) of the way we look */
    if (nd.z < (ca2 * 11174 - sa2 * 11983) >> 14)
        return 0;
    Fr *f = r_scratch(sizeof *f);
    if (!f) {
        pl_cover = 0;                                       /* (the pool is full: the flat sky and the island, as ever) */
        return 0;
    }
    f->alt = alt;
    f->nd = nd;
    f->e1 = v3(cam.m.r.x, cam.m.u.x, cam.m.f.x);
    f->e2 = v3(cam.m.r.z, cam.m.u.z, cam.m.f.z);
    const u8 *rc = pl_ring[map_now];
    f->lay[0] = (Layer){ca2, sa2, rc[0]};
    f->lay[1] = (Layer){ca, sa, rc[2]};
    f->full = covers(&nd, ca) ? 1 : alt > PL_HA && covers(&nd, ca2) ? 2 : 0;
    f->kind = alt < ALT_B ? K_BANDS : alt <= PL_HA ? K_HEMI : K_RINGS;
    f->dip = ca * 18350 >> 14;                              /* (the edge's pixels are farther than the middle's: 1.12 of the sine) */
    if (pl.cover) {
        /* the ground: sag = d^2 / 2 Re, in units of 1024 squared; the horizon it ends at, a little short of the limb */
        f->kq = U * 4096 / alt;
        s32 dt = (alt * (s32)isqrt((u32)((131072 << 8) / U)) >> 4) * 15 >> 4;
        f->dmax = dt * 15 >> 4;
        f->qmax = (dt >> 5) * (dt >> 5);
    }
    fr = f;
    return 1;
}

/* what drawing the ground needs, copied to the stack (the fast RAM) from the frame's record and the camera */
typedef struct { V3 e1, nd, e2; s32 alt, kq, qmax, dmax, cx, cz, t1; const s16 *sun; } Ctx;

/* a ground point (units) in camera space, its height a little over the ground (lift); the point is
   drawn no farther than the horizon (a radial clamp keeps the patches' edges shared). 1: it was clamped */
static int gv(const Ctx *c, V3 *o, s32 X, s32 Z, s32 lift)
{
    s32 dx = X - c->cx, dz = Z - c->cz;
    s32 q = (dx >> 5) * (dx >> 5) + (dz >> 5) * (dz >> 5);
    int cl = 0;
    if (q > c->qmax) {
        /* (a length from the larger and smaller sides: a few percent out, and no root to take) */
        s32 ax = dx < 0 ? -dx : dx, az = dz < 0 ? -dz : dz, d = ax > az ? ax + (az >> 2) + (az >> 3) : az + (ax >> 2) + (ax >> 3);
        /* f = (dmax / 32) << 12 / (d / 32), by the reciprocal table (a division is a slow BIOS call) */
        u32 zn = (u32)(d >> 5) | 1;
        int e = 0;
        while (zn < 2048) zn <<= 1, e++;
        while (zn >= 4096) zn >>= 1, e--;
        s32 f = ((c->dmax >> 5) * (s32)(rtab[zn - 2048] >> 5)) >> (14 - e);
        dx = ((dx >> 4) * f) >> 8;
        dz = ((dz >> 4) * f) >> 8;
        q = c->qmax;
        cl = 1;
    }
    s32 h = c->alt - lift + (((q >> 9) * c->kq) >> 10);
    dx >>= 3, dz >>= 3, h >>= 3;
    o->x = (c->e1.x * dx + c->nd.x * h + c->e2.x * dz) >> 14;
    o->y = (c->e1.y * dx + c->nd.y * h + c->e2.y * dz) >> 14;
    o->z = (c->e1.z * dx + c->nd.z * h + c->e2.z * dz) >> 14;
    return cl;
}

/* the row of colours for ground at (X, Z), q its squared distance (units / 32) from the camera: by how hazy it is, 0 under
   us .. 2 where the patch gives out (t1: about three heights out), and by the sun, day, dusk (45 cells wide) and night, past a line over the planet */
static int row(const Ctx *c, s32 X, s32 Z, s32 q)
{
    s32 d = ((((X >> 10) - 64) * c->sun[0] + ((Z >> 10) - 64) * c->sun[1]) >> 7) - c->sun[2];
    return (q * 2 < c->t1 ? (q * 6 < c->t1 ? 0 : 1) : 2) + (d < 0 ? 0 : d < 45 ? 3 : 6);
}

/* The map's own ground is drawn on a lattice of 8-cell steps (17 lines each way). The sag is a sum of a part of x
   and a part of z, and the rest is linear, so a lattice point's camera-space place is the sum of two vectors, one
   per column and one per row: found once per line, a point costs three adds. Nearer than a point's own horizon only
   (qm): past it the radial clamp (gv) is needed. */
typedef struct {
    const Ctx *c;
    s16 pc[17][3], pr[17][3];      /* a column's and a row's vector (the row's holds the height as well) */
    s16 ar[17], al[17], br[17], bl[17];   /* the view's right and left sides' distance (/ 256) of a column's and a row's vector: a point's is their sum */
    u16 qx[17], qz[17];            /* the squared distance's parts, in units / 32 squared / 512 */
    s32 qm, t1;                    /* qmax / 512; the patch's reach (c->t1) / 512 */
    u32 ux, uz;                    /* the columns' and rows' lines that are worked out (a square within reach needs its three) */
} Lat;

/* mode 2: every second line (the merged blocks' corners), all of them. Else only the lines of squares within the patch's reach: all
   of them (mode 0), or every second (mode 1: blocks of 16 cells). The squares' distances (qx, qz) are always worked out */
static void lat(Lat *L, const Ctx *c, int mode)
{
    L->c = c;
    L->qm = c->qmax >> 9;
    L->t1 = c->t1 >> 9;
    L->ux = L->uz = 0;
    const s32 fl = FOCAL;
    const int step = mode == 2 ? 2 : 1;
    for (int k = 0; k < 17; k += step) {
        s32 dx = (k << 13) - c->cx, dz = (k << 13) - c->cz;
        u32 qx = (u32)((dx >> 5) * (dx >> 5)) >> 9, qz = (u32)((dz >> 5) * (dz >> 5)) >> 9;
        L->qx[k] = qx > 65535 ? 65535 : qx;
        L->qz[k] = qz > 65535 ? 65535 : qz;
        if (mode == 2)
            L->ux |= 1u << k, L->uz |= 1u << k;
        else if (k & 1) {                                   /* (a square's middle line: its distance is the sum of the two) */
            u32 mk = mode ? 5u : 7u;
            if (qx < L->t1)
                L->ux |= mk << (k - 1);
            if (qz < L->t1)
                L->uz |= mk << (k - 1);
        }
    }
    for (int k = 0; k < 17; k += mode ? 2 : 1) {
        if (L->ux >> k & 1) {
            s32 dx = (k << 13) - c->cx;
            u32 qx = (u32)((dx >> 5) * (dx >> 5)) >> 9;
            s32 hx = (s32)(qx * c->kq >> 10) >> 3;
            dx >>= 3;
            L->pc[k][0] = (c->e1.x * dx + c->nd.x * hx) >> 14;
            L->pc[k][1] = (c->e1.y * dx + c->nd.y * hx) >> 14;
            L->pc[k][2] = (c->e1.z * dx + c->nd.z * hx) >> 14;
            L->ar[k] = (121 * L->pc[k][2] - fl * L->pc[k][0]) >> 8;
            L->al[k] = (121 * L->pc[k][2] + fl * L->pc[k][0]) >> 8;
        }
        if (L->uz >> k & 1) {
            s32 dz = (k << 13) - c->cz;
            u32 qz = (u32)((dz >> 5) * (dz >> 5)) >> 9;
            s32 hz = ((s32)(qz * c->kq >> 10) + c->alt) >> 3;
            dz >>= 3;
            L->pr[k][0] = (c->e2.x * dz + c->nd.x * hz) >> 14;
            L->pr[k][1] = (c->e2.y * dz + c->nd.y * hz) >> 14;
            L->pr[k][2] = (c->e2.z * dz + c->nd.z * hz) >> 14;
            L->br[k] = (121 * L->pr[k][2] - fl * L->pr[k][0]) >> 8;
            L->bl[k] = (121 * L->pr[k][2] + fl * L->pr[k][0]) >> 8;
        }
    }
}

/* lattice point (i, j) in camera space; 1: it was clamped to the horizon */
static inline int lv(const Lat *L, V3 *o, int i, int j)
{
    if (L->qx[i] + L->qz[j] > L->qm)
        return gv(L->c, o, i << 13, j << 13, 0);
    o->x = L->pc[i][0] + L->pr[j][0];
    o->y = L->pc[i][1] + L->pr[j][1];
    o->z = L->pc[i][2] + L->pr[j][2];
    return 0;
}

static inline s32 mx(s32 a, s32 b) { return a > b ? a : b; }

/* is the rectangle of the lattice (i0, j0) .. (i1, j1) wholly behind us or out at the view's right or left? Only
   judged where none of it is near the horizon: its clamped points are not where these sums put them */
static inline int off(const Lat *L, int i0, int j0, int i1, int j1)
{
    if (mx(L->qx[i0], L->qx[i1]) + mx(L->qz[j0], L->qz[j1]) > L->qm)
        return 0;
    return mx(L->pc[i0][2], L->pc[i1][2]) + mx(L->pr[j0][2], L->pr[j1][2]) < NEAR ||
           mx(L->ar[i0], L->ar[i1]) + mx(L->br[j0], L->br[j1]) < -2 || mx(L->al[i0], L->al[i1]) + mx(L->bl[j0], L->bl[j1]) < -2;
}

/* a rectangle of the lattice: r3 is its class (bits 0-2) and the sun's side at its middle (day, dusk, night), the haze from how far */
static void lq(const Lat *L, int m, int i0, int j0, int i1, int j1, int r3)
{
    if (off(L, i0, j0, i1, j1))
        return;
    V3 v[4];
    int c = lv(L, &v[0], i0, j0);
    c &= lv(L, &v[1], i1, j0);
    c &= lv(L, &v[2], i1, j1);
    c &= lv(L, &v[3], i0, j1);
    if (c)
        return;
    s32 q = (L->qx[i0] + L->qx[i1] + L->qz[j0] + L->qz[j1]) >> 1;
    r_poly(v, 4, 0x100 | pl_col[m][(q * 2 < L->t1 ? (q * 6 < L->t1 ? 0 : 1) : 2) + 3 * (r3 >> 3)][r3 & 7], 0, 1);
}

/* the rest of the planet round the map: 8 tiles of a lattice of 128-cell steps, corners nudged (jit); farther
   out is past the horizon of anything we fly to. Which corners are on the horizon is told before any is worked out
   (gv clamps them, with a division): a tile all of whose corners are is not there. xc: the corners' cells, x then z */
static void surround(const Ctx *c, V3 *sv, s16 *xc)
{
    const int m = map_now;
    const s8 *jt = pl_jit[m];
    u32 on = 0, done = 0;
    for (int n = 0; n < 16; n++) {
        int i = (n & 3) + 1, j = (n >> 2) + 1;
        s32 X = (i - 2) * 128 + jt[2 * (j * 6 + i)], Z = (j - 2) * 128 + jt[2 * (j * 6 + i) + 1];
        xc[n] = X, xc[16 + n] = Z;
        s32 dx = ((X << 10) - c->cx) >> 5, dz = ((Z << 10) - c->cz) >> 5;
        if (dx * dx + dz * dz > c->qmax)
            on |= 1u << n;
    }
    for (int tz = 1; tz < 4; tz++)
        for (int tx = 1; tx < 4; tx++) {
            if (tx == 2 && tz == 2)
                continue;
            int ix[4] = {(tz - 1) * 4 + tx - 1, (tz - 1) * 4 + tx, tz * 4 + tx, tz * 4 + tx - 1};   /* (its corners in turn) */
            u32 mk = 1u << ix[0] | 1u << ix[1] | 1u << ix[2] | 1u << ix[3];
            if ((on & mk) == mk)
                continue;
            for (int k = 0; k < 4; k++)
                if (!(done >> ix[k] & 1)) {
                    done |= 1u << ix[k];
                    gv(c, &sv[ix[k]], xc[ix[k]] << 10, xc[16 + ix[k]] << 10, 0);
                }
            s32 mx = (xc[ix[0]] + xc[ix[1]] + xc[ix[2]] + xc[ix[3]]) << 8, mz = (xc[16 + ix[0]] + xc[16 + ix[1]] + xc[16 + ix[2]] + xc[16 + ix[3]]) << 8;
            s32 dx = (mx - c->cx) >> 5, dz = (mz - c->cz) >> 5;
            V3 v[4] = {sv[ix[0]], sv[ix[1]], sv[ix[2]], sv[ix[3]]};
            r_poly(v, 4, 0x100 | pl_col[m][row(c, mx, mz, dx * dx + dz * dz)][pl_sur[m][tz * 5 + tx]], 0, 1);
        }
}

static void patch(const Ctx *c)
{
    const int m = map_now;
    struct { Lat l; V3 sv[16]; s16 xc[32]; } *B = r_scratch(sizeof *B);       /* (the pool's, not the stack's: see r_scratch) */
    if (!B)
        return;
    Lat *L = &B->l;
    const int hi = c->alt >= 22000;
    /* (while the city is still drawn, over the patch, its fine blocks near us are not seen: 16 cells blocks only) */
    const int fine = c->alt >= PL_CITY_OFF;
    lat(L, c, hi ? 2 : !fine);
    surround(c, B->sv, B->xc);
    /* the map's rectangles. From 22000 up the 16-cell blocks merged across the map, looked at one at a time (all of it
       is in reach); lower, the squares within reach (three heights, c->t1, where the haze has taken the ground's own
       colour for the disc's), finer the nearer */
    const s32 far = ((c->dmax + 16000) >> 5) * ((c->dmax + 16000) >> 5) >> 9;
    if (hi) {
        const u16 *sb = pl_sb[m][3];
        for (int i = sb[0]; i < sb[1]; i++) {
            const u8 *r = pl_rect[i];
            int i0 = r[0] << 1, j0 = r[1] << 1, i1 = i0 + ((r[2] >> 4) << 1), j1 = j0 + ((r[2] & 15) << 1);
            if (((L->qx[i0] + L->qx[i1] + L->qz[j0] + L->qz[j1]) >> 1) > far)
                continue;
            lq(L, m, i0, j0, i1, j1, r[3]);
        }
        return;
    }
    s32 a = c->alt >> 5, t0 = (a * 13 / 10 * (a * 13 / 10)) >> 9;
    for (int sz = 0; sz < 8; sz++) {
        int sj = sz * 2;
        if (L->qz[sj + 1] >= L->t1)
            continue;
        for (int sx = 0; sx < 8; sx++) {
            int si = sx * 2;
            s32 q = L->qx[si + 1] + L->qz[sj + 1];
            if (q >= L->t1 || off(L, si, sj, si + 2, sj + 2))
                continue;
            int lod = fine && q < t0 ? 1 : 2, sh = lod - 1;           /* (a block of 8 or 16 cells: 1 or 2 lattice steps) */
            const u16 *sb = &pl_sb[m][lod][sz * 8 + sx];
            for (int i = sb[0], e = sb[1]; i < e; i++) {
                const u8 *r = pl_rect[i];
                int i0 = r[0] << sh, j0 = r[1] << sh;
                lq(L, m, i0, j0, i0 + ((r[2] >> 4) << sh), j0 + ((r[2] & 15) << sh), r[3]);
            }
        }
    }
}

/* a few slow clouds, a little over the ground, drifting east a cell in 16 frames */
static void clouds(const Ctx *c)
{
    static const s8 hx[6] = {16, 8, -8, -16, -8, 8}, hz[6] = {0, 14, 14, 0, -14, -14};
    const u8 *cd = pl_cld[map_now];
    for (int i = 0; i < 4; i++, cd += 3) {
        s32 X = (((cd[0] + (pl.t >> 4)) & 255) - 64) << 10, Z = ((cd[1] & 255) - 64) << 10, r = cd[2] << 5;
        s32 dx = (X - c->cx) >> 5, dz = (Z - c->cz) >> 5;
        if (dx * dx + dz * dz > c->qmax)
            continue;
        V3 v[6];
        for (int k = 0; k < 6; k++)
            gv(c, &v[k], X + (hx[k] * r >> 4), Z + (hz[k] * r >> 4), 700);
        s32 d = ((((X >> 10) - 64) * c->sun[0] + ((Z >> 10) - 64) * c->sun[1]) >> 7) - c->sun[2];
        r_poly(v, 6, 0x100 | pl_ring[map_now][d < 0 ? 3 : d < 45 ? 4 : 5], 0, 1);
    }
}

void pl_draw(const u16 *cols, const s32 *bounds)
{
    static const s32 rect[8] = {0, 0, 3840, 0, 3840, 2560, 0, 2560};
    u16 sc[7];
    s32 sb[6];
    int k;
    const Fr *f = fr;
    if (!f)
        return;
    for (k = 0; k < 5; k++)
        sc[k] = cols[k], sb[k] = bounds[k];
    sc[5] = 0x100 | f->lay[0].col, sc[6] = 0x100 | f->lay[1].col;
    if (f->kind == K_BANDS) {
        sb[5] = -f->dip;
        r_sky(sc, sb, 7, 7);
        return;
    }
    if (f->full == 1)
        r_poly2d(rect, 4, sc[6], 0, 1);                  /* (the screen is inside the disc: all of it) */
    else {
        if (f->kind == K_HEMI)
            r_sky(sc, sb, 6, 6);                          /* (the atmosphere below the horizon) */
        else if (f->full == 2)
            r_poly2d(rect, 4, sc[5], 0, 1);
        else {
            /* the sky only down to where the atmosphere's cone takes over (its ring covers all inside the cone, a hair of overlap kept): the
               last band no longer runs under the whole planet */
            sb[4] = -f->lay[0].ca - 164;
            r_sky(sc, sb, 6, 5);
            ring(&f->lay[0]);
        }
        ring(&f->lay[1]);
    }
    if (!pl.cover)
        return;
    pl.t++;
    s32 a = f->alt >> 5;
    Ctx c = {f->e1, f->nd, f->e2, f->alt, f->kq, f->qmax, f->dmax, cam.pos.x, cam.pos.z, a * 3 * a * 3, pl_sun[map_now]};
    patch(&c);
    if (f->alt > 14000 && f->alt < 30000)
        clouds(&c);
}

s32 pl_drop_alt(int t, s32 pad_alt)
{
    if (t < 0) t = 0;
    if (t > 256) t = 256;
    s32 g = 65536 - ((t * t * (768 - 2 * t)) >> 8);         /* 1 - smooth step, 16 bits */
    return pad_alt + (s32)(((s64)(34000 - pad_alt) * g) >> 16);
}
