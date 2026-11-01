/* Tests of the PS1 ragdoll reference solver (ragdoll_ps1_ref.c): determinism, energy, resting stability, no
   tunnelling, scenes in the box world, the car, the motors. Prints one line a check and exits non-zero on a
   failure. Build and run: tests/s2/ragdoll_ps1.py (or: gcc -O2 -o t ragdoll_ps1_test.c ragdoll_ps1_ref.c -lm && ./t). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <time.h>
#include "ragdoll_ps1_ref.h"
#ifndef GOLDEN
#define GOLDEN 0x01043056u                /* the scene hash recorded when the solver was last changed on purpose */
#endif

static int fails;
#define CHECK(c, ...) do { int ok_ = (c); printf("%s ", ok_ ? "ok  " : "FAIL"); printf(__VA_ARGS__); printf("\n"); if (!ok_) fails++; } while (0)
static fx M(double m) { return (fx)(m * RP_ONE); }
static double D(int64_t v) { return (double)v / RP_ONE; }
static rp_v3 V3(double x, double y, double z) { rp_v3 v = {M(x), M(y), M(z)}; return v; }
static const rp_v3 ZERO = {0, 0, 0};
static double dist(rp_v3 a, rp_v3 b) { double x = D(a.x - b.x), y = D(a.y - b.y), z = D(a.z - b.z); return sqrt(x * x + y * y + z * z); }

static void flat(rp_boxworld *b, double h, int mat)
{
    rp_boxworld_init(b, M(16));
    for (int i = 0; i < RP_BW_CELLS; i++)
        for (int j = 0; j < RP_BW_CELLS; j++)
            b->h[i][j] = M(h), b->mat[i][j] = (uint8_t)mat;
}
static double speedmax(const rp_doll *d)
{
    double m = 0;
    for (int i = 0; i < RP_P; i++) { double v = sqrt(D(d->vel[i].x) * D(d->vel[i].x) + D(d->vel[i].y) * D(d->vel[i].y) + D(d->vel[i].z) * D(d->vel[i].z)); if (v > m) m = v; }
    return m;
}
/* the worst relative error of a bone's length against the standing doll's */
static double stretch(const rp_doll *d)
{
    rp_doll s;
    rp_spawn(&s, ZERO, 0, ZERO, ZERO);
    double w = 0;
    for (int b = 0; b < RP_BONES; b++) {
        double l = dist(rp_bone_a(d, b), rp_bone_b(d, b)), l0 = dist(rp_bone_a(&s, b), rp_bone_b(&s, b));
        double e = fabs(l - l0) / (l0 > 0.3 ? l0 : 0.3);   /* (a 10 cm hip bone is judged against 30 cm) */
        if (e > w) w = e;
    }
    return w;
}
static void run(rp_doll *d, const rp_world *w, const rp_car *c, int frames) { for (int i = 0; i < frames; i++) rp_step(d, w, c); }

/* the deepest a joint's ball is inside the height field (m) */
static double sunk(const rp_doll *d, const rp_boxworld *b)
{
    static const int rmm[RP_P] = {130, 130, 130, 110, 70, 70, 55, 55, 45, 45, 85, 85, 70, 70, 55, 55, 40, 40};
    double w = 0;
    for (int i = 0; i < RP_P; i++) {
        rp_v3 n; int m; fx h;
        b->w.floor((void *)b, d->pos[i].x, d->pos[i].z, d->pos[i].y, &h, &n, &m);
        double depth = D(h) - (D(d->pos[i].y) - rmm[i] / 1000.0);
        if (depth > w) w = depth;
    }
    return w;
}
static int inside_box(const rp_doll *d, const rp_box *x, double margin)
{
    for (int i = 0; i < RP_P; i++)
        if (D(d->pos[i].x) > D(x->lo.x) + margin && D(d->pos[i].x) < D(x->hi.x) - margin && D(d->pos[i].y) > D(x->lo.y) + margin &&
            D(d->pos[i].y) < D(x->hi.y) - margin && D(d->pos[i].z) > D(x->lo.z) + margin && D(d->pos[i].z) < D(x->hi.z) - margin)
            return 1;
    return 0;
}
/* knee/elbow bent the wrong way: how far (m) the worst joint is behind its limb line, where the doll's front is clear
   (the chest's front taken off the limb's line, more than 0.6 of a unit: not a leg kicked forward or an arm reaching) */
