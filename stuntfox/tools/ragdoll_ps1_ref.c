/* Reference solver for the PS1 port's ragdoll (see ragdoll_ps1_ref.h and design/ragdoll_ps1.md). Position based
   (small steps: a few substeps a 60 Hz frame, each with a couple of passes), integer only, so the PC and the
   console agree to the bit. 18 joints, 17 capsules, joint ranges, hinges for knees and elbows, a spine that
   folds, motors that hold a pose, friction and restitution by surface, swept tests against thin walls,
   a car as an oriented box, and sleeping. */
#include "ragdoll_ps1_ref.h"
#include <string.h>

typedef int64_t i64;
typedef uint64_t u64;
rp_surface rp_surfaces[RP_NSURF] = {
    [RP_ROAD] = {700000, 300000}, [RP_GRASS] = {1000000, 160000}, [RP_SAND] = {1300000, 60000},
    [RP_WATER] = {2000000, 0}, [RP_ROOF] = {650000, 320000},
};

static fx mul(fx a, fx b) { return (fx)(((i64)a * b) >> RP_FB); }
static fx dvd(fx a, fx b) { return b ? (fx)(((i64)a * RP_ONE) / b) : 0; }
static fx iabs(fx a) { return a < 0 ? -a : a; }
static u64 isqrt64(u64 v)
{
    u64 r = 0, b = (u64)1 << 62;
    while (b > v) b >>= 2;
    while (b) {
        if (v >= r + b) v -= r + b, r = (r >> 1) + b;
        else r >>= 1;
        b >>= 2;
    }
    return r;
}
static rp_v3 V(fx x, fx y, fx z) { rp_v3 v = {x, y, z}; return v; }
static rp_v3 add(rp_v3 a, rp_v3 b) { return V(a.x + b.x, a.y + b.y, a.z + b.z); }
static rp_v3 sub(rp_v3 a, rp_v3 b) { return V(a.x - b.x, a.y - b.y, a.z - b.z); }
static rp_v3 scl(rp_v3 a, fx k) { return V(mul(a.x, k), mul(a.y, k), mul(a.z, k)); }
static fx dot(rp_v3 a, rp_v3 b) { return (fx)((((i64)a.x * b.x) + ((i64)a.y * b.y) + ((i64)a.z * b.z)) >> RP_FB); }
static rp_v3 cross(rp_v3 a, rp_v3 b)
{
    return V((fx)((((i64)a.y * b.z) - ((i64)a.z * b.y)) >> RP_FB), (fx)((((i64)a.z * b.x) - ((i64)a.x * b.z)) >> RP_FB),
             (fx)((((i64)a.x * b.y) - ((i64)a.y * b.x)) >> RP_FB));
}
static fx len(rp_v3 a) { return (fx)isqrt64((u64)((i64)a.x * a.x + (i64)a.y * a.y + (i64)a.z * a.z)); }
static rp_v3 norm(rp_v3 a)
{
    fx l = len(a);
    return l ? V(dvd(a.x, l), dvd(a.y, l), dvd(a.z, l)) : V(0, RP_ONE, 0);
}
static fx mm(int v) { return (fx)(((i64)v * RP_ONE) / 1000); }

static const int sin_q[65] = {0, 25733, 51451, 77138, 102778, 128357, 153858, 179267, 204567, 229744, 254783, 279669, 304386, 328919, 353255, 377377, 401273, 424926, 448324, 471452, 494295, 516841, 539076, 560986, 582558, 603779, 624636, 645117, 665210, 684901, 704181, 723036, 741455, 759428, 776944, 793991, 810560, 826641, 842224, 857300, 871859, 885893, 899394, 912352, 924761, 936614, 947901, 958618, 968758, 978314, 987281, 995652, 1003425, 1010592, 1017151, 1023098, 1028428, 1033138, 1037227, 1040690, 1043527, 1045735, 1047313, 1048260, 1048576};
static fx rsin(int a)                          /* a: 65536 a turn */
{
    a &= 65535;
    int q = a >> 14, t = a & 16383;
    if (q & 1) t = 16384 - t;
    int i = t >> 8, f = t & 255, j = i < 64 ? i + 1 : 64;
    fx s = sin_q[i] + (fx)(((i64)(sin_q[j] - sin_q[i]) * f) >> 8);
    return q & 2 ? -s : s;
}
static fx rcos(int a) { return rsin(a + 16384); }

