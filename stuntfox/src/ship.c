/* Arwing flight. The controls set the rates the nose turns at (Star Fox style: UP dives);
   the air keeps pulling the flight path toward where the nose points, gravity pulls down,
   and lift holds you up once you are fast enough. All of that fades out with altitude, so
   above the sky you coast through space on thrust alone. */
#include "ship.h"
#include "gba.h"

const V3 ship_gear[3] = {{0, -40, 250}, {-150, -40, -90}, {150, -40, -90}};
static const V3 hull[] = {
    {0, 0, 400}, {-330, -30, -170}, {330, -30, -170}, {-325, 120, -250}, {325, 120, -250},
    {-325, -80, -200}, {325, -80, -200}, {0, 20, -210}, {0, 80, -10}, {0, -50, -40},
};
#define NHULL (sizeof hull / sizeof hull[0])

#define K_SPRING 900
#define C_DAMP 4000
#define STALL (60 << FX)
#define CRUISE (95 << FX)
#define FAST (175 << FX)
#define SLOW (40 << FX)

static s32 iabs(s32 v) { return v < 0 ? -v : v; }
static s32 clampi(s32 v, s32 lo, s32 hi) { return v < lo ? lo : v > hi ? hi : v; }

void ship_reset(Ship *s, V3 p, s32 heading)
{
    memset(s, 0, sizeof *s);
    s->b.pos = v3(p.x << FX, (p.y + 120) << FX, p.z << FX);
    myaw(&s->b.m, heading);
    s->b.inv_i[0] = (1 << 24) / 40000;
    s->b.inv_i[1] = (1 << 24) / 76000;
    s->b.inv_i[2] = (1 << 24) / 36000;
}

void ship_update(Ship *s, u16 keys)
{
    Body *b = &s->b;
    M3 *m = &b->m;
    s32 space = space_factor(b->pos.y >> FX), air = ONE - space;
    b->acc.y -= (G_ACC * air) >> 14;

    /* landing gear */
    s->gear = 0;
    for (int i = 0; i < 3; i++) {
        V3 mount = mlocal(m, ship_gear[i]);
        V3 mp = vadd(b->pos, v3(mount.x << FX, mount.y << FX, mount.z << FX));
        Hit h;
        s->comp[i] = 0;
        if (!ray_surface(mp, m->u, SHIP_SUSP << FX, &h))
            continue;
        s32 comp = (SHIP_SUSP << FX) - h.dist;
        if (comp <= 0)
            continue;
        s->comp[i] = comp;
        s->gear++;
        s->gear_kind = h.kind;
        s32 dl = h.dist >> FX;
        V3 rc = v3(mount.x - ((m->u.x * dl) >> 14), mount.y - ((m->u.y * dl) >> 14), mount.z - ((m->u.z * dl) >> 14));
        V3 vp = body_point_vel(b, rc);
        s32 vn = vdot(vp, h.n);
        s32 N = ((comp * K_SPRING) >> 16) - ((vn * C_DAMP) >> 16);
        if (N < 0) N = 0;
        V3 wf = m->f;
        if (i == 0) {                                      /* nose wheel steers */
            s32 d = keys & KEY_RIGHT ? 3000 : keys & KEY_LEFT ? -3000 : 0;
            wf = vadd(vscale(m->f, fcos(d)), vscale(m->r, fsin(d)));
        }
        wf = vsub(wf, vscale(h.n, vdot(wf, h.n)));
        V3 wl = vcross(h.n, wf);
        s32 flat = -((vdot(vp, wl) * 9000) >> 16);
        s32 vlon = vdot(vp, wf), flon = -(vlon >> 8);
        if (keys & KEY_B)
            flon = -clampi(vlon >> 4, -60, 60);
        s32 lim = (N * 280) >> 8, mag = iabs(flat) + iabs(flon);
        if (mag > lim) {
            flat = flat * lim / mag;
            flon = flon * lim / mag;
        }
        body_force(b, rc, vadd(vscale(h.n, N), vadd(vscale(wl, flat), vscale(wf, flon))));
    }

    /* thrust */
    s32 v = vlen(b->vel), vf = vdot(b->vel, m->f);
    s32 thrust;
    s->boosting = (keys & KEY_A) != 0;
    if (s->gear)
        thrust = keys & KEY_A ? 130 : 0;
    else {
        s32 target = keys & KEY_A ? FAST : keys & KEY_B ? SLOW : CRUISE;
        thrust = clampi((target - vf) >> 6, -140, 220);
    }
    b->acc = vadd(b->acc, vscale(m->f, thrust));

    /* aerodynamics */
    s32 vu = v >> FX, lift = vu >= (STALL >> FX) ? ONE : vu * vu * ONE / ((STALL >> FX) * (STALL >> FX));
    s32 la = (lift * air) >> 14;
    b->acc = vadd(b->acc, vscale(m->u, (G_ACC * la) >> 14));
    if (v > 256) {
        s32 k = ((1400 * la) >> 14) + 250;                 /* flight path follows the nose */
        V3 want = vscale(m->f, v);
        b->acc = vadd(b->acc, v3(((want.x - b->vel.x) * k) >> 14, ((want.y - b->vel.y) * k) >> 14,
                                 ((want.z - b->vel.z) * k) >> 14));
        s32 kd = ((((v >> 7) * air) >> 14) + (v >> 12));
        b->acc = vsub(b->acc, v3((b->vel.x * kd) >> 16, (b->vel.y * kd) >> 16, (b->vel.z * kd) >> 16));
    }

    /* attitude */
    if (!s->gear) {
        V3 wl = mworld(m, b->w), t = v3(0, 0, 0);
        if (keys & KEY_UP) t.x = 9000;
        if (keys & KEY_DOWN) t.x = -9000;
        if (keys & KEY_RIGHT) t.z = -15000;
        if (keys & KEY_LEFT) t.z = 15000;
        /* hands off the stick: level the wings (and roll back upright) by itself */
        if (!(keys & (KEY_LEFT | KEY_RIGHT | KEY_UP | KEY_DOWN)) && iabs(m->f.y) < 11000) {
            if (m->u.y > 0)
                t.z = -((m->r.y * 9000) >> 14);
            else
                t.z = m->r.y >= 0 ? -9000 : 9000;
        }
        if (keys & KEY_L) t.y = -5000;
        if (keys & KEY_R) t.y = 5000;
        if (m->u.y > 0)                                    /* banked: the lift turns you */
            t.y += (((((-m->r.y * 7000) >> 14) * la) >> 14) * m->u.y) >> 14;
        if (s->rolling) {
            t.z = s->roll_dir;
            s->rolling--;
        }
        wl = vadd(wl, vshr(vsub(t, wl), 3));
        b->w = mlocal(m, wl);
    } else {
        b->w = vsub(b->w, vshr(b->w, 4));
        /* rotate for take-off: by itself at speed, or sooner with DOWN */
        if (((keys & KEY_DOWN) && vu > 40) || ((keys & KEY_A) && vu > 52 && m->f.y < 2600))
            b->alpha.x -= 900;
    }

    s32 alt = b->pos.y >> FX;
    if (alt > 58000)                                       /* the edge of space pushes back */
        b->acc.y -= (alt - 58000) >> 2;

    body_integrate(b);

    s->impact = 0;
    for (unsigned i = 0; i < NHULL; i++) {
        s32 imp;
        if (body_collide(b, mlocal(m, hull[i]), 60, 120, &imp) && imp > s->impact)
            s->impact = imp;
    }
}