static double hyper(const rp_doll *d)
{
    double w = 0;
    int j[4][3] = {{RP_HPL, RP_KNL, RP_ANL}, {RP_HPR, RP_KNR, RP_ANR}, {RP_SHL, RP_ELL, RP_HDL}, {RP_SHR, RP_ELR, RP_HDR}};
    double sd[3], up[3], F[3];
    for (int a = 0; a < 3; a++) {
        const fx *pr = &d->pos[RP_HPR].x, *pl = &d->pos[RP_HPL].x, *pc = &d->pos[RP_CHEST].x, *pp = &d->pos[RP_PELVIS].x;
        sd[a] = D(pr[a] - pl[a]), up[a] = D(pc[a] - pp[a]);
    }
    F[0] = sd[1] * up[2] - sd[2] * up[1], F[1] = sd[2] * up[0] - sd[0] * up[2], F[2] = sd[0] * up[1] - sd[1] * up[0];
    double fl = sqrt(F[0] * F[0] + F[1] * F[1] + F[2] * F[2]);
    for (int a = 0; a < 3; a++) F[a] /= fl;
    for (int k = 0; k < 4; k++) {
        const rp_v3 *a = &d->pos[j[k][0]], *c = &d->pos[j[k][1]], *b = &d->pos[j[k][2]];
        double dn[3] = {D(b->x - a->x), D(b->y - a->y), D(b->z - a->z)};
        double dl = sqrt(dn[0] * dn[0] + dn[1] * dn[1] + dn[2] * dn[2]);
        for (int q = 0; q < 3; q++) dn[q] /= dl;
        double fd = F[0] * dn[0] + F[1] * dn[1] + F[2] * dn[2], g[3], gl = 0;
        for (int q = 0; q < 3; q++) g[q] = F[q] - dn[q] * fd, gl += g[q] * g[q];
        gl = sqrt(gl);
        if (gl < 0.6) continue;
        double off = ((D(c->x) - (D(a->x) + D(b->x)) / 2) * g[0] + (D(c->y) - (D(a->y) + D(b->y)) / 2) * g[1] + (D(c->z) - (D(a->z) + D(b->z)) / 2) * g[2]) / gl;
        if (k >= 2) off = -off;
        if (-off > w) w = -off;
    }
    return w;
}

/* ---- the checks ---- */
static uint32_t scene_hash(void)
{
    rp_boxworld b;
    flat(&b, 0, RP_ROAD);
    rp_boxworld_add(&b, V3(30, -1, 20), V3(31, 3, 80));
    rp_doll d;
    rp_spawn(&d, V3(10, 0.2, 40), 9000, V3(14, 9, 3), V3(1, 2, 3));
    uint32_t h = 0;
    for (int i = 0; i < 400; i++) { rp_step(&d, &b.w, NULL); h = h * 31 + rp_hash(&d); }
    return h;
}

static void t_determinism(void)
{
    uint32_t a = scene_hash(), c = scene_hash();
    CHECK(a == c, "determinism: the same scene twice gives the same bits (%08x)", a);
    CHECK(a == GOLDEN, "determinism: bits equal the recorded golden %08x", GOLDEN);
}

