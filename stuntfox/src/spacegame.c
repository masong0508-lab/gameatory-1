/* See spacegame.h. Positions here are in world units; the Arwing's body is in fine units
   (<< FX). Everything runs at 60 ticks a second. */
#include "spacegame.h"
#include "render.h"
#include "palette.h"
#include "model.h"
#include "world.h"
#include "draw2d.h"
#include "traffic.h"
#include "ragdoll.h"
#include "radio.h"
#include "settings.h"
#include "stage2.h"
#include "space.h"
#include "sgint.h"
#include "spacewalk.h"

int sg_state;
u8 sg_invert, sg_autoaim = 1;
u8 sw_pack;                        /* the jet pack is bought (spacewalk.c): one bit, w[3] bit 23 */
extern u8 ship_engine;             /* ship.c */

static s32 iabs(s32 v) { return v < 0 ? -v : v; }
static s32 imax(s32 a, s32 b) { return a > b ? a : b; }
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

/* a length to within a few percent, with no square root (the size of a bracket is no more exact than that) */
static s32 rlen(V3 d)
{
    s32 a = iabs(d.x), b = iabs(d.y), c = iabs(d.z), t;
    if (a < b) t = a, a = b, b = t;
    if (b < c) t = b, b = c, c = t;
    if (a < b) t = a, a = b, b = t;
    return a + (b * 11 >> 5) + (c >> 3);
}

/* a direction along d, ONE long to within a few percent, with one division */
static V3 rdir(V3 d)
{
    while (iabs(d.x) > 60000 || iabs(d.y) > 60000 || iabs(d.z) > 60000)
        d = vshr(d, 1);
    s32 l = rlen(d);
    if (l < 2)
        return v3(0, ONE, 0);
    s32 k = (1 << 28) / l;
    return v3(d.x * k >> 14, d.y * k >> 14, d.z * k >> 14);
}

/* a unit vector along any offset */
static V3 dir_of(V3 d)
{
    while (iabs(d.x) > 30000 || iabs(d.y) > 30000 || iabs(d.z) > 30000)
        d = vshr(d, 1);
    return vnorm(d);
}

/* a message on our own HUD for a few seconds (longer ones longer), not on Payback's ticker:
   that is its phone, and the space game's notes are only news while you are there to see them */
static char banner[52];
static u32 banner_end;             /* frame_count it goes at */
static void note(const char *s)
{
    int n = 0;
    while (s[n] && n < (int)sizeof banner - 1)
        banner[n] = s[n], n++;
    banner[n] = 0;
    banner_end = frame_count + 120 + 4 * n;
}
void sg_note(const char *s) { note(s); }

static V3 ship_at(const Ship *s) { return vshr(s->b.pos, FX); }

/* ---- the player's Arwing: money, upgrades, paint ---- */

static s32 credits = 300;
static s16 shield = 100, shield_max = 100;
static u8 laser_lv, engine_lv, rack_lv, missiles = 4, paint, jobs_done;
u8 sg_inf_missiles;                /* GAME SETTINGS: firing costs none */
static u16 medals;                 /* one bit per medal found */
static u8 regen;                   /* ticks since the last hit, up to 255 */

static const u8 rack_size[3] = {4, 6, 8};
static const s16 shield_size[3] = {100, 150, 200};
u8 sg_shield_k = 4;                /* GAME SETTINGS: the shield as quarters of its size, 255 nothing hurts it */
static u8 shield_lv;

static const char *const paint_name[] = {
    "FOX BLUE", "STUNT RED", "GOLD", "STEALTH", "SEA TEAL", "FLYBACK",
    "JUNGLE", "ARCTIC", "ASH", "EMBER", "SOLAR", "ACE BLACK",     /* (the campaign's rewards: locked until a mission unlocks one) */
};
typedef struct { u8 hull, tips; } Paint;
static const Paint paints[] = {
    {M_SHIP, M_CAR}, {M_STUNT, M_ACCENT}, {M_ACCENT, M_GLOW}, {M_ROAD, M_STUNT}, {M_TEAL, M_CREAM}, {M_BRICK, M_STEEL},
    {M_GRASS, M_STEEL}, {M_CREAM, M_TEAL}, {M_CONCRETE, M_ACCENT}, {M_KERB, M_STUNT}, {M_GLOW, M_ACCENT}, {M_ROAD, M_GLOW},
};
#define NPAINT (sizeof paints / sizeof paints[0])
static u16 paints_got = 0x3f;      /* one bit each: the six to begin with */

void sg_paint(void)
{
    model_hull = sg_state == SG_DEAD ? M_CONCRETE : paints[paint].hull;   /* (a wreck: scorched) */
    model_body = sg_state == SG_DEAD ? M_ROAD : paints[paint].tips;
}

/* ---- pirates, shots, explosions ---- */

#define foes sg_foes               /* (the types are in sgint.h: sgx.c has the newer kinds of foe) */
#define shots sg_shots
Foe sg_foes[NFOE];
Shot sg_shots[NSHOT];

typedef struct { V3 p; u8 t, big, pad[2]; } Boom;   /* big: 0-3 fireballs (2: the Arwing's), 4-5 smoke, 6 a spark */
#define NBOOM 8
#define SPARK 6                    /* a boom's kind (big): a laser's mark where it landed */
static Boom booms[NBOOM];
static void booms_tick(void);

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

static Shot *shoot(V3 p, V3 v, int who, int tgt)
{
    for (int i = 0; i < NSHOT; i++)
        if (!shots[i].life) {
            Shot *s = &shots[i];
            s->p = p;
            s->vx = v.x, s->vy = v.y, s->vz = v.z;
            s->who = who;
            s->tgt = tgt;
            s->life = who == S_MISSILE ? 150 : who == S_ENEMY ? 70 : 50;
            s->pad = 0;
            return s;
        }
    return 0;
}

void sgi_enemy_shot(V3 p, V3 v, int harm, int life)
{
    Shot *s = shoot(p, v, S_ENEMY, -1);
    if (s) {
        s->pad = harm;
        s->life = life;                /* (a shot that has gone past its target is only cost) */
    }
}

/* ---- the player's progress, for merge.c's checked copy ---- */

void sg_save(u32 *w)
{
    w[0] = credits;
    w[1] = medals | jobs_done << 16 | paint << 24;
    w[2] = laser_lv | engine_lv << 8 | rack_lv << 16 | shield_lv << 24;
    w[3] = missiles | sg_invert << 8 | sg_autoaim << 16 | rag_on << 24 | rag_fall << 25 | rag_wacky << 26 | rag_unlock << 27 | sw_pack << 23;
    opt_save(w);                   /* (GAME SETTINGS, in the bits between) */
}

void sg_sane(void)
{
    credits = credits < 0 ? 0 : credits > 9999999 ? 9999999 : credits;
    medals &= (1 << 12) - 1;
    if (paint >= NPAINT || !(paints_got >> paint & 1)) paint = 0;
    paints_got = (paints_got | 0x3f) & ((1 << NPAINT) - 1);
    if (laser_lv > 2) laser_lv = 2;
    if (engine_lv > 2) engine_lv = 2;
    if (rack_lv > 2) rack_lv = 2;
    if (shield_lv > 2) shield_lv = 2;
    if (missiles > rack_size[rack_lv]) missiles = rack_size[rack_lv];
    sg_invert &= 1, sg_autoaim &= 1, rag_on &= 1, rag_fall &= 1, rag_wacky &= 1, sw_pack &= 1;
    rag_unlock = (rag_unlock | rag_on | rag_wacky) & 1;
    ship_engine = engine_lv;
    shield_max = shield_size[shield_lv] * (sg_shield_k > 12 ? 4 : sg_shield_k) >> 2;
    if (shield < 0 || shield > shield_max) shield = shield_max;
}

/* credits earned or spent outside the shipyard (spacewalk.c's objectives, its mailbox); the new total */
int sg_credit(int n) { credits += n; sg_sane(); return credits; }

void sg_load(const u32 *w)
{
    credits = w[0];
    medals = w[1], jobs_done = w[1] >> 16, paint = w[1] >> 24;
    laser_lv = w[2] & 3, engine_lv = w[2] >> 8 & 3, rack_lv = w[2] >> 16 & 3, shield_lv = w[2] >> 24 & 3;
    missiles = w[3], sg_invert = w[3] >> 8 & 1, sg_autoaim = w[3] >> 16 & 1;
    opt_load(w);
    rag_on = w[3] >> 24, rag_fall = w[3] >> 25, rag_wacky = w[3] >> 26, rag_unlock = w[3] >> 27;   /* (a copy from
                                                                                   before these: all off) */
    sw_pack = w[3] >> 23 & 1;
    sg_sane();
}

