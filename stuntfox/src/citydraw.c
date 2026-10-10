/* Drawing the city: buildings, ground patches, ramps and loops near the camera, and one
   flat patch per distant sector. */
#include "world.h"
#include "render.h"
#include "palette.h"
#include "loops.h"
#ifdef MERGE
#include "tex.h"
static const TexFloor ground = {65536, 65536};
/* Payback's own colour for a tile seen from afar (light 0..3), as a raw palette index */
static int tile_color(int id, int l, int fallback)
{
    if ((unsigned)id >= TEX_IDS)
        return fallback;
    int c = pb_avg[id];
    return 0x100 | (l < 3 ? pb_shade[l][c] : c);
}
#endif

/* which buildings, lots and ramps were already drawn this frame (one bit each) */
#define SEEN_LOT 2048
#define SEEN_RAMP (2048 + 2560)
#define SEEN_LINE (2048 + 2560 + 512)
#define SEEN_TREE (2048 + 2560 + 512 + 1024)
static u32 seen[(2048 + 2560 + 512 + 1024 + 2048) / 32] SCRATCH;
static inline int first_visit(int i)
{
    u32 *w = &seen[i >> 5], b = 1u << (i & 31);
    if (*w & b)
        return 0;
    *w |= b;
    return 1;
}

#ifdef MERGE
#define VIEW_CELLS 14              /* inside Payback, its game shares the frame time ... */
#define STREET_CELLS 10            /* ... and in the streets the nearest walls hide the rest */
#else
#define VIEW_CELLS 18
#endif
#define FAR_CELLS 72

/* camera-space images of the world axes, scaled by 1/16384 per unit */
static V3 ax, ay, az;

static inline V3 cadd(V3 p, s32 dx, s32 dy, s32 dz)
{
    return v3(p.x + ((ax.x * dx + ay.x * dy + az.x * dz) >> 14),
              p.y + ((ax.y * dx + ay.y * dy + az.y * dz) >> 14),
              p.z + ((ax.z * dx + ay.z * dy + az.z * dz) >> 14));
}

/* is a sphere (camera space centre c, radius r) at least partly in view? */
static inline int in_view(V3 c, s32 r)
{
    return !(c.z < -r || FOCAL * c.x - 121 * c.z > r * 182 || -FOCAL * c.x - 121 * c.z > r * 182 ||
             FOCAL * c.y - 81 * c.z > r * 158 || -FOCAL * c.y - 81 * c.z > r * 158);
}

static void quad(V3 a, V3 b, V3 c, V3 d, int color, int bg)
{
    V3 q[4] = {a, b, c, d};
    r_poly(q, 4, color, -1, bg);
}

/* ---- building fronts: a row of windows on every storey, shop windows on the ground ---- */
#define STOREY 384
#ifdef MERGE
#define WINDOWS_FAR 4600           /* rows of windows on walls nearer than this */
#define PANES_FAR 2200             /* ... split into panes nearer than this */
#else
#define WINDOWS_FAR 7000
#define PANES_FAR 4000
#endif

/* camera-space point s units along a wall from a (dir: the world axis it runs along) and h up */
static inline V3 wpt(V3 a, V3 dir, s32 s, s32 h)
{
    return v3(a.x + ((dir.x * s + ay.x * h) >> 14), a.y + ((dir.y * s + ay.y * h) >> 14),
              a.z + ((dir.z * s + ay.z * h) >> 14));
}

static void wquad(V3 a, V3 b, V3 c, V3 d, int color, s32 key)
{
    V3 q[4] = {a, b, c, d};
    r_poly(q, 4, color, key, 0);
}

/* One side of a building from its bottom corner a, len units along dir, h high. The wall and
   its windows share one depth key: within it the last submitted is drawn first, so the panes'
   pillars go in before the window rows and those before the wall. */
