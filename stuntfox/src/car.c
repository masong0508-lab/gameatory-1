/* Car physics. Every force acts at the point where it really happens: springs and tyres at
   the four contact patches, impacts at the corner that hits, so the car pitches, rolls,
   flips and falls off loops by itself. Nothing is scripted. */
#include "car.h"
#include "gba.h"
#include "loops.h"

const V3 car_wheel[4] = {
    {-110, -10, 160}, {110, -10, 160}, {-110, -10, -150}, {110, -10, -150},
};
static const V3 hull[] = {
    {-125, -38, 240}, {125, -38, 240}, {-128, -38, -225}, {128, -38, -225},
    {-110, 12, 150}, {110, 12, 150}, {-118, 32, -225}, {118, 32, -225}, {0, 62, -40},
};
#define NHULL (sizeof hull / sizeof hull[0])

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

    c->wheels = 0;
    c->on_loop = 0;
    for (int i = 0; i < 4; i++) {
        V3 mount = mlocal(m, car_wheel[i]);
        V3 mp = vadd(b->pos, v3(mount.x << FX, mount.y << FX, mount.z << FX));
        Hit h;
        c->touch[i] = SURF_NONE;
        c->comp[i] = 0;
        if (!ray_surface(mp, m->u, CAR_SUSP << FX, &h))
            continue;
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
        s32 flon = -(vlon >> 12);                      /* rolling resistance */
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
        V3 f = vadd(vscale(h.n, N), vadd(vscale(wl, flat), vscale(wf, flon)));
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

    body_integrate(b);

    c->impact = 0;
    for (unsigned i = 0; i < NHULL; i++) {
        s32 imp;
        if (body_collide(b, mlocal(m, hull[i]), 40, 150, &imp) && imp > c->impact)
            c->impact = imp;
    }
}
