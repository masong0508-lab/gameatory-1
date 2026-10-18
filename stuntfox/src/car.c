/* Car physics. Every force acts at the point where it really happens: springs and tyres at
   the four contact patches, impacts at the corner that hits, so the car pitches, rolls,
   flips and falls off loops by itself. Nothing is scripted. */
#include "car.h"
#include "gba.h"
#include "loops.h"
#include "world.h"

const V3 car_wheel[4] = {
    {-110, -10, 160}, {110, -10, 160}, {-110, -10, -150}, {110, -10, -150},
};
static const V3 hull[] = {
    {-125, -38, 240}, {125, -38, 240}, {-128, -38, -225}, {128, -38, -225},
    {-110, 12, 150}, {110, 12, 150}, {-118, 32, -225}, {118, 32, -225}, {0, 62, -40},
};
#define NHULL (sizeof hull / sizeof hull[0])

#ifdef MERGE
/* In Payback we drive whatever vehicle we took, drawn at its own size: the hull, the wheels and the
   footprint against posts are the saloon's (drawn 114 x 235 x 235: half width, ahead, behind)
   stretched to it, 256 = the saloon's, so a bus stops at its own nose. merge.c's car_scale reads
   it from the vehicle's descriptor, which build.py sizes from the model merge.c draws for it. */
static V3 sized(const u16 *s, V3 p) { return v3(p.x * s[0] >> 8, p.y, p.z * s[p.z > 0 ? 1 : 2] >> 8); }
#else
static void car_scale(u16 s[3]) { s[0] = s[1] = s[2] = 256; }
static V3 sized(const u16 *s, V3 p) { (void)s; return p; }
#endif

#define K_SPRING 1300              /* per fine unit of compression, /65536 */
#define C_DAMP 4800
#define BUMP (44 << FX)            /* bump stop starts here */
#define ENGINE 150                 /* full-throttle drive at standstill, all four wheels */
#define VMAX (112 << FX)
#define BRAKE 220
#define BOOST_THRUST 150
#define K_LAT 10000                /* lateral tyre stiffness, /65536 of slip per tick */
#define MU_FRONT 300               /* grip, 256 = 1 */
#define MU_REAR 280
#define MU_DRIFT 120

static s32 iabs(s32 v) { return v < 0 ? -v : v; }
static s32 clampi(s32 v, s32 lo, s32 hi) { return v < lo ? lo : v > hi ? hi : v; }

/* Payback stops cars at its street objects, lamps, trees, benches and bins, each a circle on its
   floor (tools/mkworld.py, street_objects). A lamp post is thin enough to pass between hull
   points, so each circle against the car's footprint; returns the hardest impact. */