static void wall(V3 a, V3 dir, s32 len, s32 h, int m, int l, int f, const u16 *tiles)
{
    V3 b = wpt(a, dir, len, 0), at = wpt(a, dir, 0, h), bt = wpt(a, dir, len, h);
    s32 key = (a.z + b.z + at.z + bt.z) >> 2, near = a.z < b.z ? a.z : b.z;
    if (key < 0)
        key = 0;
    int wc = COLOR(m, l, f);
#ifdef MERGE
    if (tex_on && m != M_STUNT) {
        /* Payback's own wall tiles near by, their average colour further off */
        wc = tile_color(tiles[0] != 0xffff ? tiles[0] : tiles[1], l, wc);
        V3 q[4] = {a, b, bt, at};
        s32 nz = near < at.z ? near : at.z;
        if (nz < TEX_WALL_FAR) {
            TexWall t;
            tex_wall_setup(&t, at, dir, v3(-ay.x, -ay.y, -ay.z));
            for (int i = 0; i < 4; i++)
                t.tile[i] = tex_tile(tiles[i]);
            t.lut = l < 3 ? pb_shade[l] : 0;
            r_poly_tex(q, 4, wc, key, 0, PT_WALL, &t);
        } else {
            r_poly(q, 4, wc, key, 0);
        }
        return;
    }
#else
    (void)tiles;
#endif
    if (h >= STOREY + 96 && near < WINDOWS_FAR && m != M_STUNT) {
        int floors = (h - 96) / STOREY;
        int glass = m == M_GLASS ? COLOR(M_STEEL, l, f) : COLOR(M_GLASS, l < 3 ? l + 1 : 3, f);
        int shop = m == M_GLASS ? COLOR(M_STEEL, 0, f) : COLOR(M_GLASS, 0, f);
        s32 top = (floors - 1) * STOREY + 300;
        if (near < PANES_FAR && near > 400) {     /* (right up against a wall they cost too much) */
            V3 lo = wpt(v3(0, 0, 0), dir, 0, 40), hi = wpt(v3(0, 0, 0), dir, 0, top);
            for (s32 s = 512; s < len - 128; s += 512) {
                V3 p = wpt(a, dir, s - 40, 0), q = wpt(a, dir, s + 40, 0);
                wquad(vadd(p, lo), vadd(q, lo), vadd(q, hi), vadd(p, hi), wc, key);
            }
        }
        V3 p = wpt(a, dir, 64, 0), q = wpt(a, dir, len - 64, 0);
        for (int k = 0; k < floors; k++) {
            V3 lo = wpt(v3(0, 0, 0), dir, 0, k ? k * STOREY + 120 : 40);
            V3 hi = wpt(v3(0, 0, 0), dir, 0, k * STOREY + 300);
            wquad(vadd(p, lo), vadd(q, lo), vadd(q, hi), vadd(p, hi), k ? glass : shop, key);
        }
    }
    wquad(a, b, bt, at, wc, key);
}

static void draw_box(const Box *b)
{
    s32 x0 = b->x0 * CELL, z0 = b->z0 * CELL, w = (b->x1 - b->x0) * CELL, d = (b->z1 - b->z0) * CELL, h = b->h;
    V3 p = r_cam(v3(x0, 0, z0));
    V3 centre = cadd(p, w >> 1, h >> 1, d >> 1);
    if (!in_view(centre, ((w > d ? w : d) * 3 >> 2) + (h >> 1)))
        return;
    int f = fog_of(centre.z), m = b->mat;
    V3 c000 = p, c100 = cadd(p, w, 0, 0), c001 = cadd(p, 0, 0, d);
    V3 c010 = cadd(p, 0, h, 0), c110 = cadd(p, w, h, 0), c011 = cadd(p, 0, h, d), c111 = cadd(p, w, h, d);
    s32 cx = cam.pos.x, cy = cam.pos.y, cz = cam.pos.z;
    const u16 *bt = &world.btex[16 * (b - world.box)];
    if (cy > h) {
        V3 top[4] = {c010, c110, c111, c011};
#ifdef MERGE
        if (tex_on && m != M_STUNT) {
            int c = tile_color(world.ctex[b->x0 * CITY + b->z0], 3, COLOR(m, 3, f));
            TexFloor fl;
            tex_floor(&fl, h);
            r_poly_tex(top, 4, c, -1, 0, PT_FLOOR, &fl);
        } else
#endif
        r_poly(top, 4, COLOR(m, 3, f), -1, 0);
    }
    if (cx > x0 + w)
        wall(c100, az, d, h, m, 2, f, bt + 4);
    if (cx < x0)
        wall(c000, az, d, h, m, 0, f, bt + 12);
    if (cz > z0 + d)
        wall(c001, ax, w, h, m, 1, f, bt + 8);
    if (cz < z0)
        wall(c000, ax, w, h, m, 1, f, bt);
}

