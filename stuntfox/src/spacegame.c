/* See spacegame.h. Positions here are in world units; the Arwing's body is in fine units
   (<< FX). Everything runs at 60 ticks a second. */
#include "spacegame.h"
#include "render.h"
#include "palette.h"
#include "model.h"
#include "world.h"
#include "draw2d.h"
#include "traffic.h"

int sg_state;
u8 sg_invert, sg_autoaim = 1;
extern u8 ship_engine;             /* ship.c */

static s32 iabs(s32 v) { return v < 0 ? -v : v; }
static s32 imin(s32 a, s32 b) { return a < b ? a : b; }

static u32 seed = 0x2545f491;
static s32 rnd(s32 lo, s32 hi)
{
    seed = seed * 1664525 + 1013904223;
    return lo + (s32)((seed >> 8) % (u32)(hi - lo + 1));
}

/* length of any offset (vlen wants components under 46000) */
static s32 dist(V3 d)
{
    int s = 0;
    while (iabs(d.x) > 30000 || iabs(d.y) > 30000 || iabs(d.z) > 30000)
        d = vshr(d, 1), s++;
    return vlen(d) << s;
}

/* a unit vector along any offset */
static V3 dir_of(V3 d)
{
    while (iabs(d.x) > 30000 || iabs(d.y) > 30000 || iabs(d.z) > 30000)
        d = vshr(d, 1);
    return vnorm(d);
}

/* a message: on Payback's ticker, and at once on our own HUD for a couple of seconds */
static char banner[72];
static u8 banner_t;
static void note(const char *s)
{
    int n = 0;
    while (s[n] && n < (int)sizeof banner - 1)
        banner[n] = s[n], n++;
    banner[n] = 0;
    banner_t = 150;
    sg_say(s);
}

static V3 ship_at(const Ship *s) { return vshr(s->b.pos, FX); }

/* ---- the player's Arwing: money, upgrades, paint ---- */

static s32 credits = 300;
static s16 shield = 100, shield_max = 100;
static u8 laser_lv, engine_lv, rack_lv, missiles = 4, paint, jobs_done;
static u16 medals;                 /* one bit per medal found */
static u8 regen;                   /* ticks since the last hit, up to 255 */

static const u8 rack_size[3] = {4, 6, 8};
static const s16 shield_size[3] = {100, 150, 200};
static u8 shield_lv;

typedef struct { const char *name; u8 hull, tips; } Paint;
static const Paint paints[] = {
    {"FOX BLUE", M_SHIP, M_CAR},  {"STUNT RED", M_STUNT, M_ACCENT}, {"GOLD", M_ACCENT, M_GLOW},
    {"STEALTH", M_ROAD, M_STUNT}, {"SEA TEAL", M_TEAL, M_CREAM},    {"FLYBACK", M_BRICK, M_STEEL},
};
#define NPAINT (sizeof paints / sizeof paints[0])

void sg_paint(void)
{
    model_hull = paints[paint].hull;
    model_body = paints[paint].tips;
}

/* ---- pirates, shots, explosions ---- */

enum { F_NONE, F_RAIDER, F_CARRIER };
typedef struct {
    V3 p, v, home;
    s16 hp;
    u8 kind, cool, ai, pad;
} Foe;
#define NFOE 8
static Foe foes[NFOE];

enum { S_LASER, S_MISSILE, S_ENEMY };
typedef struct {
    V3 p;
    s16 vx, vy, vz;
    u8 life, who;
    s8 tgt, pad;
} Shot;
#define NSHOT 16
static Shot shots[NSHOT];

typedef struct { V3 p; u8 t, big, pad[2]; } Boom;
#define NBOOM 8
static Boom booms[NBOOM];

static void boom(V3 p, int big)
{
    int k = 0;
    for (int i = 0; i < NBOOM; i++) {
        if (!booms[i].t) { k = i; break; }
        if (booms[i].t > booms[k].t) k = i;      /* all busy: the oldest makes way */
    }
    booms[k].p = p;
    booms[k].t = 1;
    booms[k].big = big;
}

static void shoot(V3 p, V3 v, int who, int tgt)
{
    for (int i = 0; i < NSHOT; i++)
        if (!shots[i].life) {
            Shot *s = &shots[i];
            s->p = p;
            s->vx = v.x, s->vy = v.y, s->vz = v.z;
            s->who = who;
            s->tgt = tgt;
            s->life = who == S_MISSILE ? 150 : who == S_ENEMY ? 70 : 50;
            return;
        }
}

static int foe_count(void)
{
    int n = 0;
    for (int i = 0; i < NFOE; i++)
        n += foes[i].kind != F_NONE;
    return n;
}

static int spawn(int kind, V3 p, V3 home)
{
    for (int i = 0; i < NFOE; i++)
        if (foes[i].kind == F_NONE) {
            Foe *f = &foes[i];
            f->kind = kind;
            f->p = p;
            f->home = home;
            f->v = v3(0, 0, 0);
            f->hp = kind == F_CARRIER ? 50 : 4 + jobs_done / 3;
            f->cool = rnd(40, 120);
            f->ai = 0;
            return i;
        }
    return -1;
}

/* ---- jobs ---- */

enum { J_NONE, J_BOUNTY, J_COURIER, J_SALVAGE, J_RACE, J_RAID, J_BOSS, J_N };
static const char *const job_name[J_N] = {"", "BOUNTY", "COURIER", "SALVAGE", "GATE RACE", "CITY RAID", "CARRIER"};
typedef struct { u8 type, lv; s16 pay; } Offer;
static Offer offers[3];
static u8 job, job_lv, job_step, job_need;
static s16 job_pay;
static s32 job_time;               /* ticks left (0: no limit) */
static V3 job_at;                  /* courier: the rooftop; race: the next gate */
static u8 pods_got;
#define NPOD 5
#define NGATE 8

static V3 pod_pos(int i)
{
    int k = (i * 5 + job_lv * 3) % nrocks;
    return vadd(rocks[k].c, v3(0, rocks[k].r + 450, 0));
}

static V3 gate_pos(int i, s32 *heading)
{
    s32 a = i * 65536 / NGATE + 4000;
    if (heading)
        *heading = a + 16384;
    return vadd(station_pos, v3((11000 * fsin(a)) >> 14, (i & 1) ? 1600 : -1400, (11000 * fcos(a)) >> 14));
}