static void t_energy(void)
{
    rp_boxworld b;
    flat(&b, 0, RP_ROAD);
    rp_doll d;
    rp_spawn(&d, V3(40, 3.0, 40), 0, ZERO, V3(0.5, 0, 0.3));
    int64_t e0 = rp_energy(&d), emax = e0;
    double e_air = 0;
    for (int i = 0; i < 20; i++) rp_step(&d, &b.w, NULL);
    e_air = D(rp_energy(&d));
    for (int i = 0; i < 600; i++) {
        rp_step(&d, &b.w, NULL);
        if (rp_energy(&d) > emax) emax = rp_energy(&d);
    }
    CHECK(D(emax) <= D(e0) * 1.02 + 20, "energy: never gains over the start (start %.0f J, max %.0f J)", D(e0), D(emax));
    CHECK(fabs(e_air - D(e0)) < 0.04 * fabs(D(e0)) + 30, "energy: 20 frames of free fall keep it (%.0f -> %.0f J)", D(e0), e_air);
    CHECK(d.state == RP_ASLEEP, "energy: asleep after the fall (state %d, quiet %d)", d.state, d.quiet);
    CHECK(speedmax(&d) < 0.01, "energy: asleep means still (%.4f m/s)", speedmax(&d));
    CHECK(D(rp_energy(&d)) < 0.55 * D(e0), "energy: most of it gone at rest (%.0f of %.0f J)", D(rp_energy(&d)), D(e0));
}

/* after the first hard landing: the pelvis' hops (rises over 0.15 m) and the highest it gets back to over the floor */
static void hops_of(rp_doll *d, const rp_world *w, int *hops, double *top)
{
    int landed = 0, h = 0;
    double prev = 1e9, asc = 0, t = 0;
    for (int i = 0; i < 300; i++) {
        rp_step(d, w, NULL);
        for (int e = 0; e < d->nev; e++) landed |= d->ev[e].strength > 3 * RP_ONE;
        double y = D(d->pos[RP_PELVIS].y);
        if (landed) {
            if (y > prev + 0.0003) asc += y - prev;
            else { if (asc > 0.15) h++, t = asc > t ? asc : t; asc = 0; }
        }
        prev = y;
    }
    *hops = h, *top = t;
}
static void t_bounce(void)
{
    rp_boxworld b, g;
    flat(&b, 0, RP_ROAD);
    flat(&g, 0, RP_GRASS);
    rp_doll d, e;
    rp_spawn(&d, V3(40, 6.0, 40), 0, ZERO, ZERO);
    rp_spawn(&e, V3(40, 6.0, 40), 0, ZERO, ZERO);
    int hr, hg;
    double tr, tg;
    hops_of(&d, &b.w, &hr, &tr);
    hops_of(&e, &g.w, &hg, &tg);
    CHECK(hr >= 1 && hr <= 6, "bounce: a fall from 6 m on road hops %d times (best rise %.2f m), not forever", hr, tr);
    CHECK(tg < tr || hg < hr, "surfaces: grass takes the bounce out (road %d hops / %.2f m, grass %d hops / %.2f m)", hr, tr, hg, tg);
}

static void t_rest(void)
{
    rp_boxworld b;
    flat(&b, 0, RP_ROAD);
    rp_doll d;
    rp_spawn(&d, V3(40, 0.05, 40), 0, V3(3, 1, 0), V3(0, 0, 6));
    int slept = -1;
    for (int i = 0; i < 400 && slept < 0; i++) { rp_step(&d, &b.w, NULL); if (d.state == RP_ASLEEP) slept = i; }
    CHECK(slept >= 0 && slept < 300, "rest: falls asleep after a tumble (frame %d)", slept);
    rp_doll s = d;
    run(&d, &b.w, NULL, 300);
    double drift = dist(d.pos[0], s.pos[0]);
    CHECK(drift < 0.001, "rest: five more seconds, no drift (%.5f m)", drift);
    CHECK(sunk(&d, &b) < 0.03, "rest: lying on the road, not in it (%.3f m)", sunk(&d, &b));
    CHECK(stretch(&d) < 0.06, "rest: bones the right length (%.1f%%)", 100 * stretch(&d));
    CHECK(hyper(&d) < 0.2, "rest: no knee or elbow bent far backwards, where a front is clear (%.3f m; a limb pinned under the body gives way to the floor)", hyper(&d));
    /* awake and quiet: no jitter. Wake it and look at the speeds over a second. */
    rp_wake(&d);
    double vm = 0;
    for (int i = 0; i < 60; i++) { rp_step(&d, &b.w, NULL); double v = speedmax(&d); if (v > vm) vm = v; if (d.state == RP_ASLEEP) break; }
    CHECK(vm < 0.5, "rest: woken lying down it does not shiver (%.3f m/s)", vm);
}

