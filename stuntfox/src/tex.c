/* Payback's tiles on the ground, roofs and walls (MERGE build). See tex.h.

   The ground: every screen row of a flat ground lies at one depth (unless the camera rolls),
   so where the ground is along each row is worked out once a frame, at both ends of the row.
   When the camera rolls (the Arwing banking), depth changes along a row, so the ground is
   worked out at SEGS + 1 points along it instead and each piece in between is stepped on
   its own; a piece with an end past the horizon or too far away is drawn flat.
   A span then walks across the city cells it covers, a tile for each. Roofs reuse the same
   rows: a plane h units up is the ground scaled toward the camera.

   Walls are drawn in columns two pixels wide. The texture position at the top and bottom of
   each column comes from the wall's plane (u / w, v / w with u, v, w linear on screen) and is
   stepped linearly in between. */
#include "gba.h"
#include "render.h"
#include "world.h"
#include "palette.h"
#include "tex.h"

#ifdef MERGE

extern const u32 rtab[2048];                /* 2^31 / (2048 + i) */
extern const u32 erecip[2561];              /* 2^24 / i */
void tex_hrun(u8 *dst, int n, u32 uv, u32 duv, const u8 *tile, int row2);
void tex_hrun4(u8 *dst, int n, u32 uv, u32 duv, const u8 *tile, int row2);
void tex_vrun(u8 *dst, int n, u32 uv, u32 duv, const u8 *tile, const u8 *lut, int row2);
void tex_vrun4(u8 *dst, int n, u32 uv, u32 duv, const u8 *tile, const u8 *lut);
void tex_mrun(u8 *dst, int n, u32 uv, u32 duv, const u8 *mip, int row2, u32 lv);
void tex_mrun1(u8 *dst, int n, u32 uv, u32 duv, const u8 *mip, int row2);

/* per pair of screen rows: the ground under the left pixel (units * 256), its step per pixel,
   2^30 / the step per texel (two pixels), and how far the rows reach (units, 0: no ground) */
static u32 gix[80] SCRATCH2, giz[80] SCRATCH2;
static s32 gfar[80] EWRAM_BSS;
static s32 camx8, camz8, camy;
/* the camera's height over the plane the rows below are found on: the street's, or with the
   camera under the street (swimming in a canal, in a sunken yard) a plane 1024 under it, so
   the floors down there still get their tiles (the street over it is not seen from below) */
static s32 camh;
#define SEGS 6                               /* pieces of a row when rolled, 40 pixels each */
#define NOGROUND (-32768)
/* when rolled: the ground at each piece's ends, units from the camera (NOGROUND: none) */
/* (a frame uses one set or the other) */
static union {
    struct { s32 x[80], z[80], dx[80], dz[80]; } level;
    struct { s16 x[80][SEGS + 1], z[80][SEGS + 1]; } rolled;
} gt EWRAM_BSS;
#define gx gt.level.x
#define gz gt.level.z
#define gdx gt.level.dx
#define gdz gt.level.dz
#define sgx gt.rolled.x
#define sgz gt.rolled.z
static int rolled;
static const u16 *tex_tab;         /* the floor being drawn: its cells' tile ids (its TexFloor's) */
int tex_on;
/* what nearer walls hide (see tex_occlude) */
static u32 cov[110] SCRATCH;
#define cov_top ((u8 *)cov)
#define cov_bot ((u8 *)cov + 120)
#define cov_l ((u8 *)cov + 240)
#define cov_r ((u8 *)cov + 320)
u8 tex_bg;

/* a texture position and a step (texels, 16.16) as packed words (see texrun.s) */
#define PACK(s, t) ((((u32)(s) << 11) & 0xffff0000u) | (((u32)(t) >> 5) & 0xffff))
#define PSTEP(ds, dt) ((((u32)(ds) << 11) & 0xffff0000u) + (u32)((s32)(dt) >> 5))

/* far off or high up a pair of pixels steps over more than a texel, and a texel picked for each
   pair speckles and shimmers: a pair stepping MIP_STEP or more (units * 256: one and a half
   texels; from higher up, where everything slides by faster, less) takes the tile's averages
   over 2 x 2 texels, twice that over 4 x 4, four times over 8 x 8 (pb_mip, by tools/mkmip.py:
   rows of 16, 8 and 4). Rows stepping more than MIP_FLAT are drawn flat, as if past TEX_FAR
   (Payback's average colours). Above 6000 that limit falls with height, to 1.6 texels at
   TEX_TOP where the tiles stop: less than any roof steps there (the tallest are 8192 high), so
   the tiles have faded out row by row, coarsest first, before then. */