/* a tall building whose roof the Arwing can land on */
static V3 rooftop(void)
{
    for (int tries = 0; tries < 400; tries++) {
        const Box *b = &world.box[rnd(0, world.nbox - 1)];
        if (b->h < 450 || b->h > 2000 || b->x1 - b->x0 < 1 || b->z1 - b->z0 < 1 || b->x0 < 4 || b->z0 < 4 ||
            b->x1 > CITY - 5 || b->z1 > CITY - 5)
            continue;
        V3 c = v3((b->x0 + b->x1 + 1) * CELL / 2, b->h, (b->z0 + b->z1 + 1) * CELL / 2);
        s32 g = world_ground(c.x, c.z);
        if (g < b->h - 16 || world_ground(c.x + 500, c.z) != g || world_ground(c.x, c.z + 500) != g ||
            world_ground(c.x - 500, c.z) != g || world_ground(c.x, c.z - 500) != g)
            continue;                            /* (a flat roof, wide enough to land on) */
        c.y = g;
        return c;
    }
    return v3(64 * CELL, 0, 64 * CELL);
}

static void make_offers(void)
{
    int lv = 1 + jobs_done / 2;
    if (lv > 4) lv = 4;
    for (int i = 0; i < 3; i++) {
        int t;
        do {
            t = rnd(J_BOUNTY, jobs_done >= 3 ? J_BOSS : J_RAID);
        } while ((i > 0 && t == offers[0].type) || (i > 1 && t == offers[1].type));
        offers[i].type = t;
        offers[i].lv = lv;
        static const s16 base[J_N] = {0, 0, 350, 400, 500, 700, 2000};
        offers[i].pay = t == J_BOUNTY ? 120 * (2 + lv) : base[t] + 50 * lv;
    }
}

static void say_job(void)
{
    static const char *const how[J_N] = {
        "", "BOUNTY: shoot down the pirate raiders. R laser, L missile.",
        "COURIER: land on the rooftop under the beacon.",
        "SALVAGE: fly through the cargo pods, then dock.",
        "GATE RACE: fly through the gates in order.",
        "CITY RAID: pirates over the city! Shoot them down.",
        "CARRIER: destroy the pirate carrier.",
    };
    note(how[job]);
}

static void job_start(const Offer *o)
{
    job = o->type;
    job_lv = o->lv;
    job_pay = o->pay;
    job_step = 0;
    job_time = 0;
    pods_got = 0;
    V3 far = vadd(station_pos, v3(rnd(-1, 1) ? 12000 : -12000, rnd(-2000, 2000), rnd(-12000, 12000)));
    switch (job) {
    case J_BOUNTY:
        job_need = 2 + job_lv;
        for (int i = 0; i < job_need && i < NFOE; i++)
            spawn(F_RAIDER, vadd(far, v3(rnd(-2500, 2500), rnd(-1500, 1500), rnd(-2500, 2500))), far);
        break;
    case J_COURIER:
        job_at = rooftop();
        job_time = (100 + 20 * job_lv) * 60;
        break;
    case J_SALVAGE:
        job_need = NPOD;
        job_time = 150 * 60;
        break;
    case J_RACE:
        job_need = NGATE;
        job_at = gate_pos(0, 0);
        job_time = (110 - 5 * job_lv) * 60;
        break;
    case J_RAID: {
        V3 c = v3(64 * CELL, 2600, 64 * CELL);
        job_at = c;
        job_need = 3 + job_lv;
        for (int i = 0; i < job_need && i < NFOE; i++)
            spawn(F_RAIDER, vadd(c, v3(rnd(-5000, 5000), rnd(0, 1500), rnd(-5000, 5000))), c);
        break;
    }
    case J_BOSS:
        job_need = 1;
        spawn(F_CARRIER, far, far);
        spawn(F_RAIDER, vadd(far, v3(1500, 600, 0)), far);
        spawn(F_RAIDER, vadd(far, v3(-1500, 600, 0)), far);
        break;
    }
    say_job();
}

static void job_end(int ok)
{
    char b[48], *p = b;
    if (ok) {
        credits += job_pay;
        jobs_done++;
        p = d_cat(p, "JOB DONE! +");
        p = d_num(p, job_pay);
        d_cat(p, " CREDITS");
        note(b);
    } else {
        note("JOB FAILED.");
    }
    job = J_NONE;
    if (!ok)
        for (int i = 0; i < NFOE; i++)
            foes[i].kind = F_NONE;
}

/* ---- fox medals: six in space, six above the city's tallest towers ---- */

#define NMEDAL 12
static V3 medal_at[NMEDAL];

static void medals_init(void)
{
    static const s16 sp[6][3] = {
        {0, 2600, 0}, {-6200, -2200, 6200}, {9000, 4000, -9000}, {-14000, 1000, -2000},
        {3000, -5000, 15000}, {17000, 6000, 8000},
    };
    for (int i = 0; i < 6; i++)
        medal_at[i] = vadd(station_pos, v3(sp[i][0], sp[i][1], sp[i][2]));
    int n = 6;
    for (int k = 0; k < world.nbox && n < NMEDAL; k++) {
        /* the tallest box not too close to one already chosen */
        int best = -1;
        for (int i = 0; i < world.nbox; i++) {
            const Box *b = &world.box[i];
            V3 c = v3((b->x0 + b->x1 + 1) * CELL / 2, b->h + 900, (b->z0 + b->z1 + 1) * CELL / 2);
            int ok = 1;
            for (int j = 6; j < n; j++)
                if (iabs(medal_at[j].x - c.x) < 12 * CELL && iabs(medal_at[j].z - c.z) < 12 * CELL)
                    ok = 0;
            if (b->x0 < 4 || b->z0 < 4 || b->x1 > CITY - 5 || b->z1 > CITY - 5 || world_ground(c.x, c.z) < b->h - 16)
                ok = 0;
            if (ok && (best < 0 || b->h > world.box[best].h))
                best = i;
        }
        if (best < 0)
            break;
        const Box *b = &world.box[best];
        medal_at[n++] = v3((b->x0 + b->x1 + 1) * CELL / 2, b->h + 900, (b->z0 + b->z1 + 1) * CELL / 2);
    }
    for (; n < NMEDAL; n++)
        medal_at[n] = v3(n * 9000, 4000, 64 * CELL);
}

/* ---- the station ---- */

V3 sg_pad(void) { return vadd(station_pos, v3(0, BAY_Y0 + 110, BAY_PAD_Z)); }

static u8 menu, cursor, dock_stage;
static s32 st_t;                   /* ticks in this state */
static s32 turn_from;

void sg_init(void)
{
    sg_state = SG_FLY;
    medals_init();
    make_offers();
}

int sg_ship_visible(void) { return sg_state != SG_DEAD; }