/* ---- the doll ---- */
static const int16_t pose_mm[RP_NPOSE][RP_P][3] = {
    {{0}},
    /* brace: crouched, arms up and forward, head tucked */
    {{0, 800, 0}, {0, 960, 60}, {0, 1200, 110}, {0, 1370, 140}, {-190, 1220, 100}, {190, 1220, 100}, {-210, 1180, 330}, {210, 1180, 330},
     {-180, 1330, 520}, {180, 1330, 520}, {-100, 790, 0}, {100, 790, 0}, {-110, 480, 300}, {110, 480, 300}, {-100, 90, 40}, {100, 90, 40},
     {-100, 30, 190}, {100, 30, 190}},
    /* stand */
    {{0, 950, 0}, {0, 1130, 0}, {0, 1400, 0}, {0, 1600, 0}, {-190, 1400, 0}, {190, 1400, 0}, {-210, 1130, 0}, {210, 1130, 0},
     {-220, 880, 40}, {220, 880, 40}, {-100, 930, 0}, {100, 930, 0}, {-100, 500, 10}, {100, 500, 10}, {-100, 90, 0}, {100, 90, 0},
     {-100, 30, 150}, {100, 30, 150}},
    /* fetal: curled on the side */
    {{0, 260, 0}, {0, 330, 110}, {0, 400, 230}, {0, 440, 340}, {-190, 380, 230}, {190, 380, 230}, {-130, 300, 330}, {130, 300, 330},
     {-70, 280, 380}, {70, 280, 380}, {-100, 250, 0}, {100, 250, 0}, {-100, 330, 300}, {100, 330, 300}, {-100, 140, 160}, {100, 140, 160},
     {-100, 60, 60}, {100, 60, 60}},
};
static const uint8_t bone_ab[RP_BONES][2] = {
    {RP_PELVIS, RP_SPINE}, {RP_SPINE, RP_CHEST}, {RP_CHEST, RP_HEAD}, {RP_CHEST, RP_SHL}, {RP_CHEST, RP_SHR}, {RP_PELVIS, RP_HPL},
    {RP_PELVIS, RP_HPR}, {RP_SHL, RP_ELL}, {RP_ELL, RP_HDL}, {RP_SHR, RP_ELR}, {RP_ELR, RP_HDR}, {RP_HPL, RP_KNL}, {RP_KNL, RP_ANL},
    {RP_ANL, RP_TOL}, {RP_HPR, RP_KNR}, {RP_KNR, RP_ANR}, {RP_ANR, RP_TOR},
};
static const int16_t bone_r_mm[RP_BONES] = {130, 140, 90, 60, 60, 80, 80, 55, 45, 55, 45, 80, 60, 40, 80, 60, 40};
static const int16_t part_r_mm[RP_P] = {130, 130, 130, 110, 70, 70, 55, 55, 45, 45, 85, 85, 70, 70, 55, 55, 40, 40};
static const int16_t part_kg[RP_P] = {12, 8, 10, 5, 3, 3, 2, 2, 1, 1, 4, 4, 4, 4, 2, 2, 1, 1};   /* (x1, rounded) */

/* ranges: a b, min and max as a share of the pair's rest distance (Q10: 1024 = 1). A max over 1 where the bones already
   hold a pair at most as far as it stands (a straight leg is longer than the standing pose's, whose knee is bent a hair): a max
   under the bones' own reach fights them and pumps energy in */
typedef struct { uint8_t a, b; int16_t lo, hi; } Range;
static const Range ranges[] = {
    {RP_PELVIS, RP_CHEST, 700, 1200},   /* the spine folds to 70% (sitting up .. curled), not more */
    {RP_PELVIS, RP_HEAD, 640, 1200},
    {RP_SHL, RP_HPL, 780, 1200}, {RP_SHR, RP_HPR, 780, 1200}, {RP_SHL, RP_HPR, 800, 1100}, {RP_SHR, RP_HPL, 800, 1100},
    {RP_HPL, RP_ANL, 150, 1200}, {RP_HPR, RP_ANR, 150, 1200},          /* knees: fold nearly to the heel */
    {RP_SHL, RP_HDL, 180, 1200}, {RP_SHR, RP_HDR, 180, 1200},          /* elbows */
    {RP_CHEST, RP_ELL, 700, 1200}, {RP_CHEST, RP_ELR, 700, 1200},      /* the shoulders' cone: an arm cannot fold into the chest */
    {RP_SPINE, RP_KNL, 780, 1100}, {RP_SPINE, RP_KNR, 780, 1100},      /* the hips' cone */
    {RP_KNL, RP_TOL, 780, 1200}, {RP_KNR, RP_TOR, 780, 1200},          /* ankles */
    {RP_CHEST, RP_HEAD, 900, 1200},
    {RP_SHL, RP_HEAD, 900, 1200}, {RP_SHR, RP_HEAD, 900, 1200},
};
#define NRANGE ((int)(sizeof ranges / sizeof ranges[0]))
static const uint8_t braces[][2] = {                 /* rigid ties that make the torso a body */
    {RP_SHL, RP_SHR}, {RP_HPL, RP_HPR}, {RP_SPINE, RP_SHL}, {RP_SPINE, RP_SHR}, {RP_SPINE, RP_HPL}, {RP_SPINE, RP_HPR},
    {RP_PELVIS, RP_SHL}, {RP_PELVIS, RP_SHR}, {RP_CHEST, RP_HPL}, {RP_CHEST, RP_HPR}, {RP_CHEST, RP_SPINE},
};
#define NBRACE ((int)(sizeof braces / sizeof braces[0]))
static const uint8_t selfp[][2] = {
    {RP_HDL, RP_HEAD}, {RP_HDR, RP_HEAD}, {RP_HDL, RP_CHEST}, {RP_HDR, RP_CHEST}, {RP_KNL, RP_KNR}, {RP_ANL, RP_ANR}, {RP_ELL, RP_SPINE},
    {RP_ELR, RP_SPINE}, {RP_HDL, RP_PELVIS}, {RP_HDR, RP_PELVIS}, {RP_KNL, RP_SPINE}, {RP_KNR, RP_SPINE}, {RP_TOL, RP_TOR}, {RP_HDL, RP_HDR},
};
#define NSELF ((int)(sizeof selfp / sizeof selfp[0]))