#define MIP_STEP 12288
#define MIP_FLAT (4 * MIP_STEP)
extern const u8 pb_mip[][336];
extern const u16 pb_mipof[TEX_IDS];

/* Payback's tile id -> its texels (where Payback keeps it), or 0 */
#define TILE(id) ({ unsigned id_ = (id); const u8 *p_ = id_ < TEX_IDS ? PB_TEXTAB[id_] : 0; \
    u32 a_ = (u32)p_ >> 24; a_ == 8 || a_ == 6 || a_ == 3 || a_ == 2 ? p_ : (const u8 *)0; })

/* (s32)(v >> k) for 0 <= k < 64 (no runtime helper for a variable 64-bit shift; macros, as
   the ARM code in IWRAM cannot inline Thumb functions) */
#define SHR64(v, k) ({ s64 sv_ = (v); int sk_ = (k); s32 hi_ = (s32)(sv_ >> 32); u32 lo_ = (u32)sv_; \
    sk_ >= 32 ? hi_ >> (sk_ - 32) : sk_ ? (s32)(lo_ >> sk_ | (u32)hi_ << (32 - sk_)) : (s32)lo_; })

/* 1 / v for v > 0, as r / 2^(31 + e) */
HOT2 static u32 recip(u32 v, int *e)
{
    int s = 0;
    if (v >= 1u << 27) v >>= 16, s += 16;
    if (v >= 1u << 19) v >>= 8, s += 8;
    if (v >= 1u << 15) v >>= 4, s += 4;
    while (v >= 4096) v >>= 1, s++;
    while (v < 2048) v <<= 1, s--;
    *e = s;
    return rtab[v - 2048];
}

/* a * 2^sh / w */
HOT2 static s32 divq(s32 a, s32 w, int sh)
{
    if (w < 0)
        w = -w, a = -a;
    if (!w)
        return 0;
    int e;
    u32 r = recip(w, &e);
    int k = 31 + e - sh;
    s64 p = (s64)a * (s32)r;                /* (r < 2^21) */
    return k >= 0 ? SHR64(p, k) : (s32)p << -k;
}

HOT8 static u32 inv30(s32 v)                /* 2^30 / |v|, |v| at least 16 */
{
    if (v < 0) v = -v;
    if (v < 16) v = 16;
    int e;
    u32 r = recip(v, &e);
    return e + 1 >= 0 ? r >> (e + 1) : r << -(e + 1);
}

const u8 *tex_tile(int id)
{
    return TILE(id);
}