void sg_dock_now(Ship *s)
{
    V3 p = sg_pad();
    s->b.pos = v3(p.x << FX, p.y << FX, p.z << FX);
    s->b.vel = s->b.w = v3(0, 0, 0);
    myaw(&s->b.m, 0);
    s->gear = 3;
    s->boosting = 0;
    sg_state = SG_DOCKED;
    menu = cursor = 0;
    shield = shield_max;
    for (int i = 0; i < NSHOT; i++)
        shots[i].life = 0;
    if (job == J_SALVAGE && pods_got == 0xff)
        job_end(1);
    make_offers();
}

int sg_select(Ship *s)
{
    if (sg_state != SG_FLY)
        return 1;
    if (dist(vsub(ship_at(s), station_pos)) > 12000)
        return 0;
    sg_state = SG_DOCKING;
    dock_stage = ship_at(s).z - station_pos.z < HUB_HZ + 1200 ? 0 : 1;
    st_t = 0;
    note("Docking: the station's tractor beam has you.");
    return 1;
}

void sg_landed(Ship *s)
{
    if (sg_state == SG_FLY) {
        sg_dock_now(s);
        note("DOCKED AT FOX STATION. UP DOWN choose, A pick, B back.");
    }
}

/* turn the Arwing's nose toward d (a unit vector), level */
static void face(Ship *s, V3 d, int rate)
{
    M3 *m = &s->b.m;
    m->f = vnorm(vadd(m->f, vshr(vsub(d, m->f), rate)));
    m->u = vnorm(vadd(m->u, vshr(vsub(v3(0, ONE, 0), m->u), 3)));
    morth(m);
}

static int fly_to(Ship *s, V3 to, s32 top)
{
    V3 p = ship_at(s), d = vsub(to, p);
    s32 len = dist(d);
    if (len < 40)
        return 1;
    s32 sp = imin(len / 14 + 6, top);
    V3 u = dir_of(d);
    s->b.pos = vadd(s->b.pos, v3((u.x * sp) >> (14 - FX), (u.y * sp) >> (14 - FX), (u.z * sp) >> (14 - FX)));
    s->b.vel = v3((u.x * sp) >> (14 - FX), (u.y * sp) >> (14 - FX), (u.z * sp) >> (14 - FX));
    return 0;
}

static void docking(Ship *s)
{
    st_t++;
    V3 rel = vsub(ship_at(s), station_pos);
    V3 mouth = vadd(station_pos, v3(0, (BAY_Y0 + BAY_Y1) / 2, HUB_HZ + 3000));
    if (dock_stage == 0) {                       /* round the side, clear of the hub */
        V3 w = vadd(station_pos, v3(rel.x >= 0 ? 4600 : -4600, -150, HUB_HZ + 3000));
        face(s, dir_of(vsub(w, ship_at(s))), 3);
        if (fly_to(s, w, 90))
            dock_stage = 1;
    } else if (dock_stage == 1) {                /* in front of the mouth */
        face(s, dir_of(vsub(mouth, ship_at(s))), 3);
        if (fly_to(s, mouth, 90))
            dock_stage = 2;
    } else if (dock_stage == 2) {                /* in, over the pad */
        face(s, v3(0, 0, -ONE), 3);
        if (fly_to(s, sg_pad(), 45)) {
            dock_stage = 3;
            st_t = 0;
            turn_from = 32768;
        }
    } else {                                     /* the pad turns the Arwing to face out */
        s32 a = turn_from - st_t * 512;
        if (a <= 0) {
            sg_dock_now(s);
            note("DOCKED AT FOX STATION. UP DOWN choose, A pick, B back.");
            return;
        }
        myaw(&s->b.m, a);
    }
}

static void launching(Ship *s)
{
    st_t++;
    s32 sp = imin(4 + st_t, 110);
    s->b.pos.z += sp << FX;
    s->b.vel = v3(0, 0, sp << FX);
    if ((s->b.pos.z >> FX) > station_pos.z + HUB_HZ + 700) {
        s->b.pos.y += 60 << FX;
        sg_state = SG_FLY;
        s->gear = 0;
    }
}

/* ---- the hangar's menus ---- */

enum { MN_MAIN, MN_JOBS, MN_YARD, MN_PAINT, MN_OPT };
static const char *const main_items[] = {"JOB BOARD", "SHIPYARD", "PAINT SHOP", "OPTIONS", "LAUNCH"};
static int yard_price(int i)
{
    switch (i) {
    case 0: return laser_lv == 0 ? 600 : laser_lv == 1 ? 1500 : 0;
    case 1: return shield_lv == 0 ? 500 : shield_lv == 1 ? 1200 : 0;
    case 2: return engine_lv == 0 ? 400 : engine_lv == 1 ? 1000 : 0;
    case 3: return missiles < rack_size[rack_lv] ? 25 * (rack_size[rack_lv] - missiles) : 0;
    default: return rack_lv == 0 ? 300 : rack_lv == 1 ? 800 : 0;
    }
}

static int menu_len(void)
{
    switch (menu) {
    case MN_MAIN: return 5;
    case MN_JOBS: return job ? 4 : 3;
    case MN_YARD: return 5;
    case MN_PAINT: return NPAINT;
    default: return 2;
    }
}

static void buy(int i)
{
    int pr = yard_price(i);
    if (!pr) {
        note(i == 3 ? "The rack is full." : "Already the best.");
        return;
    }
    if (credits < pr) {
        note("Not enough credits!");
        return;
    }
    credits -= pr;
    switch (i) {
    case 0: laser_lv++; note(laser_lv == 1 ? "TWIN LASERS fitted!" : "HYPER LASERS fitted!"); break;
    case 1: shield_lv++; shield = shield_max = shield_size[shield_lv]; note("Shield upgraded!"); break;
    case 2: engine_lv++; ship_engine = engine_lv; note("Engine tuned!"); break;
    case 3: missiles = rack_size[rack_lv]; note("Missiles loaded."); break;
    default: rack_lv++; missiles = rack_size[rack_lv]; note("Bigger missile rack!"); break;
    }
}