static void draw_lot(const Lot *l)
{

    s32 x0 = l->x0 * CELL, z0 = l->z0 * CELL, w = (l->x1 - l->x0) * CELL, d = (l->z1 - l->z0) * CELL;
    V3 p = r_cam(v3(x0, 0, z0));
    V3 centre = cadd(p, w >> 1, 0, d >> 1);
    if (!in_view(centre, (w > d ? w : d) * 3 >> 2))
        return;
    int f = fog_of(centre.z);
#ifdef MERGE
    if (tex_on) {
        /* textured by the island polygon under it where near; Payback's colour further off */
        V3 q[4] = {p, cadd(p, w, 0, 0), cadd(p, w, 0, d), cadd(p, 0, 0, d)};
        int i = ((l->x0 + l->x1) >> 1) * CITY + ((l->z0 + l->z1) >> 1);
        r_poly_tex(q, 4, tile_color(world.ctex[i], 3, COLOR(l->mat, 2, f)), 0, 1, PT_GROUND, &ground);
        return;
    }
#endif
    quad(p, cadd(p, w, 0, 0), cadd(p, w, 0, d), cadd(p, 0, 0, d), COLOR(l->mat, 2, f < 0 ? 0 : f), 1);
}

static void draw_ramp(const Ramp *r)
{
    s32 x0 = r->x0 * CELL, z0 = r->z0 * CELL, w = (r->x1 - r->x0) * CELL, d = (r->z1 - r->z0) * CELL;
    s32 lo = r->h0, hi = r->h1;
    /* heights at the four corners (x0z0, x1z0, x1z1, x0z1) */
    s32 h00 = lo, h10 = lo, h11 = lo, h01 = lo;
    switch (r->dir) {
    case 2: h01 = h11 = hi; break;           /* rises toward +z */
    case 3: h10 = h11 = hi; break;           /* rises toward +x */
    case 4: h00 = h10 = hi; break;           /* rises toward -z */
    default: h00 = h01 = hi; break;          /* rises toward -x */
    }
    V3 p = r_cam(v3(x0, 0, z0));
    V3 centre = cadd(p, w >> 1, hi >> 1, d >> 1);
    if (centre.z < -6000)
        return;
    int f = fog_of(centre.z), m = r->mat;
    V3 t00 = cadd(p, 0, h00, 0), t10 = cadd(p, w, h10, 0), t11 = cadd(p, w, h11, d), t01 = cadd(p, 0, h01, d);
    V3 b00 = p, b10 = cadd(p, w, 0, 0), b11 = cadd(p, w, 0, d), b01 = cadd(p, 0, 0, d);
    V3 top[4] = {t00, t10, t11, t01};
    r_poly(top, 4, COLOR(m, 3, f), -2, 0);
    s32 cx = cam.pos.x, cz = cam.pos.z;
    if (cx > x0 + w && (h10 | h11))
        quad(b10, b11, t11, t10, COLOR(m, 1, f), 0);
    if (cx < x0 && (h00 | h01))
        quad(b00, t00, t01, b01, COLOR(m, 1, f), 0);
    if (cz > z0 + d && (h01 | h11))
        quad(b01, t01, t11, b11, COLOR(m, 0, f), 0);
    if (cz < z0 && (h00 | h10))
        quad(b00, b10, t10, t00, COLOR(m, 0, f), 0);
}

