/* Payback's tiles on the ground, roofs and walls (MERGE build). See tex.h.

   The ground: every screen row of a flat ground lies at one depth (unless the camera rolls),
   so where the ground is along each row is worked out once a frame, at both ends of the row.
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

/* per pair of screen rows: the ground under the left pixel (units * 256), its step per pixel,
   2^30 / the step per texel (two pixels), and how far the rows reach (units, 0: no ground) */
static s32 gx[80] EWRAM_BSS, gz[80] EWRAM_BSS, gdx[80] EWRAM_BSS, gdz[80] EWRAM_BSS;
static u32 gix[80] EWRAM_BSS, giz[80] EWRAM_BSS;
static s32 gfar[80] EWRAM_BSS;
static s32 camx8, camz8, camy;
int tex_on;

/* a texture position and a step (texels, 16.16) as packed words (see texrun.s) */
#define PACK(s, t) ((((u32)(s) << 11) & 0xffff0000u) | (((u32)(t) >> 5) & 0xffff))
#define PSTEP(ds, dt) ((((u32)(ds) << 11) & 0xffff0000u) + (u32)((s32)(dt) >> 5))

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

static u32 inv30(s32 v)                     /* 2^30 / |v|, |v| at least 16 */
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

void tex_frame(void)
{
    camx8 = cam.pos.x << 8;
    camz8 = cam.pos.z << 8;
    camy = cam.pos.y;
    V3 r = cam.m.r, u = cam.m.u, f = cam.m.f;
    int on = tex_on && camy >= 16 && camy <= 12000;
    for (int j = 0; j < 80; j++) {
        gfar[j] = 0;
        if (!on)
            continue;
        /* rays through the row pair's end pixels, doubled, >> 9 (32-bit sums only: this is
           Thumb code, where 64-bit products are slow calls) */
        s32 k = 158 - 4 * j;
        V3 base = v3(k * u.x + 2 * FOCAL * f.x, k * u.y + 2 * FOCAL * f.y, k * u.z + 2 * FOCAL * f.z);
        s32 xo[2], zo[2], far = 0;
        int ok = 1;
        for (int end = 0; end < 2; end++) {
            s32 c = end ? 239 : -239;
            s32 dx = (base.x + c * r.x) >> 9, ndy = -((base.y + c * r.y) >> 9), dz = (base.z + c * r.z) >> 9;
            s32 ax = dx < 0 ? -dx : dx, az = dz < 0 ? -dz : dz, m = ax > az ? ax : az;
            if (ndy <= 0 || camy * m >= ndy * 16000) {
                ok = 0;
                break;
            }
            int e;
            u32 inv = recip(ndy, &e);       /* 1 / ndy = inv / 2^(31 + e), inv < 2^21 */
            s32 t = (s32)(camy * (inv >> 5)), sh = 10 + e;   /* t >> sh: camy * 65536 / ndy */
            t = sh >= 0 ? t >> sh : t << -sh;
            xo[end] = (dx * t) >> 8;        /* (|dx * t| < 2^30: rays reach at most 16000 units) */
            zo[end] = (dz * t) >> 8;
            s32 dist = (m * t) >> 16;
            if (dist > far) far = dist;
        }
        if (!ok)
            continue;
        gx[j] = camx8 + xo[0];
        gz[j] = camz8 + zo[0];
        gdx[j] = (((xo[1] - xo[0]) >> 6) * 17549) >> 16;   /* / 239 */
        gdz[j] = (((zo[1] - zo[0]) >> 6) * 17549) >> 16;
        gix[j] = inv30(2 * gdx[j]);
        giz[j] = inv30(2 * gdz[j]);
        gfar[j] = far + 1;
    }
}

void tex_floor(TexFloor *fl, s32 h)
{
    s32 k = camy <= h + 16 ? 1024 : divq(camy - h, camy, 16);   /* (not drawn from below) */
    if (k < 1024)
        k = 1024;
    fl->k = k;
    fl->kinv = divq(65536, k, 16);
}