static void menu_input(Ship *s, u16 hit)
{
    int n = menu_len();
    if (hit & KEY_UP) cursor = cursor ? cursor - 1 : n - 1;
    if (hit & KEY_DOWN) cursor = cursor + 1 < n ? cursor + 1 : 0;
    if (menu == MN_PAINT)
        paint = cursor;                          /* see it on the Arwing as you choose */
    if (hit & KEY_B) {
        if (menu != MN_MAIN)
            cursor = menu - 1, menu = MN_MAIN;
        return;
    }
    if (!(hit & KEY_A))
        return;
    switch (menu) {
    case MN_MAIN:
        if (cursor == 4) {
            sg_state = SG_LAUNCH;
            st_t = 0;
            note(job ? "LAUNCH! Good hunting." : "LAUNCH! Take a job from the board for credits.");
        } else {
            menu = cursor + 1;
            cursor = menu == MN_PAINT ? paint : 0;
        }
        break;
    case MN_JOBS:
        if (cursor == 3) {
            job_end(0);
            note("Job dropped.");
        } else if (job) {
            note("Finish or drop your job.");
        } else {
            job_start(&offers[cursor]);
            sg_state = SG_LAUNCH;
            st_t = 0;
        }
        break;
    case MN_YARD:
        buy(cursor);
        break;
    case MN_PAINT:
        menu = MN_MAIN;
        cursor = 2;
        note("Fresh paint!");
        break;
    default:
        if (cursor == 0) sg_invert ^= 1;
        else sg_autoaim ^= 1;
        break;
    }
    (void)s;
}

/* ---- flying and fighting ---- */

static u8 fire_cool, last_target = 0xff;

/* the pirate nearest the Arwing's nose, within cos > lim (1.14) and range; -1 if none */
static int target_in_front(const Ship *s, s32 lim, s32 range)
{
    int best = -1;
    s32 bd = range;
    V3 p = ship_at(s);
    for (int i = 0; i < NFOE; i++) {
        if (foes[i].kind == F_NONE)
            continue;
        V3 d = vsub(foes[i].p, p);
        s32 len = dist(d);
        if (len > bd || len < 100)
            continue;
        if (vdot(dir_of(d), s->b.m.f) < lim)
            continue;
        best = i;
        bd = len;
    }
    return best;
}

static void fire(Ship *s, u16 keys, u16 hit)
{
    if (fire_cool)
        fire_cool--;
    const M3 *m = &s->b.m;
    V3 p = ship_at(s), sv = vshr(s->b.vel, FX);
    if ((keys & KEY_R) && !fire_cool) {
        fire_cool = laser_lv == 2 ? 6 : 9;
        V3 d = m->f;
        if (sg_autoaim) {
            int t = target_in_front(s, 15200, 14000);
            if (t >= 0) {
                /* lead the target: where it will be when the bolt gets there */
                V3 to = vsub(foes[t].p, p);
                s32 time = dist(to) / 300;
                d = dir_of(vadd(to, vscale(v3(foes[t].v.x << 2, foes[t].v.y << 2, foes[t].v.z << 2), time << 12)));
            }
        }
        V3 v = vadd(vscale(d, 300 << 0), sv);
        V3 nose = vadd(p, mlocal(m, v3(0, 0, 380)));
        if (laser_lv == 0) {
            shoot(nose, v, S_LASER, -1);
        } else {
            shoot(vadd(nose, mlocal(m, v3(-260, -20, -200))), v, S_LASER, -1);
            shoot(vadd(nose, mlocal(m, v3(260, -20, -200))), v, S_LASER, -1);
        }
    }
    if (hit & KEY_L) {
        if (!missiles) {
            note("No missiles. Buy more at the station's shipyard.");
        } else {
            int t = target_in_front(s, 9000, 20000);
            missiles--;
            shoot(vadd(p, mlocal(m, v3(0, -80, 300))), vadd(vscale(m->f, 120), sv), S_MISSILE, t);
            if (t < 0)
                note("Missile away (no lock).");
        }
    }
}

static void die(Ship *s)
{
    boom(ship_at(s), 2);
    sg_state = SG_DEAD;
    st_t = 0;
    s32 loss = credits / 10;
    credits -= loss;
    if (job)
        job_end(0);
    note("ARWING DOWN! Towing you back to the station...");
}

static void hurt(Ship *s, int dmg)
{
    shield -= dmg;
    regen = 0;
    if (shield <= 0) {
        shield = 0;
        die(s);
    } else if (shield < shield_max / 4) {
        note("Shield low! Dock at the station to repair.");
    }
}

static void foe_killed(int i)
{
    Foe *f = &foes[i];
    boom(f->p, f->kind == F_CARRIER ? 3 : 1);
    int pay = f->kind == F_CARRIER ? 300 : 40;
    credits += pay;
    f->kind = F_NONE;
    if (job == J_BOUNTY || job == J_RAID) {
        job_step++;
        if (!foe_count())
            job_end(1);
    } else if (job == J_BOSS) {
        int carriers = 0;
        for (int k = 0; k < NFOE; k++)
            carriers += foes[k].kind == F_CARRIER;
        if (!carriers) {
            for (int k = 0; k < NFOE; k++)
                if (foes[k].kind)
                    boom(foes[k].p, 1), foes[k].kind = F_NONE;
            job_end(1);
        }
    } else {
        note("Pirate down! +40");
        return;
    }
    if (job == J_BOUNTY || job == J_RAID) {
        char b[32], *q = d_cat(b, "PIRATE DOWN! ");
        q = d_num(q, foe_count());
        d_cat(q, " LEFT");
        note(b);
    }
}

static void foes_tick(Ship *s)
{
    V3 me = ship_at(s);
    int alive = sg_state == SG_FLY;
    for (int i = 0; i < NFOE; i++) {
        Foe *f = &foes[i];
        if (f->kind == F_NONE)
            continue;
        V3 to = vsub(me, f->p);
        s32 d = dist(to);
        int chase = alive && d < 16000;
        V3 want;
        if (f->kind == F_CARRIER) {
            V3 aim = chase ? vsub(vadd(me, v3(0, 2000, 0)), f->p) : vsub(f->home, f->p);
            want = dist(aim) > 6000 || !chase ? vscale(dir_of(aim), 22 << 0) : v3(0, 0, 0);
            f->v = vadd(f->v, vshr(vsub(want, f->v), 5));
            if (f->cool) f->cool--;
            if (!f->cool && chase) {
                f->cool = 45;
                for (int k = -1; k <= 1; k += 2) {
                    V3 gun = vadd(f->p, v3(k * 600, 500, 0));
                    shoot(gun, vscale(dir_of(vsub(me, gun)), 150), S_ENEMY, -1);
                }
                if (!(rnd(0, 4)) && foe_count() < 6)
                    spawn(F_RAIDER, vadd(f->p, v3(0, -400, 900)), f->home);
            }
        } else {
            s32 speed = 60 + 6 * job_lv;
            if (f->ai) {
                f->ai--;                         /* breaking off: keep going, then come round */
                want = vscale(dir_of(f->v), speed);
            } else if (chase) {
                want = vscale(dir_of(to), speed);
                if (d < 1300)
                    f->ai = 40 + rnd(0, 30);
            } else {
                V3 h = vsub(f->home, f->p);      /* circle the place they guard */
                if (dist(h) > 3500)
                    want = vscale(dir_of(h), speed);
                else
                    want = vscale(dir_of(vadd(f->v, vcross(v3(0, ONE, 0), f->v))), speed);
            }
            f->v = vadd(f->v, vshr(vsub(want, f->v), 4));
            if (f->cool) f->cool--;
            if (!f->cool) {
                f->cool = 70 + rnd(0, 60) - 6 * job_lv;
                if (chase && d < 9000 && vdot(dir_of(f->v), dir_of(to)) > 13000)
                    shoot(f->p, vscale(dir_of(vadd(to, v3(s->b.vel.x >> 4, s->b.vel.y >> 4, s->b.vel.z >> 4))), 170),
                          S_ENEMY, -1);
                else if (job == J_RAID && !chase)    /* strafing Payback's streets */
                    shoot(f->p, vadd(vscale(dir_of(f->v), 120), v3(0, -110, 0)), S_ENEMY, -1);
            }
        }
        f->p = vadd(f->p, f->v);
        s32 g = world_ground(f->p.x, f->p.z) + 700;
        if (f->p.y < g) {
            f->p.y = g;
            if (f->v.y < 0) f->v.y = -f->v.y >> 1;
        }
    }
}