static int foe_count(void)
{
    int n = 0;
    for (int i = 0; i < NFOE; i++)
        n += foes[i].kind != F_NONE && !foes[i].tag;     /* (the job board's: a mission's foes have tags) */
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
            f->ai = f->fl = 0;
            f->tag = 0;
            f->flo = -32768;
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

/* a flat roof the Arwing can land on, wide enough and higher than a bridge (Freedom City's are 1536) */
/* the top there: a block's, or a flat deck's over it (a car park's roof has headroom under it) */
static s32 roof_y(s32 x, s32 z)
{
    s32 g = world_ground(x, z), b, t;
    for (int k = 0; k < 2; k++)
        if (world_deck(x, z, k, &b, &t) == 1 && t > g)
            g = t;
    return g;
}

static int flat_roof(V3 *c)
{
    s32 g = roof_y(c->x, c->z);
    if (g < 2048 || roof_y(c->x + 500, c->z) != g || roof_y(c->x, c->z + 500) != g ||
        roof_y(c->x - 500, c->z) != g || roof_y(c->x, c->z - 500) != g)
        return 0;
    c->y = g;
    return 1;
}

/* where a courier job lands: one of Freedom City's real flat roofs (car parks, the long roof, the
   compound, tower H...: their middles in half cells), or on another map a tall building's. Boxes
   are no guide by themselves: a bridge is solid boxes too, with base 0. */
static V3 rooftop(void)
{
    static const u8 roofs[][2] = {
        {174, 64}, {131, 135}, {118, 210}, {244, 217}, {236, 38}, {119, 120},
        {135, 152}, {216, 55}, {146, 245}, {117, 103}, {132, 102}, {220, 23},
    };
    for (int tries = 0; tries < 24; tries++) {
        const u8 *r = roofs[rnd(0, sizeof roofs / sizeof roofs[0] - 1)];
        V3 c = v3(r[0] * CELL / 2, 0, r[1] * CELL / 2);
        if (flat_roof(&c))
            return c;
    }
    for (int tries = 0; tries < 400; tries++) {
        const Box *b = &world.box[rnd(0, world.nbox - 1)];
        if (b->base || b->h < 2048 || b->x0 < 4 || b->z0 < 4 || b->x1 > CITY - 5 || b->z1 > CITY - 5)
            continue;                            /* (no decks) */
        V3 c = v3((b->x0 + b->x1) * CELL / 2, 0, (b->z0 + b->z1) * CELL / 2);    /* (x1, z1 exclusive) */
        if (world_ground(c.x, c.z) >= b->h - 16 && flat_roof(&c))
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
        "", "BOUNTY: shoot down the raiders. R laser, L missile",
        "COURIER: land on the roof under the beacon.",
        "SALVAGE: fly through the cargo pods, then dock.",
        "GATE RACE: fly through the gates in order.",
        "CITY RAID: pirates over the city! Shoot them down",
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
            if (!foes[i].tag)
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
        /* the tallest box not too close to one already chosen (of equals the biggest: a tower's
           middle, not a corner of it) */
        int best = -1, area = 0;
        for (int i = 0; i < world.nbox; i++) {
            const Box *b = &world.box[i];
            V3 c = v3((b->x0 + b->x1) * CELL / 2, b->h + 900, (b->z0 + b->z1) * CELL / 2);   /* (x1, z1 exclusive) */
            int ok = 1;
            for (int j = 6; j < n; j++)
                if (iabs(medal_at[j].x - c.x) < 12 * CELL && iabs(medal_at[j].z - c.z) < 12 * CELL)
                    ok = 0;
            if (b->x0 < 4 || b->z0 < 4 || b->x1 > CITY - 5 || b->z1 > CITY - 5 || world_ground(c.x, c.z) < b->h - 16)
                ok = 0;
            int a = (b->x1 - b->x0) * (b->z1 - b->z0);
            if (ok && (best < 0 || b->h > world.box[best].h || (b->h == world.box[best].h && a > area)))
                best = i, area = a;
        }
        if (best < 0)
            break;
        const Box *b = &world.box[best];
        medal_at[n++] = v3((b->x0 + b->x1) * CELL / 2, b->h + 900, (b->z0 + b->z1) * CELL / 2);
    }
    for (; n < NMEDAL; n++)
        medal_at[n] = v3(n * 9000, 4000, 64 * CELL);
}

/* ---- the station ---- */

V3 sg_pad(void) { return vadd(station_pos, v3(0, BAY_Y0 + 110, BAY_PAD_Z)); }

static u8 menu, cursor, dock_stage, confirm;    /* confirm: 1 + the shipyard line a second A buys */
static s32 st_t;                   /* ticks in this state */
static s32 turn_from;

void sg_init(void)
{
    sg_state = SG_FLY;
    medals_init();
    make_offers();
    static const u32 none[4];
    opt_load(none);                /* GAME SETTINGS at their defaults until a kept copy says otherwise */
}

int sg_ship_visible(void) { return sg_state != SG_DEAD || st_t > 3; }     /* (the wreck, out of the fire) */

void sg_dock_now(Ship *s)
{
    V3 p = sg_pad();
    s->b.pos = v3(p.x << FX, p.y << FX, p.z << FX);
    s->b.vel = s->b.w = v3(0, 0, 0);
    myaw(&s->b.m, 0);
    s->gear = 3;
    s->boosting = 0;
    sg_state = SG_DOCKED;
    menu = cursor = confirm = 0;
    shield = shield_max;
    for (int i = 0; i < NSHOT; i++)
        shots[i].life = 0;
    if (job == J_SALVAGE && pods_got == 0xff)
        job_end(1);
    make_offers();
    s2_ev(EV_DOCK, 0, 0);
}

/* a new level (maybe on another map, with world.c on its world): what was out there goes, the
   job under way with it (its rooftop or pirates were the last level's); found medals stay found,
   the others wait on this world's towers */
void sg_level_enter(void)
{
    for (int i = 0; i < NSHOT; i++)
        shots[i].life = 0;
    for (int i = 0; i < NBOOM; i++)
        booms[i].t = 0;
    for (int i = 0; i < NFOE; i++)
        foes[i].kind = F_NONE;
    sgx_reset();
    job = J_NONE;
    pods_got = 0;
    sg_state = SG_FLY;
    menu = cursor = confirm = 0;
    banner_end = 0;
    shield = shield_max;
    space_station(world_grid);      /* (it hangs over this map) */
    medals_init();
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
    note("Tractor beam locked on. Docking...");
    return 1;
}

void sg_landed(Ship *s)
{
    if (sg_state == SG_FLY) {
        sg_dock_now(s);
        note("DOCKED AT FOX STATION");
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
            note("DOCKED AT FOX STATION");
            return;
        }
        myaw(&s->b.m, a);
    }
}

/* Shot down: the wreck rolls on a moment, smoking, then the station's tractor beam tows it home,
   up and out to the bay's mouth, where the docking takes it in: in view all the way, no cut to
   the hangar */
#define TUMBLE 45                                /* ticks before the beam has it */
static V3 tow_from;
static s32 tow_len;                              /* ticks of the tow */

static void tow(Ship *s)
{
    Body *b = &s->b;
    if (++st_t <= TUMBLE) {
        if (!(st_t & 7))
            boom(ship_at(s), 4);                 /* smoking (not on the tow: the camera would fly through it) */
        b->vel = vsub(b->vel, vshr(b->vel, 4));
        b->vel.y -= 40;
        b->pos = vadd(b->pos, b->vel);
        mrotate(&b->m, vshr(b->m.f, 5));         /* rolling over */
        /* on the street, not through it: it fell on under the camera, which then looked out
           from inside the walls (big flat faces that swapped shades every frame) */
        ship_settle(s);
        if (st_t == TUMBLE) {
            tow_from = ship_at(s);
            tow_len = imin(240, 90 + dist(vsub(station_pos, tow_from)) / 700);
        }
        return;
    }
    V3 to = vadd(station_pos, v3(0, (BAY_Y0 + BAY_Y1) / 2, HUB_HZ + 4500)), was = ship_at(s), d = vsub(to, tow_from);
    s32 k = (st_t - TUMBLE) * ONE / tow_len;
    if (k >= ONE) {
        b->pos = v3(to.x << FX, to.y << FX, to.z << FX);
        sg_state = SG_DOCKING;                   /* (on in, past the mouth, to the pad) */
        dock_stage = 1;
        st_t = 0;
        return;
    }
    s32 e = (k * k >> 14) * (3 * ONE - 2 * k) >> 14;          /* smooth away, smooth in */
    /* up ahead of along (clear of the roofs), but from a standstill: a rush up through the
       street's walls and roofs changed the whole picture every frame */
    s32 ku = k + (k >> 1) > ONE ? ONE : k + (k >> 1);
    s32 up = (ku * ku >> 14) * (3 * ONE - 2 * ku) >> 14;
    V3 p = v3(tow_from.x + ((d.x >> 2) * e >> 12), tow_from.y + ((d.y >> 2) * up >> 12), tow_from.z + ((d.z >> 2) * e >> 12));
    b->pos = v3(p.x << FX, p.y << FX, p.z << FX);
    b->vel = v3((p.x - was.x) << FX, (p.y - was.y) << FX, (p.z - was.z) << FX);
    if (dist(vsub(p, was)) > 8)
        face(s, dir_of(vsub(p, was)), 3);        /* nose on along the way, wings level */
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
        s2_ev(EV_LAUNCH, 0, 0);
    }
}

/* ---- the hangar's menus ---- */

enum { MN_MAIN, MN_JOBS, MN_YARD, MN_PAINT, MN_OPT, MN_SET };
static const char *const main_items[] = {"JOB BOARD", "SHIPYARD", "PAINT SHOP", "OPTIONS", "STATION", "LAUNCH"};
/* S's walker, if it is built in (weak, with no stub: absent they are 0): a STATION line before LAUNCH, and its hold on the keys */
extern int st_enter(void) __attribute__((weak));
extern int st_tick(u16 hit, u16 keys) __attribute__((weak));
static int main_n(void) { return st_enter ? 6 : 5; }
static int paints_n(void)
{
    int n = 0;
    for (int i = 0; i < (int)NPAINT; i++)
        n += paints_got >> i & 1;
    return n;
}
static int paint_at(int k)           /* the k-th paint that is unlocked */
{
    for (int i = 0; i < (int)NPAINT; i++)
        if ((paints_got >> i & 1) && !k--)
            return i;
    return 0;
}
static int paint_pos(int p)
{
    int k = 0;
    for (int i = 0; i < p; i++)
        k += paints_got >> i & 1;
    return k;
}
static int yard_price(int i)
{
    switch (i) {
    case 0: return laser_lv == 0 ? 600 : laser_lv == 1 ? 1500 : 0;
    case 1: return shield_lv == 0 ? 500 : shield_lv == 1 ? 1200 : 0;
    case 2: return engine_lv == 0 ? 400 : engine_lv == 1 ? 1000 : 0;
    case 3: return missiles < rack_size[rack_lv] ? 25 * (rack_size[rack_lv] - missiles) : 0;
    case 5: return sw_pack ? 0 : 900;              /* (a few jobs' pay: the bounties 360 and up, the rest 400 to 900) */
    default: return rack_lv == 0 ? 300 : rack_lv == 1 ? 800 : 0;
    }
}

static int menu_len(void)
{
    switch (menu) {
    case MN_MAIN: return main_n();
    case MN_JOBS: return job ? 4 : 3;
    case MN_YARD: return 6;
    case MN_PAINT: return paints_n();
    default: return 6;
    }
}