/* n pairs of pixels of one colour, on this row and row2 bytes further */
static void flat_pairs(u8 *d, int n, int color, int row2)
{
    u16 c = color | color << 8;
    for (; n > 0; n--, d += 2) {
        *(u16 *)(d + row2) = c;
        *(u16 *)d = c;
    }
}

/* one textured span of a floor on row pair j's row (and the row below when row2 is 240), x0..x1 */
HOT void tex_hspan(u8 *row, int j, int x0, int x1, const TexFloor *fl, int row2, int color)
{
    int p0 = x0 >> 1, n = ((x1 + 1) >> 1) - p0;
    if (n <= 0)
        return;
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
    u32 duv = PSTEP(dX << 3, dZ << 3);        /* units * 256 -> texels 16.16: * 8 */
    /* close up, a texel covers many pixels: one sample for every four */
    int quad = dX < 0x1000 && dX > -0x1000 && dZ < 0x1000 && dZ > -0x1000;
    u8 *d = row + 2 * p0;
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
        const u8 *tile = TILE(world.ctex[i]);
        if (tile && quad && m >= 3) {
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
}

/* 2^25 * a / w with 1 / w as r / 2^(31 + e) from recip() */
#define DIVR(a, r, e) ({ s64 p_ = (s64)(a) * (s32)(r); int k_ = 6 + (e); \
    k_ >= 0 ? SHR64(p_, k_) : (s32)p_ << -k_; })

/* a wall polygon (screen 28.4) in columns two pixels wide */
HOT void tex_wall(u8 *back, const s16 *xy, int n, const TexWall *t, int color)
{
    s32 ex0[MAXV], ey0[MAXV], ex1[MAXV], esl[MAXV];
    s32 xmin = 1 << 30, xmax = -(1 << 30);
    int ne = 0;
    for (int i = 0; i < n; i++) {
        int j = i + 1 == n ? 0 : i + 1;
        s32 xa = xy[2 * i], ya = xy[2 * i + 1], xb = xy[2 * j], yb = xy[2 * j + 1];
        if (xa < xmin) xmin = xa;
        if (xa > xmax) xmax = xa;
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
    int x = ((xmin + 7) >> 4) & ~1, xe = ((xmax + 7) >> 4) + 1;
    if (x < 0) x = 0;
    if (xe > 240) xe = 240;
    for (; x < xe; x += 2) {
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
        int r0 = (ylo + 7) >> 4, r1 = (yhi + 7) >> 4;
        if (r0 < 0) r0 = 0;
        if (r1 > 160) r1 = 160;
        int rows = r1 - r0;
        if (rows <= 0)
            continue;
        /* the texture at the top and bottom of the column (one division each) */
        int xc = x + 1, rb = r1 - 1, e;
        s32 wc = t->w[0] + xc * t->w[1], ac = t->a[0] + xc * t->a[1], bc = t->b[0] + xc * t->b[1];
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
        u8 *d = back + r0 * 240 + x;
        if (!tile) {
            u16 c = color | color << 8;
            for (int k = 0; k < rows; k++, d += 240)
                *(u16 *)d = c;
            continue;
        }
        /* per pair of rows */
        s32 ds = 0, dt = 0;
        if (rows > 2) {
            u32 inv = erecip[rows - 1];      /* 2^24 / (rows - 1), the step per row ... */
            ds = (s32)(((s64)(s1 - s0) * inv) >> 23);   /* ... doubled */
            dt = (s32)(((s64)(t1 - t0) * inv) >> 23);
        }
        u32 uv = PACK(s0, t0), duv = PSTEP(ds, dt);
        int left = rows, tall = dt < 0x5555 && dt > -0x5555 && rows >= 4;
        if (tall) {
            tex_vrun4(d, rows >> 2, uv, duv << 1, tile, t->lut);
            d += 960 * (rows >> 2), uv += (duv << 1) * (rows >> 2), left = rows & 3;
        }
        if (left >> 1) {
            tex_vrun(d, left >> 1, uv, duv, tile, t->lut, 240);
            d += 480 * (left >> 1), uv += duv * (left >> 1);
        }
        if (left & 1)
            tex_vrun(d, 1, uv, duv, tile, t->lut, 0);
    }
}

#endif