static s32 car_posts(Body *b, const u16 *sz)
{
    static const s16 tall[9] = {0, 0, 0, 0, 0, 0, 240, 200, 800};     /* bench, bin, lamp (as drawn) */
    const M3 *m = &b->m;
    s32 px = b->pos.x >> FX, py = b->pos.y >> FX, pz = b->pos.z >> FX, worst = 0;
    V3 fr = sized(sz, v3(128, 0, 240)), bk = sized(sz, v3(128, 0, -225));
    s32 hw = fr.x, ah = fr.z, bh = -bk.z;               /* (the hull's footprint) */
    for (s32 sx = (px - 768) >> 13; sx <= (px + 768) >> 13; sx++)
        for (s32 sz = (pz - 768) >> 13; sz <= (pz + 768) >> 13; sz++) {
            if (sx < 0 || sz < 0 || sx > 15 || sz > 15)
                continue;
            /* (mkworld.py lists a sector's trees after its boxes, lots, ramps and lines, with
               only its loops after them: from the end, until something else) */
            const u16 *sec = &world.sector[2 * (sx * 16 + sz)], *it = &world.item[sec[0] + sec[1]];
            for (int n = sec[1]; n--;) {
                int kind = *--it >> 13;
                if (kind == 3)
                    continue;
                if (kind != 5)
                    break;
                const Tree *t = &world.tree[*it & 0x1fff];
                s32 r = t->r << 2, dx = (t->x << 2) - px, dz = (t->z << 2) - pz, y = TREE_BASE(t);
                if (!r || dx < -768 || dx > 768 || dz < -768 || dz > 768 || py < y - 200 ||
                    py > y + 60 + (t->kind < 2 || t->kind > 8 ? t->h << 3 : tall[t->kind]))
                    continue;
#ifdef MERGE
                if (t->kind > 8 && !prop_live(t->x << 2, t->z << 2))
                    continue;                          /* (opened, taken: gone from Payback's map) */
#endif
                /* the circle's middle in the car's frame, and the nearest point of the hull's footprint */
                s32 lx = (dx * m->r.x + dz * m->r.z) >> 14, lz = (dx * m->f.x + dz * m->f.z) >> 14;
                s32 qx = clampi(lx, -hw, hw), qz = clampi(lz, -bh, ah), ex = lx - qx, ez = lz - qz, d;
                if (ex | ez) {
                    if (ex <= -r || ex >= r || ez <= -r || ez >= r || (d = (s32)isqrt(ex * ex + ez * ez)) >= r)
                        continue;
                } else {
                    /* in past the edge in one tick: out through the nearest side */
                    s32 dd[4] = {hw - lx, lx + hw, ah - lz, lz + bh};
                    int k = 0;
                    for (int j = 1; j < 4; j++)
                        if (dd[j] < dd[k]) k = j;
                    ex = k == 0 ? 1 : k == 1 ? -1 : 0, ez = k == 2 ? 1 : k == 3 ? -1 : 0;
                    d = -dd[k];
                }
                V3 n = v3(-(m->r.x * ex + m->f.x * ez), 0, -(m->r.z * ex + m->f.z * ez));
                Hit h = {(r - d) << FX, vnorm(n), SURF_GROUND, 0, 0};
                s32 imp = body_contact(b, vadd(vscale(m->r, qx), vscale(m->f, qz)), &h, 40, 150);
                if (imp > worst)
                    worst = imp;
            }
        }
    return worst;
}

/* ramp_grip: on a ramp a car keeps to it as Payback's do, whatever its slope: held on its
   surface at the speed it goes across it, its wheels square to it (the engine, brakes and
   steering still drive it); off its end onto a floor about level with it, level again */
#define RIDE 76                    /* how far the body rides off what its wheels stand on (units) */
static int ramp_under(const Body *b)
{
    u8 sh = world_cell(b->pos.x >> FX, b->pos.z >> FX)->shape;
    return sh >= 2 && sh <= 5;
}

static void ramp_square(M3 *m, V3 n)
{
    m->u = n;
    m->f = vnorm(vsub(m->f, vscale(n, vdot(m->f, n))));
    m->r = vcross(m->u, m->f);
}

static void ramp_follow(Car *c)
{
    Body *b = &c->b;
    int was = c->on_ramp, under = ramp_under(b);
    if (!(was | under))
        return;                                /* (off ramps, as most of the time) */
    V3 n = world_normal(b->pos.x >> FX, b->pos.z >> FX);
    s32 g = ground_fine(b->pos.x, b->pos.z) + ((RIDE << (FX + 14)) / n.y);
    c->on_ramp = under && b->pos.y <= g + (48 << FX);
    if (!c->on_ramp) {
        if (was && b->pos.y < g + (320 << FX) && b->pos.y > g - (600 << FX)) {
            if (b->pos.y < g)
                b->pos.y = g;                  /* (up a step onto it: Payback's knee) */
            b->vel.y = 0;
            ramp_square(&b->m, n);
        } else if (was) {
            /* off its end into the air: a hop, not the ramp's slope (a 2048 rise in a cell is
               twice the speed upward, which threw a car 13000 up for ten seconds) */
            V3 u = b->m.u;                     /* (still square to the ramp) */
            s32 h = (iabs(b->vel.x) + iabs(b->vel.z)) >> 1, uh = iabs(u.x) + iabs(u.z);
            if (b->vel.y > h && uh > u.y >> 1) {
                b->vel.y = h;
                ramp_square(&b->m, vnorm(v3(u.x * u.y / (2 * uh), u.y, u.z * u.y / (2 * uh))));
            }
        }
        return;
    }
    b->pos.y = g;
    b->vel.y = -(n.x * (b->vel.x >> 6) + n.z * (b->vel.z >> 6)) / n.y << 6;
    ramp_square(&b->m, n);
    b->w = vscale(n, vdot(b->w, n));           /* (turning still, no pitching or rolling) */
}

