/* Arwing flight. The controls set the rates the nose turns at (Star Fox style: UP dives);
   the air keeps pulling the flight path toward where the nose points, gravity pulls down,
   and lift holds you up once you are fast enough. All of that fades out with altitude, so
   above the sky you coast through space on thrust alone. */
#include "ship.h"
#include "gba.h"
#include "world.h"

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
#define CLIMB 4500                 /* the nose's rise (f.y, 1.14) in the climb out: about 16 degrees */

u16 ship_speed_k = 256;            /* GAME SETTINGS: the speeds flown, 256 = as above */
u8 ship_engine;                    /* 0..2: the shipyard's engine upgrades */

static u8 rest;                    /* ticks the ship has lain still (see ship_update) */

static s32 iabs(s32 v) { return v < 0 ? -v : v; }
static s32 clampi(s32 v, s32 lo, s32 hi) { return v < lo ? lo : v > hi ? hi : v; }

void ship_reset(Ship *s, V3 p, s32 heading)
{
    memset(s, 0, sizeof *s);
    rest = 0;                                      /* (a new ship is never held) */
    s->b.pos = v3(p.x << FX, (p.y + 120) << FX, p.z << FX);
    myaw(&s->b.m, heading);
    s->b.inv_i[0] = (1 << 24) / 40000;
    s->b.inv_i[1] = (1 << 24) / 76000;
    s->b.inv_i[2] = (1 << 24) / 36000;
}

/* A held, the way ahead is kept clear: how steep a climb (tan, 1.14) passes MARGIN over what
   stands in the flight path in the next second and a half, a wing's width either side: blocks,
   Payback's edge walls and decks. Ground no higher than the floor under you is no obstacle (a
   take-off run, a flight over the street). */
#define MARGIN 900
#define STEEP 13700                /* tan of the steepest climb flown (CAP): past it the lift jets */
#define CAP 10500                  /* (its f.y, about 40 degrees; the hands-off pitch-over is at 11000) */
static s32 look(const Body *b, s32 dx, s32 dz, s32 reach, s32 *near, int roof)
{
    s32 x = b->pos.x >> FX, y = b->pos.y >> FX, z = b->pos.z >> FX, under = world_cell(x, z)->hi + 300;
    s32 worst = 0, first = 1 << 20, wx = dz * 420 >> 14, wz = -dx * 420 >> 14;
    for (s32 t = 512; t <= reach; t += t < 4096 ? 512 : 1024) {   /* (finer near) */
        s32 px = x + (dx * t >> 14), pz = z + (dz * t >> 14);
        for (int k = -1; k <= 1; k++) {
            s32 qx = px + k * wx, qz = pz + k * wz, h = world_cell(qx, qz)->hi, lo, hi;
            if (world_wall(qx, qz, &lo, &hi) && hi > h)
                h = hi;                                    /* (Payback's walls on its edges: a plaza's rail) */
            /* a deck: in the way if a climb would meet it; under one already, those as high are
               roofs to fly on under */
            if (world_deck(qx, qz, 0, &lo, &hi) && hi > h && lo < y + 200 + (roof ? 0 : t * 4700 >> 14))
                h = hi;
            if (h <= under || h + MARGIN <= y)
                continue;
            s32 tan = ((h + MARGIN - y) << 10) / t << 4;
            if (tan > worst)
                worst = tan;
            if (t < first)
                first = t;
        }
    }
    *near = first;
    return worst > 4 * ONE ? 4 * ONE : worst;
}

/* the way the flight path goes (or the nose, near a standstill), level, unit, and the pace that
   way; -1 for none (straight up or down) */
static int way(const Body *b, s32 *dx, s32 *dz)
{
    s32 vx = b->vel.x >> FX, vz = b->vel.z >> FX, vh = isqrt(vx * vx + vz * vz);
    if (vh > 8) {
        *dx = vx * ONE / vh, *dz = vz * ONE / vh;
        return vh;
    }
    s32 fl = isqrt(b->m.f.x * b->m.f.x + b->m.f.z * b->m.f.z);
    if (fl < 1000)
        return -1;
    *dx = b->m.f.x * ONE / fl, *dz = b->m.f.z * ONE / fl;
    return 0;
}