static fx rest_bone[RP_BONES], rest_brace[NBRACE], rest_range[NRANGE], radius[RP_P], invm[RP_P], rest_set;
static fx pose_fx[RP_NPOSE][RP_P][3];
static void init_tables(void)
{
    if (rest_set) return;
    for (int p = 0; p < RP_NPOSE; p++)
        for (int i = 0; i < RP_P; i++)
            for (int a = 0; a < 3; a++)
                pose_fx[p][i][a] = mm(pose_mm[p == 0 ? RP_POSE_STAND : p][i][a]);
    rp_v3 *st = (rp_v3 *)pose_fx[RP_POSE_STAND];
    for (int i = 0; i < RP_BONES; i++) rest_bone[i] = len(sub(st[bone_ab[i][1]], st[bone_ab[i][0]]));
    for (int i = 0; i < NBRACE; i++) rest_brace[i] = len(sub(st[braces[i][1]], st[braces[i][0]]));
    for (int i = 0; i < NRANGE; i++) rest_range[i] = len(sub(st[ranges[i].b], st[ranges[i].a]));
    for (int i = 0; i < RP_P; i++) radius[i] = mm(part_r_mm[i]), invm[i] = dvd(RP_ONE, part_kg[i] * RP_ONE);
    rest_set = 1;
}
int rp_bones_of_doll(void) { return RP_BONES; }

fx rp_bone_r(int b) { return mm(bone_r_mm[b]); }
rp_v3 rp_bone_a(const rp_doll *d, int b) { return d->pos[bone_ab[b][0]]; }
rp_v3 rp_bone_b(const rp_doll *d, int b) { return d->pos[bone_ab[b][1]]; }
void rp_frame(const rp_doll *d, int b, fx m[9])
{
    rp_v3 along = norm(sub(rp_bone_b(d, b), rp_bone_a(d, b)));
    rp_v3 side = sub(d->pos[RP_HPR], d->pos[RP_HPL]);
    rp_v3 up = norm(cross(along, side));
    rp_v3 right = norm(cross(up, along));
    m[0] = right.x, m[1] = right.y, m[2] = right.z, m[3] = up.x, m[4] = up.y, m[5] = up.z, m[6] = along.x, m[7] = along.y, m[8] = along.z;
}

void rp_spawn(rp_doll *d, rp_v3 feet, int yaw, rp_v3 v, rp_v3 w)
{
    init_tables();
    memset(d, 0, sizeof *d);
    fx c = rcos(yaw), s = rsin(yaw);
    for (int i = 0; i < RP_P; i++) {
        rp_v3 l = V(pose_fx[RP_POSE_STAND][i][0], pose_fx[RP_POSE_STAND][i][1], pose_fx[RP_POSE_STAND][i][2]);
        rp_v3 p = V(mul(l.x, c) + mul(l.z, s), l.y, mul(l.z, c) - mul(l.x, s));
        d->pos[i] = add(feet, p);
        rp_v3 r = sub(p, V(0, pose_fx[RP_POSE_STAND][0][1], 0));
        d->vel[i] = add(v, cross(w, r));
    }
    d->state = RP_LIVE;
    d->nsub = 4;
}
void rp_wake(rp_doll *d) { if (d->state == RP_ASLEEP) d->state = RP_LIVE; d->quiet = 0; }
void rp_impulse(rp_doll *d, int part, rp_v3 dv) { d->vel[part] = add(d->vel[part], dv); rp_wake(d); }
void rp_motor(rp_doll *d, int pose, fx brace) { d->pose = (uint8_t)pose; d->brace = brace; if (brace) rp_wake(d); }

#define G (10286002)                           /* 9.81 m/s^2 */
#define HZ 60

typedef struct { rp_v3 n; fx depth; int mat; fx e, mu; uint8_t kind; } Contact;

static void distance(rp_v3 *p, int a, int b, fx rest, fx lo, fx hi)
{
    rp_v3 d = sub(p[b], p[a]);
    fx l = len(d), t = l;
    if (!l) return;
    if (l < lo) t = lo; else if (l > hi) t = hi; else return;
    fx k = dvd(l - t, l), ws = invm[a] + invm[b];
    d = scl(d, dvd(k, ws));
    p[a] = add(p[a], scl(d, invm[a]));
    p[b] = sub(p[b], scl(d, invm[b]));
    (void)rest;
}

/* a hinge: joint j between a and b bends only toward the way the doll faces (sign +1 knee, -1 elbow). A plane test flips
   with every wobble of a straight leg and pumps energy in, so it is a ball behind the limb the joint may not enter
   (centre behind the limb's middle by a bone length, radius a bone length: a straight leg touches it, a bent one is clear
   of it), pushed out of by inverse mass like any other contact, and the limb's own bones keep the lengths. */
