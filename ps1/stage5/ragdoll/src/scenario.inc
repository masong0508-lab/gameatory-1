/* scenario.inc: the scripted test, shared by the PS1 disc and the PC checks (include after the solver .c).
   A car climbs a 14 degree ramp at 20 m/s, the driver bails out at the lip (thrown with the car's speed plus a kick
   and a spin), the car lands and runs into five pedestrians who turn into ragdolls as it reaches them; a building
   stands behind them. 60 Hz, 720 frames, then it starts over. Everything in Q20 metres. */
#define MM(v) ((fx)(((i64)(v) * 1048576) / 1000))
#define SC_FRAMES 720
#define NACT 6                                  /* [0] the driver, [1..5] pedestrians */
#define RAMP_Z0 MM(20000)
#define RAMP_Z1 MM(32000)
#define RAMP_HW MM(4000)
#define RAMP_SLOPE MM(250)
#define CAR_HX MM(900)
#define CAR_HY MM(600)
#define CAR_HZ MM(2200)

typedef struct { rp_doll d; int active, released; } Actor;
static Actor act[NACT];
static rp_car car;
static rp_world sc_w;
static rp_box sc_box[2];
static rp_v3 ramp_n;
static struct { fx y, z, vy, vz; int air, landed, tair; } cs;
static const struct { int x, z, yaw; } ped_at[5] = { {-700, 66000, 32768}, {400, 68000, 32768}, {1800, 67500, 31000}, {-2300, 70000, 34000}, {3000, 69500, 32768} };
static const int ped_shirt[6] = { 0xC03030, 0x3070D0, 0x30A050, 0xD0B030, 0xA040C0, 0xE08030 };   /* [0] = driver */
static int sc_frame_no;
static int sc_ped_x(int i) { return ped_at[i].x; }

#if defined(RP_REF) || (defined(RP_LEVEL) && RP_LEVEL == 0)
static i64 sdiv20(fx a, fx d) { return ((i64)a * RP_ONE) / d; }
#else
static i64 sdiv20(fx a, fx d) { u64 q = udiv64_32((u64)(uint32_t)(a < 0 ? -a : a) << RP_FB, (uint32_t)(d < 0 ? -d : d)); return ((a < 0) ^ (d < 0)) ? -(i64)q : (i64)q; }
#endif

