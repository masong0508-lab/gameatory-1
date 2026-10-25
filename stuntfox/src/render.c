/* Flat-shaded polygon renderer. The hot parts (HOT) are ARM code run from IWRAM.

   Polygons are clipped against the view frustum in camera space, projected to 28.4 fixed
   point screen coordinates, bucket-sorted by depth and filled far to near (painter's
   algorithm) into the mode 4 back buffer. */
#include "render.h"
#ifdef MERGE
#include "tex.h"
#endif

#define NBUCKET 1024
#define MAXBG 640

/* Polygons live in a pool of variable-size records (4 + 4 * n bytes) and are linked by their
   EWRAM word index. */
typedef struct {
    u16 next;
    u8 n, color;                  /* n: vertices, and the kind (PT_*) << 6 */
    s16 xy[];                     /* then, for a textured kind, its TexFloor or TexWall */
} Poly;

#define PIDX(p) ((u16)(((u32)(p) >> 2) & 0xffff))
#define PPTR(i) ((Poly *)(0x02000000 + ((u32)(i) << 2)))

Camera cam;
s32 focal = FOCAL_NORMAL;
void r_set_focal(s32 f)
{
    focal = f;
}
int r_polys;
#ifdef MERGE
const u8 *r_pmap;
#define MAPC(c) ((c) >= 0x100 ? (c) & 0xff : r_pmap ? r_pmap[c] : (c))
#else
#define MAPC(c) (c)
#endif
static u8 *pool_at;
#ifdef MERGE
extern u8 __pool_a[], __pool_a_end[];          /* (the most a frame was seen to want: 9.8 of its 10.2 KB, Real Park from high up) */
/* poola lies over Payback's copies of the cells it changes (CUBE_BeginModify 0x0803c3bc: 200 slots
   of 64 bytes from 0x02003f24, byte 8 0xff when free, the first free one taken). Most levels use
   one or two, but Freedom City's second changes 56 cells as it starts. So the pool starts past the
   highest slot in use, PB_SPARE free ones left for what Payback changes before our next frame,
   and r_end marks free again the slots it covered: at a frame's start, a slot not free is Payback's.
   Payback takes the lowest free slot, so if it has gone past the spare ones the first slot under
   the pool is taken: only then (and now and again, to give back what it freed) look them all over. */
#define PB_SLOT ((u8 *)0x02003f24)
#define PB_NSLOT 200
#define PB_SPARE 8
static u8 *pool_lo;
static u8 *pool_floor(void)
{
    static u8 n;
    if (pool_lo && PB_SLOT[((pool_lo - PB_SLOT) & ~63) + 8] == 0xff && ++n & 63)
        return pool_lo;
    const u8 *f = PB_SLOT + 64 * PB_NSLOT + 8;
    int k = PB_NSLOT;
    while (k && f[-64] == 0xff)
        f -= 64, k--;
    u8 *lo = PB_SLOT + 64 * (k + PB_SPARE);
    return lo > __pool_a ? lo : __pool_a;
}

#define POOL_END __pool_a_end
#else
static u32 pool[15000] EWRAM_BSS;
#define POOL ((u8 *)pool)
#define POOL_END ((u8 *)(pool + 15000))
#endif
static u16 bucket[NBUCKET] SCRATCH;
static u32 bused[NBUCKET / 32] SCRATCH;     /* a bit for each bucket in use (r_flush_fg empties them as it goes) */
static u8 bage;                             /* frames since the buckets were last cleared whole (0: do it now) */
static u16 bglist[MAXBG] SCRATCH;
static int npoly, nbg;
static int npoly_done;                      /* npoly when the last frame's drawing ended */
#ifdef MERGE
#define MAXWL 64
static u32 wl[MAXWL] SCRATCH;              /* the frame's textured walls: bucket << 16 | index */
static int nwl;
#endif
static u8 *back;
#ifdef MERGE
void r_reset(void) { bage = 0; }
void r_end(void)
{
    for (u8 *f = PB_SLOT + 8 + 64 * ((pool_lo - PB_SLOT + 55) >> 6); f < pool_at; f += 64)
        *f = 0xff;
    npoly_done = npoly;
}
#endif
extern const u32 rtab[2048];                /* 2^31 / (2048 + i) (tables.c) */
extern const u32 erecip[2561];              /* (1 << 24) / i, for edge slopes */
static const u16 inv_n[MAXV + 1] = {0, 65535, 32768, 21845, 16384, 13107, 10923, 9362, 8192, 7282, 6554, 5958, 5461, 5041, 4681, 4369, 4096};