static void hinge(rp_v3 *p, int a, int j, int b, int sign)
{
    /* which way is front: the chest's, taken off the limb's own line; where the limb points along it (a leg kicked
       forward, an arm reaching) there is no front to speak of, and the limit fades out */
    rp_v3 side = norm(sub(p[RP_HPR], p[RP_HPL]));
    rp_v3 up = norm(sub(p[RP_CHEST], p[RP_PELVIS]));
    rp_v3 F = cross(side, up);
    rp_v3 dn = norm(sub(p[b], p[a]));
    rp_v3 fd = sub(F, scl(dn, dot(F, dn)));
    fx fl = len(fd);
    if (fl < RP_ONE * 35 / 100) return;
    fx k = (fl - RP_ONE * 35 / 100) * 3 / 2;
    if (k > RP_ONE) k = RP_ONE;
    rp_v3 fwd = V(dvd(fd.x, fl), dvd(fd.y, fl), dvd(fd.z, fl));
    rp_v3 mid = V((p[a].x + p[b].x) >> 1, (p[a].y + p[b].y) >> 1, (p[a].z + p[b].z) >> 1);
    fx r = len(sub(p[j], p[a]));                                          /* (the upper bone) */
    rp_v3 q = sub(mid, scl(fwd, sign * r));
    rp_v3 dq = sub(p[j], q);
    fx l = len(dq);
    if (l < r) {
        rp_v3 need;
        if (l < RP_ONE / 256) need = scl(fwd, sign * r);      /* (dead centre: out the front) */
        else need = V((fx)((i64)dq.x * (r - l) / l), (fx)((i64)dq.y * (r - l) / l), (fx)((i64)dq.z * (r - l) / l));
        need = scl(need, k);
        fx wj = invm[j], wm = (invm[a] + invm[b]) / 4, ws = wj + wm;
        rp_v3 back = scl(need, dvd(wm, ws));
        p[j] = add(p[j], scl(need, dvd(wj, ws)));
        p[a] = sub(p[a], back);
        p[b] = sub(p[b], back);
    }
}

static void doll_frame(const rp_v3 *p, int upright, rp_v3 *r, rp_v3 *u, rp_v3 *f)
{
    rp_v3 right = norm(sub(p[RP_HPR], p[RP_HPL])), up = upright ? V(0, RP_ONE, 0) : norm(sub(p[RP_CHEST], p[RP_PELVIS]));
    rp_v3 fw = cross(right, up);
    if (upright) { fw = norm(V(fw.x, 0, fw.z)); right = norm(cross(up, fw)); }
    else fw = norm(fw), up = cross(fw, right);
    *r = right, *u = up, *f = fw;
}

static void motors(rp_doll *d, rp_v3 *p, const rp_world *w, fx h)
{
    if (!d->pose || !d->brace) return;
    rp_v3 r, u, f;
    int stand = d->pose == RP_POSE_STAND;
    doll_frame(p, stand && d->brace > RP_ONE / 2, &r, &u, &f);
    rp_v3 o = p[RP_PELVIS];
    if (stand && d->brace > RP_ONE / 2) {                        /* get-up: the pelvis is held up over the floor under it */
        fx gh, y = o.y;
        rp_v3 n;
        int m;
        if (w->floor(w->user, o.x, o.z, y + RP_ONE, &gh, &n, &m)) {
            fx want = gh + pose_fx[RP_POSE_STAND][0][1];
            fx lift = mul(want - o.y, mul(d->brace, mul(h, 6 * RP_ONE)));
            if (lift > mm(15)) lift = mm(15);
            if (lift < -mm(15)) lift = -mm(15);
            for (int i = 0; i < RP_P; i++) p[i].y += lift >> 1;
            o.y += lift >> 1;
        }
    }
    fx k = mul(d->brace, mul(h, 18 * RP_ONE));                  /* share of the way to the target a substep (18/s) */
    int up_mode = stand && d->brace > RP_ONE / 2;
    rp_v3 dls[RP_P];
    memset(dls, 0, sizeof dls);
    for (int i = 1; i < RP_P; i++) {
        /* a pose held in a frame made of the torso must not drive the torso (the frame would chase its own target and
           roll); with the world's up as the frame (get-up) everything is driven */
        if (!up_mode && (i == RP_SPINE || i == RP_CHEST || i == RP_SHL || i == RP_SHR || i == RP_HPL || i == RP_HPR)) continue;
        rp_v3 l = V(pose_fx[d->pose][i][0], pose_fx[d->pose][i][1] - pose_fx[d->pose][0][1], pose_fx[d->pose][i][2]);
        rp_v3 t = add(o, add(add(scl(r, l.x), scl(u, l.y)), scl(f, l.z)));
        rp_v3 dl = scl(sub(t, p[i]), k);
        fx m = len(dl);
        if (m > mm(4)) dl = scl(dl, dvd(mm(4), m));
        dls[i] = dl;
    }
    /* an actuator pushes off the rest of the body: no net momentum (the whole body moves back by the mass-weighted mean
       of the moves) and no net spin (turned back about the mass centre by the moves' angular impulse over an isotropic
       inertia), or a braced doll in the air somersaults */
    i64 mx = 0, my = 0, mz = 0, M = 0;
    for (int i = 0; i < RP_P; i++) { mx += (i64)p[i].x * part_kg[i], my += (i64)p[i].y * part_kg[i], mz += (i64)p[i].z * part_kg[i], M += part_kg[i]; }
    rp_v3 com = V((fx)(mx / M), (fx)(my / M), (fx)(mz / M));
    rp_v3 mom = {0, 0, 0}, L = {0, 0, 0};
    i64 I = 0;
    for (int i = 0; i < RP_P; i++) {
        rp_v3 r = sub(p[i], com), c = cross(r, dls[i]);
        mom = add(mom, scl(dls[i], part_kg[i] * RP_ONE));
        L = add(L, scl(c, part_kg[i] * RP_ONE));
        I += (((i64)r.x * r.x + (i64)r.y * r.y + (i64)r.z * r.z) >> RP_FB) * part_kg[i] * 2 / 3;
    }
    mom = scl(mom, dvd(RP_ONE, (fx)(M * RP_ONE)));
    rp_v3 om = I > 0 ? V((fx)(((i64)L.x * RP_ONE) / I), (fx)(((i64)L.y * RP_ONE) / I), (fx)(((i64)L.z * RP_ONE) / I)) : V(0, 0, 0);
    for (int i = 0; i < RP_P; i++) {
        rp_v3 r = sub(p[i], com);
        p[i] = sub(sub(add(p[i], dls[i]), mom), cross(om, r));
    }
}