HOT4 void tex_frame(void)
{
    camx8 = cam.pos.x << 8;
    camz8 = cam.pos.z << 8;
    camy = cam.pos.y;
    camh = camy >= 16 ? camy : 1024;
    V3 r = cam.m.r, u = cam.m.u, f = cam.m.f;
    int on = tex_on && camy <= TEX_TOP;
    rolled = r.y > 600 || r.y < -600;      /* (two degrees: below that a row barely changes depth) */
#pragma clang loop unroll(disable)
    for (int j = 0; j < 80; j++)
        gfar[j] = 0;
    if (!on)
        return;
    /* a row's step a pair -> as far as TEX_FAR at the limit: * kf / 65536 */
    s32 kf = divq(TEX_FAR, camy <= 6000 ? MIP_FLAT : MIP_FLAT - (camy - 6000) * ((MIP_FLAT - 13107) / (TEX_TOP - 6000)), 16);
    /* rays through the row pair's pixels, doubled (>> 9 below): the ray through the top row's
       left end, stepped by adds along the row (from end to end) and down the rows */
    int np = rolled ? SEGS + 1 : 2;
    s32 cs = rolled ? 80 : 478;
    s32 bx = 158 * u.x + 2 * FOCAL * f.x - 239 * r.x, by = 158 * u.y + 2 * FOCAL * f.y - 239 * r.y,
        bz = 158 * u.z + 2 * FOCAL * f.z - 239 * r.z;
    s32 ex = cs * r.x, ey = cs * r.y, ez = cs * r.z;
    /* with the camera upright the rays rise up the screen: from the bottom row up, once a whole
       row is above the horizon so are all the rows above it */
    int up = u.y > 0, j = up ? 79 : 0, dj = up ? -1 : 1;
    bx -= j * 4 * u.x, by -= j * 4 * u.y, bz -= j * 4 * u.z;
    s32 sx = dj * 4 * u.x, sy = dj * 4 * u.y, sz = dj * 4 * u.z;
    for (; (unsigned)j < 80; j += dj, bx -= sx, by -= sy, bz -= sz) {
        s32 xo[SEGS + 1], zo[SEGS + 1], fa[SEGS + 1], near = 0x7fffffff, sky = 1;
        s32 ax = bx, ay = by, az = bz, lndy = 0;
        u32 inv = 0;
        int e = 0;
        for (int end = 0; end < np; end++, ax += ex, ay += ey, az += ez) {
            s32 dx = ax >> 9, ndy = -(ay >> 9), dz = az >> 9;
            s32 adx = dx < 0 ? -dx : dx, adz = dz < 0 ? -dz : dz, m = adx > adz ? adx : adz;
            fa[end] = 0;
            xo[end] = zo[end] = 0;
            if (ndy <= 0)
                continue;
            sky = 0;
            if (camh * m >= ndy * 16000)
                continue;                   /* past the horizon or out of reach */
            if (ndy != lndy)
                inv = recip(ndy, &e), lndy = ndy;   /* 1 / ndy = inv / 2^(31 + e), inv < 2^21 */
            s32 t = (s32)(camh * (inv >> 5)), sh = 10 + e;   /* t >> sh: camh * 65536 / ndy */
            t = sh >= 0 ? t >> sh : t << -sh;
            xo[end] = (dx * t) >> 8;        /* (|dx * t| < 2^30: rays reach at most 16000 units) */
            zo[end] = (dz * t) >> 8;
            fa[end] = ((m * t) >> 16) + 1;
            if (fa[end] < near) near = fa[end];
        }
        if (sky && up)
            break;
        /* a row stepping past the limit a pair is as far as one reaching TEX_FAR (rolled: if all
           its pieces do; each piece is checked again for TEX_FAR, not for this) */
        if (rolled) {
            s32 st = 0x7fffffff;
            for (int i = 0; i < np; i++) {
                sgx[j][i] = fa[i] ? xo[i] >> 8 : NOGROUND;
                sgz[j][i] = zo[i] >> 8;
                if (i && fa[i] && fa[i - 1]) {
                    s32 a = xo[i] - xo[i - 1], b = zo[i] - zo[i - 1];
                    a = a < 0 ? -a : a, b = b < 0 ? -b : b;
                    if (b > a) a = b;
                    if (a < st) st = a;
                }
            }
            gfar[j] = near == 0x7fffffff ? 0 : near;   /* (each piece is checked again) */
            st = st == 0x7fffffff ? 0 : (s32)(((s64)st * kf * 3277) >> 32);   /* (a pair: 1 / 20 of a piece) */
            if (gfar[j] && st > gfar[j])
                gfar[j] = st;
            continue;
        }
        if (!fa[0] || !fa[1])
            continue;
        gx[j] = camx8 + xo[0];
        gz[j] = camz8 + zo[0];
        gdx[j] = (((xo[1] - xo[0]) >> 6) * 17549) >> 16;   /* / 239 */
        gdz[j] = (((zo[1] - zo[0]) >> 6) * 17549) >> 16;
        gix[j] = inv30(2 * gdx[j]);
        giz[j] = inv30(2 * gdz[j]);
        gfar[j] = fa[0] > fa[1] ? fa[0] : fa[1];
        s32 a = gdx[j] < 0 ? -gdx[j] : gdx[j], b = gdz[j] < 0 ? -gdz[j] : gdz[j];
        a = (s32)(((s64)(a > b ? a : b) * 2 * kf) >> 16);
        if (a > gfar[j])
            gfar[j] = a;
    }
}

void tex_floor(TexFloor *fl, s32 h)
{
    fl->tab = world.ctex;
    s32 k = camy <= h + 16 ? 1024 : divq(camy - h, camh, 16);   /* (not drawn from below) */
    if (k < 1024)
        k = 1024;
    fl->k = k;
    fl->kinv = divq(65536, k, 16);
}


/* n pairs of pixels of one colour, on this row and row2 bytes further */
static inline __attribute__((target("arm"))) void flat_pairs(u8 *d, int n, int color, int row2)
{
    u16 c = color | color << 8;
    for (; n > 0; n--, d += 2) {
        *(u16 *)(d + row2) = c;
        *(u16 *)d = c;
    }
}

/* n pixel pairs of a floor from d, the ground under the first at X, Z (units * 256, already
   scaled for the floor's height), stepping dX, dZ a pair; ix, iz: 2^30 / |dX|, |dZ| */