static void shots_tick(Ship *s)
{
    V3 me = ship_at(s);
    for (int i = 0; i < NSHOT; i++) {
        Shot *sh = &shots[i];
        if (!sh->life)
            continue;
        sh->life--;
        if (sh->who == S_MISSILE && sh->tgt >= 0 && foes[(int)sh->tgt].kind) {
            V3 v = v3(sh->vx, sh->vy, sh->vz), w = vscale(dir_of(vsub(foes[(int)sh->tgt].p, sh->p)), 200);
            v = vadd(v, vshr(vsub(w, v), 3));
            sh->vx = v.x, sh->vy = v.y, sh->vz = v.z;
        } else if (sh->who == S_MISSILE && sh->vx * sh->vx + sh->vy * sh->vy + sh->vz * sh->vz < 200 * 200) {
            V3 v = v3(sh->vx, sh->vy, sh->vz);
            v = vadd(v, vshr(v, 4));
            sh->vx = v.x, sh->vy = v.y, sh->vz = v.z;
        }
        V3 half = v3(sh->vx >> 1, sh->vy >> 1, sh->vz >> 1);
        for (int step = 0; step < 2 && sh->life; step++) {
            sh->p = vadd(sh->p, half);
            if (sh->p.y < world_ground(sh->p.x, sh->p.z)) {
                if (sh->who != S_LASER)
                    boom(sh->p, 0);
                sh->life = 0;
                break;
            }
            if (sh->who == S_ENEMY) {
                V3 d = vsub(sh->p, me);
                if (sg_state == SG_FLY && iabs(d.x) < 330 && iabs(d.y) < 200 && iabs(d.z) < 330) {
                    sh->life = 0;
                    boom(sh->p, 0);
                    hurt(s, 6 + 2 * job_lv);
                }
                continue;
            }
            if (sg_state == SG_FLY && city_hit(sh->p, sh->who == S_MISSILE ? 100 : 25)) {
                sh->life = 0;            /* a person or a car down in the city */
                boom(sh->p, sh->who == S_MISSILE);
                break;
            }
            for (int k = 0; k < NFOE; k++) {
                Foe *f = &foes[k];
                if (!f->kind)
                    continue;
                s32 r = f->kind == F_CARRIER ? 1300 : 380;
                V3 d = vsub(sh->p, f->p);
                if (iabs(d.x) > r || iabs(d.y) > r || iabs(d.z) > r)
                    continue;
                sh->life = 0;
                f->hp -= sh->who == S_MISSILE ? 12 : laser_lv == 2 ? 3 : 2;
                if (f->hp <= 0)
                    foe_killed(k);
                else
                    boom(sh->p, 0);
                break;
            }
        }
    }
    for (int i = 0; i < NBOOM; i++)
        if (booms[i].t && ++booms[i].t > 24)
            booms[i].t = 0;
}

static void pickups(Ship *s)
{
    V3 p = ship_at(s);
    for (int i = 0; i < NMEDAL; i++) {
        if (medals & (1 << i))
            continue;
        V3 d = vsub(medal_at[i], p);
        if (iabs(d.x) < 420 && iabs(d.y) < 420 && iabs(d.z) < 420) {
            medals |= 1 << i;
            credits += 150;
            int n = 0;
            for (int k = 0; k < NMEDAL; k++)
                n += (medals >> k) & 1;
            char b[40], *q = b;
            q = d_cat(q, "FOX MEDAL ");
            q = d_num(q, n);
            q = d_cat(q, " OF 12! +150");
            if (n == NMEDAL) {
                credits += 3000;
                d_cat(b, "ALL 12 FOX MEDALS! +3000 CREDITS!");
            }
            note(b);
        }
    }
    if (job == J_SALVAGE)
        for (int i = 0; i < NPOD; i++) {
            if (pods_got & (1 << i))
                continue;
            V3 d = vsub(pod_pos(i), p);
            if (iabs(d.x) < 450 && iabs(d.y) < 450 && iabs(d.z) < 450) {
                pods_got |= 1 << i;
                int n = 0;
                for (int k = 0; k < NPOD; k++)
                    n += (pods_got >> k) & 1;
                job_step = n;
                if (n >= NPOD) {
                    pods_got = 0xff;
                    note("All pods aboard! Dock at the station to cash in.");
                } else {
                    note("Pod aboard!");
                }
            }
        }
    if (job == J_RACE) {
        V3 d = vsub(job_at, p);
        if (iabs(d.x) < 700 && iabs(d.y) < 700 && iabs(d.z) < 700) {
            job_step++;
            job_time += 6 * 60;
            if (job_step >= NGATE) {
                job_pay += job_time / 60 * 3;           /* seconds to spare */
                job_end(1);
            } else {
                job_at = gate_pos(job_step, 0);
                note(job_step == NGATE - 1 ? "Last gate!" : "Gate! +6 seconds");
            }
        }
    }
    if (job == J_COURIER && s->gear >= 2 && vlen(s->b.vel) < (25 << FX)) {
        V3 d = vsub(job_at, p);
        if (iabs(d.x) < 900 && iabs(d.z) < 900 && iabs(d.y) < 400)
            job_end(1);
    }
}