static int buy(int i)
{
    int pr = yard_price(i);
    if (!pr) {
        note(i == 3 ? "The rack is full." : i == 5 ? "The jet pack is already fitted." : "Already the best.");
        return 0;
    }
    if (credits < pr) {
        note("Not enough credits!");
        return 0;
    }
    credits -= pr;
    switch (i) {
    case 0: laser_lv++; note(laser_lv == 1 ? "TWIN LASERS fitted!" : "HYPER LASERS fitted!"); break;
    case 1: shield_lv++; sg_sane(); shield = shield_max; note("Shield upgraded!"); break;
    case 2: engine_lv++; ship_engine = engine_lv; note("Engine tuned!"); break;
    case 3: missiles = rack_size[rack_lv]; note("Missiles loaded."); break;
    case 5: sw_pack = 1; note("JET PACK fitted! Bail out in space."); break;
    default: rack_lv++; missiles = rack_size[rack_lv]; note("Bigger missile rack!"); break;
    }
    return 1;
}

static void menu_input(Ship *s, u16 hit, u16 keys)
{
    int n = menu_len();
    if (menu == MN_SET) {
        if (opt_input(hit, keys))
            menu = MN_OPT, cursor = 5;
        return;
    }
    if (hit & (KEY_UP | KEY_DOWN | KEY_B)) {
        if (confirm && (hit & KEY_B)) {
            confirm = 0;                         /* (B: not that one, still in the shipyard) */
            return;
        }
        confirm = 0;
    }
    if (hit & KEY_UP) cursor = cursor ? cursor - 1 : n - 1;
    if (hit & KEY_DOWN) cursor = cursor + 1 < n ? cursor + 1 : 0;
    if (menu == MN_PAINT)
        paint = paint_at(cursor);                /* see it on the Arwing as you choose */
    if (hit & KEY_B) {
        if (menu != MN_MAIN)
            cursor = menu - 1, menu = MN_MAIN;
        else if (st_enter)
            st_enter();                          /* (B on the main menu: out of the hangar into the station) */
        return;
    }
    if (!(hit & KEY_A))
        return;
    switch (menu) {
    case MN_MAIN:
        if (cursor == main_n() - 1) {
            sg_launch();
        } else if (cursor == 4) {
            st_enter();
        } else {
            menu = cursor + 1;
            cursor = menu == MN_PAINT ? paint_pos(paint) : 0;
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
        /* a purchase you can afford asks first: one A must not spend every credit you have */
        if (confirm != cursor + 1 && yard_price(cursor) && credits >= yard_price(cursor))
            confirm = cursor + 1;
        else
            confirm = 0, buy(cursor);
        break;
    case MN_PAINT:
        menu = MN_MAIN;
        cursor = 2;
        note("Fresh paint!");
        break;
    default:
        if (cursor == 0) sg_invert ^= 1;
        else if (cursor == 1) sg_autoaim ^= 1;
        else if (cursor == 2) {
            if (rag_unlock) rag_on ^= 1;
            else note("Locked. There is a secret code...");
        }
        else if (cursor == 3) rag_fall ^= 1;
        else if (cursor == 4) radio_set_mode((radio_mode() + 1) % 3);
        else menu = MN_SET, opt_open();
        break;
    }
    (void)s;
}

/* the secret: on the OPTIONS screen, L L R R L R (the shoulder buttons do nothing else in the
   hangar) unlocks the ragdolls and turns them on (they cost frames in a crowd, so they are not
   there to begin with); again it makes them WACKY, and again puts them back */
static void cheat_input(u16 hit)
{
    static const u16 code[6] = {KEY_L, KEY_L, KEY_R, KEY_R, KEY_L, KEY_R};
    static u8 at;
    if (menu != MN_OPT) {
        at = 0;
        return;
    }
    if (!(hit & (KEY_L | KEY_R)))
        return;
    hit &= KEY_L | KEY_R;
    if (hit == code[at])
        at++;
    else
        at = hit == code[0];
    if (at < 6)
        return;
    at = 0;
    if (!rag_unlock) {
        rag_unlock = rag_on = 1;
        note("RAGDOLLS UNLOCKED! People go flying.");
        return;
    }
    rag_wacky ^= 1;
    if (rag_wacky)
        rag_on = 1;
    note(rag_wacky ? "WACKY RAGDOLLS! Superballs on the moon." : "Ragdolls back to normal.");
}

/* ---- flying and fighting ---- */

/* the gunsight, units out from the nose, as the last look found it (sg_hud's, or a burst's
   first volley's):
   sight_hit, the first thing on the nose line (what fire() makes the twin bolts cross at), and
   sight_reach, where it is drawn (it follows sight_hit out over 3 or 4 frames, so a nose line
   grazing a car's edge does not throw it to the ground behind and back). Scratch, not keep: a
   frame's worth of aim, and the test harness reads it */
static volatile s16 sight_reach SCRATCH, sight_hit SCRATCH;
static u8 fire_cool, hud_turn, last_target = 0xff, last_tag;   /* last_target: what auto-aim locks (as the last look found it):
                                              a pirate 0..7, Payback's person or vehicle NFOE + its record's
                                              index, 0xff none */
#define NOSE 380                   /* the muzzle, ahead of the Arwing's middle */
#define SIGHT 4500                 /* how far out the gunsight sits when nothing is under it */

/* does a shot's step from a to b run into the city: the ground (a block's top, a floor), the
   slab of a deck over the cell b is in (a bridge, a car park's floor, Little Chicago's railway
   roof) or a railing on the edge the step crosses, as high as it is drawn (RAIL_H over its
   foot; Payback's walls there stop its cars to their full height, its people too, but what we
   draw is the railing). Nothing is built higher than 10752 over the street: above that only
   the ground is looked at. (world_ground, world_deck and world_wall as they are, read in place:
   the sight's ray and every shot's half-step come through here) */
#define RAIL_H 192
static int __attribute__((noinline)) shot_edge(V3 a, V3 b, int i);
static inline __attribute__((always_inline)) int shot_test(V3 a, V3 b)
{
    if ((u32)b.x >= CITY * CELL || (u32)b.z >= CITY * CELL)
        return b.y < 0;                                /* (off the map the ground is 0) */
    int i = (b.x >> 10) * CITY + (b.z >> 10);
    const Cell *c = &world.cell[i];
    if (b.y < ((u32)(c->shape - 2) < 4 ? world_ground(b.x, b.z) : c->hi))
        return 1;                                      /* (world_ground for a ramp) */
    if (b.y > world.yoff + 10752)
        return 0;
    const s8 *d = &world.deck[4 * i], *d2 = &world.deck2[4 * i];
    if (!(d[0] | d[1] | d2[0] | d2[1]) && !((a.x ^ b.x) >> 10) && !((a.z ^ b.z) >> 10))
        return 0;                                      /* (most steps: no deck, and in one cell) */
    return shot_edge(a, b, i);
}

int shot_blocked(V3 a, V3 b)
{
    return shot_test(a, b);
}

/* the rest of it, for the cell (index i) under b: its decks, and the railings on the edges the
   step crosses */
static int shot_edge(V3 a, V3 b, int i)
{
    s32 lo = a.y < b.y ? a.y : b.y, hi = a.y < b.y ? b.y : a.y, bot, top;
    for (int k = 0; k < 2; k++) {
        const s8 *d = &(k ? world.deck2 : world.deck)[4 * i];
        if ((d[0] | d[1]) && world_deck(b.x, b.z, k, &bot, &top) && lo <= top && hi >= bot)
            return 1;
    }
    s32 ax = a.x >> 10, az = a.z >> 10, bx = b.x >> 10, bz = b.z >> 10;
    if (ax == bx && az == bz)
        return 0;
    /* the edge of a's cell the step leaves by, and of b's it comes in by: bits -z, +x, +z, -x */
    s32 y = (a.y + b.y) >> 1;
    const s8 *h = (const s8 *)world.wall + CITY * CITY;
    if ((u32)a.x < CITY * CELL && (u32)a.z < CITY * CELL) {
        int j = ax * CITY + az;
        if (world.wall[j] & ((bx > ax) << 1 | (bx < ax) << 3 | (bz > az) << 2 | (bz < az))) {
            bot = (h[2 * j] + HBIAS) * 64;
            if (y < bot + RAIL_H && y > bot - 32)
                return 1;
        }
    }
    if (!(world.wall[i] & ((bx > ax) << 3 | (bx < ax) << 1 | (bz > az) | (bz < az) << 2)))
        return 0;
    bot = (h[2 * i] + HBIAS) * 64;
    return y < bot + RAIL_H && y > bot - 32;
}

/* how far from `from` along dir (1.14) the city is in the way (as shot_blocked finds it), in
   12 steps of SIGHT / 12; SIGHT if it is not within that */
static s32 world_ray(V3 from, V3 dir)
{
    V3 step = vscale(dir, SIGHT / 12), p = from;
    for (int k = 1; k <= 12; k++) {
        V3 q = vadd(p, step);
        if (shot_test(p, q))
            return k * (SIGHT / 12) - SIGHT / 24;
        p = q;
    }
    return SIGHT;
}

/* can the nose at a see b: no ground, roof or deck slab on the line between, cell by cell (the
   line's height where it enters and leaves each cell it crosses, against the cell's top; a
   railing is lower than a body). In b's own cell only where the line comes in: b stands there.
   What auto-aim and a missile lock on to must be in sight */
static int seen(V3 a, V3 b)
{
    V3 d = vsub(b, a);
    if ((u32)a.x >= CITY * CELL || (u32)a.z >= CITY * CELL || (u32)b.x >= CITY * CELL || (u32)b.z >= CITY * CELL)
        return 0;
    s32 cx = a.x >> 10, cz = a.z >> 10, ex = b.x >> 10, ez = b.z >> 10, sx = d.x < 0 ? -1 : 1, sz = d.z < 0 ? -1 : 1;
    /* t along the line, 16.16: where it crosses the next x and z edges, and from one to the next */
    u32 ax = iabs(d.x), az = iabs(d.z), big = 0x7fffffff;
    u32 dtx = ax ? (CELL << 16) / ax : big, dtz = az ? (CELL << 16) / az : big;
    u32 tx = ax ? ((u32)(d.x < 0 ? a.x & 1023 : CELL - (a.x & 1023)) << 16) / ax : big;
    u32 tz = az ? ((u32)(d.z < 0 ? a.z & 1023 : CELL - (a.z & 1023)) << 16) / az : big;
    s32 t0 = 0, y0 = a.y, bot, top;
    for (int k = 0; k < 40; k++) {
        u32 tn = tx < tz ? tx : tz;
        int last = (cx == ex && cz == ez) || tn >= 65536;   /* (or past b, by the rounding) */
        s32 t1 = last ? 65536 : (s32)tn;
        s32 y1 = a.y + ((d.y * t1) >> 16), lo = imin(y0, y1), hi = imax(y0, y1);
        const Cell *c = &world.cell[cx * CITY + cz];
        if ((u32)(c->shape - 2) < 4) {                 /* (a ramp: its ground where the line comes and goes,
                                                          those points held inside this cell) */
            s32 x0 = cx << 10, z0 = cz << 10;
            if (y0 < world_ground(imin(imax(a.x + ((d.x * t0) >> 16), x0), x0 + 1023),
                                  imin(imax(a.z + ((d.z * t0) >> 16), z0), z0 + 1023))
                || (!last && y1 < world_ground(imin(imax(a.x + ((d.x * t1) >> 16), x0), x0 + 1023),
                                               imin(imax(a.z + ((d.z * t1) >> 16), z0), z0 + 1023))))
                return 0;
        } else if ((last ? y0 : lo) < c->hi)
            return 0;
        int i = 4 * (cx * CITY + cz);
        for (int kk = 0; kk < 2; kk++) {
            const s8 *dk = &(kk ? world.deck2 : world.deck)[i];
            s32 tm = (t0 + t1) >> 1;
            if ((dk[0] | dk[1]) && world_deck(a.x + ((d.x * tm) >> 16), a.z + ((d.z * tm) >> 16), kk, &bot, &top)
                && lo <= top && hi >= bot)
                return 0;
        }
        if (last)
            return 1;
        if (tx < tz)
            cx += sx, tx += dtx;
        else
            cz += sz, tz += dtz;
        if ((u32)cx >= CITY || (u32)cz >= CITY)
            return 0;
        t0 = t1, y0 = y1;
    }
    return 1;
}

/* the pirate nearest the Arwing's nose, within cos > lim (1.14) and range; -1 if none
   (*at: how far) */
static int target_in_front(const Ship *s, s32 lim, s32 range, s32 *at)
{
    int best = -1;
    s32 bd = range;
    V3 p = ship_at(s);
    for (int i = 0; i < NFOE; i++) {
        if (foes[i].kind == F_NONE)
            continue;
        V3 d = vsub(foes[i].p, p);
        if (iabs(d.x) > bd || iabs(d.y) > bd || iabs(d.z) > bd)
            continue;                    /* (farther than that on one axis: no length to find) */
        s32 len = foes[i].tag || foes[i].kind > F_CARRIER ? rlen(d) : dist(d);    /* (a mission's foe to within a few percent) */
        if (len > bd || len < 100)
            continue;
        if (vdot(d, s->b.m.f) < lim * len >> 14)   /* (the cosine to the nose, as a dot with a unit vector would give it, with no square root) */
            continue;
        best = i;
        bd = len;
    }
    *at = bd;
    return best;
}

/* what is ahead of the nose: the lock (the nearest pirate or, over the city, Payback's person
   or vehicle inside the cone of cos > lim within range that the nose can see, tagged as
   last_target is; -1 none) and *reach, how far along the nose line the first thing is (the
   ground, a deck, a railing, a person, a vehicle; SIGHT if nothing within it). Of city_scan's
   candidates the best one in sight is locked, looking at no more than `looks` of them (each
   look walks the line to it); 0 looks: no city lock */
static int lock_scan(const Ship *s, s32 lim, s32 range, s32 *reach, int looks)
{
    V3 nose = vadd(ship_at(s), mlocal(&s->b.m, v3(0, 0, NOSE))), p;
    s32 at[CITY_CANDS], fat;
    u8 cand[CITY_CANDS];
    int t = target_in_front(s, lim, range, &fat);
    int n = city_scan(nose, s->b.m.f, world_ray(nose, s->b.m.f), lim, range, reach, cand, at);
    if (n > looks)
        n = looks;
    for (int k = 0; k < n && (t < 0 || at[k] < fat); k++)
        if (city_target_at(cand[k], &p, 0) && seen(nose, p))
            return NFOE + cand[k];
    return t;
}

static int tag_of(int t) { return t >= NFOE && t != 0xff ? city_tag(t - NFOE) : 0; }

/* a lock's middle and velocity (units a tick) now; 0 if it is gone (or its index names another record now) */
static int lock_at(int t, int tag, V3 *p, V3 *v)
{
    if (t < 0 || t == 0xff)
        return 0;
    if (t >= NFOE)
        return city_tag(t - NFOE) == tag && city_target_at(t - NFOE, p, v);
    if (!foes[t].kind)
        return 0;
    *p = foes[t].p;
    *v = foes[t].v;
    return 1;
}

static void fire(Ship *s, u16 keys, u16 hit)
{
    int idle = !fire_cool;
    if (fire_cool)
        fire_cool--;
    const M3 *m = &s->b.m;
    V3 p = ship_at(s), sv = vshr(s->b.vel, FX);
    s32 way = vdot(sv, m->f);      /* (the gunsight's distances, less this tick's way forward) */
    sight_hit = imax(sight_hit - way, 0), sight_reach = imax(sight_reach - way, 0);
    if ((keys & KEY_R) && !fire_cool) {
        fire_cool = laser_lv == 2 ? 6 : 9;
        V3 d = m->f, nose = vadd(p, mlocal(m, v3(0, 0, NOSE))), aim = nose, tp, tv;
        s32 reach = 0;
        if (idle && (laser_lv || sg_autoaim)) {
            /* the first volley of a burst looks for itself: the nose may have only now come onto
               what it is fired at, and sg_hud's look is up to two frames old. This frame's
               sg_hud draws from this look and does not look again; held, the volleys after it
               take sg_hud's */
            s32 r;
            int t = lock_scan(s, 15200, 14000, &r, sg_autoaim ? 2 : 0);
            sight_hit = r;
            last_target = sg_autoaim ? t : -1;
            last_tag = tag_of(last_target);
            hud_turn = 1;
        }
        if (sg_autoaim && lock_at(last_target, last_tag, &tp, &tv) && vdot(dir_of(vsub(tp, p)), m->f) > 15200) {
            /* lead the target (still ahead: the lock is the last frame's): where it will be
               when the bolt gets there */
            V3 to = vsub(tp, p);
            s32 time = dist(to) / 300;
            to = vadd(to, v3(tv.x * time, tv.y * time, tv.z * time));
            d = dir_of(to);
            reach = dist(to);
            aim = vadd(p, to);
        }
        if (laser_lv && !reach) {
            /* twin bolts cross on what the nose line meets, so both meet what the gunsight is on
               (parallel, 520 apart, they straddled a person): the last look */
            reach = imin(imax(sight_hit, 200), SIGHT);
            aim = vadd(nose, vscale(m->f, reach));
        }
        V3 v = vadd(vscale(d, 300 << 0), sv);
        if (laser_lv == 0) {
            shoot(nose, v, S_LASER, -1);
        } else {
            for (int k = -1; k <= 1; k += 2) {
                V3 o = vadd(nose, mlocal(m, v3(k * 260, -20, -200)));
                shoot(o, vadd(vscale(dir_of(vsub(aim, o)), 300), sv), S_LASER, -1);
            }
        }
    }
    if (hit & KEY_L) {
        if (!missiles) {
            note("No missiles: buy more at the shipyard.");
        } else {
            /* off the nose line at 200 or more (the ship's forward speed and 120), locked on
               what the nose can see in the wide cone ahead; shots_tick steers it */
            s32 at, fwd = vdot(sv, m->f) + 120;
            int t = lock_scan(s, 9000, 20000, &at, CITY_CANDS);
            if (!sg_inf_missiles)
                missiles--;
            Shot *ms = shoot(vadd(p, mlocal(m, v3(0, 0, 300))), vscale(m->f, fwd > 200 ? fwd : 200), S_MISSILE, t);
            if (ms)
                ms->pad = tag_of(t);
            if (t < 0)
                note("Missile away (no lock)."), banner_end = frame_count + 75;   /* (said in passing) */
        }
    }
}

static void die(Ship *s)
{
    boom(ship_at(s), 2);
    boom(ship_at(s), 5);
    sg_state = SG_DEAD;
    st_t = 0;
    s2_ev(EV_ARWING_DOWN, 0, 0);
    s32 loss = credits / 10;
    credits -= loss;
    if (job)
        job_end(0);
    note("ARWING DOWN! Towing you to the station...");
}

static void hurt(Ship *s, int dmg)
{
    if (sg_shield_k == 255)
        dmg = 0;                   /* (GAME SETTINGS: invincible) */
    shield -= dmg;
    regen = 0;
    if (shield <= 0) {
        shield = 0;
        die(s);
    } else if (shield < shield_max / 4) {
        note("Shield low! Dock at the station to repair.");
    }
}

/* flying into the city: the shield takes the blow, the more the faster it hit (a scrape or a
   firm landing costs nothing; full speed into a tower costs most of a fresh shield) */
#define CRASH_MIN (16 << FX)       /* speed into the wall, fine units a tick */

static void crash(Ship *s)
{
    if (s->impact <= CRASH_MIN || regen < 20)
        return;                                  /* (one blow, not every tick of it) */
    hurt(s, 4 + (s->impact - CRASH_MIN) / 512);
    if (sg_state == SG_FLY && shield >= shield_max / 4)
        note("CRASH! The shield took the blow.");
}

static void foe_killed(int i)
{
    Foe *f = &foes[i];
    if (f->tag || f->kind > F_CARRIER) {         /* a mission's, or a newer kind: sgx.c */
        sgx_killed(i);
        return;
    }
    boom(f->p, f->kind == F_CARRIER ? 3 : 1);
    int pay = f->kind == F_CARRIER ? 300 : 40;
    credits += pay;
    s2_ev(EV_FOE_DOWN, 0, f->kind);
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

/* a mission's foes take their lengths and directions to within a few percent (no square root: sgx.c's way), the board's exact */
#define DIST(v) (f->tag ? rlen(v) : dist(v))
#define DIR(v) (f->tag ? rdir(v) : dir_of(v))
static void foes_tick(Ship *s)
{
    V3 me = ship_at(s);
    int alive = sg_state == SG_FLY;
    for (int i = 0; i < NFOE; i++) {
        Foe *f = &foes[i];
        if (f->kind == F_NONE || (f->fl & FL_HOLD) || ((f->tag || f->kind > F_CARRIER) && !SGX_WORK(f, i)))
            continue;                            /* (a mission's foe is worked on every other tick, two ticks' worth) */
        if (f->kind > F_CARRIER) {
            sgx_tick_foe(i, s);
            continue;
        }
        int dt = f->tag ? 2 : 1;
        V3 to = vsub(me, f->p);
        /* a mission's foe thinks one tick in four and when its gun is ready (sgx_steer), and flies on in between: the
           board's own think every tick, as ever */
        int turn = !f->tag || !f->cool || sgx_steer(i), sl = f->tag ? 2 : 4;
        s32 d = turn ? DIST(to) : 0;
        int chase = alive && d < 16000;
        V3 want;
        if (!turn) {
            f->cool -= f->cool < dt ? f->cool : dt;
        } else if (f->kind == F_CARRIER) {
            V3 aim = chase ? vsub(vadd(me, v3(0, 2000, 0)), f->p) : vsub(f->home, f->p);
            want = DIST(aim) > 6000 || !chase ? vscale(DIR(aim), 22 << 0) : v3(0, 0, 0);
            f->v = vadd(f->v, vshr(vsub(want, f->v), sl + 1));
            f->cool -= f->cool < dt ? f->cool : dt;
            if (!f->cool && chase) {
                f->cool = 45;
                for (int k = -1; k <= 1; k += 2) {
                    V3 gun = vadd(f->p, v3(k * 600, 500, 0));
                    shoot(gun, vscale(DIR(vsub(me, gun)), 150), S_ENEMY, -1);
                }
                if (!(rnd(0, 4)) && (f->tag ? sgx_foes() < NFOE - 1 : foe_count() < 6)) {
                    int k = spawn(F_RAIDER, vadd(f->p, v3(0, -400, 900)), f->home);
                    if (k >= 0)
                        foes[k].tag = f->tag;    /* (a mission's carrier brings its raiders into the mission) */
                }
            }
        } else {
            s32 speed = 60 + 6 * job_lv;
            if (f->ai) {
                f->ai -= f->tag ? (f->ai > 3 ? 4 : f->ai) : 1;                /* breaking off: keep going, then come round */
                want = vscale(DIR(f->v), speed);
            } else if (chase) {
                want = vscale(DIR(to), speed);
                if (d < 1300)
                    f->ai = 40 + rnd(0, 30);
            } else {
                V3 h = vsub(f->home, f->p);      /* circle the place they guard */
                if (DIST(h) > 3500)
                    want = vscale(DIR(h), speed);
                else
                    want = vscale(DIR(vadd(f->v, vcross(v3(0, ONE, 0), f->v))), speed);
            }
            f->v = vadd(f->v, vshr(vsub(want, f->v), sl));
            f->cool -= f->cool < dt ? f->cool : dt;
            if (!f->cool) {
                f->cool = 70 + rnd(0, 60) - 6 * job_lv;
                if (chase && d < 9000 && vdot(DIR(f->v), DIR(to)) > 13000)
                    shoot(f->p, vscale(DIR(vadd(to, v3(s->b.vel.x >> 4, s->b.vel.y >> 4, s->b.vel.z >> 4))), 170),
                          S_ENEMY, -1);
                else if (job == J_RAID && !chase)    /* strafing Payback's streets */
                    shoot(f->p, vadd(vscale(DIR(f->v), 120), v3(0, -110, 0)), S_ENEMY, -1);
            }
        }
        if (f->tag && !f->cool)
            f->cool = chase ? 3 : 12;            /* (ready, but with nothing to shoot at: it thinks again in four ticks, or twelve when the Arwing is far) */
        f->p = vadd(f->p, f->v);
        if (f->tag)
            f->p = vadd(f->p, f->v);
        s32 g = f->tag ? sgx_floor(f) : world_ground(f->p.x, f->p.z) + 700;     /* (a mission's foes stay over the roofs ahead) */
        if (f->p.y < g) {
            f->p.y = g;
            if (f->v.y < 0) f->v.y = -f->v.y >> 1;
        }
    }
}
#undef DIST
#undef DIR

static int near_cam(V3 p, s32 r);
/* a mission's foes' shots (they carry their harm in pad): every other tick, two ticks' worth in one step, the city looked at
   once and the Arwing at the half and at the end (the street objects are no cover from them: that look is a shot's dearest) */
static void enemy_step(Ship *s, Shot *sh, int idx, V3 me)
{
    if (!SGX_DUE(idx))
        return;
    sh->life = sh->life > 2 ? sh->life - 2 : 0;
    if (!sh->life)
        return;
    V3 v = v3(sh->vx, sh->vy, sh->vz), was = sh->p, mid = vadd(was, v);
    sh->p = vadd(mid, v);
    if (shot_blocked(was, sh->p)) {
        if (near_cam(sh->p, 16000))
            boom(sh->p, SPARK);
        sh->life = 0;
        return;
    }
    if (sg_state != SG_FLY)
        return;
    for (int k = 0; k < 2; k++) {
        V3 at = k ? sh->p : mid, d = vsub(at, me);
        if (iabs(d.x) < 330 && iabs(d.y) < 200 && iabs(d.z) < 330) {
            sh->life = 0;
            if (sgx_shed < 2)
                boom(at, SPARK);                 /* (a short one: it is a boom a frame draws for every hit) */
            hurt(s, sh->pad);
            return;
        }
    }
}

static void shots_tick(Ship *s)
{
    V3 me = ship_at(s), lo = v3(0x7fffffff, 0x7fffffff, 0x7fffffff), hi = v3(-0x7fffffff, -0x7fffffff, -0x7fffffff);
    u32 near[2] = {0, 0};
    u8 live[NSHOT];
    int nl = 0, nfoe = 0;
    for (int i = 0; i < NSHOT; i++) {
        /* the shots in flight, and who in the city they can meet this tick: the box round where
           they fly (a missile turns by less than its speed in a tick), widened by what a body
           reaches (city_near) */
        const Shot *sh = &shots[i];
        if (!sh->life)
            continue;
        live[nl++] = i;
        if (sg_state != SG_FLY || sh->who == S_ENEMY)
            continue;
        V3 a = sh->p, b = vadd(a, v3(sh->vx, sh->vy, sh->vz));
        s32 r = sh->who == S_MISSILE ? imax(iabs(sh->vx), imax(iabs(sh->vy), iabs(sh->vz))) : 0;
        lo = v3(imin(lo.x, imin(a.x, b.x) - r), imin(lo.y, imin(a.y, b.y) - r), imin(lo.z, imin(a.z, b.z) - r));
        hi = v3(imax(hi.x, imax(a.x, b.x) + r), imax(hi.y, imax(a.y, b.y) + r), imax(hi.z, imax(a.z, b.z) + r));
    }
    if (nl)
        nfoe = sgx_foes();             /* (none over the city: no half-step looks for them there) */
    if (lo.x <= hi.x)
        city_near(lo, hi, near);
    for (int j = 0; j < nl; j++) {
        Shot *sh = &shots[live[j]];
        if (sh->who == S_ENEMY && sh->pad) {
            enemy_step(s, sh, live[j], me);
            continue;
        }
        sh->life--;
        if (sh->who == S_MISSILE) {
            /* a missile steers at its lock (a pirate, or Payback's person or vehicle, read each
               tick: it moves) at the speed it has, 200 or more (it left at the ship's speed and
               120: at 200 a boosting Arwing overtook it into its own burst); without a lock it
               works up to 200 */
            V3 v = v3(sh->vx, sh->vy, sh->vz), tp, tv;
            if (lock_at(sh->tgt, (u8)sh->pad, &tp, &tv)) {
                V3 w = vscale(dir_of(vsub(tp, sh->p)), imax(dist(v), 200));
                v = vadd(v, vshr(vsub(w, v), 3));
            } else {
                if (sh->tgt >= NFOE)
                    sh->tgt = -1;          /* (its record left the list: fly on) */
                if (sh->vx * sh->vx + sh->vy * sh->vy + sh->vz * sh->vz < 200 * 200)
                    v = vadd(v, vshr(v, 4));
            }
            sh->vx = v.x, sh->vy = v.y, sh->vz = v.z;
        }
        V3 half = v3(sh->vx >> 1, sh->vy >> 1, sh->vz >> 1), p0 = sh->p;
        /* the street objects drawn (a lamp post, a tree, a crate, opened): once a tick, over both
           halves, the first met at q, so far along (in |half|^2) */
        V3 q = vadd(p0, vadd(half, half));
        s32 hh = half.x * half.x + half.y * half.y + half.z * half.z, met = 0x7fffffff;
        if (sg_state == SG_FLY && prop_hit(&q, vadd(half, half)))
            met = (q.x - p0.x) * half.x + (q.y - p0.y) * half.y + (q.z - p0.z) * half.z;
        for (int step = 0; step < 2 && sh->life; step++) {
            V3 was = sh->p;
            sh->p = vadd(sh->p, half);
            int prop = met != 0x7fffffff && (step || met <= hh);   /* (met in this half) */
            if (shot_blocked(was, sh->p) && !(prop && !shot_blocked(was, q))) {
                /* the street, a roof, a deck or a railing (unless a street object met in this
                   half stands before it): a laser's spark marks where it landed, a missile bursts
                   and hurts whoever is near (from where it was last in the open: the step ends
                   inside what it hit) */
                boom(sh->p, sh->who == S_MISSILE ? 1 : SPARK);
                if (sh->who == S_MISSILE && sg_state == SG_FLY)
                    city_blast(was, 100, 450, -1);
                sh->life = 0;
                break;
            }
            if (sh->who == S_ENEMY) {
                V3 d = vsub(prop ? q : sh->p, me);
                if (sg_state == SG_FLY && iabs(d.x) < 330 && iabs(d.y) < 200 && iabs(d.z) < 330) {
                    sh->life = 0;
                    boom(sh->p, 0);
                    hurt(s, sh->pad ? sh->pad : 6 + 2 * job_lv);
                } else if (prop) {
                    sh->p = q;           /* (the street objects are cover) */
                    sh->life = 0;
                    boom(sh->p, 0);
                }
                continue;
            }
            int hit = 0;
            if (!prop && sg_state == SG_FLY && (near[0] | near[1]) && (hit = city_hit(sh->p, sh->who == S_MISSILE ? 100 : 25, near))) {
                sh->life = 0;            /* a person or a car hit in the city */
                boom(sh->p, sh->who == S_MISSILE);
                if (sh->who == S_MISSILE)
                    city_blast(sh->p, 100, 450, hit - 1);   /* (the one hit took the whole of it) */
                break;
            }
            for (int k = 0; nfoe && k < NFOE; k++) {
                Foe *f = &foes[k];
                if (!f->kind)
                    continue;
                s32 r = sgx_radius(f);
                V3 d = vsub(sh->p, f->p);
                if (iabs(d.x) > r || iabs(d.y) > r || iabs(d.z) > r)
                    continue;
                if (f->tag && sgx_shielded(k))
                    continue;            /* (a shield: the shot goes through to the guns inside it) */
                if (prop && met < (f->p.x - p0.x) * half.x + (f->p.y - p0.y) * half.y + (f->p.z - p0.z) * half.z)
                    continue;            /* (the street object stands before it) */
                sh->life = 0;
                int dm = sh->who == S_MISSILE ? 12 : laser_lv == 2 ? 3 : 2, dead;
                if (f->tag || f->kind > F_CARRIER)
                    dead = sgx_damage(k, dm);    /* (a mission's, or a part, or a boss still shielded: -1) */
                else
                    dead = (f->hp -= dm) <= 0;
                if (dead > 0)
                    foe_killed(k);
                else
                    boom(sh->p, dead < 0 ? SPARK : 0);
                break;
            }
            if (prop && sh->life) {
                sh->p = q;               /* a lamp post, a tree, a crate (opened) in the street */
                sh->life = 0;
                boom(sh->p, sh->who == S_MISSILE);
                if (sh->who == S_MISSILE)
                    city_blast(sh->p, 100, 450, -1);
            }
        }
    }
    booms_tick();
}

static void booms_tick(void)
{
    for (int i = 0; i < NBOOM; i++)
        if (booms[i].t && ++booms[i].t > (booms[i].big == SPARK ? 12 : booms[i].big == 2 || booms[i].big >= 4 ? 48 : 24))
            booms[i].t = 0;
}

/* the empty Arwing (bailed out of, merge.c) comes down at p: the same fire, pieces and smoke as
   a shot-down one, and nothing else: no credits lost, the shield as it was */
void sg_crash(V3 p)
{
    boom(p, 2);
    boom(p, 5);
}

/* while the Arwing is not out sg_tick does not run: the fire and smoke of a crash still go on,
   and shots in the air fly on and out */
void sg_fx_tick(void)
{
    booms_tick();
    for (int i = 0; i < NSHOT; i++) {
        Shot *sh = &shots[i];
        if (sh->life && !--sh->life)
            continue;
        if (sh->life)
            sh->p = vadd(sh->p, v3(sh->vx, sh->vy, sh->vz));
    }
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
                s2_ev(EV_PICKUP, 1 + i, n);       /* (a pod's tag: 1 + its place; a boss's pod has the boss's tag) */
                if (n >= NPOD) {
                    pods_got = 0xff;
                    note("All pods aboard! Dock to cash in.");
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
    sgx_pickups(p);
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
    case SG_DOCKED: {
        u16 own = (keys & ~(KEY_LEFT | KEY_RIGHT)) | (keys & KEY_LEFT ? KEY_RIGHT : 0) | (keys & KEY_RIGHT ? KEY_LEFT : 0);   /* (the D-pad's own sides: keys came mirrored) */
        if (cp_dock_keys(hit, own, menu == MN_MAIN))   /* (the campaign's quick menu has them) */
            break;
        if (st_tick && st_tick(hit, own))       /* (the station's walker has them: it is outside the hangar) */
            break;
        menu_input(s, hit, own);
        cheat_input(hit);
        break;
    }
    case SG_LAUNCH:
        launching(s);
        break;
    case SG_DEAD:
        tow(s);
        break;
    default: {
        u16 k = keys & ~(KEY_L | KEY_R);
        if (sg_invert)
            k = (k & ~(KEY_UP | KEY_DOWN)) | (keys & KEY_UP ? KEY_DOWN : 0) | (keys & KEY_DOWN ? KEY_UP : 0);
        ship_update(s, k);
        crash(s);
        if (sg_state != SG_FLY)
            break;
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
        sgx_tick();
    }
    if (job_time && sg_state == SG_FLY && !--job_time)
        job_end(0);
}

/* ---- drawing, 3D ---- */

/* a mission's foes' shot: a thick line along the nearer axis of the screen, with no division (they are a few of them, every frame,
   and from afar a pixel or two) */
static void bolt_fast(V3 a, V3 b, int color, s32 w)
{
    V3 c0 = r_cam(a), c1 = r_cam(b);
    if (c0.z < NEAR && c1.z < NEAR)
        return;
    V3 o = iabs(c1.x - c0.x) > iabs(c1.y - c0.y) ? v3(0, w, 0) : v3(w, 0, 0);
    V3 q[4] = {vadd(c0, o), vadd(c1, o), vsub(c1, o), vsub(c0, o)};
    r_poly(q, 4, color, -1, 0);
}

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

/* a fireball's scale, at most what keeps it 43 pixels round on the screen (mdl_boom is 260 at 256):
   flown into, or bursting under the nose, one would fill the screen and then go at once */
static s32 boom_cap(V3 p, s32 scale)
{
    s32 c = dist(vsub(p, cam.pos)) * 5 >> 4;
    return scale < c ? scale : c;
}

static void place_draw(const Model *md, V3 p, const M3 *m, s32 scale)
{
    Place pl;
    V3 d = vsub(p, cam.pos);
    int far = iabs(d.x) > 28000 || iabs(d.y) > 28000 || iabs(d.z) > 28000 ? 2 : 0;
    if (model_place(&pl, p, m, scale, far, md->radius))
        model_draw(md, &pl);
}

/* smoke: the fireball's shape, dull greys, lit and not glowing */
#define SF3(m, a, b, c) {3, m, 0, {a, b, c}}
#define K 9459                                   /* 1 / sqrt 3 */
static const MVert smoke_v[] = {{0, 256, 0}, {0, -256, 0}, {256, 0, 0}, {-256, 0, 0}, {0, 0, 256}, {0, 0, -256}};
static const MFace smoke_f[] = {
    SF3(M_CONCRETE, 0, 2, 4), SF3(M_ROAD, 0, 4, 3), SF3(M_CONCRETE, 0, 3, 5), SF3(M_ROAD, 0, 5, 2),
    SF3(M_ROAD, 1, 4, 2), SF3(M_CONCRETE, 1, 3, 4), SF3(M_ROAD, 1, 5, 3), SF3(M_CONCRETE, 1, 2, 5),
};
static const N3 smoke_n[] = {{K, K, K}, {-K, K, K}, {-K, K, -K}, {K, K, -K}, {K, -K, K}, {-K, -K, K}, {-K, -K, -K}, {K, -K, -K}};
#undef K
static const Model mdl_smoke = {smoke_v, smoke_f, 6, 8, 260, (N3 *)smoke_n};

/* pieces of the Arwing flying off, tumbling and falling */
static __attribute__((noinline)) void debris(const Boom *b)
{
    static const s8 out[6][3] = {{4, 3, 1}, {-4, 2, 2}, {1, 4, -4}, {-2, 1, 4}, {3, 2, -3}, {-3, 4, -1}};
    static const MVert shard[3] = {{-70, -30, -40}, {70, 20, -50}, {0, 40, 80}};
    Place pl;
    M3 m;
    s32 t = b->t;
    for (int i = 0; i < 6; i++) {
        myaw(&m, t * 2900 + i * 11000);
        V3 p = vadd(b->p, v3(out[i][0] * t * 8, out[i][1] * t * 8 - t * t, out[i][2] * t * 8));
        if (model_place(&pl, p, &m, 256, 0, 120))
            model_poly(&pl, shard, 3, COLOR(i & 1 ? M_SHIP : M_CAR, 2, pl.fog));
    }
}

static __attribute__((noinline)) void hangar_draw(void)
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

/* (each part of the frame in a function of its own: what a part keeps on the stack is not kept while the models of the others are drawn,
   and the polygon routines are the deepest thing in the game) */
static __attribute__((noinline)) void draw_shots(void)
{
    for (int i = 0; i < NSHOT; i++) {
        const Shot *sh = &shots[i];
        if (!sh->life || !near_cam(sh->p, sh->who == S_ENEMY && sh->pad ? (sgx_shed ? 3500 : 6000) : 20000))
            continue;
        V3 v = v3(sh->vx, sh->vy, sh->vz);
        if (sh->who == S_ENEMY && sh->pad)
            bolt_fast(sh->p, vsub(sh->p, vshr(v, 1)), COLOR(M_STUNT, 3, 0), 20);
        else if (sh->who == S_MISSILE)
            bolt(sh->p, vsub(sh->p, vshr(v, 0)), COLOR(M_ACCENT, 3, 0), 22);
        else
            bolt(sh->p, vsub(sh->p, vshr(v, 1)), sh->who == S_LASER ? COLOR(M_GRASS, 3, 0) : COLOR(M_STUNT, 3, 0),
                 sh->who == S_LASER ? 14 : 20);
    }
}

static __attribute__((noinline)) void draw_booms(void)
{
    M3 m;
    for (int i = 0; i < NBOOM; i++) {
        const Boom *b = &booms[i];
        if (!b->t || !near_cam(b->p, 30000))
            continue;
        myaw(&m, b->t * 3000);
        if (b->big == SPARK) {                   /* where a laser landed: the small boom, in half its time */
            if (near_cam(b->p, 16000))
                place_draw(&mdl_boom, b->p, &m, boom_cap(b->p, b->t < 4 ? b->t * 35 : 140 + (b->t - 4) * 4));
            continue;
        }
        if (b->big >= 4) {                       /* smoke, rising: a puff, or the wreck's cloud; it swells, */
            s32 t = b->t, k = t < 24 ? t : 48 - t;   /* then thins away (no big shape gone at once) */
            place_draw(&mdl_smoke, vadd(b->p, v3(0, t * 10, 0)), &m, b->big == 5 ? 60 + k * 12 : 30 + k * 6);
            continue;
        }
        if (b->big == 2) {                       /* the Arwing: pieces flying, and a small fire that dies down */
            debris(b);
            if (b->t < 10)
                place_draw(&mdl_boom, b->p, &m, (10 - b->t) * 10);
            continue;
        }
        s32 grow = b->t < 8 ? b->t * 32 : 256 + (b->t - 8) * 8;
        place_draw(&mdl_boom, b->p, &m, boom_cap(b->p, (grow * (b->big == 3 ? 1024 : b->big == 2 ? 640 : b->big ? 360 : 140)) >> 8));
    }
}

static __attribute__((noinline)) void draw_marks(void)
{
    M3 m;
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
}

void sg_draw(const Ship *s)
{
    (void)s;
    if (near_cam(station_pos, 9000))
        hangar_draw();
    sgx_draw();                                  /* (the foes the frame can draw, and the escape pods) */
    draw_shots();
    draw_booms();
    draw_marks();
    model_body = M_CAR;
}

/* ---- drawing, 2D ---- */

#define INK COLOR(M_CREAM, 3, 0)
#define HI COLOR(M_ACCENT, 3, 0)
#define TITLE COLOR(M_GLOW, 3, 0)
#define DIM COLOR(M_STEEL, 1, 0)
#define PANEL COLOR(M_ROAD, 0, 0)
#define HELP COLOR(M_STEEL, 3, 0)

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

static void brackets(int x, int y, int r, int c) { d_corners(x, y, r, c); }

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

static void radar(const Ship *s, int clear)    /* clear: no panel behind it (filling it is most of its cost) */
{
    const int cx = 28, cy = 88, R = 22;
    if (!clear)
        d_fill(cx - R - 2, cy - R - 2, 2 * R + 6, 2 * R + 5, PANEL);
    int bare = clear && sgx_tagged();            /* (over the streets, a mission's foes on it: its blips and no cross, the cross is half of it) */
    if (!bare) {
        d_hline(cx - R, cx + R, cy, DIM);
        d_vline(cx, cy - R, cy + R, DIM);
    }
    V3 p = ship_at(s), f = s->b.m.f, r = s->b.m.r;
    V3 fl = vnorm(v3(f.x, 0, f.z)), rl = vnorm(v3(r.x, 0, r.z));
    for (int i = -1; i < NFOE + 1; i++) {
        V3 w;
        int c;
        if (i < 0) w = station_pos, c = INK;
        else if (i == NFOE) {
            if (job == J_COURIER || job == J_RACE) w = job_at, c = HI;
            else continue;
        } else if (foes[i].kind && foes[i].kind != F_TURRET && foes[i].kind != F_BAY) w = foes[i].p, c = COLOR(M_STUNT, 3, 0);   /* (a boss's guns are on its body) */
        else continue;
        V3 d = vsub(w, p);
        while (iabs(d.x) > 30000 || iabs(d.z) > 30000)
            d = vshr(d, 1), d.y = 0;
        s32 fx = vdot(rl, v3(d.x, 0, d.z)), fz = vdot(fl, v3(d.x, 0, d.z));
        s32 len = iabs(fx) + iabs(fz);
        s32 range = 24000;
        if (len > range) fx = fx * range / len, fz = fz * range / len;
        int x = cx - (fx * 60 >> 16), y = cy - (fz * 60 >> 16);   /* (the screen shows the world mirrored; 60 / 65536 is R / range) */
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

/* text on a dark panel, centred on cx, on one or two lines of up to most (25 at most) letters,
   broken at a space; y: the top line */
static void panel_text(const char *s, int cx, int y, int most, int c)
{
    int n = 0, cut = 0, k;
    while (s[n]) n++;
    if (n > most) {
        for (cut = most; cut > 0 && s[cut] != ' '; cut--)
            ;
        if (!cut) cut = most;
    }
    char t[2][26];
    int len[2] = {cut ? cut : n, 0};
    for (k = 0; k < len[0] && k < most; k++) t[0][k] = s[k];
    t[0][len[0] = k] = 0;
    const char *r = s + len[0] + (cut && s[cut] == ' ');
    for (k = 0; cut && r[k] && k < most; k++) t[1][k] = r[k];
    t[1][len[1] = k] = 0;
    int w = (len[0] > len[1] ? len[0] : len[1]) * TEXT_W + 8;
    d_fill(cx - w / 2, y - 2, w, len[1] ? 21 : 12, PANEL);
    for (k = 0; k < 2 && len[k]; k++)
        d_text(cx - len[k] * TEXT_W / 2, y + 9 * k, t[k], c);
}

/* the note on screen, if any: over the city, between Payback's hearts and the Arwing, left of its
   map; in the hangar at the top, between its weapon icon and its score, over the menu (or how
   the menu works) */
static void banner_draw(int here)
{
    int docked = sg_state == SG_DOCKED && here;
    const char *t = frame_count < banner_end ? banner : docked ? "D-PAD, A PICK, B BACK"
                  : here && sg_state == SG_DOCKING ? "DOCKING..." : here && sg_state == SG_LAUNCH ? "LAUNCH!" : 0;
    if (t)
        panel_text(t, docked ? 87 : 81, docked ? 4 : 42, docked ? 22 : 25, TITLE);
}

void sg_banner(void) { banner_draw(0); }

static void menu_draw(void)
{
    char b[48], *p;
    const int x = 8, y0 = 40;
    /* narrow where the Arwing should show (main menu, paint), wide for the lists (and clear of
       Payback's map) */
    int w = menu == MN_JOBS || menu == MN_YARD ? 152 : 120;
    int more = menu == MN_MAIN && job && sw_pack ? 10 : 0;   /* (a job's line and the pack's: one row more) */
    d_fill(x - 4, y0 - 3, w, menu == MN_YARD ? 90 : 86 + more, PANEL);
    d_hline(x - 4, x + w - 5, y0 + 9, DIM);
    static const char *const titles[] = {"FOX STATION HANGAR", "JOB BOARD", "SHIPYARD", "PAINT SHOP", "OPTIONS"};
    d_text(x, y0, titles[menu], TITLE);
    p = d_cat(b, "CREDITS ");
    p = d_num(p, credits);
    d_text(x, y0 + (menu == MN_YARD ? 78 : 74 + more), b, HI);
    int n = menu_len(), top = menu == MN_PAINT && cursor > 5 ? cursor - 5 : 0;   /* (the paints: six lines of them) */
    for (int i = top; i < n && i < top + 6; i++) {
        int y = y0 + 12 + (i - top) * (menu == MN_YARD ? 9 : 10), c = i == cursor ? HI : INK;
        p = b;
        *p = 0;
        switch (menu) {
        case MN_MAIN:
            if (i == 0 && job && n > 5)          /* (a sixth line takes the place of the job's line below) */
                p = d_cat(d_cat(b, "JOB: "), job_name[job]);
            else
                d_cat(b, main_items[i == n - 1 ? 5 : i]);
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
            static const char *const names[] = {"LASERS", "SHIELD", "ENGINE", "MISSILES", "MISSILE RACK", "JET PACK"};
            static const char *const lv[3] = {" MK1", " MK2", " MK3"};
            p = d_cat(p, names[i]);
            int l = i == 0 ? laser_lv : i == 1 ? shield_lv : i == 2 ? engine_lv : i == 4 ? rack_lv : -1;
            if (l >= 0) p = d_cat(p, lv[l]);
            else if (i == 3) { p = d_cat(p, " "); p = d_num(p, missiles); p = d_cat(p, "/"); p = d_num(p, rack_size[rack_lv]); }
            int pr = yard_price(i);
            p = d_cat(p, pr ? "  " : i == 5 ? "  FITTED" : "  FULL");
            if (pr) { p = d_num(p, pr); d_cat(p, "CR"); }
            break;
        }
        case MN_PAINT:
            d_cat(b, paint_name[paint_at(i)]);
            break;
        default:
            d_cat(b, i == 0 ? (sg_invert ? "STICK: UP CLIMBS" : "STICK: UP DIVES") : i == 1 ? (sg_autoaim ? "AIM: AUTO" : "AIM: MANUAL")
                   : i == 2 ? (!rag_unlock ? "RAGDOLLS: LOCKED" : !rag_on ? "RAGDOLLS: OFF" : rag_wacky ? "RAGDOLLS: WACKY" : "RAGDOLLS: ON")
                   : i == 3 ? (rag_fall ? "FALL DAMAGE: ON" : "FALL DAMAGE: OFF")
                   : i == 4 ? radio_mode_name(radio_mode()) : "GAME SETTINGS >");
            break;
        }
        if (i == cursor)
            d_text(x - 2, y, ">", HI);
        d_text(x + 6, y, b, c);
    }
    if (menu == MN_MAIN && job && n < 6) {
        p = d_cat(b, "JOB: ");
        d_cat(p, job_name[job]);
        d_text(x, y0 + 64, b, TITLE);
    }
    if (menu == MN_MAIN && sw_pack)
        d_text(x, y0 + (job ? 74 : 64), "JET PACK FITTED", HELP);
    /* what the line under the cursor does, before you pick it (24 letters at most) */
    if (menu == MN_JOBS) {
        static const char *const what[J_N] = {"", "SHOOT DOWN RAIDERS", "LAND ON A CITY ROOFTOP", "GRAB 5 PODS, THEN DOCK",
                                              "FLY 8 GATES IN TIME", "SHOOT PIRATES OVER CITY", "DESTROY THE CARRIER"};
        if (cursor == 3)
            d_text(x, y0 + 53, "GIVE UP THE JOB YOU HAVE", INK);
        else if (job)
            d_text(x, y0 + 53, "FINISH OR DROP YOUR JOB", INK);
        else {
            d_text(x, y0 + 53, what[offers[cursor].type], INK);
            d_text(x, y0 + 63, "A: TAKE IT AND LAUNCH", HELP);
        }
    }
    if (menu == MN_YARD) {
        static const char *const what[] = {"MORE SHOTS, HARDER HITS", "TAKE MORE HITS", "FASTER FLYING",
                                           "REFILL THE RACK", "CARRY MORE MISSILES", "FLY FREE IN SPACE"};
        if (confirm)
            d_text(x, y0 + 67, "A AGAIN: BUY  B: NO", HI);
        else
            d_text(x, y0 + 67, what[cursor], HELP);
    }
    if (menu == MN_OPT)
        d_text(x, y0 + 64, "A CHANGES IT", HELP);
}

void sg_hud(const Ship *s)
{
#ifdef NOHUD
    return;
#endif
    char b[48], *p;
    banner_draw(1);
    if (sg_state == SG_DOCKED) {
        if (menu == MN_SET)
            opt_draw();
        else
            opt_hud(1), menu_draw();               /* (opt_hud: Payback's sprites back, off the page) */
        return;
    }
    if (sg_state == SG_DOCKING || sg_state == SG_DEAD)
        return;
    /* shield, credits, missiles: top left, beside Payback's weapon icon, left of its hearts */
    d_text(16, 20, "SHIELD", INK);
    bar(54, 22, 40, shield, shield_max, shield * 4 < shield_max ? COLOR(M_STUNT, 3, 0) : COLOR(M_GRASS, 3, 0));
    p = d_cat(b, "CR ");
    p = d_num(p, credits);
    p = d_cat(p, " MSL ");
    d_num(p, missiles);
    d_text(16, 29, b, INK);
    if ((s->b.pos.y >> FX) > SPACE_LO || job || sgx_foes())
        radar(s, !job && (s->b.pos.y >> FX) <= SPACE_LO);     /* (not over the streets: Payback has its map; over them a mission's pirates get it bare) */
    /* the gunsight: on the first thing the nose line meets (the street, a roof, a deck, a
       person, a car), so what is under it is what the bolts reach; SIGHT out over nothing (the
       camera sits above and behind, so a fixed sight was over the bolts' line at every nearer
       range: what it was on was missed under). It comes in at once and goes out over 3 or 4
       frames: the camera sees a change of depth as a jump on the screen. Auto-aim's lock is the
       best of the people and cars ahead that the nose can see (two looks). Both are looked for
       every other frame (fire() takes the ship's way since off them, tick by tick), or by the
       volley that starts a burst */
    int x, y, lock = last_target;
    if ((hud_turn ^= 1)) {
        s32 reach;
        lock = lock_scan(s, 15200, 14000, &reach, sg_autoaim ? 2 : 0);
        sight_hit = reach;
        last_tag = tag_of(lock);
    }
    s32 hit = sight_hit, r = sight_reach;   /* (drawn: nearer at once, farther half the way a frame) */
    r = hit < r || r <= 0 || r > SIGHT ? hit : r + ((hit - r + 1) >> 1);
    sight_reach = r;
    if (project(vadd(ship_at(s), mlocal(&s->b.m, v3(0, 0, NOSE + r))), &x, &y)) {
        d_hline(x - 5, x - 2, y, HI);
        d_hline(x + 2, x + 5, y, HI);
        d_vline(x, y - 5, y - 2, HI);
        d_vline(x, y + 2, y + 5, HI);
    }
    /* pirates on screen get brackets; the one auto-aim locks gets the bright ones, and so does
       the person or vehicle it locks in the city (that one alone) */
    if (!sg_autoaim)
        lock = -1;
    last_target = lock;
    s32 near_[NFOE], size_[NFOE];
    for (int i = 0; i < NFOE; i++) {
        size_[i] = foes[i].kind ? sgx_size(&foes[i]) : 0;      /* (one with no bracket to draw is no nearer than the rest) */
        near_[i] = size_[i] ? rlen(vsub(foes[i].p, cam.pos)) : 0x7fffffff;
    }
    for (int i = 0; i < NFOE; i++) {
        s32 sz = size_[i];
        if (!sz)
            continue;
        int rank = 0;                    /* (the three nearest have brackets, and the one locked: more is more to draw than to read) */
        for (int k = 0; k < NFOE; k++)
            rank += near_[k] < near_[i] || (near_[k] == near_[i] && k < i);
        if ((rank > (sgx_shed ? 0 : 2) && i != lock) || !project(foes[i].p, &x, &y))
            continue;
        s32 dd = near_[i];
        int r = sz * FOCAL / (dd ? dd : 1) + 4;
        if (r > 40) r = 40;
        brackets(x, y, r, i == lock ? HI : COLOR(M_STUNT, 3, 0));
    }
    V3 tp, tv;
    if (lock >= NFOE && lock_at(lock, last_tag, &tp, &tv) && project(tp, &x, &y)) {
        s32 dd = rlen(vsub(tp, cam.pos));
        int r = 300 * FOCAL / (dd ? dd : 1) + 4;
        if (r > 40) r = 40;
        brackets(x, y, r, HI);
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
        p = d_cat(p, "LAND AT THE BEACON ");
        d_time(p, job_time / 60);
        marker(vadd(job_at, v3(0, 300, 0)), HI);
        break;
    case J_SALVAGE:
        if (pods_got == 0xff) {
            d_cat(p, "SALVAGE: DOCK TO CASH IN");
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
        if (sgx_boss_text(b))
            break;
        if (s->b.pos.y >> FX > SPACE_LO) {
            d_cat(p, "HOLD SELECT NEAR STATION");
            if (!near_cam(station_pos, 12000))
                marker(station_pos, INK);
        }
        break;
    }
    if (b[0] && !s2_hud_owned()) {                  /* (a mission's line owns y117) */
        int n = 0;
        while (b[n]) n++;
        d_fill(0, 115, n * TEXT_W + 8, 11, PANEL);
        d_text(4, 117, b, HI);
    }
    sgx_boss_bar();
}

/* ---- stage 2: for sgx.c, the station's walker, the shops and the missions (spacegame.h, sgint.h) ---- */

int sg_job_active(void) { return job != J_NONE; }

void sgi_boom(V3 p, int big) { boom(p, big); }
s32 sgi_dist(V3 d) { return dist(d); }
V3 sgi_dir(V3 d) { return dir_of(d); }
s32 sgi_rnd(s32 lo, s32 hi) { return rnd(lo, hi); }
s32 sgi_rand(void) { seed = seed * 1664525 + 1013904223; return seed >> 16; }
s32 sgi_roof(s32 x, s32 z) { return roof_y(x, z); }
int sgi_seen(V3 a, V3 b) { return seen(a, b); }
void sgi_place(const Model *md, V3 p, const M3 *m, s32 scale) { place_draw(md, p, m, scale); }
int sgi_near(V3 p, s32 r) { return near_cam(p, r); }
void sgi_note(const char *s) { note(s); }
int sgi_tier(void) { return jobs_done >= 6 ? 3 : jobs_done >= 3 ? 2 : 1; }

int sgi_free_foe(void)
{
    for (int i = 0; i < NFOE; i++)
        if (foes[i].kind == F_NONE)
            return i;
    return -1;
}

void sgi_foe_killed(int i) { foe_killed(i); }

int sg_credits(void) { return credits; }

void sg_give(int n)
{
    credits += n;
    credits = credits < 0 ? 0 : credits > 9999999 ? 9999999 : credits;
}
void sgi_pay(int n) { sg_give(n); }

void sg_get_progress(void *out)
{
    SgProgress *p = out;
    p->credits = credits;
    p->medals = medals;
    p->paints = paints_got;
    p->laser = laser_lv, p->engine = engine_lv, p->rack = rack_lv, p->shield = shield_lv;
    p->missiles = missiles, p->paint = paint, p->jobs = jobs_done;
    p->flags = sg_invert | sg_autoaim << 1;
    for (int i = 0; i < 16; i++)
        p->spare[i] = 0;
}

void sg_set_progress(const void *in)
{
    const SgProgress *p = in;
    credits = p->credits;
    medals = p->medals;
    paints_got = p->paints;
    laser_lv = p->laser, engine_lv = p->engine, rack_lv = p->rack, shield_lv = p->shield;
    missiles = p->missiles, paint = p->paint, jobs_done = p->jobs;
    sg_invert = p->flags & 1, sg_autoaim = p->flags >> 1 & 1;
    sg_sane();
}

int sg_price(int item)
{
    if (item >= SGB_PAINT)
        return item - SGB_PAINT < (int)NPAINT && (paints_got >> (item - SGB_PAINT) & 1) ? 0 : -1;
    return item >= 0 && item < 5 ? yard_price(item) : -1;
}

int sg_buy(int item)
{
    if (sg_price(item) < 0)
        return 0;
    if (item >= SGB_PAINT) {
        paint = item - SGB_PAINT;
        return 1;
    }
    return buy(item);
}

int sg_paints(const char *const **names)
{
    *names = paint_name;
    return NPAINT;
}

int sg_paint_unlocked(int i) { return (unsigned)i < NPAINT && (paints_got >> i & 1); }

void sg_unlock_paint(int i)
{
    if ((unsigned)i < NPAINT)
        paints_got |= 1 << i;
}

/* what the docked menu shows, as one word: the same word, and nothing about the hangar's view has changed (but its crew) */
u32 sg_menu_sig(void)
{
    u32 h = menu | cursor << 4 | dock_stage << 9 | confirm << 11 | paint << 15 | sg_state << 20 | (frame_count < banner_end) << 24;
    h = (h * 0x01000193) ^ banner_end ^ credits ^ missiles << 24 ^ cp_sig();
    return menu == MN_SET ? h ^ frame_count : h;      /* (the settings page has its own cursor and values: always redrawn) */
}

int sg_launch(void)
{
    if (sg_state != SG_DOCKED)
        return 0;
    sg_state = SG_LAUNCH;
    st_t = 0;
    note(job ? "LAUNCH! Good hunting." : "LAUNCH! Jobs on the board pay credits.");
    return 1;
}