/* parked with the hands off, the gear's springs chatter by a hair for ever, and every tick of it costs the
   city's collision tests; after a second at rest the ship is held still, till a key, a push or a move */
#define REST_N 60
#define REST_V 160                                 /* the creep and spin that count as still */
static V3 rest_pos, rest_f;

static int rest_held(const Body *b)
{
    return !(b->vel.x | b->vel.y | b->vel.z | b->w.x | b->w.y | b->w.z | b->acc.x | b->acc.y | b->acc.z | b->alpha.x | b->alpha.y | b->alpha.z) &&
           !((b->pos.x ^ rest_pos.x) | (b->pos.y ^ rest_pos.y) | (b->pos.z ^ rest_pos.z) |
             (b->m.f.x ^ rest_f.x) | (b->m.f.y ^ rest_f.y) | (b->m.f.z ^ rest_f.z));
}

void ship_update(Ship *s, u16 keys)
{
    Body *b = &s->b;
    M3 *m = &b->m;
    if (rest >= REST_N) {
        if (!keys && rest_held(b)) {
            s->impact = 0;
            return;
        }
        rest = 0;
    }
    s32 space = space_factor(b->pos.y >> FX), air = ONE - space;
    b->acc.y -= (G_ACC * air) >> 14;

    /* (on UP or DOWN the pilot flies it as they like; under a deck, a bridge or a covered yard,
       it keeps level till it is out from under (rising, it pinned itself to the roof), slows for
       a wall under it and turns the way that is open) */
    s32 lo, hi, pitch = CLIMB, clear = 0, near = 0, steer = 0, dx, dz;
    int assist = (keys & KEY_A) && !(keys & (KEY_UP | KEY_DOWN)) && air > ONE / 4;
    int roof = 0;
    for (int k = -1; k <= 1 && assist; k++)               /* (over the nose and either wing tip, now and */
        for (s32 t = 0; t <= 400; t += 400) {             /* a moment on) */
            s32 x = (b->pos.x >> FX) + ((m->r.x * 340 * k + m->f.x * t) >> 14);
            s32 z = (b->pos.z >> FX) + ((m->r.z * 340 * k + m->f.z * t) >> 14);
            if (world_deck(x, z, 0, &lo, &hi) && lo > (b->pos.y >> FX))
                roof = 1;
        }
    if (roof && b->vel.y > 0)
        b->acc.y -= b->vel.y >> 2;
    /* (looked again every third tick: a look is some 100 reads of the city) */
    static s32 seen, seen_near;
    static u8 seen_t, seen_roof;
    s32 vh = assist ? way(b, &dx, &dz) : -1;
    if (vh < 0)
        seen_t = 0;
    else if (seen_t && seen_roof == roof)
        seen_t--, clear = seen, near = seen_near;
    else {
        clear = seen = look(b, dx, dz, clampi(vh * 90, 3072, 16384), &near, roof);
        seen_near = near, seen_roof = roof, seen_t = 2;
    }
    if (roof && clear && near < 2048) {
        /* 50 degrees either side: toward the side that is open further */
        s32 c = 10531, sn = 12551, nl, nr;
        look(b, (dx * c - dz * sn) >> 14, (dz * c + dx * sn) >> 14, 3072, &nl, 1);
        look(b, (dx * c + dz * sn) >> 14, (dz * c - dx * sn) >> 14, 3072, &nr, 1);
        if (nr > near + 512 || nl > near + 512 || near < 1024)
            steer = nr >= nl ? 1 : -1;                    /* (and in a dead end, round till it is open) */
    }

    /* landing gear */
    int was = s->gear;
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
            s32 d = keys & KEY_RIGHT ? 3000 : keys & KEY_LEFT ? -3000 : steer * 3000;
            wf = vadd(vscale(m->f, fcos(d)), vscale(m->r, fsin(d)));
        }
        wf = vsub(wf, vscale(h.n, vdot(wf, h.n)));
        V3 wl = vcross(h.n, wf);
        s32 flat = -((vdot(vp, wl) * 9000) >> 16);
        s32 vlon = vdot(vp, wf), flon = keys & KEY_A ? -(vlon >> 11) : -(vlon >> 8);   /* (rolling) */
        if (keys & KEY_B)
            flon = -clampi(vlon >> 4, -60, 60);
        s32 lim = (N * 280) >> 8, mag = iabs(flat) + iabs(flon);
        if (mag > lim) {
            flat = flat * lim / mag;
            flon = flon * lim / mag;
        }
        body_force(b, rc, vadd(vscale(h.n, N), vadd(vscale(wl, flat), vscale(wf, flon))));
    }

    /* off the ground under thrust: a second of climb (full lift, nose held up) before the
       wings carry it; touching down again ends it */
    if (s->gear)
        s->climb = 0;
    else if (was && (keys & KEY_A))
        s->climb = 70;
    else if (s->climb)
        s->climb--;
    /* too steep to fly over: the lift jets, and a pace that rises over it before you get there;
       under a roof, a pace that stops short of it (a crawl no wall hurts) */
    int jets = clear > STEEP && !roof;
    s32 most = jets ? clampi((50 << FX) * (ONE >> 4) / (clear >> 4), 10 << FX, FAST)
             : roof && clear ? clampi((near - 450) * (ONE / 24) >> 6, 4 << FX, FAST) : 0;   /* (0: no limit) */
    if (clear && !roof) {
        s32 t8 = clear >> 6;                               /* the climb that clears it, as f.y */
        pitch = clampi((t8 << 14) / (s32)isqrt(65536 + t8 * t8), CLIMB, CAP);
    }
    if ((clear || roof) && !s->gear && s->climb < 12)
        s->climb = 12;                                     /* (full lift: slowed under a roof, it sank) */

    /* thrust */
    s32 v = vlen(b->vel), vf = vdot(b->vel, m->f);
    s32 thrust;
    s->boosting = (keys & KEY_A) != 0;
    if (s->gear)
        thrust = keys & KEY_A && (!most || vf < most) ? 260 : 0;
    else {
        s32 target = keys & KEY_A ? FAST + ship_engine * (35 << FX) : keys & KEY_B ? SLOW : CRUISE + ship_engine * (12 << FX);
        target = target * ship_speed_k >> 8;
        if (most && target > most)
            target = jets ? 10 << FX : most;
        thrust = clampi((target - vf) >> 6, -140, 220);
    }
    /* the jets rise straight up toward 50 units a tick, and brake */
    if (jets)
        b->acc.y += clampi(((50 << FX) - b->vel.y) >> 4, 0, 3 * G_ACC) + (s->gear ? G_ACC : 0);
    s32 hx = b->vel.x >> 4, hz = b->vel.z >> 4, hv = most ? isqrt(hx * hx + hz * hz) << 4 : 0;
    if (hv > most) {
        s32 k = (hv - most) * (ONE >> 4) / (hv >> 4);
        b->acc.x -= (b->vel.x * k >> 14) >> 3, b->acc.z -= (b->vel.z * k >> 14) >> 3;
    }
    b->acc = vadd(b->acc, vscale(m->f, thrust));

    /* aerodynamics */
    s32 vu = v >> FX, lift = vu >= (STALL >> FX) || s->climb ? ONE : vu * vu * ONE / ((STALL >> FX) * (STALL >> FX));
    s32 la = (lift * air) >> 14;
    b->acc = vadd(b->acc, vscale(jets ? v3(0, ONE, 0) : m->u, (G_ACC * la) >> 14));   /* (the jets hold you up) */
    if (v > 256) {
        s32 k = ((1400 * la) >> 14) + 250;                 /* flight path follows the nose */
        V3 path = jets ? b->vel : vscale(m->f, v);        /* (on the jets they fly it) */
        b->acc = vadd(b->acc, v3(((path.x - b->vel.x) * k) >> 14, ((path.y - b->vel.y) * k) >> 14,
                                 ((path.z - b->vel.z) * k) >> 14));
        s32 kd = ((((v >> 7) * air) >> 14) + (v >> 12));
        b->acc = vsub(b->acc, v3((b->vel.x * kd) >> 16, (b->vel.y * kd) >> 16, (b->vel.z * kd) >> 16));
    }

    /* attitude */