static int sc_floor(void *u, fx x, fx z, fx y, fx *h, rp_v3 *n, int *mat)
{
    (void)u; (void)y;
    if (iabs(x) < RAMP_HW && z >= RAMP_Z0 && z < RAMP_Z1) { *h = mul(z - RAMP_Z0, RAMP_SLOPE); *n = ramp_n; *mat = RP_ROAD; return 1; }
    *h = 0; *n = V(0, RP_ONE, 0); *mat = RP_ROAD;
    return 1;
}
static int sc_solid(void *u, rp_v3 p, fx r, rp_v3 *n, fx *depth)
{
    (void)u;
    for (int i = 0; i < 2; i++) {
        const rp_box *x = &sc_box[i];
        if (p.x < x->lo.x - r || p.x > x->hi.x + r || p.y < x->lo.y - r || p.y > x->hi.y + r || p.z < x->lo.z - r || p.z > x->hi.z + r) continue;
        rp_v3 c = V(p.x < x->lo.x ? x->lo.x : p.x > x->hi.x ? x->hi.x : p.x, p.y < x->lo.y ? x->lo.y : p.y > x->hi.y ? x->hi.y : p.y,
                    p.z < x->lo.z ? x->lo.z : p.z > x->hi.z ? x->hi.z : p.z);
        rp_v3 d = sub(p, c);
        fx l = len(d);
        if (l > 0 && l < r) { *n = norm(d); *depth = r - l; return 1; }
        if (l == 0) {
            fx f[6] = {p.x - x->lo.x, x->hi.x - p.x, p.y - x->lo.y, x->hi.y - p.y, p.z - x->lo.z, x->hi.z - p.z};
            int k = 0;
            for (int j = 1; j < 6; j++) if (f[j] < f[k]) k = j;
            rp_v3 nn[6] = {{-RP_ONE, 0, 0}, {RP_ONE, 0, 0}, {0, -RP_ONE, 0}, {0, RP_ONE, 0}, {0, 0, -RP_ONE}, {0, 0, RP_ONE}};
            *n = nn[k]; *depth = f[k] + r;
            return 1;
        }
    }
    return 0;
}
static int sc_sweep(void *u, rp_v3 a, rp_v3 bb, fx r, fx *t, rp_v3 *n)
{
    (void)u;
    fx best = RP_ONE + 1;
    rp_v3 d = sub(bb, a);
    for (int i = 0; i < 2; i++) {
        const rp_box *x = &sc_box[i];
        fx lo[3] = {x->lo.x - r, x->lo.y - r, x->lo.z - r}, hi[3] = {x->hi.x + r, x->hi.y + r, x->hi.z + r};
        const fx *a3 = &a.x, *d3 = &d.x;
        if ((a.x < lo[0] && bb.x < lo[0]) || (a.x > hi[0] && bb.x > hi[0]) || (a.y < lo[1] && bb.y < lo[1]) || (a.y > hi[1] && bb.y > hi[1]) ||
            (a.z < lo[2] && bb.z < lo[2]) || (a.z > hi[2] && bb.z > hi[2])) continue;      /* the path's box misses the box: no hit (exact) */
        i64 t0 = 0, t1 = RP_ONE;
        int ax = -1, sg = 0, ok = 1;
        for (int k = 0; k < 3 && ok; k++) {
            if (!d3[k]) { if (a3[k] < lo[k] || a3[k] > hi[k]) ok = 0; continue; }
            i64 ta = sdiv20(lo[k] - a3[k], d3[k]), tb = sdiv20(hi[k] - a3[k], d3[k]);
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

static void car_matrix(int ang)       /* pitch about x: nose up for ang > 0 (65536 a turn) */
{
    fx s = rsin(ang), c = rcos(ang);
    car.m[0] = RP_ONE, car.m[1] = 0, car.m[2] = 0;
    car.m[3] = 0, car.m[4] = c, car.m[5] = -s;
    car.m[6] = 0, car.m[7] = s, car.m[8] = c;
}
static int car_ang;

static void sc_reset(void)
{
    init_tables();
    sc_w.user = 0; sc_w.floor = sc_floor; sc_w.solid = sc_solid; sc_w.sweep = sc_sweep;
    ramp_n = norm(V(0, RP_ONE, -RAMP_SLOPE));
    sc_box[0].lo = V(MM(-9000), 0, MM(92000)); sc_box[0].hi = V(MM(9000), MM(14000), MM(104000));     /* the building */
    sc_box[1].lo = V(MM(-9000), 0, MM(60000)); sc_box[1].hi = V(MM(-7500), MM(1100), MM(86000));     /* a low wall along the road */
    memset(act, 0, sizeof act);
    for (int i = 0; i < 5; i++) {      /* the pedestrians stand there, waiting; they only run in the solver from the moment the car is near */
        rp_v3 feet = V(MM(ped_at[i].x), 0, MM(ped_at[i].z)), z0 = {0, 0, 0};
        rp_spawn(&act[1 + i].d, feet, ped_at[i].yaw, z0, z0);
#ifdef FORCE_LOD
        act[1 + i].d.lod = FORCE_LOD;
#endif
    }
    cs.y = CAR_HY; cs.z = MM(4000); cs.vz = MM(20000); cs.vy = 0; cs.air = cs.landed = cs.tair = 0;
    car.half_x = CAR_HX, car.half_y = CAR_HY, car.half_z = CAR_HZ; car.mass = RP_ONE * 1200;
    car_ang = 0; car_matrix(0);
    sc_frame_no = 0;
}

/* the car and the triggers for one frame; the caller then steps the dolls (and times them) */
static void sc_script(void)
{
    const fx dt = RP_ONE / 60;
    int f = sc_frame_no;
    if (!cs.air) {
        cs.z += mul(cs.vz, dt);
        if (cs.z >= RAMP_Z0 && cs.z < RAMP_Z1) { cs.y = mul(cs.z - RAMP_Z0, RAMP_SLOPE) + CAR_HY * 104 / 100; car_ang = 0x0990; cs.vy = mul(cs.vz, RAMP_SLOPE); }
        else if (cs.z >= RAMP_Z1) { cs.air = 1; cs.tair = 0; }
        else if (cs.landed) { cs.vz -= mul(MM(9000), dt); if (cs.vz < 0) cs.vz = 0; }
    } else {
        cs.vy -= mul(G, dt); cs.y += mul(cs.vy, dt); cs.z += mul(cs.vz, dt); cs.tair++;
        car_ang = 0x0990 - cs.tair * 24; if (car_ang < -2000) car_ang = -2000;
        if (cs.y <= CAR_HY && cs.vy < 0) { cs.y = CAR_HY; cs.vy = 0; cs.air = 0; cs.landed = 1; car_ang = 0; }
    }
    if (cs.landed && !cs.air) { cs.vy = 0; }
    if (cs.z > MM(88000)) { cs.z = MM(88000); cs.vz = 0; }
    car_matrix(car_ang);
    car.pos = V(0, cs.y, cs.z); car.vel = V(0, cs.vy, cs.vz);
    /* the driver bails out at the lip */
    if (!act[0].active && cs.z >= RAMP_Z1 - MM(1500)) {
        rp_v3 feet = V(0, cs.y + CAR_HY + MM(150), cs.z - MM(300)), v = V(MM(600), cs.vy + MM(3500), cs.vz + MM(2000)), w = V(MM(3500), 0, MM(1200));
        rp_spawn(&act[0].d, feet, 0, v, w);
#ifdef FORCE_LOD
        act[0].d.lod = FORCE_LOD;
#endif
        act[0].active = 1;
    }
    for (int i = 1; i < NACT; i++) {
        fx gap = MM(ped_at[i - 1].z) - cs.z;
        if (!act[i].active && gap < MM(6000) && cs.vz > 0) { act[i].active = 1; rp_motor(&act[i].d, RP_POSE_STAND, RP_ONE); }
        if (act[i].active && !act[i].released && gap < MM(3300)) { act[i].released = 1; rp_motor(&act[i].d, RP_POSE_NONE, 0); }
    }
    (void)f;
}
#ifndef SC_T0
#define SC_T0()
#define SC_T1(i)
#endif
static void sc_step_dolls(void)
{
    for (int i = 0; i < NACT; i++) if (act[i].active) { SC_T0(); rp_step(&act[i].d, &sc_w, &car); SC_T1(i); }
    sc_frame_no++;
}