void r_init(void)
{
#ifndef MERGE
    REG_DISPCNT = 4 | 0x400 | 0x1000 | 0x40;  /* mode 4, BG2, OBJ, 1D tiles */
    back = (u8 *)0x0600a000;
#endif
}

void r_begin(void)
{
    if (!bage++) {                              /* (the first frame, a new level, and every 256th: scratch held what was in memory, and nothing else may be trusted for long) */
        u32 *b = (u32 *)bucket;
        for (int i = 0; i < NBUCKET / 2; i++)
            b[i] = 0;
        for (int i = 0; i < NBUCKET / 32; i++)
            bused[i] = 0;
    } else if (npoly != npoly_done) {           /* (a polygon added since the last flush: never drawn, and its memory is gone) */
        for (int i = 0; i < NBUCKET / 32; i++)
            for (u32 m = bused[i], b = i * 32; m; m >>= 1, b++)
                if (m & 1)
                    bucket[b] = 0;
        for (int i = 0; i < NBUCKET / 32; i++)
            bused[i] = 0;
    }
    npoly = nbg = 0;
#ifdef MERGE
    pool_at = pool_lo = pool_floor();
    nwl = 0;
    /* draw into the page Payback is not showing */
    back = (REG_DISPCNT & 0x10) ? (u8 *)0x06000000 : (u8 *)0x0600a000;
#else
    pool_at = POOL;
#endif
}

#ifdef MERGE
/* only the target page (the 2D drawing of a menu, before any frame has begun) */
void r_back(void)
{
    back = (REG_DISPCNT & 0x10) ? (u8 *)0x06000000 : (u8 *)0x0600a000;
}
#endif

V3 r_cam(V3 p)
{
    V3 d = vsub(p, cam.pos);
    return v3(vdot(cam.m.r, d), vdot(cam.m.u, d), vdot(cam.m.f, d));
}

V3 r_cam_far(V3 p, int shift)
{
    V3 d = vshr(vsub(p, cam.pos), shift);
    return v3(vdot(cam.m.r, d), vdot(cam.m.u, d), vdot(cam.m.f, d));
}

int r_nofog;

int fog_of(int z)
{
    if (r_nofog)
        return 0;
    return z < 9000 ? 0 : z < 14000 ? 1 : z < 19000 ? 2 : 3;
}

/* ---- clipping ---- */

/* (n << 12) / d exactly, for 0 <= n <= d < 2^20 (where a plane cuts an edge): from the
   reciprocal table, then put right (a division is a slow BIOS call) */
HOT8 static u32 cut12(u32 n, u32 d)
{
    int e = 0;
    u32 m = d;
    if (m >= 1 << 16) m >>= 4, e += 4;
    if (m >= 1 << 14) m >>= 2, e += 2;
    if (m >= 1 << 13) m >>= 1, e++;
    if (m >= 1 << 12) m >>= 1, e++;
    while (m < 2048) m <<= 1, e--;
    n <<= 12;
    u32 q = (u32)(((u64)n * rtab[m - 2048]) >> (31 + e));
    while (q * d > n) q--;
    while ((q + 1) * d <= n) q++;
    return q;
}
/* (na << 12) / (na - nb) for na, nb of opposite signs */
#define CUT(na, nb) (s32)cut12((na) < 0 ? -(na) : (na), (na) < (nb) ? (nb) - (na) : (na) - (nb))

/* signed distance of v from clip plane k: 0 near, 1 right, 2 left, 3 top, 4 bottom */
#define PLANE(v, k) ((k) == 0 ? (v)->z - NEAR : (k) == 1 ? (v)->z * 121 - (v)->x * fl : \
                     (k) == 2 ? (v)->z * 121 + (v)->x * fl : (k) == 3 ? (v)->z * 81 - (v)->y * fl : \
                     (v)->z * 81 + (v)->y * fl)