/* ---- road markings and trees ---- */
#ifdef MERGE
#define DASH_FAR 6000              /* centre line dashes nearer than this */
#define ZEBRA_FAR 3500             /* zebra crossings nearer than this */
#define TREE_FAR 6000
#else
#define DASH_FAR 8000
#define ZEBRA_FAR 5000
#define TREE_FAR 8000
#endif

/* ground quad x0..x1, z0..z1 (units, relative to camera-space point o at world (ox, 0, oz)) */
static void mark(V3 o, s32 x0, s32 z0, s32 x1, s32 z1, int color)
{
    V3 q[4] = {cadd(o, x0, 2, z0), cadd(o, x1, 2, z0), cadd(o, x1, 2, z1), cadd(o, x0, 2, z1)};
    r_poly(q, 4, color, 0, 1);
}

/* the dashed centre line of a stretch of road; along is the world axis it runs along */
static void draw_line(const Line *ln)
{
#ifdef MERGE
    if (tex_on)
        return;                    /* Payback's road tiles have their own markings */
#endif
    int d = ln->dir & 1;
    s32 at = ln->at * CELL, t0 = ln->from * CELL, t1 = ln->to * CELL;
    s32 ca = d ? cam.pos.z : cam.pos.x, ct = d ? cam.pos.x : cam.pos.z;
    s32 off = at - ca;
    if (off < -DASH_FAR || off > DASH_FAR)
        return;
    /* the part within reach */
    s32 a = ct - DASH_FAR, b = ct + DASH_FAR;
    if (a < t0) a = t0;
    if (b > t1) b = t1;
    if (a >= b)
        return;
    V3 o = r_cam(d ? v3(t0, 0, at) : v3(at, 0, t0));
    int col = COLOR(M_SHIP, 2, 0);
    for (s32 t = (a - t0) & ~1023; t < b - t0; t += CELL) {
        if (d)
            mark(o, t + 256, -24, t + 768, 24, col);
        else
            mark(o, -24, t + 256, 24, t + 768, col);
    }
    /* zebra crossings where the road meets a junction: stripes across both lanes */
    s32 near = off < 0 ? -off : off;
    if (near > ZEBRA_FAR || !(ln->dir & 6))
        return;
    for (int end = 0; end < 2; end++) {
        if (!(ln->dir & (2 << end)))
            continue;
        s32 z0 = end ? t1 - t0 - 448 : 64, z1 = z0 + 384, ce = t0 + z0 + 192 - ct;
        if (ce < -ZEBRA_FAR || ce > ZEBRA_FAR)
            continue;
        for (s32 x = -896; x < 896; x += 320) {
            if (d)
                mark(o, z0, x, z1, x + 160, col);
            else
                mark(o, x, z0, x + 160, z1, col);
        }
    }
}

#ifdef MERGE
/* Payback's railings and walls along cell edges: a see-through slanted panel standing on one
   edge of a street cell (tools/mkworld.py, fence_of), or any other edge Payback stops people at
   (edge_walls). Drawn as an iron railing along the edge, so no edge stops you unseen. */