static int collide(const rp_world *w, rp_v3 *pp, fx r, Contact *c, int first)
{
    int hit = 0;
    rp_v3 p = *pp, n;
    fx h, depth;
    int mat = RP_ROAD;
    if (w->floor(w->user, p.x, p.z, p.y, &h, &n, &mat)) {
        fx sd = dot(n, sub(p, V(p.x, h, p.z)));
        if (sd < r) {
            fx push = r - sd;
            p = add(p, scl(n, push));
            if (!first || push > c->depth) c->n = n, c->depth = push, c->mat = mat, c->kind = RP_EV_FLOOR;
            hit = 1;
        }
    }
    if (w->solid(w->user, p, r, &n, &depth)) {
        p = add(p, scl(n, depth));
        if (depth > c->depth || !hit) c->n = n, c->depth = depth, c->mat = RP_ROOF, c->kind = RP_EV_WALL;
        hit = 1;
    }
    *pp = p;
    return hit;
}

static void car_local(const rp_car *c, rp_v3 pos, rp_v3 p, rp_v3 *l)
{
    rp_v3 d = sub(p, pos);
    l->x = mul(d.x, c->m[0]) + mul(d.y, c->m[1]) + mul(d.z, c->m[2]);
    l->y = mul(d.x, c->m[3]) + mul(d.y, c->m[4]) + mul(d.z, c->m[5]);
    l->z = mul(d.x, c->m[6]) + mul(d.y, c->m[7]) + mul(d.z, c->m[8]);
}
static rp_v3 car_world(const rp_car *c, rp_v3 l)
{
    return V(mul(l.x, c->m[0]) + mul(l.y, c->m[3]) + mul(l.z, c->m[6]), mul(l.x, c->m[1]) + mul(l.y, c->m[4]) + mul(l.z, c->m[7]),
             mul(l.x, c->m[2]) + mul(l.y, c->m[5]) + mul(l.z, c->m[8]));
}
/* a ball against the car's box: out along the shallowest axis */
static int car_push(const rp_car *c, rp_v3 cpos, rp_v3 *pp, fx r, rp_v3 *n, fx *depth)
{
    rp_v3 l;
    car_local(c, cpos, *pp, &l);
    fx hx = c->half_x + r, hy = c->half_y + r, hz = c->half_z + r;
    if (iabs(l.x) >= hx || iabs(l.y) >= hy || iabs(l.z) >= hz) return 0;
    fx dx = hx - iabs(l.x), dy = hy - iabs(l.y), dz = hz - iabs(l.z);
    rp_v3 ax;
    fx dp;
    if (dx <= dy && dx <= dz) ax = V(l.x < 0 ? -RP_ONE : RP_ONE, 0, 0), dp = dx;
    else if (dy <= dz) ax = V(0, l.y < 0 ? -RP_ONE : RP_ONE, 0), dp = dy;
    else ax = V(0, 0, l.z < 0 ? -RP_ONE : RP_ONE), dp = dz;
    *n = car_world(c, ax);
    *depth = dp;
    *pp = add(*pp, scl(*n, dp));
    return 1;
}

static void event(rp_doll *d, int kind, int part, int mat, fx strength)
{
    if (d->nev < RP_EVENTS) {
        d->ev[d->nev].kind = (uint8_t)kind, d->ev[d->nev].part = (uint8_t)part, d->ev[d->nev].mat = (uint8_t)mat;
        d->ev[d->nev].strength = strength;
        d->nev++;
    }
}