HOT __attribute__((minsize)) static int clip(const V3 *in, int n, V3 *out, int k)
{
    int m = 0;
    const s32 fl = focal;
    s32 da = PLANE(in, k), db;
    for (int i = 0; i < n; i++, da = db) {
        const V3 *a = &in[i], *b = &in[i + 1 == n ? 0 : i + 1];
        db = PLANE(b, k);
        if (da >= 0)
            out[m++] = *a;
        if ((da >= 0) != (db >= 0)) {
            s32 na = da, nb = db;
            while (na > 262143 || na < -262143 || nb > 262143 || nb < -262143)
                na >>= 1, nb >>= 1;
            s32 t = CUT(na, nb);
            out[m].x = a->x + (((b->x - a->x) * t) >> 12);
            out[m].y = a->y + (((b->y - a->y) * t) >> 12);
            out[m].z = a->z + (((b->z - a->z) * t) >> 12);
            m++;
        }
        if (m >= MAXV - 1)
            break;
    }
    return m;
}

HOT7 static Poly *alloc(int key, int bg, int n, int extra)
{
    u32 size = 4 + 4 * n + extra;
    if (pool_at + size > POOL_END)
        return 0;                               /* (full: the rest of the frame is left out) */
    Poly *p = (Poly *)pool_at;
    if (bg) {
        if (nbg >= MAXBG)
            return 0;
        bglist[nbg++] = PIDX(p);
    } else {
        int b = key >> 5;
        if (b < 0) b = 0;
        if (b >= NBUCKET) b = NBUCKET - 1;
        p->next = bucket[b];
        bucket[b] = PIDX(p);
        bused[b >> 5] |= 1u << (b & 31);
    }
    pool_at += size;
    npoly++;
    return p;
}

HOT static void poly(const V3 *v, int n, int color, int key, int bg, int type, const void *info, int isize)
{
    V3 a[MAXV], b[MAXV];
    int outcode_all = 0x1f, outcode_any = 0;
    const s32 fl = focal;
    for (int i = 0; i < n; i++) {
        const V3 *p = &v[i];
        s32 zx = p->z * 121, zy = p->z * 81, x = p->x * fl, y = p->y * fl;
        int oc = (p->z < NEAR) | ((zx < x) << 1) | ((zx < -x) << 2) | ((zy < y) << 3) | ((zy < -y) << 4);
        outcode_all &= oc;
        outcode_any |= oc;
    }
    if (outcode_all)
        return;                                  /* entirely outside one plane */
    const V3 *cur = v;                           /* (the first cut reads v itself) */
    V3 *tmp = a, *o = b;
    for (int k = 0; k < 5 && n >= 3; k++) {
        if (!(outcode_any & (1 << k)))
            continue;
        n = clip(cur, n, tmp, k);
        cur = tmp, tmp = o, o = (V3 *)cur;
    }
    if (n < 3)
        return;
    if (key == -1) {
        s32 sum = 0;
        for (int i = 0; i < n; i++) sum += cur[i].z;
        key = (s32)(((s64)sum * inv_n[n]) >> 16);
    } else if (key < 0) {                       /* -2: the farthest point (driving surfaces) */
        key = cur[0].z;
        for (int i = 1; i < n; i++) if (cur[i].z > key) key = cur[i].z;
    }
    Poly *p = alloc(key, bg, n, isize);
    if (!p)
        return;
#ifdef MERGE
    if (type == PT_WALL && !bg && nwl < MAXWL)
        wl[nwl++] = (u32)(key < 0 ? 0 : key >= NBUCKET << 5 ? NBUCKET - 1 : key >> 5) << 16 | PIDX(p);
#endif
    p->n = n | type << 6;
    p->color = MAPC(color);
    for (int i = 0; i < isize >> 2; i++)
        ((u32 *)&p->xy[2 * n])[i] = ((const u32 *)info)[i];
    for (int i = 0; i < n; i++) {
        s32 z = cur[i].z, s = 0;
        u32 zn = (u32)z;
        while (zn < 2048) zn <<= 1, s++;
        while (zn >= 4096) zn >>= 1, s--;
        s64 inv = rtab[zn - 2048];
        int sh = 31 - s;
        s32 sx = 1920 + (s32)(((s64)cur[i].x * (FOCAL * 16) * inv) >> sh);
        s32 sy = 1280 - (s32)(((s64)cur[i].y * (FOCAL * 16) * inv) >> sh);
        if (sx < 0) sx = 0;
        if (sx > 3840) sx = 3840;
        if (sy < 0) sy = 0;
        if (sy > 2560) sy = 2560;
        p->xy[2 * i] = sx;
        p->xy[2 * i + 1] = sy;
    }
}