#define BANK 10500                                     /* sin of the bank LEFT / RIGHT hold (1.14) */
    if (!s->gear) {
        V3 wl = mworld(m, b->w), t = v3(0, 0, 0);
        if (keys & KEY_UP) t.x = 9000;
        /* (DOWN pulls the nose up, like a stick: low over the ground it stops at a steep climb,
           since held on after take-off it looped the Arwing down into the street) */
        if ((keys & KEY_DOWN) && !(m->f.y > 11000 && (b->pos.y >> FX) - world_ground(b->pos.x >> FX, b->pos.z >> FX) < 6000))
            t.x = -9000;
        if (keys & KEY_RIGHT) t.z = -15000;
        if (keys & KEY_LEFT) t.z = 15000;
        /* ... and in the air, the nose drifts back to level too (not in a loop); from a steep
           climb or dive it pitches over to come out upright, never left hanging on its tail or
           diving on into the street. Just off the ground it holds a climb. */
        if (air > ONE / 4 && !(keys & (KEY_UP | KEY_DOWN))) {
            if ((clear || roof) && m->u.y > 0)
                t.x = clampi(((m->f.y - (roof ? 0 : pitch)) * 12000) >> 14, -9000, 9000);   /* (the climb that clears the way) */
            else if (iabs(m->f.y) >= 11000)
                t.x = m->f.y > 0 ? 9000 : -9000;
            else if (m->u.y > 0)
                t.x = ((m->f.y - (s->climb ? CLIMB : 0)) * 5000) >> 14;
        }
        int held = air > ONE / 4 && m->u.y > 0 && (keys & (KEY_LEFT | KEY_RIGHT));
        if (held) {
            /* in the air, upright: LEFT / RIGHT bank to about 40 degrees and hold it there,
               turning about the world's up (a level turn), instead of rolling on and over */
            s32 want = keys & KEY_RIGHT ? -BANK : BANK;
            t.z = clampi(((want - m->r.y) * 3) >> 1, -15000, 15000);
            V3 turn = mworld(m, v3(0, (-m->r.y * 9000) >> 14, 0));
            t.y = turn.y;
            t.x += turn.x;
            /* the lift the bank tips sideways is made up for */
            b->acc.y += (((G_ACC * la) >> 14) * (ONE - m->u.y)) >> 14;
        }
        /* hands off the stick: level the wings (and roll back upright) by itself */
        if (!(keys & (KEY_LEFT | KEY_RIGHT | KEY_UP | KEY_DOWN)) && iabs(m->f.y) < 11000) {
            if (m->u.y > 0)
                t.z = -((m->r.y * 9000) >> 14);
            else
                t.z = m->r.y >= 0 ? -9000 : 9000;
        }
        if (keys & KEY_L) t.y = -5000;
        if (keys & KEY_R) t.y = 5000;
        if (steer) t.y = steer * 6000;
        s32 yaw = (6000 * space) >> 14;                    /* no air to bank against: steer */
        if (keys & KEY_RIGHT) t.y += yaw;
        if (keys & KEY_LEFT) t.y -= yaw;
        if (m->u.y > 0 && !held)                           /* banked: the lift turns you */
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
        if (((keys & KEY_DOWN) && vu > 30) || ((keys & KEY_A) && !roof && vu > (clear ? 24 : 36) && m->f.y < 2600))
            b->alpha.x -= 1400;
    }

    s32 alt = b->pos.y >> FX;
    if (alt > 58000)                                       /* the edge of space pushes back */
        b->acc.y -= (alt - 58000) >> 2;

    body_integrate(b);

    ship_settle(s);
    if (keys || s->gear < 3 || iabs(b->vel.x) + iabs(b->vel.y) + iabs(b->vel.z) > REST_V || iabs(b->w.x) + iabs(b->w.y) + iabs(b->w.z) > REST_V)
        rest = 0;
    else if (++rest >= REST_N) {                           /* (still: held as it lies) */
        b->vel = b->w = b->acc = b->alpha = v3(0, 0, 0);
        rest_pos = b->pos, rest_f = m->f;
    }
}

/* the hull against the city: pushed out of what it is in, bouncing and rubbing */
void ship_settle(Ship *s)
{
    Body *b = &s->b;
    s->impact = 0;
    water_floats = ship_hull = 1;                          /* (the hull skims water; the gear never rests on it) */
    for (unsigned i = 0; i < NHULL; i++) {
        s32 imp;
        if (body_collide(b, mlocal(&b->m, hull[i]), 60, 120, &imp) && imp > s->impact)
            s->impact = imp;
    }
    water_floats = ship_hull = 0;
}