#define RAIL_FAR 5000
static void draw_fence(const Tree *t)
{
    int cx = t->x & 127, e = t->kind - 2;
    s32 x0 = cx * CELL, z0 = t->z * CELL;
    s32 dx = x0 + 512 - cam.pos.x, dz = z0 + 512 - cam.pos.z;
    if (dx < -RAIL_FAR || dx > RAIL_FAR || dz < -RAIL_FAR || dz > RAIL_FAR)
        return;
    static const s8 lo[4][4] = {{0, 0, 1, 0}, {1, 0, 1, 1}, {1, 1, 0, 1}, {0, 1, 0, 0}};
    V3 o = r_cam(v3(x0, 0, z0));
    V3 b0 = cadd(o, lo[e][0] * CELL, 0, lo[e][1] * CELL), b1 = cadd(o, lo[e][2] * CELL, 0, lo[e][3] * CELL);
    if (!in_view(v3((b0.x + b1.x) >> 1, (b0.y + b1.y) >> 1, (b0.z + b1.z) >> 1), 600))
        return;
    s32 key = (b0.z + b1.z) >> 1;
    int f = fog_of(key > 0 ? key : 0);
    V3 step = v3((b1.x - b0.x) >> 2, (b1.y - b0.y) >> 2, (b1.z - b0.z) >> 2);
    V3 up = v3(ay.x >> 4, ay.y >> 4, ay.z >> 4);                       /* (1024 units: 1.14 >> 4) */
#define UP(p, k) v3((p).x + ((up.x * (k)) >> 10), (p).y + ((up.y * (k)) >> 10), (p).z + ((up.z * (k)) >> 10))
    for (int bar = 0; bar < 2; bar++) {
        s32 h0 = bar ? 150 : 70, h1 = h0 + 22;
        V3 q[4] = {UP(b0, h0), UP(b1, h0), UP(b1, h1), UP(b0, h1)};
        r_poly(q, 4, COLOR(M_STEEL, bar ? 3 : 2, f), key, 0);
    }
    if (key < 2500) {
        V3 side = v3(step.x >> 4, step.y >> 4, step.z >> 4);           /* (16 units wide) */
        for (int k = 0; k <= 4; k++) {
            V3 p = v3(b0.x + step.x * k, b0.y + step.y * k, b0.z + step.z * k);
            V3 q[4] = {p, vadd(p, side), UP(vadd(p, side), 180), UP(p, 180)};
            r_poly(q, 4, COLOR(M_STEEL, 1, f), key, 0);
        }
    }
#undef UP
}
#endif

#ifdef MERGE
/* Payback's benches, bins and lamps (tools/mkworld.py, street_objects): Payback stops people at
   benches and bins, so they must be seen. Little boxes, turned as Payback turns them. */
#define PROP_FAR 4500
static void prop_box(s32 cx, s32 cz, s32 y0, s32 y1, s32 hx, s32 hz, s32 c, s32 s, int mat, int f)
{
    V3 ux = v3((c * hx) >> 14, 0, (s * hx) >> 14), uz = v3((-s * hz) >> 14, 0, (c * hz) >> 14);
    V3 w[8];
    static const s8 sg[4][2] = {{-1, -1}, {1, -1}, {1, 1}, {-1, 1}};
    for (int k = 0; k < 4; k++) {
        s32 x = cx + sg[k][0] * ux.x + sg[k][1] * uz.x, z = cz + sg[k][0] * ux.z + sg[k][1] * uz.z;
        w[k] = r_cam(v3(x, y0, z));
        w[k + 4] = r_cam(v3(x, y1, z));
    }
    s32 ex = cam.pos.x - cx, ez = cam.pos.z - cz;
    for (int k = 0; k < 4; k++) {
        int j = (k + 1) & 3;
        /* the side between corners k and j faces out along their average from the centre */
        s32 nx = (sg[k][0] + sg[j][0]) * ux.x + (sg[k][1] + sg[j][1]) * uz.x;
        s32 nz = (sg[k][0] + sg[j][0]) * ux.z + (sg[k][1] + sg[j][1]) * uz.z;
        if ((s64)nx * (ex - (nx >> 1)) + (s64)nz * (ez - (nz >> 1)) <= 0)
            continue;
        V3 q[4] = {w[k], w[j], w[j + 4], w[k + 4]};
        r_poly(q, 4, COLOR(mat, 1 + (k & 1), f), -1, 0);
    }
    if (cam.pos.y > y1) {
        V3 q[4] = {w[4], w[5], w[6], w[7]};
        r_poly(q, 4, COLOR(mat, 3, f), -1, 0);
    }
}