void car_reset(Car *c, V3 p, s32 heading)
{
    memset(c, 0, sizeof *c);
    c->b.pos = v3(p.x << FX, p.y << FX, p.z << FX);
    myaw(&c->b.m, heading);
    /* box 256 x 90 x 480 units, mass 1; scaled up a little for steadier handling */
    c->b.inv_i[0] = (1 << 24) / 30000;     /* pitch */
    c->b.inv_i[1] = (1 << 24) / 36000;     /* yaw */
    c->b.inv_i[2] = (1 << 24) / 16000;     /* roll */
    c->boost = 4096;
}

void car_update(Car *c, u16 keys)
{
    Body *b = &c->b;
    M3 *m = &b->m;
    s32 air = space_factor(b->pos.y >> FX);
    int target = keys & KEY_RIGHT ? ONE : keys & KEY_LEFT ? -ONE : 0;
    c->steer += (target - c->steer) >> 2;
    s32 vf = vdot(b->vel, m->f);
    c->speed = vf;
    s32 su = iabs(vf) >> FX;
    s32 dmax = 5000 * 28 / (28 + su);                 /* less lock at speed */
    s32 delta = (c->steer * dmax) >> 14;
    V3 ffront = vadd(vscale(m->f, fcos(delta)), vscale(m->r, fsin(delta)));
    int throttle = (keys & KEY_A) != 0, brake = (keys & KEY_B) != 0;
    int drift = (keys & KEY_L) != 0;

    b->acc.y -= (G_ACC * (ONE - air)) >> 14;

    u16 sz[3];
    car_scale(sz);
    c->wheels = 0;
    c->on_loop = 0;
    for (int i = 0; i < 4; i++) {
        V3 mount = mlocal(m, sized(sz, car_wheel[i]));
        V3 mp = vadd(b->pos, v3(mount.x << FX, mount.y << FX, mount.z << FX));
        Hit h;
        c->touch[i] = SURF_NONE;
        c->comp[i] = 0;
        if (!ray_surface(mp, m->u, CAR_SUSP << FX, &h) || (h.kind == SURF_RAMP && !c->on_ramp))
            continue;                          /* (a ramp ahead: ramp_follow takes the car onto it) */
        s32 comp = (CAR_SUSP << FX) - h.dist;
        if (comp <= 0)
            continue;
        c->touch[i] = h.kind;
        c->comp[i] = comp;
        c->wheels++;
        if (h.kind == SURF_LOOP) {
            c->on_loop++;
            c->loop_ang = h.ang;
            c->loop_idx = h.idx;
        }
        s32 dl = h.dist >> FX;
        V3 rc = v3(mount.x - ((m->u.x * dl) >> 14), mount.y - ((m->u.y * dl) >> 14), mount.z - ((m->u.z * dl) >> 14));
        V3 vp = body_point_vel(b, rc);
        s32 vn = vdot(vp, h.n);
        s32 N = ((comp * K_SPRING) >> 16) - ((vn * C_DAMP) >> 16);
        if (comp > BUMP)
            N += ((comp - BUMP) * K_SPRING * 6) >> 16;
        if (N < 0)
            N = 0;
        /* tyre frame on the surface */
        V3 wf = i < 2 ? ffront : m->f;
        wf = vsub(wf, vscale(h.n, vdot(wf, h.n)));
        V3 wl = vcross(h.n, wf);
        s32 vlat = vdot(vp, wl), vlon = vdot(vp, wf);
        s32 flat = -((vlat * K_LAT) >> 16);
        s32 flon = -(vlon >> (throttle | brake ? 12 : 8));   /* rolling resistance; off the gas, the engine's
                                                                braking too (it rolled 11 cells in 5 s) */
        if (throttle) {
            s32 x = (iabs(vf) << 7) / (VMAX >> 7);      /* speed / VMAX, 1.14 */
            s32 e = vf < 0 ? ENGINE : (ENGINE * (ONE - ((x * x) >> 14))) >> 14;
            if (e > 0)
                flon += e >> 2;
        } else if (brake) {
            if (vf > (2 << FX))
                flon -= BRAKE >> 2;
            else if (vf > -(30 << FX))
                flon -= ENGINE >> 3;                    /* reverse */
        }
        s32 mu = i < 2 ? MU_FRONT : drift ? MU_DRIFT : MU_REAR;
        s32 lim = (N * mu) >> 8, mag = iabs(flat) + iabs(flon);
        if (mag > lim) {
            flat = flat * lim / mag;
            flon = flon * lim / mag;
        }
        /* (on a ramp ramp_follow bears the car: only the tyres' grip along it) */
        V3 f = vadd(h.kind == SURF_RAMP ? v3(0, 0, 0) : vscale(h.n, N), vadd(vscale(wl, flat), vscale(wf, flon)));
        body_force(b, rc, f);
    }

    /* A loop's track is a helix: it drifts sideways by its width over one turn so the exit
       clears the entry. Its slight twist steers the car along it, as the track's banking would. */
    if (c->on_loop >= 2) {
        const Loop *lp = &world.loop[c->loop_idx];
        V3 lf, ls;
        loop_frame(lp, &lf, &ls);
        s32 lat = (((b->pos.x - (lp->x << FX)) >> 4) * ls.x + ((b->pos.z - (lp->z << FX)) >> 4) * ls.z) >> 10;
        s32 err = ((lp->w * c->loop_ang) >> 8) - lat;
        s32 pitch = (lp->w << 14) / ((lp->r * 6434) >> 10);   /* sideways per unit along, 1.14 */
        s32 v = vlen(b->vel);
        s32 want = (v * pitch) >> 14, vs = vdot(b->vel, ls);
        s32 a = (err >> 5) + ((want - vs) >> 2);
        if (a > 160) a = 160;
        if (a < -160) a = -160;
        b->acc = vadd(b->acc, vscale(ls, a));
        b->alpha.y += (pitch - vdot(m->f, ls)) >> 1;
    }

    /* boost jet: thrust along the nose, works on the ground and in the air */
    c->boosting = 0;
    if ((keys & KEY_R) && c->boost > 0) {
        b->acc = vadd(b->acc, vscale(m->f, BOOST_THRUST));
        c->boost -= 28;
        c->boosting = 1;
    } else if (c->boost < 4096 && !(keys & KEY_R)) {
        c->boost += 8;
    }

    if (c->wheels == 0) {
        /* air control: a little pitch, spin and roll from the controls, like Stunt Race FX */
        V3 a = v3(0, 0, 0);
        if (keys & KEY_UP) a.x += 260;
        if (keys & KEY_DOWN) a.x -= 260;
        if (keys & KEY_RIGHT) a.y += 200;
        if (keys & KEY_LEFT) a.y -= 200;
        if (keys & KEY_L) a.z += 300;
        if (keys & KEY_R && !c->boost) a.z -= 300;
        b->alpha = vadd(b->alpha, a);
    } else {
        b->w = vsub(b->w, vshr(b->w, 6));
    }

    /* air drag */
    s32 v = vlen(b->vel);
    s32 kd = ((v >> 8) * (ONE - air)) >> 14;
    b->acc = vsub(b->acc, v3((b->vel.x * kd) >> 16, (b->vel.y * kd) >> 16, (b->vel.z * kd) >> 16));

    /* in Payback's water nothing is under the wheels: water drag, and a sink about as fast as
       Payback sinks its cars (8 units a tick, which it then wrecks, and drowns whoever is in) */
    s32 ws;
    c->in_water = world_water(b->pos.x >> FX, b->pos.z >> FX, &ws) && b->pos.y < (ws + 40) << FX;
    if (c->in_water) {
        b->acc = vsub(b->acc, vshr(b->vel, 4));
        b->w = vsub(b->w, vshr(b->w, 4));
    }

    body_integrate(b);

    c->impact = 0;
    ramp_pass = ramp_grip << c->on_ramp;       /* (ramps: ramp_follow) */
    for (unsigned i = 0; i < NHULL; i++) {
        s32 imp;
        if (body_collide(b, mlocal(m, sized(sz, hull[i])), 40, 150, &imp) && imp > c->impact)
            c->impact = imp;
    }
    ramp_pass = 0;
    s32 imp = car_posts(b, sz);
    if (imp > c->impact)
        c->impact = imp;
    if (ramp_grip)
        ramp_follow(c);
}