#ifdef MERGE
/* the key a polygon gets from key -1 (the middle of what is in view), for a part of it that is drawn
   on its own: it keeps its place among the rest as if it were whole */
int r_key(const V3 *v, int n)
{
    V3 a[MAXV], b[MAXV];
    int all = 0x1f, any = 0;
    for (int i = 0; i < n; i++) {
        const V3 *p = &v[i];
        s32 zx = p->z * 121, zy = p->z * 81, x = p->x * focal, y = p->y * focal;
        int oc = (p->z < NEAR) | ((zx < x) << 1) | ((zx < -x) << 2) | ((zy < y) << 3) | ((zy < -y) << 4);
        all &= oc, any |= oc;
    }
    if (all)
        return 0;
    const V3 *cur = v;
    V3 *tmp = a, *o = b;
    for (int k = 0; k < 5 && n >= 3; k++) {
        if (!(any & (1 << k)))
            continue;
        n = clip(cur, n, tmp, k);
        cur = tmp, tmp = o, o = (V3 *)cur;
    }
    s32 sum = 0;
    for (int i = 0; i < n; i++) sum += cur[i].z;
    return n < 3 ? 0 : (s32)(((s64)sum * inv_n[n]) >> 16);
}
#endif

HOT4 void r_poly(const V3 *v, int n, int color, int key, int bg)
{
    poly(v, n, color, key, bg, 0, 0, 0);
}

#ifdef MERGE
void r_poly_tex(const V3 *v, int n, int color, int key, int bg, int type, const void *info)
{
    if (type != PT_WALL && (cam.pos.y > TEX_TOP
                            || (cam.pos.y < 16 && (type == PT_GROUND || ((const TexFloor *)info)->k == 65536))))
        type = 0;                  /* (no tiles on floors from up there: flat, see tex_frame; from under
                                      the street, only on the floors down there) */
    if (type == PT_FLOOR && tex_floor_far < 1 << 30) {   /* (GAME SETTINGS' speed: roofs wholly past it are flat) */
        s32 z = v[0].z;
        for (int i = 1; i < n; i++)
            if (v[i].z < z)
                z = v[i].z;
        if (z > tex_floor_far)
            type = 0;
    }
    poly(v, n, color, key, bg, type, info, type == PT_WALL ? sizeof(TexWall) : type ? sizeof(TexFloor) : 0);
}
#endif

void r_poly2d(const s32 *xy, int n, int color, int key, int bg)
{
    Poly *p = alloc(key, bg, n, 0);
    if (!p)
        return;
    p->n = n;
    p->color = MAPC(color);
    for (int i = 0; i < 2 * n; i++)
        p->xy[i] = xy[i];
}

/* clip a screen-space polygon (28.4) by a*x + b*y + c >= 0 */
static int clip2d(const s32 *in, int n, s32 *out, s32 a, s32 b, s32 c)
{
    int m = 0;
    for (int i = 0; i < n; i++) {
        const s32 *p = &in[2 * i], *q = &in[2 * (i + 1 == n ? 0 : i + 1)];
        s32 dp = (a * p[0] + b * p[1] + c) >> 8;          /* |a|, |b| <= 16384: fits in 32 bits */
        s32 dq = (a * q[0] + b * q[1] + c) >> 8;
        if (dp >= 0) {
            out[2 * m] = p[0];
            out[2 * m + 1] = p[1];
            m++;
        }
        if ((dp >= 0) != (dq >= 0)) {
            s32 na = dp, nb = dq;
            while (na > 262143 || na < -262143 || nb > 262143 || nb < -262143)
                na >>= 1, nb >>= 1;
            s32 t = CUT(na, nb);
            out[2 * m] = p[0] + (((q[0] - p[0]) * t) >> 12);
            out[2 * m + 1] = p[1] + (((q[1] - p[1]) * t) >> 12);
            m++;
        }
    }
    return m;
}