static void t_tunnel(void)
{
    int bad_wall = 0, bad_deck = 0, shots = 0;
    for (int sp = 0; sp < 3; sp++)
        for (int a = 0; a < 16; a++) {
            double speed = sp == 0 ? 30 : sp == 1 ? 60 : 80;
            rp_boxworld b;
            flat(&b, 0, RP_ROAD);
            rp_boxworld_add(&b, V3(60, -1, 0), V3(60.10, 12, 400));       /* a 10 cm wall */
            rp_boxworld_add(&b, V3(100, 5.0, 0), V3(160, 5.05, 400));    /* a 5 cm deck, 5 m up */
            double ang = (a - 8) * 0.05;
            rp_doll d, e;
            rp_spawn(&d, V3(50, 1.0, 100 + a), 0, V3(speed * cos(ang), 1, speed * sin(ang)), V3(a & 1 ? 4 : -4, 2, 3));
            run(&d, &b.w, NULL, 90);
            int far_ = 0;
            for (int i = 0; i < RP_P; i++) if (D(d.pos[i].x) > 60.2) far_++;
            bad_wall += far_ > 0;
            rp_spawn(&e, V3(120, 12, 100 + a), 0, V3(speed * 0.1, -speed * 0.9, speed * 0.1), V3(2, 1, 3));
            run(&e, &b.w, NULL, 60);
            int under = 0;
            for (int i = 0; i < RP_P; i++) if (D(e.pos[i].y) < 4.9 && D(e.pos[i].x) > 100.2 && D(e.pos[i].x) < 159.8) under++;
            bad_deck += under > 0;
            shots++;
        }
    CHECK(bad_wall == 0, "tunnelling: %d throws at a 10 cm wall at 30/60/80 m/s, %d got through", shots, bad_wall);
    CHECK(bad_deck == 0, "tunnelling: %d drops at a 5 cm deck at 30/60/80 m/s, %d got through", shots, bad_deck);
}