void rp_step(rp_doll *d, const rp_world *w, const rp_car *car)
{
    init_tables();
    d->nev = 0, d->hurt = d->hurt_car = 0;
    if (d->state == RP_FREE) return;
    if (d->state == RP_ASLEEP) {
        if (!car || (iabs(car->pos.x - d->pos[0].x) > 8 * RP_ONE || iabs(car->pos.z - d->pos[0].z) > 8 * RP_ONE)) {
            d->contacts = 0;
            if (!d->brace) return;
        }
        d->state = RP_LIVE;
    }
    /* substeps from the fastest joint: nothing travels more than a few centimetres in one */
    fx vmax = 0;
    for (int i = 0; i < RP_P; i++) { fx m = iabs(d->vel[i].x) + iabs(d->vel[i].y) + iabs(d->vel[i].z); if (m > vmax) vmax = m; }
    int ns = 4 + (int)(((i64)vmax * 3 / 4) >> RP_FB) / 5;
    if (ns > 12) ns = 12;
    d->nsub = (uint8_t)ns;
    fx h = RP_ONE / HZ / ns;
    int touch[RP_P];
    memset(touch, 0, sizeof touch);
    for (int s = 0; s < ns; s++) {
        rp_v3 p0[RP_P], pre[RP_P];
        Contact ct[RP_P];
        memset(ct, 0, sizeof ct);
        fx damp = RP_ONE - mul(h, RP_ONE / 4);                  /* (air: 0.25/s) */
        for (int i = 0; i < RP_P; i++) {
            rp_v3 v = d->vel[i];
            v.y -= mul(G, h);
            v = scl(v, damp);
            fx m = len(v);
            if (m > 80 * RP_ONE) v = scl(v, dvd(80 * RP_ONE, m));
            d->vel[i] = v;
            pre[i] = v;
            p0[i] = d->pos[i];
            d->pos[i] = add(d->pos[i], scl(v, h));
        }
        rp_v3 cp = car ? add(car->pos, scl(car->vel, h * (s + 1))) : V(0, 0, 0);
        rp_v3 *p = d->pos;
        for (int it = 0; it < 3; it++) {
            for (int i = 0; i < RP_BONES; i++) distance(p, bone_ab[i][0], bone_ab[i][1], rest_bone[i], rest_bone[i], rest_bone[i]);
            for (int i = 0; i < NBRACE; i++) distance(p, braces[i][0], braces[i][1], rest_brace[i], rest_brace[i], rest_brace[i]);
            for (int i = 0; i < NRANGE; i++)
                distance(p, ranges[i].a, ranges[i].b, rest_range[i], (fx)(((i64)rest_range[i] * ranges[i].lo) >> 10), (fx)(((i64)rest_range[i] * ranges[i].hi) >> 10));
            if (it == 0) motors(d, p, w, h);
            hinge(p, RP_HPL, RP_KNL, RP_ANL, 1);
            hinge(p, RP_HPR, RP_KNR, RP_ANR, 1);
            hinge(p, RP_SHL, RP_ELL, RP_HDL, -1);
            hinge(p, RP_SHR, RP_ELR, RP_HDR, -1);
            for (int i = 0; i < NSELF; i++) {
                int a = selfp[i][0], b = selfp[i][1];
                rp_v3 dd = sub(p[b], p[a]);
                fx l = len(dd), rr = (radius[a] + radius[b]) * 3 / 4;
                if (l && l < rr) {
                    dd = scl(dd, dvd(dvd(l - rr, l), invm[a] + invm[b]));
                    p[a] = add(p[a], scl(dd, invm[a]));
                    p[b] = sub(p[b], scl(dd, invm[b]));
                }
            }
            for (int i = 0; i < RP_P; i++) {
                /* a fast joint: the swept path first, so a thin wall or deck stops it */
                rp_v3 dpos = sub(p[i], p0[i]);
                if (iabs(dpos.x) + iabs(dpos.y) + iabs(dpos.z) > radius[i] / 2) {
                    fx t;
                    rp_v3 n;
                    if (w->sweep(w->user, p0[i], p[i], radius[i], &t, &n)) {
                        p[i] = add(add(p0[i], scl(dpos, t)), scl(n, mm(1)));
                        ct[i].n = n, ct[i].depth = mm(1), ct[i].mat = RP_ROOF, ct[i].kind = RP_EV_WALL;
                        touch[i] = 1;
                    }
                }
                Contact c = ct[i];
                rp_v3 q = p[i];
                if (collide(w, &q, radius[i], &c, 1) || c.depth) {
                    /* friction: the sideways move this substep is held (static) or cut (sliding) by mu x the push */
                    rp_v3 dm = sub(q, p0[i]);
                    rp_v3 tg = sub(dm, scl(c.n, dot(dm, c.n)));
                    fx tl = len(tg), lim = mul(c.depth, rp_surfaces[c.mat].mu);
                    if (tl) q = sub(q, tl <= lim ? tg : scl(tg, dvd(lim, tl)));
                    ct[i] = c;
                    touch[i] = 1;
                    p[i] = q;
                }
                if (car) {
                    rp_v3 n;
                    fx dp;
                    if (car_push(car, cp, &p[i], radius[i], &n, &dp)) {
                        ct[i].kind = RP_EV_CAR;
                        if (dp >= ct[i].depth) ct[i].n = n, ct[i].depth = dp;
                        ct[i].mat = RP_ROAD;
                        touch[i] = 1;
                    }
                }
                /* bones: the middle of a long one is a ball as well, moved by moving both ends */
            }
            for (int b = 0; b < RP_BONES; b++) {
                int a = bone_ab[b][0], c2 = bone_ab[b][1];
                if (rest_bone[b] < mm(250)) continue;
                rp_v3 m = V((p[a].x + p[c2].x) >> 1, (p[a].y + p[c2].y) >> 1, (p[a].z + p[c2].z) >> 1), m2 = m;
                Contact c;
                memset(&c, 0, sizeof c);
                int hit = collide(w, &m2, mm(bone_r_mm[b]), &c, 0);
                if (car) { rp_v3 n; fx dp; if (car_push(car, cp, &m2, mm(bone_r_mm[b]), &n, &dp)) { hit = 1; c.n = n, c.depth = dp, c.kind = RP_EV_CAR, c.mat = RP_ROAD; } }
                if (hit) {
                    rp_v3 dm = sub(m2, m);
                    p[a] = add(p[a], dm), p[c2] = add(p[c2], dm);
                    if (c.depth > ct[a].depth) ct[a] = c;
                    if (c.depth > ct[c2].depth) ct[c2] = c;
                    touch[a] = touch[c2] = 1;
                }
            }
        }
        /* speeds from where they got to; what came into a surface bounces by its e; the rest of a contact is damped */
        fx ih = dvd(RP_ONE, h), hard_e = 0;
        int hard_floor = 0;
        for (int i = 0; i < RP_P; i++) {
            rp_v3 v = scl(sub(d->pos[i], p0[i]), ih);
            Contact *c = &ct[i];
            if (c->depth) {
                fx vn = dot(pre[i], c->n);
                fx e = c->kind == RP_EV_CAR ? RP_ONE * 3 / 10 : rp_surfaces[c->mat].e;
                if (c->kind == RP_EV_CAR) vn = dot(sub(pre[i], car ? car->vel : V(0, 0, 0)), c->n);
                if (vn < -RP_ONE) {                              /* came in at over 1 m/s */
                    fx cur = dot(v, c->n), want = mul(-vn, e) + (c->kind == RP_EV_CAR && car ? dot(car->vel, c->n) : 0);
                    v = add(v, scl(c->n, want - cur));
                    fx st = -vn;
                    if (st > 3 * RP_ONE) {
                        if (c->kind == RP_EV_FLOOR && c->n.y > RP_ONE / 2 && (!hard_floor || e > hard_e)) hard_floor = 1, hard_e = e;
                        event(d, c->kind, i, c->mat, st);
                        int hurt = (int)(((i64)mul(st, st) * part_kg[i]) >> (RP_FB + 1));    /* J: half m v^2 */
                        d->hurt = d->hurt > 0x7fff0000 - hurt ? 0x7fff0000 : d->hurt + hurt;
                        if (c->kind == RP_EV_CAR) d->hurt_car = d->hurt_car > 0x7fff0000 - hurt ? 0x7fff0000 : d->hurt_car + hurt;
                    }
                }
                if (c->kind != RP_EV_CAR) {                    /* (a joint pushed out of something deep is not a launch) */
                    fx vup = dot(v, c->n), lim = (vn < -RP_ONE ? mul(-vn, e) : 0) + RP_ONE * 3 / 2;
                    if (vup > lim) v = sub(v, scl(c->n, vup - lim));
                }
                v = scl(v, RP_ONE - mul(h, 3 * RP_ONE));       /* rolling losses on the ground */
            }
            d->vel[i] = v;
        }
        /* the body bounces as one: a landing feet first would otherwise be eaten by the limbs folding. The mass-centre
           goes back up at e of the speed it came down at (the share the joints that hit the floor did not already give) */
        if (hard_floor) {
            i64 cpre = 0, cnow = 0, mt = 0;
            for (int i = 0; i < RP_P; i++) cpre += (i64)pre[i].y * part_kg[i], cnow += (i64)d->vel[i].y * part_kg[i], mt += part_kg[i];
            fx vpre = (fx)(cpre / mt), vnow = (fx)(cnow / mt), want = mul(-vpre, hard_e);
            if (vpre < -3 * RP_ONE && vnow < want) {
                fx add_ = want - vnow;
                for (int i = 0; i < RP_P; i++) d->vel[i].y += add_;
            }
        }
    }
    int nt = 0;
    fx vm = 0;
    for (int i = 0; i < RP_P; i++) {
        nt += touch[i];
        fx m = iabs(d->vel[i].x) + iabs(d->vel[i].y) + iabs(d->vel[i].z);
        if (m > vm) vm = m;
    }
    d->contacts = (uint8_t)nt;
    d->steps += ns;
    if (nt && vm < RP_ONE / 6 && !d->brace) {
        if (++d->quiet > 24) {
            d->state = RP_ASLEEP;
            for (int i = 0; i < RP_P; i++) d->vel[i] = V(0, 0, 0);
        }
    } else d->quiet = 0;
}

