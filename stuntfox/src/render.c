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
   EWRAM word index, so the pool can be split over several free stretches of RAM (inside
   Payback only scattered buffers are free). */
typedef struct {
    u16 next;
    u8 n, color;                  /* n: vertices, and the kind (PT_*) << 6 */
    s16 xy[];                     /* then, for a textured kind, its TexFloor or TexWall */
} Poly;

#define PIDX(p) ((u16)(((u32)(p) >> 2) & 0xffff))
#define PPTR(i) ((Poly *)(0x02000000 + ((u32)(i) << 2)))

Camera cam;
int r_polys;
#ifdef MERGE
const u8 *r_pmap;
#define MAPC(c) ((c) >= 0x100 ? (c) & 0xff : r_pmap ? r_pmap[c] : (c))
#else
#define MAPC(c) (c)
#endif
#ifdef MERGE
extern u8 __pool_a[], __pool_a_end[], __pool_b[], __pool_b_end[], __pool_c[], __pool_c_end[], __pool_d[], __pool_d_end[];
static u8 *const pool_parts[] = {__pool_a, __pool_a_end, __pool_b, __pool_b_end, __pool_c, __pool_c_end,
                                 __pool_d, __pool_d_end};
#else
static u32 pool[15000] EWRAM_BSS;
static u8 *const pool_parts[] = {(u8 *)pool, (u8 *)(pool + 15000)};
#endif
#define NPARTS (int)(sizeof pool_parts / sizeof pool_parts[0] / 2)
static u8 *pool_at, *pool_end;
static int pool_part;
static u16 bucket[NBUCKET] SCRATCH;
static u16 bglist[MAXBG] SCRATCH;
static int npoly, nbg;
static u8 *back;
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
    u32 *b = (u32 *)bucket;
    for (int i = 0; i < NBUCKET / 2; i += 4)
        b[i] = b[i + 1] = b[i + 2] = b[i + 3] = 0;
    npoly = nbg = 0;
    pool_at = pool_parts[0];
    pool_end = pool_parts[1];
    pool_part = 0;
#ifdef MERGE
    /* draw into the page Payback is not showing */
    back = (REG_DISPCNT & 0x10) ? (u8 *)0x06000000 : (u8 *)0x0600a000;
#endif
}

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

/* signed distance of v from clip plane k: 0 near, 1 right, 2 left, 3 top, 4 bottom */
#define PLANE(v, k) ((k) == 0 ? (v)->z - NEAR : (k) == 1 ? (v)->z * 121 - (v)->x * FOCAL : \
                     (k) == 2 ? (v)->z * 121 + (v)->x * FOCAL : (k) == 3 ? (v)->z * 81 - (v)->y * FOCAL : \
                     (v)->z * 81 + (v)->y * FOCAL)

HOT static int clip(V3 *in, int n, V3 *out, int k)
{
    int m = 0;
    for (int i = 0; i < n; i++) {
        V3 *a = &in[i], *b = &in[i + 1 == n ? 0 : i + 1];
        s32 da = PLANE(a, k), db = PLANE(b, k);
        if (da >= 0)
            out[m++] = *a;
        if ((da >= 0) != (db >= 0)) {
            s32 na = da, nb = db;
            while (na > 262143 || na < -262143 || nb > 262143 || nb < -262143)
                na >>= 1, nb >>= 1;
            s32 t = (na << 12) / (na - nb);
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

HOT static Poly *alloc(int key, int bg, int n, int extra)
{
    u32 size = 4 + 4 * n + extra;
    while (pool_at + size > pool_end) {
        if (++pool_part >= NPARTS)
            return 0;
        pool_at = pool_parts[2 * pool_part];
        pool_end = pool_parts[2 * pool_part + 1];
    }
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
    }
    pool_at += size;
    npoly++;
    return p;
}

HOT static void poly(const V3 *v, int n, int color, int key, int bg, int type, const void *info, int isize)
{
    V3 a[MAXV], b[MAXV];
    int outcode_all = 0x1f, outcode_any = 0;
    for (int i = 0; i < n; i++) {
        const V3 *p = &v[i];
        s32 zx = p->z * 121, zy = p->z * 81, x = p->x * FOCAL, y = p->y * FOCAL;
        int oc = (p->z < NEAR) | ((zx < x) << 1) | ((zx < -x) << 2) | ((zy < y) << 3) | ((zy < -y) << 4);
        outcode_all &= oc;
        outcode_any |= oc;
        a[i] = v[i];
    }
    if (outcode_all)
        return;                                  /* entirely outside one plane */
    V3 *cur = a, *tmp = b;
    for (int k = 0; k < 5 && n >= 3; k++) {
        if (!(outcode_any & (1 << k)))
            continue;
        n = clip(cur, n, tmp, k);
        V3 *s = cur; cur = tmp; tmp = s;
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

void r_poly(const V3 *v, int n, int color, int key, int bg)
{
    poly(v, n, color, key, bg, 0, 0, 0);
}

#ifdef MERGE
void r_poly_tex(const V3 *v, int n, int color, int key, int bg, int type, const void *info)
{
    poly(v, n, color, key, bg, type, info, type == PT_WALL ? sizeof(TexWall) : sizeof(TexFloor));
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
            s32 t = (na << 12) / (na - nb);
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

void r_flush_bg(void)
{
    for (int i = 0; i < nbg; i++)
        raster(PPTR(bglist[i]));
}

HOT void r_flush_fg(void)
{
    for (int b = NBUCKET - 1; b >= 0; b--)
        for (int i = bucket[b]; i; i = PPTR(i)->next)
            raster(PPTR(i));
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