HOT __attribute__((noinline)) static void tex_walk(u8 *d, int n, s32 X, s32 Z, s32 dX, s32 dZ, u32 ix, u32 iz, int row2, int color)
{
    u32 duv = PSTEP(dX << 3, dZ << 3);        /* units * 256 -> texels 16.16: * 8 */
    /* close up, a texel covers many pixels: one sample for every four */
    int quad = dX < 0x1000 && dX > -0x1000 && dZ < 0x1000 && dZ > -0x1000;
    /* far off, the level of the tile's averages (see MIP_STEP; from 9000 up, at half the step) */
    int lv = 0;
    s32 ms = MIP_STEP - (camy < 3000 ? 0 : camy > 9000 ? 6000 : camy - 3000);
    for (s32 a = dX < 0 ? -dX : dX, b = dZ < 0 ? -dZ : dZ, c = a > b ? a : b; c >= ms && lv < 3; c >>= 1)
        lv++;
    /* a texel of them from the same texture position: its column at bit 27 + lv, its row (32 >> lv
       texels long) at bit 11 + lv */
    u32 mlv = ((32u >> lv) - 1) << (5 - lv) | (6 + 2 * lv) << 16 | (u32)(27 + lv) << 24;
    int moff = lv == 1 ? 0 : lv == 2 ? 256 : 320;
    while (n > 0) {
        int cx = X >> 18, cz = Z >> 18;
        if ((unsigned)cx >= CITY || (unsigned)cz >= CITY) {
            flat_pairs(d, n, color, row2);
            return;
        }
        int m = n;
        if (dX) {
            u32 dist = dX > 0 ? (u32)(((cx + 1) << 18) - X) : (u32)(X - (cx << 18) + 1);
            int t = (int)(((u64)dist * ix) >> 30) + 1;
            if (t < m) m = t;
        }
        if (dZ) {
            u32 dist = dZ > 0 ? (u32)(((cz + 1) << 18) - Z) : (u32)(Z - (cz << 18) + 1);
            int t = (int)(((u64)dist * iz) >> 30) + 1;
            if (t < m) m = t;
        }
        int i = cx * CITY + cz;
        unsigned id = tex_tab[i];
        const u8 *tile = TILE(id);
        if (tile && lv && pb_mipof[id]) {
            const u8 *mt = pb_mip[pb_mipof[id] - 1] + moff;
            if (lv == 1)
                tex_mrun1(d, m, PACK(X << 3, Z << 3), duv, mt, row2);
            else
                tex_mrun(d, m, PACK(X << 3, Z << 3), duv, mt, row2, mlv);
        } else if (tile && quad && m >= 3) {
            u32 uv = PACK(X << 3, Z << 3);
            u8 *e = d;
            int k = m;
            if ((u32)e & 2) {
                tex_hrun(e, 1, uv, duv, tile, row2);
                e += 2, uv += duv, k--;
            }
            tex_hrun4(e, k >> 1, uv, duv << 1, tile, row2);
            if (k & 1)
                tex_hrun(e + 4 * (k >> 1), 1, uv + (k - 1) * duv, duv, tile, row2);
        } else if (tile)
            tex_hrun(d, m, PACK(X << 3, Z << 3), duv, tile, row2);
        else
            flat_pairs(d, m, pb_pmap[COLOR(world.cell[i].mat, 2, 0)], row2);
        d += 2 * m;
        X += m * dX;
        Z += m * dZ;
        n -= m;
    }
}


/* tex_hspan with the camera rolled: piece by piece, 20 pairs each */
HOT6 static void tex_hspan_rolled(u8 *row, int j, int p0, int n, const TexFloor *fl, int row2, int color)
{
    while (n > 0) {
        int sg = (p0 * 3277) >> 16, m = 20 * (sg + 1) - p0;   /* p0 / 20 (exact to 8191): Thumb calls the BIOS for / */
        if (m > n) m = n;
        s32 xa = sgx[j][sg], xb = sgx[j][sg + 1], za = sgz[j][sg], zb = sgz[j][sg + 1];
        s32 far = 0;
        if (xa != NOGROUND && xb != NOGROUND) {
            s32 v[4] = {xa, xb, za, zb};
            for (int i = 0; i < 4; i++) {
                s32 a = v[i] < 0 ? -v[i] : v[i];
                if (a > far) far = a;
            }
        }
        if (!far || ((far * fl->k) >> 16) >= TEX_FAR) {
            flat_pairs(row + 2 * p0, m, color, row2);
        } else {
            /* a pair: 256 / 20 of the piece's ends' difference (as 26215 / 2^11: no division,
               which costs a BIOS call; |xb - xa| < 2^16) */
            s32 dX = ((xb - xa) * 26215) >> 11, dZ = ((zb - za) * 26215) >> 11;
            int q = p0 - 20 * sg;
            s32 X = camx8 + (xa << 8) + q * dX + (dX >> 2), Z = camz8 + (za << 8) + q * dZ + (dZ >> 2);
            if (fl->k != 65536) {
                X = camx8 + (s32)(((s64)(X - camx8) * fl->k) >> 16);
                Z = camz8 + (s32)(((s64)(Z - camz8) * fl->k) >> 16);
                dX = (s32)(((s64)dX * fl->k) >> 16);
                dZ = (s32)(((s64)dZ * fl->k) >> 16);
            }
            tex_walk(row + 2 * p0, m, X, Z, dX, dZ, inv30(dX), inv30(dZ), row2, color);
        }
        p0 += m;
        n -= m;
    }
}