uint32_t rp_hash(const rp_doll *d)
{
    uint32_t h = 2166136261u;
    for (int i = 0; i < RP_P; i++)
        for (int a = 0; a < 3; a++) {
            const fx *pp = &d->pos[i].x, *vv = &d->vel[i].x;
            h = (h ^ (uint32_t)pp[a]) * 16777619u;
            h = (h ^ (uint32_t)vv[a]) * 16777619u;
        }
    return h;
}
int64_t rp_energy(const rp_doll *d)
{
    init_tables();
    i64 e = 0;
    for (int i = 0; i < RP_P; i++) {
        i64 v2 = ((i64)d->vel[i].x * d->vel[i].x + (i64)d->vel[i].y * d->vel[i].y + (i64)d->vel[i].z * d->vel[i].z) >> RP_FB;
        e += (v2 * part_kg[i]) >> 1;
        e += ((i64)G * d->pos[i].y >> RP_FB) * part_kg[i];
    }
    return e;
}

/* ---- a ready world: height field cells and boxes ---- */
static fx cell_h(const rp_boxworld *b, fx x, fx z, rp_v3 *n, int *mat)
{
    fx cs = b->cell;
    int ix = (int)(x / cs), iz = (int)(z / cs);
    if (x < 0) ix = 0;
    if (z < 0) iz = 0;
    if (ix > RP_BW_CELLS - 2) ix = RP_BW_CELLS - 2;
    if (iz > RP_BW_CELLS - 2) iz = RP_BW_CELLS - 2;
    fx fx_ = dvd(x - ix * cs, cs), fz = dvd(z - iz * cs, cs);
    fx h00 = b->h[ix][iz], h10 = b->h[ix + 1][iz], h01 = b->h[ix][iz + 1], h11 = b->h[ix + 1][iz + 1], hh, dx, dz;
    if (fx_ + fz <= RP_ONE) hh = h00 + mul(fx_, h10 - h00) + mul(fz, h01 - h00), dx = h10 - h00, dz = h01 - h00;
    else hh = h11 + mul(RP_ONE - fx_, h01 - h11) + mul(RP_ONE - fz, h10 - h11), dx = h11 - h01, dz = h11 - h10;
    *n = norm(V(-dvd(dx, cs), RP_ONE, -dvd(dz, cs)));
    *mat = b->mat[ix][iz];
    return hh;
}
static int bw_floor(void *u, fx x, fx z, fx y, fx *h, rp_v3 *n, int *mat)
{
    (void)y;
    *h = cell_h((rp_boxworld *)u, x, z, n, mat);
    return 1;
}
static int bw_solid(void *u, rp_v3 p, fx r, rp_v3 *n, fx *depth)
{
    rp_boxworld *b = u;
    for (int i = 0; i < b->nbox; i++) {
        const rp_box *x = &b->box[i];
        if (p.x < x->lo.x - r || p.x > x->hi.x + r || p.y < x->lo.y - r || p.y > x->hi.y + r || p.z < x->lo.z - r || p.z > x->hi.z + r) continue;
        /* nearest point of the box, else (inside) the shallowest face */
        rp_v3 c = V(p.x < x->lo.x ? x->lo.x : p.x > x->hi.x ? x->hi.x : p.x, p.y < x->lo.y ? x->lo.y : p.y > x->hi.y ? x->hi.y : p.y,
                    p.z < x->lo.z ? x->lo.z : p.z > x->hi.z ? x->hi.z : p.z);
        rp_v3 d = sub(p, c);
        fx l = len(d);
        if (l > 0 && l < r) { *n = V(dvd(d.x, l), dvd(d.y, l), dvd(d.z, l)); *depth = r - l; return 1; }
        if (l == 0) {
            fx f[6] = {p.x - x->lo.x, x->hi.x - p.x, p.y - x->lo.y, x->hi.y - p.y, p.z - x->lo.z, x->hi.z - p.z};
            int k = 0;
            for (int j = 1; j < 6; j++) if (f[j] < f[k]) k = j;
            rp_v3 nn[6] = {{-RP_ONE, 0, 0}, {RP_ONE, 0, 0}, {0, -RP_ONE, 0}, {0, RP_ONE, 0}, {0, 0, -RP_ONE}, {0, 0, RP_ONE}};
            *n = nn[k];
            *depth = f[k] + r;
            return 1;
        }
    }
    return 0;
}
static int bw_sweep(void *u, rp_v3 a, rp_v3 bb, fx r, fx *t, rp_v3 *n)
{
    rp_boxworld *b = u;
    fx best = RP_ONE + 1;
    rp_v3 d = sub(bb, a);
    for (int i = 0; i < b->nbox; i++) {
        const rp_box *x = &b->box[i];
        fx lo[3] = {x->lo.x - r, x->lo.y - r, x->lo.z - r}, hi[3] = {x->hi.x + r, x->hi.y + r, x->hi.z + r};
        const fx *a3 = &a.x, *d3 = &d.x;
        i64 t0 = 0, t1 = RP_ONE;
        int ax = -1, sg = 0, ok = 1;
        for (int k = 0; k < 3 && ok; k++) {
            if (!d3[k]) { if (a3[k] < lo[k] || a3[k] > hi[k]) ok = 0; continue; }
            i64 ta = ((i64)(lo[k] - a3[k]) * RP_ONE) / d3[k], tb = ((i64)(hi[k] - a3[k]) * RP_ONE) / d3[k];
            int s = d3[k] > 0 ? -1 : 1;
            if (ta > tb) { i64 tt = ta; ta = tb; tb = tt; }
            if (ta > t0) t0 = ta, ax = k, sg = s;
            if (tb < t1) t1 = tb;
            if (t0 > t1) ok = 0;
        }
        if (ok && ax >= 0 && t0 < best && t0 > 0) {
            best = (fx)t0;
            *n = V(ax == 0 ? sg * RP_ONE : 0, ax == 1 ? sg * RP_ONE : 0, ax == 2 ? sg * RP_ONE : 0);
        }
    }
    if (best > RP_ONE) return 0;
    *t = best > 2000 ? best - 2000 : 0;
    return 1;
}
void rp_boxworld_init(rp_boxworld *b, fx cell)
{
    memset(b, 0, sizeof *b);
    b->cell = cell;
    b->w.user = b, b->w.floor = bw_floor, b->w.solid = bw_solid, b->w.sweep = bw_sweep;
}
void rp_boxworld_add(rp_boxworld *b, rp_v3 lo, rp_v3 hi) { if (b->nbox < RP_BW_BOXES) b->box[b->nbox].lo = lo, b->box[b->nbox++].hi = hi; }