void sg_tick(Ship *s, u16 keys, u16 hit)
{
    switch (sg_state) {
    case SG_DOCKING:
        docking(s);
        break;
    case SG_DOCKED:
        menu_input(s, hit);
        break;
    case SG_LAUNCH:
        launching(s);
        break;
    case SG_DEAD:
        if (++st_t > 150) {
            sg_dock_now(s);
            note("Repaired and refuelled. Fly safe.");
        }
        break;
    default: {
        u16 k = keys & ~(KEY_L | KEY_R);
        if (sg_invert)
            k = (k & ~(KEY_UP | KEY_DOWN)) | (keys & KEY_UP ? KEY_DOWN : 0) | (keys & KEY_DOWN ? KEY_UP : 0);
        ship_update(s, k);
        fire(s, keys, hit);
        pickups(s);
        if (regen < 255) regen++;
        if (regen > 180 && shield < shield_max && !(st_t++ & 31))
            shield++;
        break;
    }
    }
    if (sg_state != SG_DOCKED) {
        foes_tick(s);
        shots_tick(s);
    }
    if (banner_t)
        banner_t--;
    if (job_time && sg_state == SG_FLY && !--job_time)
        job_end(0);
}

/* ---- drawing, 3D ---- */

static void bolt(V3 a, V3 b, int color, s32 w)
{
    V3 c0 = r_cam(a), c1 = r_cam(b);
    if (c0.z < NEAR && c1.z < NEAR)
        return;
    s32 dx = c1.x - c0.x, dy = c1.y - c0.y, len = iabs(dx) + iabs(dy);
    V3 o = len ? v3(dy * w / len, -dx * w / len, 0) : v3(w, 0, 0);
    V3 q[4] = {vadd(c0, o), vadd(c1, o), vsub(c1, o), vsub(c0, o)};
    r_poly(q, 4, color, -1, 0);
}

static int near_cam(V3 p, s32 r)
{
    V3 d = vsub(p, cam.pos);
    return iabs(d.x) < r && iabs(d.y) < r && iabs(d.z) < r;
}

static void place_draw(const Model *md, V3 p, const M3 *m, s32 scale)
{
    Place pl;
    V3 d = vsub(p, cam.pos);
    int far = iabs(d.x) > 28000 || iabs(d.y) > 28000 || iabs(d.z) > 28000 ? 2 : 0;
    if (model_place(&pl, p, m, scale, far, md->radius))
        model_draw(md, &pl);
}

static void hangar_draw(void)
{
    static const s16 crate_at[4][2] = {{-640, -760}, {-420, -760}, {-640, -540}, {620, -780}};
    V3 deck = vadd(station_pos, v3(0, BAY_Y0, 0));
    M3 m;
    myaw(&m, 16384);
    model_body = M_STUNT;
    place_draw(&mdl_sport, vadd(deck, v3(-560, 58, -250)), &m, 256);
    myaw(&m, -16384);
    model_body = M_TEAL;
    place_draw(&mdl_van, vadd(deck, v3(580, 58, -200)), &m, 256);
    myaw(&m, 0);
    for (int i = 0; i < 4; i++)
        place_draw(&mdl_crate, vadd(deck, v3(crate_at[i][0], 0, crate_at[i][1])), &m, 256);
    place_draw(&mdl_crate, vadd(deck, v3(-640, 220, -760)), &m, 256);
    /* the crew: one minds the pad, one checks the cars, one walks the back wall */
    model_body = M_ACCENT;
    model_legs = M_STEEL;
    myaw(&m, -16384);
    place_draw(&mdl_stand, vadd(deck, v3(300, 0, -420)), &m, 256);
    myaw(&m, 12000);
    place_draw(&mdl_stand, vadd(deck, v3(-420, 0, 120)), &m, 256);
    s32 t = (frame_count >> 1) & 511, x = t < 256 ? t * 4 - 512 : (511 - t) * 4 - 512;
    myaw(&m, t < 256 ? 16384 : -16384);
    place_draw((frame_count >> 3) & 1 ? &mdl_stride_a : &mdl_stride_b, vadd(deck, v3(x, 0, -560)), &m, 256);
    model_body = M_CAR;
    model_legs = M_ROAD;
}

void sg_draw(const Ship *s)
{
    M3 m;
    (void)s;
    if (near_cam(station_pos, 9000))
        hangar_draw();
    for (int i = 0; i < NFOE; i++) {
        const Foe *f = &foes[i];
        if (!f->kind || !near_cam(f->p, 60000))
            continue;
        m.f = f->v.x || f->v.y || f->v.z ? dir_of(f->v) : v3(0, 0, ONE);
        m.u = v3(0, ONE, 0);
        morth(&m);
        place_draw(f->kind == F_CARRIER ? &mdl_carrier : &mdl_raider, f->p, &m, 256);
    }
    for (int i = 0; i < NSHOT; i++) {
        const Shot *sh = &shots[i];
        if (!sh->life || !near_cam(sh->p, 20000))
            continue;
        V3 v = v3(sh->vx, sh->vy, sh->vz);
        if (sh->who == S_MISSILE)
            bolt(sh->p, vsub(sh->p, vshr(v, 0)), COLOR(M_ACCENT, 3, 0), 22);
        else
            bolt(sh->p, vsub(sh->p, vshr(v, 1)), sh->who == S_LASER ? COLOR(M_GRASS, 3, 0) : COLOR(M_STUNT, 3, 0),
                 sh->who == S_LASER ? 14 : 20);
    }
    for (int i = 0; i < NBOOM; i++) {
        const Boom *b = &booms[i];
        if (!b->t || !near_cam(b->p, 30000))
            continue;
        myaw(&m, b->t * 3000);
        s32 grow = b->t < 8 ? b->t * 32 : 256 + (b->t - 8) * 8;
        place_draw(&mdl_boom, b->p, &m, (grow * (b->big == 3 ? 1024 : b->big == 2 ? 640 : b->big ? 360 : 140)) >> 8);
    }
    myaw(&m, frame_count * 700);
    for (int i = 0; i < NMEDAL; i++)
        if (!(medals & (1 << i)) && near_cam(medal_at[i], 26000))
            place_draw(&mdl_medal, medal_at[i], &m, 256);
    myaw(&m, frame_count * 300);
    if (job == J_SALVAGE)
        for (int i = 0; i < NPOD; i++)
            if (!(pods_got & (1 << i)) && near_cam(pod_pos(i), 26000))
                place_draw(&mdl_pod, pod_pos(i), &m, 384);
    if (job == J_RACE)
        for (int i = job_step; i < NGATE && i < job_step + 3; i++) {
            s32 h;
            V3 g = gate_pos(i, &h);
            myaw(&m, h);
            model_body = i == job_step ? M_ACCENT : M_STEEL;
            if (near_cam(g, 40000))
                place_draw(&mdl_gate, g, &m, 256);
        }
    if (job == J_COURIER && near_cam(job_at, 40000)) {
        myaw(&m, 0);
        model_body = M_ACCENT;
        place_draw(&mdl_beacon, job_at, &m, 256);
    }
    model_body = M_CAR;
}