/* one textured span of a floor on row pair j's row (and the row below when row2 is 240), x0..x1
   (only the setup: tex_walk does the pixels) */
HOT6 void tex_hspan(u8 *row, int j, int x0, int x1, const TexFloor *fl, int row2, int color)
{
    int p0 = x0 >> 1, n = ((x1 + 1) >> 1) - p0;
    if (tex_bg) {
        /* the ground: not where walls will cover it (from an even pair, as tex_walk pairs up
           the pixels by their address, so the rest comes out the same) */
        int l = cov_l[j] & ~1, r = cov_r[j];
        if (p0 < l)
            n -= l - p0, p0 = l;
        if (p0 + n > r)
            n = r - p0;
    }
    if (n <= 0)
        return;
    tex_tab = fl->tab;
    if (rolled) {
        tex_hspan_rolled(row, j, p0, n, fl, row2, color);
        return;
    }
    s32 dX = 2 * gdx[j], dZ = 2 * gdz[j];
    s32 X = gx[j] + 2 * p0 * gdx[j] + (gdx[j] >> 1), Z = gz[j] + 2 * p0 * gdz[j] + (gdz[j] >> 1);
    u32 ix = gix[j], iz = giz[j];
    if (fl->k != 65536) {
        X = camx8 + (s32)(((s64)(X - camx8) * fl->k) >> 16);
        Z = camz8 + (s32)(((s64)(Z - camz8) * fl->k) >> 16);
        dX = (s32)(((s64)dX * fl->k) >> 16);
        dZ = (s32)(((s64)dZ * fl->k) >> 16);
        ix = (u32)(((u64)ix * (u32)fl->kinv) >> 16);
        iz = (u32)(((u64)iz * (u32)fl->kinv) >> 16);
    }
    tex_walk(row + 2 * p0, n, X, Z, dX, dZ, ix, iz, row2, color);
}

void fill_trap(u8 *row, int rows, s32 xl, s32 sl, s32 xr, s32 sr, u32 color4);

/* rows y.. of a floor polygon between the 16.16 edges xl and xr; *done: the last row a
   texel pair already covered (start the polygon with -1) */
HOT3 void tex_rows(u8 *back, int y, int rows, s32 xl, s32 sl, s32 xr, s32 sr, int type, const void *info,
              int color, int *done)
{
    static const TexFloor ground = {65536, 65536};
    const TexFloor *fl = type == PT_FLOOR ? (const TexFloor *)info : &ground;
    while (rows > 0) {
        s32 far = gfar[y >> 1];
        if (!far || ((far * fl->k) >> 16) >= TEX_FAR) {
            /* too far for tiles: flat, these rows and the next ones as far */
            int n = 1;
            while (n < rows && (!gfar[(y + n) >> 1] || ((gfar[(y + n) >> 1] * fl->k) >> 16) >= TEX_FAR))
                n++;
            fill_trap(back + y * 240, n, xl, sl, xr, sr, color * 0x01010101u);
            y += n, rows -= n, xl += n * sl, xr += n * sr;
            continue;
        }
        if (type != PT_GROUND && y != *done) {   /* (PT_GROUND: the ground under it has its tiles) */
            int x0 = (xl + 0x7fff) >> 16, x1 = (xr + 0x7fff) >> 16;
            if (x0 < 0) x0 = 0;
            if (x1 > 240) x1 = 240;
            /* a pair of rows from an even row; a polygon's first row may be odd: on its own */
            tex_hspan(back + y * 240, y >> 1, x0, x1, fl, y & 1 ? 0 : 240, color);
            *done = y | 1;                      /* (an odd row was on its own: on to the next) */
        }
        y++, rows--, xl += sl, xr += sr;
    }
}