static void draw_prop(const Tree *t)
{
    s32 cx = (t->x & 127) * CELL + CELL / 2, cz = t->z * CELL + CELL / 2;
    s32 dx = cx - cam.pos.x, dz = cz - cam.pos.z;
    if (dx < -PROP_FAR || dx > PROP_FAR || dz < -PROP_FAR || dz > PROP_FAR)
        return;
    V3 p = r_cam(v3(cx, 0, cz));
    if (p.z < 64 || !in_view(cadd(p, 0, 300, 0), 800))
        return;
    int f = fog_of(p.z);
    s32 a = (t->x >> 7) << 8, c = fcos(a), s = fsin(a);
    if (t->kind == 6) {                                    /* a bench: seat and backrest */
        prop_box(cx, cz, 0, 110, 290, 90, c, s, M_PLAZA, f);
        prop_box(cx - ((-s * 80) >> 14), cz - ((c * 80) >> 14), 110, 240, 290, 18, c, s, M_PLAZA, f);
    } else if (t->kind == 7) {                             /* a bin */
        prop_box(cx, cz, 0, 200, 80, 80, c, s, M_GLASS, f);
    } else {                                               /* a street lamp */
        prop_box(cx, cz, 0, 780, 16, 16, c, s, M_STEEL, f);
        prop_box(cx + ((c * 90) >> 14), cz + ((s * 90) >> 14), 760, 800, 110, 34, c, s, M_CREAM, f);
    }
}
#endif

/* a park tree, drawn as a cut-out facing the camera: trunk, crown and a lit side */
static void draw_tree(const Tree *t)
{
#ifdef MERGE
    if (t->kind >= 6) {
        draw_prop(t);
        return;
    }
    if (t->kind >= 2) {
        draw_fence(t);
        return;
    }
#endif
    s32 x = t->x << 2, z = t->z << 2, h = t->h << 3;
    s32 dx = x - cam.pos.x, dz = z - cam.pos.z;
    if (dx < -TREE_FAR || dx > TREE_FAR || dz < -TREE_FAR || dz > TREE_FAR)
        return;
    V3 p = r_cam(v3(x, 0, z));
    if (p.z < 64 || p.z > TREE_FAR || !in_view(cadd(p, 0, h >> 1, 0), h))
        return;
    int f = fog_of(p.z);
    s32 r = h * 3 >> 3, tw = h >> 4;
    V3 c = cadd(p, 0, h - r, 0), top = cadd(p, 0, h - r, 0);
    static const s8 ring[6][2] = {{0, 16}, {14, 8}, {14, -8}, {0, -16}, {-14, -8}, {-14, 8}};
    V3 crown[6], lit[6];
    for (int i = 0; i < 6; i++) {
        crown[i] = v3(c.x + ring[i][0] * r / 16, c.y + ring[i][1] * r / 16, c.z);
        lit[i] = v3(c.x - r / 5 + ring[i][0] * r / 28, c.y + r / 5 + ring[i][1] * r / 28, c.z);
    }
    /* same depth key: the last submitted is drawn first */
    r_poly(lit, 6, COLOR(M_GRASS, t->kind ? 3 : 2, f), p.z, 0);
    r_poly(crown, 6, COLOR(M_GRASS, t->kind ? 1 : 0, f), p.z, 0);
    V3 trunk[4] = {v3(p.x - tw, p.y, p.z), v3(p.x + tw, p.y, p.z), v3(top.x + tw, top.y, top.z),
                   v3(top.x - tw, top.y, top.z)};
    r_poly(trunk, 4, COLOR(M_BRICK, 0, f), p.z, 0);
}

/* A loop: a helix of LOOP_SEG quads, red and white like a Stunt Race FX track, shaded by
   which way each piece faces. Its points are worked out once. */
static V3 loop_pts[4][LOOP_SEG + 1][2] SCRATCH;
static u8 loop_light[4][LOOP_SEG] SCRATCH;
static int loops_ready;