static void t_scenes(void)
{
    /* stairs: 10 steps of 0.2 m, 0.35 deep */
    {
        rp_boxworld b;
        flat(&b, 0, RP_ROAD);
        for (int s = 0; s < 10; s++) rp_boxworld_add(&b, V3(50 + s * 0.35, -1, 30), V3(60, s * 0.2 + 0.2, 36));
        rp_doll d;
        rp_spawn(&d, V3(54, 3.5, 33), 16384, V3(1, 0, 0), V3(0, 0, 2));
        run(&d, &b.w, NULL, 500);
        int in = 0;
        for (int s = 0; s < 10; s++) in += inside_box(&d, &b.box[s], 0.05);
        CHECK(!in && d.state == RP_ASLEEP, "scene stairs: comes to rest on the steps, nothing inside them (asleep %d, inside %d)", d.state == RP_ASLEEP, in);
        CHECK(stretch(&d) < 0.07, "scene stairs: bones the right length (%.1f%%)", 100 * stretch(&d));
    }
    /* a 30 degree slope: slides and settles, does not float or sink */
    {
        rp_boxworld b;
        rp_boxworld_init(&b, M(16));
        for (int i = 0; i < RP_BW_CELLS; i++)
            for (int j = 0; j < RP_BW_CELLS; j++) b.h[i][j] = M(i * 16 * 0.5774 > 100 ? 100 : i * 16 * 0.5774), b.mat[i][j] = RP_ROAD;
        rp_doll d;
        rp_spawn(&d, V3(40, 24, 40), 8000, ZERO, ZERO);
        run(&d, &b.w, NULL, 900);
        CHECK(sunk(&d, &b) < 0.04, "scene slope: never in the slope (%.3f m)", sunk(&d, &b));
        CHECK(stretch(&d) < 0.08, "scene slope: bones the right length (%.1f%%)", 100 * stretch(&d));
        CHECK(speedmax(&d) < 12, "scene slope: a slide, not a launch (%.1f m/s)", speedmax(&d));
        rp_doll g;
        rp_boxworld sand = b;
        for (int i = 0; i < RP_BW_CELLS; i++) for (int j = 0; j < RP_BW_CELLS; j++) sand.mat[i][j] = RP_SAND;
        sand.w.user = &sand;
        rp_spawn(&g, V3(40, 24, 40), 8000, ZERO, ZERO);
        run(&g, &sand.w, NULL, 900);
        CHECK(g.state == RP_ASLEEP, "scene slope: on sand it grips and sleeps (state %d)", g.state);
    }
    /* a corner: thrown into the inside corner of two walls */
    {
        rp_boxworld b;
        flat(&b, 0, RP_ROAD);
        rp_boxworld_add(&b, V3(60, -1, 0), V3(62, 10, 100));
        rp_boxworld_add(&b, V3(0, -1, 70), V3(100, 10, 72));
        rp_doll d;
        rp_spawn(&d, V3(55, 0.5, 65), 5000, V3(9, 3, 9), V3(1, 3, 2));
        run(&d, &b.w, NULL, 400);
        int in = inside_box(&d, &b.box[0], 0.03) + inside_box(&d, &b.box[1], 0.03);
        CHECK(!in && stretch(&d) < 0.08, "scene corner: no joint inside either wall (%d), bones %.1f%%", in, 100 * stretch(&d));
    }
    /* stepping off a 12 m roof */
    {
        rp_boxworld b;
        flat(&b, 0, RP_ROAD);
        rp_boxworld_add(&b, V3(20, -1, 20), V3(40, 12, 60));
        rp_doll d;
        rp_spawn(&d, V3(39.6, 12.0, 40), 16384, V3(6, 0, 0), ZERO);
        long hurt = 0;
        for (int i = 0; i < 400; i++) { rp_step(&d, &b.w, NULL); hurt += d.hurt; }
        int in = inside_box(&d, &b.box[0], 0.04);
        CHECK(!in && D(d.pos[0].x) > 39.5 && d.state == RP_ASLEEP, "scene roof: off a roof edge, lands in the street, asleep (inside %d, x %.1f, state %d)", in, D(d.pos[0].x), d.state);
        CHECK(hurt > 1500 && hurt < 60000, "scene roof: a 12 m fall costs %ld J in all (fall damage: the joints' speed changes as they hit, a share of the 7000 J a 63 kg body has at 15 m/s)", hurt);
    }
}

static void t_car(void)
{
    rp_boxworld b;
    flat(&b, 0, RP_ROAD);
    for (int k = 0; k < 2; k++) {
        double v = k ? 20 : 1;
        rp_doll d;
        rp_spawn(&d, V3(40, 0.0, 40), 0, ZERO, ZERO);
        rp_car c;
        memset(&c, 0, sizeof c);
        c.pos = V3(40, 0.7, 30), c.vel = V3(0, 0, v), c.half_x = M(0.9), c.half_y = M(0.7), c.half_z = M(2.2), c.mass = M(1400);
        c.m[0] = c.m[4] = c.m[8] = RP_ONE;
        double hurt = 0, hurt_car = 0;
        int cars = 0;
        for (int i = 0; i < 90; i++) {
            c.pos.z += c.vel.z / 60;
            rp_step(&d, &b.w, &c);
            hurt += (double)d.hurt, hurt_car += (double)d.hurt_car;
            for (int e = 0; e < d.nev; e++) cars += d.ev[e].kind == RP_EV_CAR;
        }
        double vz = 0;
        for (int i = 0; i < RP_P; i++) vz += D(d.vel[i].z);
        if (k) {
            CHECK(D(d.pos[0].z) > 44, "car: hit at 20 m/s it is thrown ahead of the car (z %.1f)", D(d.pos[0].z));
            CHECK(hurt > 5 && hurt_car > 5 && cars > 0, "car: the hit costs the doll %.1f and shows on the car side as %.1f (%d car events)", hurt, hurt_car, cars);
        } else {
            CHECK(hurt < 5, "car: crawling at 1 m/s it is only pushed, not hurt (%.2f)", hurt);
        }
    }
}