/* ---- drawing, 2D ---- */

#define INK COLOR(M_CREAM, 3, 0)
#define HI COLOR(M_ACCENT, 3, 0)
#define TITLE COLOR(M_GLOW, 3, 0)
#define DIM COLOR(M_STEEL, 1, 0)
#define PANEL COLOR(M_ROAD, 0, 0)

/* where a world point is on screen; 0 if behind */
static int project(V3 w, int *sx, int *sy)
{
    V3 d = vsub(w, cam.pos);
    while (iabs(d.x) > 30000 || iabs(d.y) > 30000 || iabs(d.z) > 30000)
        d = vshr(d, 1);
    s32 z = vdot(cam.m.f, d);
    if (z < 64)
        return 0;
    *sx = 120 + FOCAL * vdot(cam.m.r, d) / z;
    *sy = 80 - FOCAL * vdot(cam.m.u, d) / z;
    return 1;
}

static void brackets(int x, int y, int r, int c)
{
    d_hline(x - r, x - r + 3, y - r, c), d_vline(x - r, y - r, y - r + 3, c);
    d_hline(x + r - 3, x + r, y - r, c), d_vline(x + r, y - r, y - r + 3, c);
    d_hline(x - r, x - r + 3, y + r, c), d_vline(x - r, y + r - 3, y + r, c);
    d_hline(x + r - 3, x + r, y + r, c), d_vline(x + r, y + r - 3, y + r, c);
}

static void marker(V3 w, int c)
{
    int x, y;
    int on = project(w, &x, &y) && x > 4 && x < 236 && y > 4 && y < 156;
    if (!on) {
        /* off screen: a pointer on the edge, toward it */
        V3 d = vsub(w, cam.pos);
        while (iabs(d.x) > 30000 || iabs(d.y) > 30000 || iabs(d.z) > 30000)
            d = vshr(d, 1);
        s32 rx = vdot(cam.m.r, d), ry = vdot(cam.m.u, d), big = iabs(rx) > iabs(ry) ? iabs(rx) : iabs(ry);
        if (!big)
            return;
        x = 120 + rx * 100 / big;
        y = 80 - ry * 64 / big;
    }
    d_hline(x - 3, x + 3, y, c);
    d_vline(x, y - 3, y + 3, c);
    d_hline(x - 1, x + 1, y - 2, c);
    d_hline(x - 1, x + 1, y + 2, c);
}

static void radar(const Ship *s)
{
    const int cx = 28, cy = 88, R = 22;
    d_fill(cx - R - 2, cy - R - 2, 2 * R + 6, 2 * R + 5, PANEL);
    d_hline(cx - R, cx + R, cy, DIM);
    d_vline(cx, cy - R, cy + R, DIM);
    V3 p = ship_at(s), f = s->b.m.f, r = s->b.m.r;
    V3 fl = vnorm(v3(f.x, 0, f.z)), rl = vnorm(v3(r.x, 0, r.z));
    for (int i = -1; i < NFOE + 1; i++) {
        V3 w;
        int c;
        if (i < 0) w = station_pos, c = INK;
        else if (i == NFOE) {
            if (job == J_COURIER || job == J_RACE) w = job_at, c = HI;
            else continue;
        } else if (foes[i].kind) w = foes[i].p, c = COLOR(M_STUNT, 3, 0);
        else continue;
        V3 d = vsub(w, p);
        while (iabs(d.x) > 30000 || iabs(d.z) > 30000)
            d = vshr(d, 1), d.y = 0;
        s32 fx = vdot(rl, v3(d.x, 0, d.z)), fz = vdot(fl, v3(d.x, 0, d.z));
        s32 len = iabs(fx) + iabs(fz);
        s32 range = 24000;
        if (len > range) fx = fx * range / len, fz = fz * range / len;
        int x = cx - fx * R / range, y = cy - fz * R / range;     /* (the screen shows the world mirrored) */
        d_rect(x - 1, y - 1, 2 + (c == INK), 2 + (c == INK), c);
    }
    d_pixel(cx, cy - 1, TITLE);
    d_rect(cx - 1, cy, 3, 2, TITLE);
}

static void bar(int x, int y, int w, int val, int max, int c)
{
    d_rect(x, y, w, 3, DIM);
    d_rect(x, y, max ? w * val / max : 0, 3, c);
}

static int menu_w = 120;
static void menu_draw(void)
{
    char b[48], *p;
    const int x = 8, y0 = 40;
    /* narrow where the Arwing should show (main menu, paint), wide for the lists */
    int w = menu == MN_JOBS || menu == MN_YARD ? 152 : 120;
    menu_w = w;
    d_fill(x - 4, y0 - 3, w, 86, PANEL);
    d_hline(x - 4, x + w - 5, y0 + 9, DIM);
    static const char *const titles[] = {"FOX STATION HANGAR", "JOB BOARD", "SHIPYARD", "PAINT SHOP", "OPTIONS"};
    d_text(x, y0, titles[menu], TITLE);
    p = d_cat(b, "CREDITS ");
    p = d_num(p, credits);
    d_text(x, y0 + 74, b, HI);
    int n = menu_len();
    for (int i = 0; i < n; i++) {
        int y = y0 + 12 + i * 10, c = i == cursor ? HI : INK;
        p = b;
        *p = 0;
        switch (menu) {
        case MN_MAIN:
            d_cat(b, main_items[i]);
            break;
        case MN_JOBS:
            if (i == 3) {
                d_cat(b, "DROP CURRENT JOB");
                break;
            }
            p = d_cat(p, job_name[offers[i].type]);
            p = d_cat(p, " ");
            if (offers[i].type == J_BOUNTY) {
                p = d_num(p, 2 + offers[i].lv);
                p = d_cat(p, " RAIDERS ");
            }
            p = d_num(p, offers[i].pay);
            d_cat(p, "CR");
            if (job && c == INK) c = DIM;
            break;
        case MN_YARD: {
            static const char *const names[] = {"LASERS", "SHIELD", "ENGINE", "MISSILES", "MISSILE RACK"};
            static const char *const lv[3] = {" MK1", " MK2", " MK3"};
            p = d_cat(p, names[i]);
            int l = i == 0 ? laser_lv : i == 1 ? shield_lv : i == 2 ? engine_lv : i == 4 ? rack_lv : -1;
            if (l >= 0) p = d_cat(p, lv[l]);
            else { p = d_cat(p, " "); p = d_num(p, missiles); p = d_cat(p, "/"); p = d_num(p, rack_size[rack_lv]); }
            int pr = yard_price(i);
            p = d_cat(p, pr ? "  " : "  FULL");
            if (pr) { p = d_num(p, pr); d_cat(p, "CR"); }
            break;
        }
        case MN_PAINT:
            d_cat(b, paints[i].name);
            break;
        default:
            d_cat(b, i == 0 ? (sg_invert ? "STICK: UP CLIMBS" : "STICK: UP DIVES") : (sg_autoaim ? "AIM: AUTO" : "AIM: MANUAL"));
            break;
        }
        if (i == cursor)
            d_text(x - 2, y, ">", HI);
        d_text(x + 6, y, b, c);
    }
    if (menu == MN_MAIN && job) {
        p = d_cat(b, "JOB: ");
        d_cat(p, job_name[job]);
        d_text(x, y0 + 64, b, TITLE);
    }
    if (menu == MN_JOBS)
        d_text(x, y0 + 54, "A TAKE THE JOB AND LAUNCH", DIM);
    if (menu == MN_OPT)
        d_text(x, y0 + 54, "A CHANGES IT", DIM);
}