/* Sky and ground as bands parallel to the horizon. bounds[] holds nbands - 1 sines of
   elevation (1.14), descending; band k lies between bounds[k] (below) and bounds[k - 1].
   Only the first ndraw bands are drawn (the rest is known to be covered). */
void r_sky(const u16 *colors, const s32 *bounds, int nbands, int ndraw)
{
    /* world up in camera space; the ray through screen point (sx, sy) (28.4) is
       ((sx - 1920) / 16, (1280 - sy) / 16, FOCAL), and its elevation test against level L is
       (sx - 1920) * wr + (1280 - sy) * wu + 16 * FOCAL * (wf - L) >= 0 */
    s32 wr = cam.m.r.y, wu = cam.m.u.y, wf = cam.m.f.y;
    s32 a = wr, b = -wu, c0 = -1920 * wr + 1280 * wu + 16 * FOCAL * wf;
    static const s32 rect[8] = {0, 0, 3840, 0, 3840, 2560, 0, 2560};
    s32 t1[2 * MAXV], t2[2 * MAXV];
    /* the test is linear, so its least and greatest value over the screen are at corners */
    s32 lo = c0 + (a < 0 ? 3840 * a : 0) + (b < 0 ? 2560 * b : 0);
    s32 hi = c0 + (a > 0 ? 3840 * a : 0) + (b > 0 ? 2560 * b : 0);
    for (int k = 0; k < ndraw; k++) {
        int n = 4;
        const s32 *src = rect;
        if (k < nbands - 1) {                       /* d >= bounds[k] */
            s32 c = c0 - 16 * FOCAL * bounds[k], o = c - c0;
            if (hi + o < 0)
                continue;                           /* all of the screen is below this band */
            if (lo + o < 0) {
                n = clip2d(src, n, t1, a, b, c);
                src = t1;
            }
        }
        if (n >= 3 && k > 0) {                      /* d <= bounds[k - 1] */
            s32 c = c0 - 16 * FOCAL * bounds[k - 1], o = c - c0;
            if (lo + o > 0)
                continue;                           /* all of it is above */
            if (hi + o > 0) {
                n = clip2d(src, n, src == t1 ? t2 : t1, -a, -b, -c);
                src = src == t1 ? t2 : t1;
            }
        }
        if (n >= 3)
            r_poly2d(src, n, colors[k], 0, 1);
    }
}

/* ---- rasteriser ---- */

void fill_trap(u8 *row, int rows, s32 xl, s32 sl, s32 xr, s32 sr, u32 color4);

/* Fill a convex polygon: walk the two chains down from the top vertex and fill each run of
   rows between vertex events in one go (fill.s). */
