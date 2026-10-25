/* Rigid body dynamics and contact with the world: the city's ground and buildings, the
   loops, the space station and asteroids. See physics.h for the units. */
#include "physics.h"
#include "world.h"

V3 station_pos;
Rock rocks[NROCK];
int nrocks;
u8 water_floats, ramp_grip, ramp_pass, ship_hull;

#define STEP (192 << FX)              /* a deck's side taller than this is a wall */
/* A point less than this under the ground is pushed up onto it, not out of a wall: Payback
   tests its walls at a man's knee, 0x40 of its steps (512 units) up, so anything lower is
   stepped onto, and a car's lowest points ride 38 units up (tools/mkworld.py KERB) */
#define KERB (440 << FX)
#define WALL_T 128                    /* half thickness of an edge wall (units) */
#define RAMP_STEP (600 << FX)         /* off a ramp a car goes up onto a floor this much higher (car.c) */

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

s32 body_contact(Body *b, V3 r, const Hit *h, s32 bounce, s32 friction)
{
    V3 vp = body_point_vel(b, r);
    s32 vn = vdot(vp, h->n);
    s32 push = h->dist < (40 << FX) ? h->dist : 40 << FX;
    b->pos = vadd(b->pos, vscale(h->n, push));
    if (vn < 0) {
        s32 me = body_eff_mass(b, r, h->n);
        s32 j = (((-vn) * (256 + bounce)) >> 8) * me >> 8;
        V3 J = vscale(h->n, j);
        V3 vt = vsub(vp, vscale(h->n, vn));
        s32 vtl = vlen(vt);
        if (vtl > 16) {
            s32 jt = (vtl * me) >> 8, lim = (j * friction) >> 8;
            if (jt > lim) jt = lim;
            J = vsub(J, vscale(vnorm(vt), jt));
        }
        body_impulse(b, r, J);
    }
    return -vn;
}

int body_collide(Body *b, V3 r, s32 bounce, s32 friction, s32 *impact)
{
    V3 p = vadd(b->pos, v3(r.x << FX, r.y << FX, r.z << FX));
    Hit h;
    if (!penetrate(p, &h))
        return 0;
    *impact = body_contact(b, r, &h, bounce, h.kind == SURF_RAMP ? 0 : friction);
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
    case SHAPE_WATER: return (water_floats ? c->hi : c->lo) << FX;     /* (things sink in it) */
    default: return c->hi << FX;
    }
}

/* deck k over the cell under p (fine): its bottom and top there (fine), as world_deck */
static int deck_at(V3 p, int k, s32 *bottom, s32 *top)
{
    int s = world_deck(p.x >> FX, p.z >> FX, k, bottom, top);
    if (!s)
        return 0;
    *bottom <<= FX;
    *top <<= FX;
    return s;
}

/* the deck whose top is the surface under p (fine): the higher one p is over the middle of (a
   second deck is only ever over a first); as world_deck, with which one in *k */
static int deck_under(V3 p, int *k, s32 *top)
{
    s32 db, ub, ut;
    int s = deck_at(p, 0, &db, top), s2;
    if (!s)
        return 0;
    if ((s2 = deck_at(p, 1, &ub, &ut)) && p.y > ((ub + ut) >> 1)) {
        *k = 1;
        *top = ut;
        return s2;
    }
    *k = 0;
    return p.y > ((db + *top) >> 1) ? s : 0;
}

/* the deck p (fine) is inside: 1 with its bottom and top there (fine) */
static int deck_in(V3 p, s32 *bottom, s32 *top)
{
    if (!deck_at(p, 0, bottom, top))
        return 0;
    if (p.y > *bottom && p.y < *top)
        return 1;
    return deck_at(p, 1, bottom, top) && p.y > *bottom && p.y < *top;
}