void tex_wall_setup(TexWall *t, V3 o, V3 s, V3 d)
{
    /* plane point o + a * s + b * d (texels: s, d are 32 units long, 1.14 here) */
    if (o.x > 30000) o.x = 30000;
    if (o.x < -30000) o.x = -30000;
    if (o.y > 30000) o.y = 30000;
    if (o.y < -30000) o.y = -30000;
    if (o.z > 30000) o.z = 30000;
    if (o.z < -30000) o.z = -30000;
    V3 n = v3((s.y * d.z - s.z * d.y) >> 12, (s.z * d.x - s.x * d.z) >> 12, (s.x * d.y - s.y * d.x) >> 12);
    V3 a = v3((d.y * o.z - d.z * o.y) >> 12, (d.z * o.x - d.x * o.z) >> 12, (d.x * o.y - d.y * o.x) >> 12);
    V3 b = v3((o.y * s.z - o.z * s.y) >> 12, (o.z * s.x - o.x * s.z) >> 12, (o.x * s.y - o.y * s.x) >> 12);
    t->w[0] = n.z * FOCAL - 120 * n.x + 80 * n.y, t->w[1] = n.x, t->w[2] = -n.y;
    t->a[0] = a.z * FOCAL - 120 * a.x + 80 * a.y, t->a[1] = a.x, t->a[2] = -a.y;
    t->b[0] = b.z * FOCAL - 120 * b.x + 80 * b.y, t->b[1] = b.x, t->b[2] = -b.y;
    /* w is n . (the ray through the pixel), so a column's depth is FOCAL * (n . o) / w: past
       TEX_WALL_FAR where |w| < FOCAL * |n . o| / TEX_WALL_FAR (each column switches on its
       own, at one distance, rather than a whole wall at once) */
    s64 no = (s64)n.x * o.x + (s64)n.y * o.y + (s64)n.z * o.z;
    if (no < 0) no = -no;
    t->wlim = (s32)((no * (FOCAL * 65536 / TEX_WALL_FAR)) >> 16);
    t->skip[0] = t->skip[1] = t->skip[2] = t->skip[3] = 0;
}

/* 2^25 * a / w with 1 / w as r / 2^(31 + e) from recip() */
#define DIVR(a, r, e) ({ s64 p_ = (s64)(a) * (s32)(r); int k_ = 6 + (e); \
    k_ >= 0 ? SHR64(p_, k_) : (s32)p_ << -k_; })

/* a wall polygon's slanted edges (screen 28.4); returns how many, and the columns it spans */
HOT static int wall_edges(const s16 *xy, int n, s32 *ex0, s32 *ey0, s32 *ex1, s32 *esl, s32 *xmin, s32 *xmax)
{
    int ne = 0;
    for (int i = 0; i < n; i++) {
        int j = i + 1 == n ? 0 : i + 1;
        s32 xa = xy[2 * i], ya = xy[2 * i + 1], xb = xy[2 * j], yb = xy[2 * j + 1];
        if (xa < *xmin) *xmin = xa;
        if (xa > *xmax) *xmax = xa;
        if (xa > xb) {
            s32 s = xa; xa = xb; xb = s;
            s = ya; ya = yb; yb = s;
        }
        s32 dx = xb - xa, dy = yb - ya;
        if (dx <= 0 || (dy < 0 ? -dy : dy) >= dx * 1024)
            continue;                       /* (upright: the edges beside it end at its ends) */
        ex0[ne] = xa, ey0[ne] = ya, ex1[ne] = xb;
        esl[ne] = divq(dy, dx, 16);
        ne++;
    }
    return ne;
}

/* the rows of the wall's column x (even): r0 .. the returned row - 1 */
static inline __attribute__((target("arm"), always_inline)) int wall_rows(int x, int ne, const s32 *ex0, const s32 *ey0, const s32 *ex1, const s32 *esl,
                            s32 xmin, s32 xmax, int *r0)
{
    s32 X = (x << 4) + 16, ylo = 1 << 30, yhi = -(1 << 30);
    if (X < xmin) X = xmin;
    if (X > xmax) X = xmax;
    for (int e = 0; e < ne; e++) {
        if (X < ex0[e] || X > ex1[e])
            continue;
        s32 yy = ey0[e] + (s32)(((s64)(X - ex0[e]) * esl[e]) >> 16);
        if (yy < ylo) ylo = yy;
        if (yy > yhi) yhi = yy;
    }
    int a = (ylo + 7) >> 4, b = (yhi + 7) >> 4;
    *r0 = a < 0 ? 0 : a;
    return b > 160 ? 160 : b;
}