static void t_motor(void)
{
    rp_boxworld b;
    flat(&b, 0, RP_ROAD);
    rp_doll d;
    rp_spawn(&d, V3(40, 4, 40), 0, ZERO, ZERO);
    rp_motor(&d, RP_POSE_BRACE, RP_ONE);
    run(&d, &b.w, NULL, 20);
    double hands = D(d.pos[RP_HDL].y) - D(d.pos[RP_PELVIS].y);
    CHECK(hands > 0.1, "motor: braced in the air the hands come up (%.2f m above the pelvis)", hands);
    /* get up from lying */
    rp_spawn(&d, V3(40, 0.05, 40), 0, V3(2, 1, 0), V3(0, 0, 8));
    run(&d, &b.w, NULL, 200);
    rp_motor(&d, RP_POSE_STAND, RP_ONE);
    run(&d, &b.w, NULL, 240);
    double head = D(d.pos[RP_HEAD].y);
    CHECK(head > 1.35, "motor: the stand pose gets a lying doll up (head %.2f m)", head);
    CHECK(stretch(&d) < 0.08 && sunk(&d, &b) < 0.05, "motor: standing keeps bones %.1f%% and feet on the road (%.3f)", 100 * stretch(&d), sunk(&d, &b));
    rp_motor(&d, RP_POSE_NONE, 0);
    run(&d, &b.w, NULL, 120);
    CHECK(D(d.pos[RP_HEAD].y) < head - 0.3, "motor: limp again it falls (%.2f m)", D(d.pos[RP_HEAD].y));
}

static void t_soak(void)
{
    rp_boxworld b;
    flat(&b, 0, RP_ROAD);
    rp_boxworld_add(&b, V3(60, -1, 0), V3(60.2, 12, 500));
    rp_boxworld_add(&b, V3(80, -1, 20), V3(120, 15, 80));
    srand(7);
    int bad = 0, asleep = 0, n = 200;
    double wstretch = 0, wsunk = 0, wend = 0;
    clock_t t0 = clock();
    uint32_t steps = 0;
    for (int k = 0; k < n; k++) {
        rp_doll d;
        double sp = 5 + rand() % 70;
        double a = (rand() % 628) / 100.0;
        rp_spawn(&d, V3(30 + rand() % 40, rand() % 8 * 1.0, 100 + rand() % 200), rand() & 65535, V3(sp * cos(a), (rand() % 20), sp * sin(a)), V3((rand() % 15) - 7, (rand() % 15) - 7, (rand() % 15) - 7));
        for (int i = 0; i < 600; i++) {
            rp_step(&d, &b.w, NULL);
            double s = stretch(&d);
            if (i > 30 && s > wstretch) wstretch = s;
            double sk = sunk(&d, &b);
            if (sk > wsunk) wsunk = sk;
        }
        steps += d.steps;
        if (d.state == RP_ASLEEP && stretch(&d) > wend) wend = stretch(&d);
        asleep += d.state == RP_ASLEEP;
        bad += inside_box(&d, &b.box[1], 0.05);
    }
    double ms = 1000.0 * (clock() - t0) / CLOCKS_PER_SEC;
    CHECK(bad == 0, "soak: %d random throws of up to 75 m/s, 10 s each: %d ended inside the block", n, bad);
    CHECK(wstretch < 0.75, "soak: worst bone length error %.1f%% (a forearm in the frame of a 60 m/s hit on a wall; transient)", 100 * wstretch);
    CHECK(wend < 0.06, "soak: worst bone length error of a doll that came to rest %.1f%%", 100 * wend);
    CHECK(wsunk < 0.12, "soak: deepest into the ground %.3f m", wsunk);
    CHECK(asleep >= n * 9 / 10, "soak: %d of %d asleep after 10 s", asleep, n);
    printf("info  soak cost: %.2f ms a throw of 600 frames on this PC (%u substeps)\n", ms / n, steps / n);
}

int main(void)
{
    t_determinism();
    t_energy();
    t_bounce();
    t_rest();
    t_tunnel();
    t_scenes();
    t_car();
    t_motor();
    t_soak();
    printf("%s: %d failed\n", fails ? "FAILED" : "ALL OK", fails);
    return fails != 0;
}
