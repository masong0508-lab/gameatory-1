/* Rigid body dynamics and contact with the world: the city's ground and buildings, the
   loops, the space station and asteroids. See physics.h for the units. */
#include "physics.h"
#include "world.h"

V3 station_pos;
Rock rocks[16];
int nrocks;

#define STEP (192 << FX)              /* taller than this is a wall, not a kerb */

static s32 clampi(s32 v, s32 lo, s32 hi) { return v < lo ? lo : v > hi ? hi : v; }
static V3 vclamp(V3 v, s32 m) { return v3(clampi(v.x, -m, m), clampi(v.y, -m, m), clampi(v.z, -m, m)); }

/* local spin change (1.18) from a raw local torque or angular impulse r x f */
static V3 spin(const Body *b, V3 rl, V3 fl)
{
    s32 tx = clampi((rl.y * fl.z - rl.z * fl.y) >> 4, -1000000, 1000000);
    s32 ty = clampi((rl.z * fl.x - rl.x * fl.z) >> 4, -1000000, 1000000);
    s32 tz = clampi((rl.x * fl.y - rl.y * fl.x) >> 4, -1000000, 1000000);
    return v3((tx * b->inv_i[0]) >> 10, (ty * b->inv_i[1]) >> 10, (tz * b->inv_i[2]) >> 10);
}

void body_force(Body *b, V3 r, V3 f)
{
    f = vclamp(f, 20000);
    b->acc = vadd(b->acc, f);
    b->alpha = vadd(b->alpha, spin(b, mworld(&b->m, r), mworld(&b->m, f)));
}

void body_impulse(Body *b, V3 r, V3 j)
{
    j = vclamp(j, 60000);
    b->vel = vadd(b->vel, j);
    V3 dw = vclamp(spin(b, mworld(&b->m, r), mworld(&b->m, j)), 60000);
    b->w = vclamp(vadd(b->w, mlocal(&b->m, dw)), 50000);
}

V3 body_point_vel(const Body *b, V3 r)
{
    V3 w = b->w;
    return v3(b->vel.x + ((w.y * r.z - w.z * r.y) >> 10),
              b->vel.y + ((w.z * r.x - w.x * r.z) >> 10),
              b->vel.z + ((w.x * r.y - w.y * r.x) >> 10));
}

s32 body_eff_mass(const Body *b, V3 r, V3 n)
{
    V3 c = mworld(&b->m, vcross(r, n));
    s32 s = 256 + ((((c.x * c.x) >> 4) * b->inv_i[0]) >> 12) + ((((c.y * c.y) >> 4) * b->inv_i[1]) >> 12) +
            ((((c.z * c.z) >> 4) * b->inv_i[2]) >> 12);
    return 65536 / s;
}

void body_integrate(Body *b)
{
    b->vel = vclamp(vadd(b->vel, b->acc), 110000);
    b->acc = v3(0, 0, 0);
    b->pos = vadd(b->pos, b->vel);
    V3 a = vclamp(b->alpha, 60000);
    b->alpha = v3(0, 0, 0);
    b->w = vclamp(vadd(b->w, mlocal(&b->m, a)), 50000);
    mrotate(&b->m, vshr(b->w, 4));
}

int body_collide(Body *b, V3 r, s32 bounce, s32 friction, s32 *impact)
{
    V3 p = vadd(b->pos, v3(r.x << FX, r.y << FX, r.z << FX));
    Hit h;
    if (!penetrate(p, &h))
        return 0;
    V3 vp = body_point_vel(b, r);
    s32 vn = vdot(vp, h.n);
    *impact = -vn;
    s32 push = h.dist < (40 << FX) ? h.dist : 40 << FX;
    b->pos = vadd(b->pos, vscale(h.n, push));
    if (vn < 0) {
        s32 me = body_eff_mass(b, r, h.n);
        s32 j = (((-vn) * (256 + bounce)) >> 8) * me >> 8;
        V3 J = vscale(h.n, j);
        V3 vt = vsub(vp, vscale(h.n, vn));
        s32 vtl = vlen(vt);
        if (vtl > 16) {
            s32 jt = (vtl * me) >> 8, lim = (j * friction) >> 8;
            if (jt > lim) jt = lim;
            J = vsub(J, vscale(vnorm(vt), jt));
        }
        body_impulse(b, r, J);
    }
    return 1;
}