void sg_hud(const Ship *s)
{
#ifdef NOHUD
    return;
#endif
    char b[48], *p;
    if (sg_state == SG_DOCKED) {
        menu_draw();
        if (banner_t) {
            char t[25];
            int n = 0, most = (menu_w - 8) / TEXT_W;
            while (banner[n] && n < most) t[n] = banner[n], n++;
            t[n] = 0;
            d_text(8, 104, t, TITLE);
        }
        return;
    }
    if (banner_t) {
        /* (on two lines when long: the ticker only says each line once) */
        int n = 0, most = 232 / TEXT_W, cut;
        while (banner[n]) n++;
        if (n <= most) {
            d_text(120 - n * TEXT_W / 2, 100, banner, TITLE);
        } else {
            for (cut = most; cut > 0 && banner[cut] != ' '; cut--)
                ;
            if (!cut) cut = most;
            char t[48];
            int k = 0;
            for (; k < cut && k < 47; k++) t[k] = banner[k];
            t[k] = 0;
            d_text(120 - k * TEXT_W / 2, 92, t, TITLE);
            const char *r = banner + cut + (banner[cut] == ' ');
            for (k = 0; r[k] && k < 47; k++) t[k] = r[k];
            t[k] = 0;
            d_text(120 - k * TEXT_W / 2, 102, t, TITLE);
        }
    }
    if (sg_state == SG_DOCKING) {
        d_text(84, 40, "DOCKING...", HI);
        return;
    }
    if (sg_state == SG_DEAD)
        return;
    /* shield, credits, missiles: top left, under Payback's weapon icon */
    d_text(4, 40, "SHIELD", INK);
    bar(42, 42, 40, shield, shield_max, shield * 4 < shield_max ? COLOR(M_STUNT, 3, 0) : COLOR(M_GRASS, 3, 0));
    p = d_cat(b, "CR ");
    p = d_num(p, credits);
    p = d_cat(p, "  MSL ");
    d_num(p, missiles);
    d_text(4, 50, b, INK);
    if ((s->b.pos.y >> FX) > SPACE_LO || job || foe_count())
        radar(s);                                /* (not over the streets: Payback has its map) */
    /* the gunsight, ahead of the nose */
    int x, y;
    if (project(vadd(ship_at(s), mlocal(&s->b.m, v3(0, 0, 4500))), &x, &y)) {
        d_hline(x - 5, x - 2, y, HI);
        d_hline(x + 2, x + 5, y, HI);
        d_vline(x, y - 5, y - 2, HI);
        d_vline(x, y + 2, y + 5, HI);
    }
    /* pirates on screen get brackets; the one auto-aim locks gets the bright ones */
    int lock = sg_autoaim ? target_in_front(s, 15200, 14000) : -1;
    last_target = lock;
    for (int i = 0; i < NFOE; i++) {
        if (!foes[i].kind || !project(foes[i].p, &x, &y))
            continue;
        s32 dd = dist(vsub(foes[i].p, cam.pos));
        int r = (foes[i].kind == F_CARRIER ? 1200 : 400) * FOCAL / (dd ? dd : 1) + 4;
        if (r > 40) r = 40;
        brackets(x, y, r, i == lock ? HI : COLOR(M_STUNT, 3, 0));
    }
    /* the job */
    p = b;
    *p = 0;
    switch (job) {
    case J_BOUNTY: case J_RAID: case J_BOSS:
        p = d_cat(p, job_name[job]);
        p = d_cat(p, ": PIRATES ");
        d_num(p, foe_count());
        for (int i = 0; i < NFOE; i++)
            if (foes[i].kind) { marker(foes[i].p, COLOR(M_STUNT, 3, 0)); break; }
        break;
    case J_COURIER:
        p = d_cat(p, "DELIVER TO THE BEACON ");
        d_time(p, job_time / 60);
        marker(vadd(job_at, v3(0, 300, 0)), HI);
        break;
    case J_SALVAGE:
        if (pods_got == 0xff) {
            d_cat(p, "SALVAGE: DOCK AT THE STATION");
            marker(station_pos, HI);
        } else {
            p = d_cat(p, "PODS ");
            p = d_num(p, job_step);
            p = d_cat(p, "/5 ");
            d_time(p, job_time / 60);
            for (int i = 0; i < NPOD; i++)
                if (!(pods_got & (1 << i))) { marker(pod_pos(i), HI); break; }
        }
        break;
    case J_RACE:
        p = d_cat(p, "GATE ");
        p = d_num(p, job_step + 1);
        p = d_cat(p, "/8 ");
        d_time(p, job_time / 60);
        marker(job_at, HI);
        break;
    default:
        if (s->b.pos.y >> FX > SPACE_LO) {
            d_cat(p, "HOLD SELECT NEAR THE STATION: DOCK");
            if (!near_cam(station_pos, 12000))
                marker(station_pos, INK);
        }
        break;
    }
    if (b[0])
        d_text(4, 117, b, HI);
    if (sg_state == SG_LAUNCH)
        d_text(96, 40, "LAUNCH!", HI);
}