/* ---- walls hidden behind nearer walls ----
   A wall is drawn in columns two pixels wide, each filled from its top row to its bottom row,
   and walls are drawn far to near. Going through them nearest first, cov_top/cov_bot hold for
   each column a run of rows that the walls drawn after this one will paint over: a column of
   this wall inside that run is left out. The ground is drawn before all of them: the rows of a
   pair covered from the screen's left edge to column cov_l, and from cov_r to its right edge,
   are left out of it. */

HOT11 __attribute__((minsize)) void tex_cover_clear(void)
{
#pragma clang loop unroll(disable)
    for (int i = 0; i < 60; i++)
        cov[i] = 0;
}

HOT5 void tex_occlude(const s16 *xy, int n, TexWall *t)
{
    s32 ex0[MAXV], ey0[MAXV], ex1[MAXV], esl[MAXV], xmin = 1 << 30, xmax = -(1 << 30);
    int ne = wall_edges(xy, n, ex0, ey0, ex1, esl, &xmin, &xmax);
    int x = ((xmin + 7) >> 4) & ~1, xe = ((xmax + 7) >> 4) + 1;
    if (x < 0) x = 0;
    if (xe > 240) xe = 240;
    s32 ylo = xy[1], yhi = xy[1];               /* (no column of it reaches past these rows) */
    for (int i = 1; i < n; i++) {
        if (xy[2 * i + 1] < ylo) ylo = xy[2 * i + 1];
        if (xy[2 * i + 1] > yhi) yhi = xy[2 * i + 1];
    }
    ylo = (ylo + 7) >> 4, yhi = (yhi + 7) >> 4;
    for (; x < xe; x += 2) {
        int c = x >> 1, top = cov_top[c], bot = cov_bot[c];
        if (ylo >= top && yhi <= bot) {
            t->skip[c >> 5] |= 1u << (c & 31);
            continue;
        }
        int r0, r1 = wall_rows(x, ne, ex0, ey0, ex1, esl, xmin, xmax, &r0);
        if (r1 <= r0)
            continue;
        if (r0 >= top && r1 <= bot) {
            t->skip[c >> 5] |= 1u << (c & 31);
            continue;
        }
        if (r0 <= bot && r1 >= top) {       /* overlapping or touching: one run */
            if (r0 < top) top = r0;
            if (r1 > bot) bot = r1;
        } else if (r1 - r0 > bot - top) {   /* apart: keep the longer */
            top = r0, bot = r1;
        } else
            continue;
        cov_top[c] = top, cov_bot[c] = bot;
    }
}

/* each row pair's run of columns covered from the left edge (to cov_l), and from the right
   edge (from cov_r). Going along the columns from an edge, the row pairs that all of them so far
   cover are one run (lo..hi - 1) that only shrinks: a pair leaving it at a column is covered up
   to that column. */
HOT9 __attribute__((minsize)) static void cover_from(u8 *out, int c, int dc, int all)
{
    int lo = 0, hi = 80;
    for (; (unsigned)c < 120 && lo < hi; c += dc) {
        int a = (cov_top[c] + 1) >> 1, b = cov_bot[c] >> 1, v = dc > 0 ? c : c + 1;
        while (lo < hi && lo < a)
            out[lo++] = v;
        while (hi > lo && hi > b)
            out[--hi] = v;
    }
    while (lo < hi)
        out[lo++] = all;
}

HOT11 __attribute__((minsize)) void tex_cover_done(void)
{
    cover_from(cov_l, 0, 1, 120);
    cover_from(cov_r, 119, -1, 0);
}

/* how many rows a column's pieces are, so that none puts the texture out by more than a pixel:
   a straight run is out by about (the texture's run down the column, ds or dt, in texels) times (the
   share w changes by, dw / w0) over 4, in texels of 2 pixels; half the rows is a fourth of it */
__attribute__((noinline)) static int wall_split(int rows, s32 ds, s32 dt, s32 w0, s32 dw)
{
    if (ds < 0) ds = -ds;
    if (dt < 0) dt = -dt;
    s64 err = (s64)(ds > dt ? ds : dt) * (dw < 0 ? -dw : dw), lim = (s64)w0 << 17;
    int j = 0;
    while (j < 3 && err > lim)
        j++, lim <<= 2;
    return (rows + (1 << j) - 1) >> j;
}