static void loops_prepare(void)
{
    for (int k = 0; k < world.nloop && k < 4; k++) {
        const Loop *lp = &world.loop[k];
        for (int i = 0; i <= LOOP_SEG; i++) {
            loop_point(lp, i, -lp->w / 2, &loop_pts[k][i][0]);
            loop_point(lp, i, lp->w / 2, &loop_pts[k][i][1]);
        }
        for (int i = 0; i < LOOP_SEG; i++) {
            /* the inside faces the axis: up at the bottom, down at the top */
            s32 c = fcos((i * 2 + 1) * 32768 / LOOP_SEG);
            loop_light[k][i] = c > 8000 ? 3 : c > -8000 ? 2 : 1;
        }
    }
    loops_ready = 1;
}

static void draw_loop(int k)
{
    if (!loops_ready)
        loops_prepare();
    V3 a0 = r_cam(loop_pts[k][0][0]), a1 = r_cam(loop_pts[k][0][1]);
    for (int i = 0; i < LOOP_SEG; i++) {
        V3 b0 = r_cam(loop_pts[k][i + 1][0]), b1 = r_cam(loop_pts[k][i + 1][1]);
        s32 z = (a0.z + b1.z) >> 1;
        if (z > -4000) {
            V3 q[4] = {a0, a1, b1, b0};
            r_poly(q, 4, COLOR(i & 1 ? M_SHIP : M_STUNT, loop_light[k][i], fog_of(z)), -2, 0);
        }
        a0 = b0;
        a1 = b1;
    }
}

static void draw_far(int sx, int sz)
{
    const u16 *fr = &world.far[2 * (sx * 16 + sz)];
    int m = fr[0] & 0xff;
    if (!m || m == M_ROAD)
        return;                                 /* the island polygon already looks like road */
    V3 p = r_cam_far(v3(sx * 8 * CELL, 0, sz * 8 * CELL), 2);
    s32 e = (8 * CELL) >> 2;
    V3 q[4] = {p, v3(p.x + ((ax.x * e) >> 14), p.y + ((ax.y * e) >> 14), p.z + ((ax.z * e) >> 14)), p, p};
    q[2] = v3(q[1].x + ((az.x * e) >> 14), q[1].y + ((az.y * e) >> 14), q[1].z + ((az.z * e) >> 14));
    q[3] = v3(p.x + ((az.x * e) >> 14), p.y + ((az.y * e) >> 14), p.z + ((az.z * e) >> 14));
    int f = fog_of(((q[0].z + q[2].z) >> 1) << 2);
    r_poly(q, 4, COLOR(m, 3, f < 2 ? 2 : f), -1, 1);
}

