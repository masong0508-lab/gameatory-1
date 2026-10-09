/* Drawing the city: buildings, ground patches, ramps and loops near the camera, and one
   flat patch per distant sector. */
#include "world.h"
#include "render.h"
#include "palette.h"
#include "loops.h"

static u8 box_seen[2048] EWRAM_BSS, lot_seen[2560] EWRAM_BSS, ramp_seen[512] EWRAM_BSS;
static u8 stamp;

#define VIEW_CELLS 18
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

static void draw_box(const Box *b)
{
    s32 x0 = b->x0 * CELL, z0 = b->z0 * CELL, w = (b->x1 - b->x0) * CELL, d = (b->z1 - b->z0) * CELL, h = b->h;
    V3 p = r_cam(v3(x0, 0, z0));
    V3 centre = cadd(p, w >> 1, h >> 1, d >> 1);
    if (!in_view(centre, ((w > d ? w : d) * 3 >> 2) + (h >> 1)))
        return;
    int f = fog_of(centre.z), m = b->mat;
    V3 c000 = p, c100 = cadd(p, w, 0, 0), c001 = cadd(p, 0, 0, d), c101 = cadd(p, w, 0, d);
    V3 c010 = cadd(p, 0, h, 0), c110 = cadd(p, w, h, 0), c011 = cadd(p, 0, h, d), c111 = cadd(p, w, h, d);
    s32 cx = cam.pos.x, cy = cam.pos.y, cz = cam.pos.z;
    if (cy > h)
        quad(c010, c110, c111, c011, COLOR(m, 3, f), 0);
    if (cx > x0 + w)
        quad(c100, c101, c111, c110, COLOR(m, 2, f), 0);
    if (cx < x0)
        quad(c000, c010, c011, c001, COLOR(m, 0, f), 0);
    if (cz > z0 + d)
        quad(c001, c011, c111, c101, COLOR(m, 1, f), 0);
    if (cz < z0)
        quad(c000, c100, c110, c010, COLOR(m, 1, f), 0);
}

static void draw_lot(const Lot *l)
{

    s32 x0 = l->x0 * CELL, z0 = l->z0 * CELL, w = (l->x1 - l->x0) * CELL, d = (l->z1 - l->z0) * CELL;
    V3 p = r_cam(v3(x0, 0, z0));
    V3 centre = cadd(p, w >> 1, 0, d >> 1);
    if (!in_view(centre, (w > d ? w : d) * 3 >> 2))
        return;
    int f = fog_of(centre.z);
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

/* A loop: a helix of LOOP_SEG quads, red and white like a Stunt Race FX track, shaded by
   which way each piece faces. Its points are worked out once. */
static V3 loop_pts[4][LOOP_SEG + 1][2] EWRAM_BSS;
static u8 loop_light[4][LOOP_SEG] EWRAM_BSS;
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
    if (!loops_ready)
        loops_prepare();
    if (++stamp == 0) {
        memset(box_seen, 0, sizeof box_seen);
        memset(lot_seen, 0, sizeof lot_seen);
        memset(ramp_seen, 0, sizeof ramp_seen);
        stamp = 1;
    }
    s32 ccx = cam.pos.x >> 13, ccz = cam.pos.z >> 13;    /* camera sector */
    int alt = cam.pos.y > 0 ? cam.pos.y : 0;

    /* the island the city stands on, as one big background polygon */
    {
        const s32 e = CITY * CELL;
        V3 q[4] = {r_cam_far(v3(0, 0, 0), 3), r_cam_far(v3(e, 0, 0), 3), r_cam_far(v3(e, 0, e), 3),
                   r_cam_far(v3(0, 0, e), 3)};
        r_poly(q, 4, COLOR(M_ROAD, 2, alt > 6000 ? 2 : 0), 0, 1);
    }

    /* from the air you see more of each block, so look a little less far */
    int view = VIEW_CELLS * CELL - (alt < 3000 ? alt : 3000);
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
                    if (box_seen[i] != stamp) { box_seen[i] = stamp; draw_box(&world.box[i]); }
                    break;
                case 1:
                    if (lot_seen[i] != stamp) { lot_seen[i] = stamp; draw_lot(&world.lot[i]); }
                    break;
                case 2:
                    if (ramp_seen[i] != stamp) { ramp_seen[i] = stamp; draw_ramp(&world.ramp[i]); }
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