HOT static void raster(const Poly *p)
{
    int n = p->n & 0x3f;
    const s16 *xy = p->xy;
#ifdef MERGE
    int type = p->n >> 6, done = -1;
    const void *info = &xy[2 * n];
    if (type == PT_WALL) {
        tex_wall(back, xy, n, info, p->color);
        return;
    }
#endif
    int top = 0;
    s32 ymin = xy[1], ymax = xy[1];
    for (int i = 1; i < n; i++) {
        s32 y = xy[2 * i + 1];
        if (y < ymin) ymin = y, top = i;
        if (y > ymax) ymax = y;
    }
    int y = (ymin + 7) >> 4, ye = (ymax + 7) >> 4;
    int ia = top, ib = top, enda = y, endb = y, guard = 2 * n;
    s32 xa = 0, sa = 0, xb = 0, sb = 0;
    u32 c = p->color * 0x01010101u;
    while (y < ye) {
        while (y >= enda) {
            if (--guard < 0)
                return;
            int j = ia + 1 == n ? 0 : ia + 1;
            s32 y0 = xy[2 * ia + 1], y1 = xy[2 * j + 1], x0 = xy[2 * ia];
            enda = (y1 + 7) >> 4;
            if (enda > y) {
                sa = (s32)(((s64)(xy[2 * j] - x0) * erecip[y1 - y0]) >> 8);
                xa = (x0 << 12) + (s32)(((s64)(y * 16 + 8 - y0) * sa) >> 4);
            }
            ia = j;
        }
        while (y >= endb) {
            if (--guard < 0)
                return;
            int j = ib == 0 ? n - 1 : ib - 1;
            s32 y0 = xy[2 * ib + 1], y1 = xy[2 * j + 1], x0 = xy[2 * ib];
            endb = (y1 + 7) >> 4;
            if (endb > y) {
                sb = (s32)(((s64)(xy[2 * j] - x0) * erecip[y1 - y0]) >> 8);
                xb = (x0 << 12) + (s32)(((s64)(y * 16 + 8 - y0) * sb) >> 4);
            }
            ib = j;
        }
        int y1 = enda < endb ? enda : endb;
        if (y1 > ye) y1 = ye;
        int rows = y1 - y;
#ifdef MERGE
        if (type) {
            if (xa + sa * (rows >> 1) <= xb + sb * (rows >> 1))
                tex_rows(back, y, rows, xa, sa, xb, sb, type, info, p->color, &done);
            else
                tex_rows(back, y, rows, xb, sb, xa, sa, type, info, p->color, &done);
        } else
#endif
        if (xa + sa * (rows >> 1) <= xb + sb * (rows >> 1))
            fill_trap(back + y * 240, rows, xa, sa, xb, sb, c);
        else
            fill_trap(back + y * 240, rows, xb, sb, xa, sa, c);
        xa += sa * rows;
        xb += sb * rows;
        y = y1;
    }
}

#ifdef MERGE
/* which parts of walls nearer walls hide: the walls go to tex_occlude nearest first, the
   reverse of the order r_flush_fg draws them in (buckets near to far, and in a bucket as
   submitted, as each bucket's list starts with its last) */
static void occlude(void)
{
    tex_cover_clear();
    for (int i = 1; i < nwl; i++) {
        u32 w = wl[i];
        int k = i;
        for (; k > 0 && wl[k - 1] > w; k--)
            wl[k] = wl[k - 1];
        wl[k] = w;
    }
    for (int i = 0; i < nwl; i++) {
        Poly *p = PPTR(wl[i] & 0xffff);
        int n = p->n & 0x3f;
        tex_occlude(p->xy, n, (TexWall *)&p->xy[2 * n]);
    }
    tex_cover_done();
}
#endif

void r_flush_bg(void)
{
#ifdef MERGE
    occlude();
    tex_bg = 1;
#endif
    for (int i = 0; i < nbg; i++)
        raster(PPTR(bglist[i]));
#ifdef MERGE
    tex_bg = 0;
#endif
}

/* far to near: the buckets in use, the highest first, found a word of bits at a time */
HOT6B void r_flush_fg(void)
{
    for (int w = NBUCKET / 32 - 1; w >= 0; w--) {
        u32 m = bused[w];
        bused[w] = 0;
        for (int b = w * 32 + 31; m; b--, m <<= 1) {
            if (!(m >> 31))
                continue;
            for (int i = bucket[b]; i; i = PPTR(i)->next)
                raster(PPTR(i));
            bucket[b] = 0;
        }
    }
    r_polys = npoly;
}

u8 *r_target(void) { return back; }

void r_pixel(int x, int y, int color)
{
    if ((unsigned)x >= 240 || (unsigned)y >= 160)
        return;
    u16 *p = (u16 *)(back + y * 240 + (x & ~1));
    color = MAPC(color);
    *p = x & 1 ? (*p & 0xff) | (color << 8) : (*p & 0xff00) | color;
}

#ifndef MERGE
void r_flip(void)
{
    static u32 last;
    do
        vblank_wait();
    while (frame_count - last < 2);                 /* at most 30 frames a second */
    last = frame_count;
    REG_DISPCNT ^= 0x10;
    back = (REG_DISPCNT & 0x10) ? (u8 *)0x06000000 : (u8 *)0x0600a000;
}
#endif