s32 space_factor(s32 y)
{
    if (y <= SPACE_LO) return 0;
    if (y >= SPACE_HI) return ONE;
    return (y - SPACE_LO) * (ONE / 64) / ((SPACE_HI - SPACE_LO) / 64);
}

/* ---- surfaces ---- */

s32 ground_fine(s32 x, s32 z)
{
    if (x < 0 || z < 0 || x >= (CITY * CELL) << FX || z >= (CITY * CELL) << FX)
        return 0;
    const Cell *c = &world.cell[(x >> 18) * CITY + (z >> 18)];
    s32 fx = x & 0x3ffff, fz = z & 0x3ffff, d = c->hi - c->lo;
    switch (c->shape) {
    case 2: return (c->lo << FX) + ((d * fz) >> 10);
    case 3: return (c->lo << FX) + ((d * fx) >> 10);
    case 4: return (c->lo << FX) + ((d * (0x40000 - fz)) >> 10);
    case 5: return (c->lo << FX) + ((d * (0x40000 - fx)) >> 10);
    default: return c->hi << FX;
    }
}

/* a deck over the cell under p (fine): 1 with its bottom and top (fine) */
static int deck_at(V3 p, s32 *bottom, s32 *top)
{
    if (!world_deck(p.x >> FX, p.z >> FX, bottom, top))
        return 0;
    *bottom <<= FX;
    *top <<= FX;
    return 1;
}

s32 surface_fine(V3 p)
{
    s32 db, dt;
    if (deck_at(p, &db, &dt) && p.y > ((db + dt) >> 1))
        return dt;
    return ground_fine(p.x, p.z);
}

/* Where p (fine) is relative to a loop. On the track's footprint returns 1 with the gap from
   p out to the track surface (fine, positive inside the loop), the surface normal (pointing
   in, toward the loop's axis) and the angle around the loop. */
static int loop_probe(const Loop *lp, V3 p, s32 *gap, V3 *n, u16 *ang)
{
    s32 dx = p.x - (lp->x << FX), dz = p.z - (lp->z << FX), along, lat;
    switch (lp->dir & 3) {
    case 0: along = dz; lat = dx; break;
    case 1: along = dx; lat = -dz; break;
    case 2: along = -dz; lat = -dx; break;
    default: along = -dx; lat = dz; break;
    }
    s32 r = lp->r << FX, w = lp->w << FX;
    if (along > r + (256 << FX) || along < -r - (256 << FX) || lat < -w || lat > 2 * w ||
        p.y > 2 * r + (256 << FX))
        return 0;
    s32 ax = along >> 4, ay = (p.y - r) >> 4;            /* 1/16 units */
    s32 rho = (s32)isqrt((u32)(ax * ax) + (u32)(ay * ay));
    if (rho < (lp->r << 3))
        return 0;
    u16 a = fatan2(ax, -ay);
    s32 off = lat - ((lp->w * a) >> 8);
    if (off < -(w >> 1) || off > (w >> 1))
        return 0;
    *gap = ((lp->r << 4) - rho) << 4;
    s32 na = -ax * ONE / rho, nu = -ay * ONE / rho;
    switch (lp->dir & 3) {
    case 0: *n = v3(0, nu, na); break;
    case 1: *n = v3(na, nu, 0); break;
    case 2: *n = v3(0, nu, -na); break;
    default: *n = v3(-na, nu, 0); break;
    }
    *ang = a;
    return 1;
}