/* a wall polygon (screen 28.4) in columns two pixels wide */
HOT void tex_wall(u8 *back, const s16 *xy, int n, const TexWall *t, int color)
{
    s32 ex0[MAXV], ey0[MAXV], ex1[MAXV], esl[MAXV], xmin = 1 << 30, xmax = -(1 << 30);
    int ne = wall_edges(xy, n, ex0, ey0, ex1, esl, &xmin, &xmax);
    int x = ((xmin + 7) >> 4) & ~1, xe = ((xmax + 7) >> 4) + 1;
    if (x < 0) x = 0;
    if (xe > 240) xe = 240;
    for (; x < xe; x += 2) {
        if (t->skip[x >> 6] & 1u << ((x >> 1) & 31))
            continue;                       /* (a nearer wall paints over it) */
        int r0, r1 = wall_rows(x, ne, ex0, ey0, ex1, esl, xmin, xmax, &r0);
        int rows = r1 - r0;
        if (rows <= 0)
            continue;
        /* the texture at the top and bottom of the column (one division each) */
        int xc = x + 1, rb = r1 - 1, e;
        s32 wc = t->w[0] + xc * t->w[1], ac = t->a[0] + xc * t->a[1], bc = t->b[0] + xc * t->b[1];
        s32 wm = wc + ((r0 + r1) >> 1) * t->w[2];
        if ((wm < 0 ? -wm : wm) < t->wlim)
            goto flat;                       /* too far for its tiles */
        s32 w = wc + r0 * t->w[2], A = ac + r0 * t->a[2], B = bc + r0 * t->b[2];
        if (w < 0) w = -w, A = -A, B = -B;
        u32 r = recip(w | 1, &e);
        s32 s0 = DIVR(A, r, e), t0 = DIVR(B, r, e), s1 = s0, t1 = t0;
        if (rb > r0) {
            w = wc + rb * t->w[2], A = ac + rb * t->a[2], B = bc + rb * t->b[2];
            if (w < 0) w = -w, A = -A, B = -B;
            r = recip(w | 1, &e);
            s1 = DIVR(A, r, e), t1 = DIVR(B, r, e);
        }
        int slot = ((s0 >> 1) + (s1 >> 1)) >> 21;     /* a tile for every 32 texels */
        if (slot < 0) slot = 0;
        if (slot > 3) slot = 3;
        const u8 *tile = t->tile[slot];
        if (!tile) {
        flat:;
            u16 c = color | color << 8;
            u8 *f = back + r0 * 240 + x;
            for (int k = 0; k < rows; k++, f += 240)
                *(u16 *)f = c;
            continue;
        }
        u8 *d = back + r0 * 240 + x;
        /* per pair of rows, stepped linearly; where that would put the texture out by more than a
           pixel (a tall wall close by, looked at from above or below, or with the camera rolled: the
           texture's run down the column times the share its depth changes by, over 2 texels) in 2,
           4 or 8 pieces, each with its own exact ends, so the texture keeps its perspective (half
           the rows is a fourth of the error) */
        s32 w0 = wc + r0 * t->w[2], w1 = wc + rb * t->w[2], dw = w1 - w0;
        if (w0 < 0) w0 = -w0;
        int split = rows > 16 && dw ? wall_split(rows, s1 - s0, t1 - t0, w0, dw) : rows;
        int ra = r0;
        while (ra < r1) {
            int L = r1 - ra;
            s32 ds = 0, dt = 0, sb = s1, tb = t1;
            int span = L - 1;                /* (rows from the top to the exact end) */
            if (L > split) {
                L = span = split;
                int R = ra + L;
                w = wc + R * t->w[2], A = ac + R * t->a[2], B = bc + R * t->b[2];
                if (w < 0) w = -w, A = -A, B = -B;
                r = recip(w | 1, &e);
                sb = DIVR(A, r, e), tb = DIVR(B, r, e);
            }
            if (span > 1) {
                u32 inv = erecip[span];      /* 2^24 / span, the step per row ... */
                ds = (s32)(((s64)(sb - s0) * inv) >> 23);   /* ... doubled */
                dt = (s32)(((s64)(tb - t0) * inv) >> 23);
            }
            u32 uv = PACK(s0, t0), duv = PSTEP(ds, dt);
            int left = L, tall = dt < 0x5555 && dt > -0x5555 && L >= 4;
            u8 *dd = d;
            if (tall) {
                tex_vrun4(dd, L >> 2, uv, duv << 1, tile, t->lut);
                dd += 960 * (L >> 2), uv += (duv << 1) * (L >> 2), left = L & 3;
            }
            if (left >> 1) {
                tex_vrun(dd, left >> 1, uv, duv, tile, t->lut, 240);
                dd += 480 * (left >> 1), uv += duv * (left >> 1);
            }
            if (left & 1)
                tex_vrun(dd, 1, uv, duv, tile, t->lut, 0);
            d += 240 * L;
            ra += L;
            s0 = sb, t0 = tb;
        }
    }
}

#endif