void world_draw(void)
{
    ax = v3(cam.m.r.x, cam.m.u.x, cam.m.f.x);
    ay = v3(cam.m.r.y, cam.m.u.y, cam.m.f.y);
    az = v3(cam.m.r.z, cam.m.u.z, cam.m.f.z);
#ifdef MERGE
    loops_ready = 0;               /* scratch RAM: worked out again whenever a loop is in view */
#endif
    for (unsigned i = 0; i < sizeof seen / 4; i += 4)
        seen[i] = seen[i + 1] = seen[i + 2] = seen[i + 3] = 0;
    s32 ccx = cam.pos.x >> 13, ccz = cam.pos.z >> 13;    /* camera sector */
    int alt = cam.pos.y > 0 ? cam.pos.y : 0;

    /* the island the city stands on, as one big background polygon */
    {
        const s32 e = CITY * CELL;
        V3 q[4] = {r_cam_far(v3(0, 0, 0), 3), r_cam_far(v3(e, 0, 0), 3), r_cam_far(v3(e, 0, e), 3),
                   r_cam_far(v3(0, 0, e), 3)};
#ifdef MERGE
        if (tex_on)
            r_poly_tex(q, 4, COLOR(M_ROAD, 2, alt > 6000 ? 2 : 0), 0, 1, PT_FLOOR, &ground);
        else
#endif
        r_poly(q, 4, COLOR(M_ROAD, 2, alt > 6000 ? 2 : 0), 0, 1);
    }

    /* from the air you see more of each block, so look a little less far */
    int view = VIEW_CELLS * CELL - (alt < 3000 ? alt : 3000);
#ifdef STREET_CELLS
    if (alt < 1500)
        view = STREET_CELLS * CELL;
#endif
    if (alt > 30000) view = 0;
    int vs = (view >> 13) + 1, fs = FAR_CELLS / 8;
    /* flat patches for distant sectors: only worth it from the air */
    if (alt > 2500)
        for (int sx = ccx - fs; sx <= ccx + fs; sx++)
            for (int sz = ccz - fs; sz <= ccz + fs; sz++) {
                if (sx < 0 || sz < 0 || sx > 15 || sz > 15)
                    continue;
                s32 dx = sx * 8192 + 4096 - cam.pos.x, dz = sz * 8192 + 4096 - cam.pos.z;
                s32 adx = dx < 0 ? -dx : dx, adz = dz < 0 ? -dz : dz;
                if ((adx > adz ? adx : adz) <= view - 4096)
                    continue;
                V3 c = r_cam_far(v3(sx * 8192 + 4096, 0, sz * 8192 + 4096), 3);
                const s32 rad = 750;                    /* sector half diagonal / 8 */
                if (c.z < -rad || FOCAL * c.x - 121 * c.z > rad * 182 || -FOCAL * c.x - 121 * c.z > rad * 182 ||
                    FOCAL * c.y - 81 * c.z > rad * 158 || -FOCAL * c.y - 81 * c.z > rad * 158)
                    continue;
                draw_far(sx, sz);
            }
    if (!view)
        return;
    for (int sx = ccx - vs; sx <= ccx + vs; sx++)
        for (int sz = ccz - vs; sz <= ccz + vs; sz++) {
            if (sx < 0 || sz < 0 || sx > 15 || sz > 15)
                continue;
            s32 dx = sx * 8192 + 4096 - cam.pos.x, dz = sz * 8192 + 4096 - cam.pos.z;
            s32 adx = dx < 0 ? -dx : dx, adz = dz < 0 ? -dz : dz;
            if ((adx > adz ? adx : adz) > view - 4096)
                continue;
            V3 c = r_cam(v3(sx * 8192 + 4096, 1500, sz * 8192 + 4096));
            const s32 rad = 7000;
            if (c.z < -rad || FOCAL * c.x - 121 * c.z > rad * 182 || -FOCAL * c.x - 121 * c.z > rad * 182 ||
                FOCAL * c.y - 81 * c.z > rad * 158 || -FOCAL * c.y - 81 * c.z > rad * 158)
                continue;
            int s = sx * 16 + sz;
            const u16 *it = &world.item[world.sector[2 * s]];
            for (int k = world.sector[2 * s + 1]; k > 0; k--, it++) {
                int kind = *it >> 13, i = *it & 0x1fff;
                switch (kind) {
                case 0:
                    if (first_visit(i)) draw_box(&world.box[i]);
                    break;
                case 1:
                    if (first_visit(SEEN_LOT + i)) draw_lot(&world.lot[i]);
                    break;
                case 2:
                    if (first_visit(SEEN_RAMP + i)) draw_ramp(&world.ramp[i]);
                    break;
                case 4:
                    if (first_visit(SEEN_LINE + i)) draw_line(&world.line[i]);
                    break;
                case 5:
                    if (first_visit(SEEN_TREE + i)) draw_tree(&world.tree[i]);
                    break;
                }
            }
        }
    for (int i = 0; i < world.nloop && i < 4; i++) {
        const Loop *lp = &world.loop[i];
        s32 dx = lp->x - cam.pos.x, dz = lp->z - cam.pos.z;
        if (dx > -view && dx < view && dz > -view && dz < view)
            draw_loop(i);
    }
}