int ray_surface(V3 p, V3 up, s32 max, Hit *h)
{
    s32 best = max + 1;
    int found = 0;
    V3 n = world_normal(p.x >> FX, p.z >> FX);
    s32 g = ground_fine(p.x, p.z), db, dt;
    if (deck_at(p, &db, &dt) && p.y > ((db + dt) >> 1)) {
        g = dt;                                   /* on a bridge deck: flat */
        n = v3(0, ONE, 0);
    }
    s32 un = vdot(up, n);
    if (un > 6000) {
        s32 s = p.y - g;
        if (s > -max && s < 2 * max) {
            s32 t = s * n.y / un;
            if (t < best) {
                best = t;
                h->n = n;
                h->kind = SURF_GROUND;
                found = 1;
            }
        }
    }
    for (int i = 0; i < world.nloop; i++) {
        s32 gap;
        u16 a;
        V3 ln;
        if (!loop_probe(&world.loop[i], p, &gap, &ln, &a))
            continue;
        un = vdot(up, ln);
        if (un > 6000 && gap > -max && gap < 2 * max) {
            s32 t = gap * ONE / un;
            if (t < best) {
                best = t;
                h->n = ln;
                h->kind = SURF_LOOP;
                h->ang = a;
                h->idx = i;
                found = 1;
            }
        }
    }
    /* the station's deck */
    s32 sx = (p.x >> FX) - station_pos.x, sz = (p.z >> FX) - station_pos.z;
    if (up.y > 6000 && sx > -HUB_HX && sx < HUB_HX && sz > -HUB_HZ && sz < HUB_HZ) {
        s32 s = p.y - ((station_pos.y + HUB_HY) << FX);
        if (s > -max && s < 2 * max) {
            s32 t = s * ONE / up.y;
            if (t < best) {
                best = t;
                h->n = v3(0, ONE, 0);
                h->kind = SURF_DECK;
                found = 1;
            }
        }
    }
    if (!found || best > max || best < -(max >> 1))
        return 0;
    h->dist = best;
    return 1;
}