s32 surface_fine(V3 p)
{
    s32 dt;
    int k;
    if (deck_under(p, &k, &dt))
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
    if (p.y >= (world.top << FX) + 8 * max)   /* over everything the city has: the station's deck alone is left */
        goto station;
    V3 n = world_normal(p.x >> FX, p.z >> FX);
    s32 g = ground_fine(p.x, p.z), dt;
    int k, ds = deck_under(p, &k, &dt);
    if (ds) {
        g = dt;                                   /* on a bridge deck: flat, or its ramp */
        n = ds > 1 ? world_deck_normal(p.x >> FX, p.z >> FX, k) : v3(0, ONE, 0);
    }
    s32 un = vdot(up, n);
    if (un > 6000) {
        s32 s = p.y - g;
        /* (over a steep slope the gap straight down is much more than the gap square to it) */
        if (s > -max && s < 8 * max) {
            s32 t = s < 2 * max ? s * n.y / un : ((s >> 4) * n.y / un) << 4;
            if (t < best) {
                best = t;
                h->n = n;
                h->kind = !ds && ramp_grip && n.y < 16000 ? SURF_RAMP : SURF_GROUND;
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
station:;
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

#ifdef MERGE
int sw_solid(V3 p, Hit *h);
extern u8 sw_moon_near;            /* spacewalk.c: the camera is within reach of the moon's box (nothing out there else is asked) */
#endif
/* the station and the asteroids (far above the city: Thumb, in ROM) */
static COLD int space_hit(V3 p, Hit *h)
{
    s32 px = p.x >> FX, py = p.y >> FX, pz = p.z >> FX;
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
    if ((dx > 29000 || dx < -29000 || dz > 29000 || dz < -29000 || dy > 12000 || dy < -12000))
        goto moon;                                          /* (the rocks all lie within that of the station) */
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
moon:
#ifdef MERGE
    return sw_moon_near ? sw_solid(p, h) : 0;      /* the moon and its rocks (spacewalk.c), when the camera is by them */
#else
    return 0;
#endif
}

/* a railing drawn along edge k (-z, +x, +z, -x) of the cell under p (fine), p's height in its
   slab (as a wall's from its foot). mkworld.py lists each as a tree of the cell it stops you in,
   either side of the edge; seen from across a one way one is its top rail alone (draw_fence).
   (A sector lists its trees last, but for loops.) */
static int rail_on(V3 p, int k)
{
    static const s8 step[4][2] = {{0, -1}, {1, 0}, {0, 1}, {-1, 0}};
    s32 y = p.y >> FX;
    for (int side = 0; side < 2; side++) {
        int cx = (p.x >> (FX + 10)) + (side ? step[k][0] : 0), cz = (p.z >> (FX + 10)) + (side ? step[k][1] : 0);
        int kind = 2 + (k ^ side << 1);
        if (cx < 0 || cz < 0 || cx >= CITY || cz >= CITY)
            continue;
        const u16 *sec = &world.sector[2 * ((cx >> 3) * 16 + (cz >> 3))], *it = &world.item[sec[0] + sec[1]];
        for (int n = sec[1]; n--;) {
            int what = *--it >> 13;
            if (what == 3)
                continue;
            if (what != 5)
                break;
            const Tree *t = &world.tree[*it & 0x1fff];
            s32 b;
            if (t->kind == kind && t->z == cz && (t->x & 127) == cx && y < (b = RAIL_BASE(t)) + 192 &&
                y > b + (side && t->x >> 7 ? 118 : -32))
                return 1;
        }
    }
    return 0;
}

int penetrate(V3 p, Hit *h)
{
    s32 db, dt;
    if (p.y > world.top << FX)             /* over the highest thing the city has: only the station and the rocks are left */
        return (p.y >> FX) > SPACE_LO ? space_hit(p, h) : 0;
    if (deck_in(p, &db, &dt)) {
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
                if (deck_in(q, &qb, &qt))
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
        if (ramp_grip) {
            u8 sh = world_cell(p.x >> FX, p.z >> FX)->shape;
            int slope = sh >= 2 && sh <= 5;
            if (ramp_pass && (slope || (ramp_pass > 1 && d <= RAMP_STEP)))
                return 0;
            if (slope) {
                /* (in from its side as well: Payback stands a car on a ramp it lets it into) */
                h->n = v3(0, ONE, 0);
                h->dist = d;
                h->kind = SURF_RAMP;
                return 1;
            }
        }
        if (d <= KERB) {
            h->n = world_normal(p.x >> FX, p.z >> FX);
            h->dist = (d * h->n.y) >> 14;
            h->kind = SURF_GROUND;
            return 1;
        }
        /* inside a building: out through the nearest face that has open space beyond it */
        s32 fx = (p.x >> FX) & 1023, fz = (p.z >> FX) & 1023, best = 0x7fffffff;
        const s32 c = CELL << FX, top = p.y + KERB;
        h->n = v3(0, ONE, 0);
        if (ground_fine(p.x - c, p.z) <= top && fx + 1 < best) best = fx + 1, h->n = v3(-ONE, 0, 0);
        if (ground_fine(p.x + c, p.z) <= top && 1024 - fx < best) best = 1024 - fx, h->n = v3(ONE, 0, 0);
        if (ground_fine(p.x, p.z - c) <= top && fz + 1 < best) best = fz + 1, h->n = v3(0, 0, -ONE);
        if (ground_fine(p.x, p.z + c) <= top && 1024 - fz < best) best = 1024 - fz, h->n = v3(0, 0, ONE);
        h->dist = best == 0x7fffffff ? d : best << FX;
        h->kind = SURF_GROUND;
        return 1;
    }
    /* Payback's walls along cell edges (railings, fences, a block's open side over a kerb): a
       slab WALL_T deep each side of the edge, out on the side the point is in (a car moves well
       under WALL_T a tick, so it is never carried out the far side) */
    s32 wl, wh;
    int wb = world_wall(p.x >> FX, p.z >> FX, &wl, &wh), rb = ship_hull ? world_rails(p.x >> FX, p.z >> FX) : 0;
    if (rb || (wb && !ship_hull && p.y > ((wl - 32) << FX) && p.y < (wh << FX))) {
        s32 fx = (p.x >> FX) & 1023, fz = (p.z >> FX) & 1023;
        s32 d[4] = {fz, 1023 - fx, 1023 - fz, fx};
        static const s8 in[4][2] = {{0, 1}, {-1, 0}, {0, -1}, {1, 0}};
        /* (the Arwing: these are the car's walls, as tall as Payback's record across the edge and
           one range for the whole cell. It meets what we draw there instead: the railings, on any
           edge they are drawn along, marked by mkworld.py whether or not the car has a wall there,
           and the buildings and decks themselves) */
        int best = -1;
        for (int k = 0; k < 4; k++)
            if (d[k] < WALL_T && (best < 0 || d[k] < d[best]) && (ship_hull ? rb >> k & 1 && rail_on(p, k) : wb >> k & 1))
                best = k;
        if (best >= 0) {
            h->n = v3(in[best][0] * ONE, 0, in[best][1] * ONE);
            h->dist = (WALL_T - d[best]) << FX;
            h->kind = SURF_GROUND;
            return 1;
        }
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
    if ((p.y >> FX) > SPACE_LO)
        return space_hit(p, h);
    return 0;
}