int penetrate(V3 p, Hit *h)
{
    s32 db, dt;
    if (deck_at(p, &db, &dt) && p.y > db && p.y < dt) {
        /* inside a bridge deck: out over the top or down under it, whichever is nearer ... */
        h->kind = SURF_GROUND;
        if (dt - p.y > STEP) {
            /* ... unless it came in from the side (a parapet, a wall): then out sideways,
               through the nearest edge of the cell that has no deck at this height beyond it,
               when that is deep in the deck or the cell beyond has a floor about here (a car
               on a bridge running into its parapet sits right on the parapet's bottom) */
            s32 cx = p.x & ((CELL << FX) - 1), cz = p.z & ((CELL << FX) - 1);
            s32 gap[4] = {cx, (CELL << FX) - cx, cz, (CELL << FX) - cz};
            static const s8 dir[4][2] = {{-1, 0}, {1, 0}, {0, -1}, {0, 1}};
            int best = -1;
            for (int k = 0; k < 4; k++) {
                V3 q = v3(p.x + dir[k][0] * (gap[k] + (8 << FX)), p.y, p.z + dir[k][1] * (gap[k] + (8 << FX)));
                s32 qb, qt;
                if (deck_at(q, &qb, &qt) && p.y > qb && p.y < qt)
                    continue;
                if (p.y - db <= STEP) {
                    s32 f = surface_fine(q);
                    if (f > p.y + STEP || f < p.y - 2 * STEP)
                        continue;
                }
                if (best < 0 || gap[k] < gap[best])
                    best = k;
            }
            if (best >= 0) {
                h->n = v3(dir[best][0] * ONE, 0, dir[best][1] * ONE);
                h->dist = gap[best] + (8 << FX);
                return 1;
            }
        }
        if (dt - p.y <= STEP || dt - p.y < p.y - db) {
            h->n = v3(0, ONE, 0);
            h->dist = dt - p.y;
        } else {
            h->n = v3(0, -ONE, 0);
            h->dist = p.y - db;
        }
        return 1;
    }
    s32 g = ground_fine(p.x, p.z);
    if (p.y < g) {
        s32 d = g - p.y;
        if (d <= STEP) {
            h->n = world_normal(p.x >> FX, p.z >> FX);
            h->dist = (d * h->n.y) >> 14;
            h->kind = SURF_GROUND;
            return 1;
        }
        /* inside a building: out through the nearest face that has open space beyond it */
        s32 fx = (p.x >> FX) & 1023, fz = (p.z >> FX) & 1023, best = 0x7fffffff;
        const s32 c = CELL << FX, top = p.y + STEP;
        h->n = v3(0, ONE, 0);
        if (ground_fine(p.x - c, p.z) <= top && fx + 1 < best) best = fx + 1, h->n = v3(-ONE, 0, 0);
        if (ground_fine(p.x + c, p.z) <= top && 1024 - fx < best) best = 1024 - fx, h->n = v3(ONE, 0, 0);
        if (ground_fine(p.x, p.z - c) <= top && fz + 1 < best) best = fz + 1, h->n = v3(0, 0, -ONE);
        if (ground_fine(p.x, p.z + c) <= top && 1024 - fz < best) best = 1024 - fz, h->n = v3(0, 0, ONE);
        h->dist = best == 0x7fffffff ? d : best << FX;
        h->kind = SURF_GROUND;
        return 1;
    }
    for (int i = 0; i < world.nloop; i++) {
        s32 gap;
        u16 a;
        if (loop_probe(&world.loop[i], p, &gap, &h->n, &a) && gap < 0 && gap > -(160 << FX)) {
            h->dist = -gap;
            h->kind = SURF_LOOP;
            h->ang = a;
            h->idx = i;
            return 1;
        }
    }
    s32 px = p.x >> FX, py = p.y >> FX, pz = p.z >> FX;
    if (py > SPACE_LO) {
        s32 dx = px - station_pos.x, dy = py - station_pos.y, dz = pz - station_pos.z;
        s32 ox = HUB_HX - (dx < 0 ? -dx : dx), oy = HUB_HY - (dy < 0 ? -dy : dy), oz = HUB_HZ - (dz < 0 ? -dz : dz);
        if (ox > 0 && oy > 0 && oz > 0) {
            /* the docking bay is open space; its floor, ceiling and walls push back into it */
            s32 bx = BAY_HX - (dx < 0 ? -dx : dx), b0 = dy - BAY_Y0, b1 = BAY_Y1 - dy, bz = dz - BAY_Z0;
            if (bx > 0 && b0 > 0 && b1 > 0 && bz > 0)
                return 0;
            s32 best;
            h->kind = SURF_DECK;
            if (oy <= ox && oy <= oz) best = oy, h->n = v3(0, dy < 0 ? -ONE : ONE, 0);
            else if (ox <= oz) best = ox, h->n = v3(dx < 0 ? -ONE : ONE, 0, 0);
            else best = oz, h->n = v3(0, 0, dz < 0 ? -ONE : ONE);
            if (b0 > 0 && b1 > 0 && bz > 0 && -bx < best)
                best = -bx, h->n = v3(dx < 0 ? ONE : -ONE, 0, 0);
            if (bx > 0 && bz > 0 && b0 <= 0 && -b0 < best)
                best = -b0, h->n = v3(0, ONE, 0);
            if (bx > 0 && bz > 0 && b1 <= 0 && -b1 < best)
                best = -b1, h->n = v3(0, -ONE, 0);
            if (bx > 0 && b0 > 0 && b1 > 0 && bz <= 0 && -bz < best)
                best = -bz, h->n = v3(0, 0, ONE);
            h->dist = (best + 1) << FX;
            return 1;
        }
        for (int i = 0; i < nrocks; i++) {
            V3 d = vsub(v3(px, py, pz), rocks[i].c);
            s32 r = rocks[i].r;
            if (d.x > r || d.x < -r || d.y > r || d.y < -r || d.z > r || d.z < -r)
                continue;
            s32 l = vlen(d);
            if (l < r && l > 0) {
                h->dist = (r - l) << FX;
                h->n = vnorm(d);
                h->kind = SURF_ROCK;
                return 1;
            }
        }
    }
    return 0;
}
