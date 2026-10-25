/* Combat in the city (MERGE build; stage2.md 8): the foes a mission asks for (stage2.h: sg_foe_spawn ...), the
   bosses with their guns and bays, the ace and the courier, and the escape pods. spacegame.c keeps the Arwing, its
   shots, the jobs and the old raiders and carrier; it calls in here for the newer kinds of foe and for anything
   that has a tag (a mission's). A tagged foe flies over the roofs it is about to meet, and the frame draws at
   most the few nearest (sgx_draw). Foes of every kind stay in spacegame.c's table (8 of them); a boss is a body
   and its parts in it, which share its tag. Nothing here touches the ticker: the HUD is spacegame's. */
#include "sgint.h"
#define APART __attribute__((noinline))   /* (their locals kept off the frames the renderer is called from: a frame is stack for every polygon below it) */
#include "sgmodels.h"
#include "physics.h"
#include "world.h"
#include "render.h"
#include "palette.h"
#include "draw2d.h"
#include "pbapi.h"

#define N(a) ((int)(sizeof a / sizeof a[0]))
#include "sgnorm.inc"

static const Model sgm_turret = {turret_v, turret_f, N(turret_v), N(turret_f), 330, (N3 *)turret_n};
static const Model sgm_wing = {wing_v, wing_f, N(wing_v), N(wing_f), 1100, (N3 *)wing_n};
static const Model sgm_hull = {hull_v, hull_f, N(hull_v), N(hull_f), 2800, (N3 *)hull_n};
static const Model sgm_disc = {disc_v, disc_f, N(disc_v), N(disc_f), 3000, (N3 *)disc_n};
static const Model sgm_wing_lo = {wing_lo_v, wing_lo_f, N(wing_lo_v), N(wing_lo_f), 1100, (N3 *)wing_lo_n};
static const Model sgm_hull_lo = {hull_lo_v, hull_lo_f, N(hull_lo_v), N(hull_lo_f), 2800, (N3 *)hull_lo_n};
static const Model sgm_disc_lo = {disc_lo_v, disc_lo_f, N(disc_lo_v), N(disc_lo_f), 3000, (N3 *)disc_lo_n};
enum { SM_NONE, SM_WING, SM_HULL, SM_DISC, SM_LO };         /* (SM_LO + a shape: its far shape, with about half the faces) */
static const Model *const sg_models[] = {0, &sgm_wing, &sgm_hull, &sgm_disc, 0, &sgm_wing_lo, &sgm_hull_lo, &sgm_disc_lo};

/* ---- boss_tab: the bosses (stage2.md 8.3), in ROM ---- */
enum { BF_PHASED = 1 };            /* the body is shielded while any part stands, and the bays while a turret does */
#define PT_FIXED 0x80              /* a part that stays where it was put down: its offset is from the spawn point, its height the roof's */
typedef struct { s16 x, y, z; u8 kind, hp; } Part;        /* kind (| PT_FIXED); x y z: where on the body (its own frame) */
typedef struct {
    u8 kind, model, trim, flags;   /* the body's kind; its shape; the paint of its trim faces; BF_ */
    s16 hp, radius, scale;         /* its health; how far a shot hits it; how big it is drawn (256 = the model) */
    u8 rate, nparts;               /* how fast it goes round its place (units a tick) */
    s16 orbit;                     /* ... on a circle this wide */
    char name[12];
    Part part[6];
} BossDef;
#define NBOSS 9
static const BossDef boss_tab[NBOSS] = {
    {F_HULL, SM_WING, M_STUNT, 0, 40, 1300, 384, 14, 2, 1800, "GULLWING",
     {{-640, 60, -380, F_TURRET, 8}, {640, 60, -380, F_TURRET, 8}}},
    {F_HULL, SM_WING, M_ACCENT, 0, 60, 1500, 460, 12, 2, 2200, "DROPSHIP",
     {{-520, -120, -200, F_BAY, 12}, {520, -120, -200, F_BAY, 12}}},
    {F_HULL, SM_HULL, M_BRICK, 0, 70, 2300, 300, 10, 4, 1800, "SIEGE BARGE",
     {{-1700, 0, -1700, F_TURRET | PT_FIXED, 10}, {1700, 0, -1700, F_TURRET | PT_FIXED, 10},
      {-1700, 0, 1700, F_TURRET | PT_FIXED, 10}, {1700, 0, 1700, F_TURRET | PT_FIXED, 10}}},
    {F_CARRIER, SM_NONE, 0, 0, 80, 1300, 256, 0, 2, 0, "CARRIER",
     {{-650, 330, -700, F_TURRET, 8}, {650, 330, -700, F_TURRET, 8}}},
    {F_HULL, SM_HULL, M_STEEL, 0, 90, 2500, 384, 9, 4, 2400, "FRIGATE",
     {{-420, 620, 1200, F_TURRET, 9}, {420, 620, 1200, F_TURRET, 9}, {-420, 620, 300, F_TURRET, 9}, {420, 620, 300, F_TURRET, 9}}},
    {F_ACE, SM_NONE, 0, 0, 50, 450, 256, 0, 0, 0, "KESTREL", {{0}}},
    {F_HULL, SM_WING, M_BRICK, 0, 100, 2300, 640, 8, 2, 2600, "IRON COMET",
     {{-1000, 120, -600, F_TURRET, 12}, {1000, 120, -600, F_TURRET, 12}}},
    {F_COURIER, SM_NONE, 0, 0, 30, 560, 190, 0, 0, 0, "COURIER", {{0}}},
    {F_HULL, SM_DISC, M_STUNT, BF_PHASED, 150, 2800, 256, 6, 6, 1500, "MOTHERSHIP",
     {{-1000, 560, 1000, F_TURRET, 10}, {1000, 560, 1000, F_TURRET, 10}, {-1000, 560, -1000, F_TURRET, 10},
      {1000, 560, -1000, F_TURRET, 10}, {-2650, 0, 0, F_BAY, 14}, {2650, 0, 0, F_BAY, 14}}},
};

static s32 iabs(s32 v) { return v < 0 ? -v : v; }
static s32 imax(s32 a, s32 b) { return a > b ? a : b; }

/* ---- escape pods: what a boss, an ace or a courier leaves, to fly through for credits ---- */
typedef struct { V3 p; u16 tag, life; } Pod;      /* life: ticks left, 0 free */
static Pod pods[2];
static u8 last_phase;
static u16 text_t;                 /* ticks since the boss came or changed phase: its name is up for a few seconds */

static void pod_drop(V3 at, int tag)
{
    int k = pods[0].life <= pods[1].life ? 0 : 1;
    pods[k].p = v3(at.x, imax(at.y, sgi_roof(at.x, at.z) + 700), at.z);
    pods[k].tag = tag;
    pods[k].life = 1800;
}

int sgx_pickups(V3 p)
{
    int n = 0;
    for (int i = 0; i < 2; i++) {
        V3 d = vsub(pods[i].p, p);
        if (pods[i].life && iabs(d.x) < 450 && iabs(d.y) < 450 && iabs(d.z) < 450) {
            pods[i].life = 0;
            sgi_pay(150);
            sgi_note("ESCAPE POD! +150 CREDITS");
            s2_ev(EV_PICKUP, pods[i].tag, 0);
            n++;
        }
    }
    return n;
}

/* ---- the table ---- */
void sgx_reset(void)
{
    for (int i = 0; i < NFOE; i++)
        sg_foes[i].kind = F_NONE;
    pods[0].life = pods[1].life = 0;
    last_phase = 0;
}

int sgx_tagged(void)
{
    for (int i = 0; i < NFOE; i++)
        if (sg_foes[i].kind && sg_foes[i].tag)
            return 1;
    return 0;
}

int sgx_foes(void)
{
    int n = 0;
    for (int i = 0; i < NFOE; i++)
        n += sg_foes[i].kind != F_NONE;
    return n;
}

static int is_part(const Foe *f) { return f->kind == F_TURRET || f->kind == F_BAY; }
static int is_body(const Foe *f) { return FL_BOSS(f) && !is_part(f); }
static const BossDef *def_of(const Foe *f) { return &boss_tab[FL_BOSS(f) - 1]; }

static Foe *make(int i, int kind, V3 p, V3 home, int hp, int tag, int boss)
{
    Foe *f = &sg_foes[i];
    f->kind = kind;
    f->p = p;
    f->home = home;
    f->v = v3(0, 0, 0);
    f->hp = hp;
    f->cool = sgi_rnd(40, 120);
    f->ai = 0;
    f->fl = boss << 4;
    f->tag = tag;
    f->flo = -32768;
    return f;
}

static int default_hp(int kind)
{
    return kind == F_CARRIER ? 50 : kind == F_TURRET ? 8 : kind == F_ACE ? 30 : kind == F_COURIER ? 20 : 3 + sgi_tier();
}

int sg_foe_spawn(int kind, V3 p, V3 home, int hp, int tag)
{
    int i = sgi_free_foe();
    if (!tag || i < 0 || kind < F_RAIDER || kind > F_COURIER)
        return -1;
    if (kind != F_TURRET)
        p.y = imax(p.y, sgi_roof(p.x, p.z) + 1000);       /* (over the roofs) */
    Foe *f = make(i, kind, p, home, hp > 0 ? hp : default_hp(kind), tag, 0);
    if (kind == F_TURRET)
        f->fl |= FL_FIXED;
    return i;
}

int sg_foe_alive(int tag)
{
    int n = 0;
    for (int i = 0; i < NFOE; i++)
        n += sg_foes[i].kind && (tag ? sg_foes[i].tag == tag : sg_foes[i].tag != 0);
    return n;
}

void sg_foe_clear(int tag)
{
    for (int i = 0; i < NFOE; i++)
        if (sg_foes[i].kind && (tag ? sg_foes[i].tag == tag : sg_foes[i].tag != 0))
            sg_foes[i].kind = F_NONE;
    for (int i = 0; i < 2; i++)
        if (!tag || pods[i].tag == tag)
            pods[i].life = 0;
}

void sg_foe_hold(int tag, int on)
{
    for (int i = 0; i < NFOE; i++)
        if (sg_foes[i].kind && (tag ? sg_foes[i].tag == tag : sg_foes[i].tag != 0))
            sg_foes[i].fl = on ? sg_foes[i].fl | FL_HOLD : sg_foes[i].fl & ~FL_HOLD;
}

static Foe *body_of(int tag)
{
    for (int i = 0; i < NFOE; i++)
        if (sg_foes[i].kind && is_body(&sg_foes[i]) && (!tag || sg_foes[i].tag == tag))
            return &sg_foes[i];
    return 0;
}

int sg_boss_alive(int tag) { return body_of(tag) != 0; }

int sg_foe_escaped(int tag)
{
    for (int i = 0; i < NFOE; i++)
        if (sg_foes[i].kind && sg_foes[i].tag == tag && (sg_foes[i].fl & FL_GONE))
            return 1;
    return 0;
}

int sg_boss_spawn(int boss, V3 p, int tag)
{
    if (!tag || (unsigned)boss >= NBOSS || body_of(0))
        return -1;                                        /* (one boss at a time) */
    const BossDef *d = &boss_tab[boss];
    int free = 0;
    for (int i = 0; i < NFOE; i++)
        free += !sg_foes[i].kind;
    if (free < 1 + d->nparts)
        return -1;
    p.y = imax(p.y, sgi_roof(p.x, p.z) + 1000);
    int h = sgi_free_foe();
    make(h, d->kind, p, p, d->hp, tag, boss + 1);
    for (int k = 0; k < d->nparts; k++) {
        const Part *pt = &d->part[k];
        int i = sgi_free_foe();
        V3 off = v3(pt->x, pt->y, pt->z), at = vadd(p, off);
        if (pt->kind & PT_FIXED)
            at = v3(at.x, sgi_roof(at.x, at.z) + 20, at.z);
        Foe *f = make(i, pt->kind & ~PT_FIXED, at, off, pt->hp, tag, boss + 1);
        f->ai = h;
        if (pt->kind & PT_FIXED)
            f->fl |= FL_FIXED;
    }
    last_phase = 0;
    text_t = 0;
    return h;
}

/* ---- the shapes foes have ---- */
s32 sgx_radius(const Foe *f)
{
    switch (f->kind) {
    case F_CARRIER: return 1300;
    case F_TURRET: return 330;
    case F_ACE: return 450;
    case F_COURIER: return 560;
    case F_BAY: return 520;
    case F_HULL: return def_of(f)->radius;
    }
    return 380;
}

s32 sgx_size(const Foe *f)
{
    if (f->kind == F_TURRET || f->kind == F_BAY) {         /* (a boss's guns have brackets only when you are near enough to pick one) */
        V3 d = vsub(f->p, cam.pos);
        return iabs(d.x) + iabs(d.y) + iabs(d.z) > 7000 ? 0 : sgx_radius(f);
    }
    return f->kind == F_RAIDER ? 400 : f->kind == F_CARRIER ? 1200 : sgx_radius(f);
}

/* the length of an offset to within a few percent (the longest, and a third and an eighth of the other two): to scale a
   direction that has to look right, not to be exact, with no square root */
static s32 rough_len(V3 v)
{
    s32 a = iabs(v.x), b = iabs(v.y), c = iabs(v.z), t;
    if (a < b) t = a, a = b, b = t;
    if (b < c) t = b, b = c, c = t;
    if (a < b) t = a, a = b, b = t;
    return a + (b * 11 >> 5) + (c >> 3);
}

/* a direction along d, ONE long to within a few percent, with one division */
static V3 dirr(V3 d)
{
    while (iabs(d.x) > 60000 || iabs(d.y) > 60000 || iabs(d.z) > 60000)
        d = vshr(d, 1);
    s32 l = rough_len(d);
    if (l < 2)
        return v3(0, ONE, 0);
    s32 k = (1 << 28) / l;
    return v3(d.x * k >> 14, d.y * k >> 14, d.z * k >> 14);
}

/* a foe's frame: its nose along the way it goes (a body's flat), to within a few percent (a model that is a few
   percent long cannot be seen, and a square root and a division for each of three vectors is most of what a model costs) */
static APART void frame_of(const Foe *f, M3 *m)
{
    V3 v = f->v;
    if (f->kind == F_HULL || f->kind == F_COURIER)
        v.y = 0;
    m->f = rough_len(v) < 4 ? v3(0, 0, ONE) : dirr(v);
    V3 h = dirr(v3(m->f.z, 0, -m->f.x));                  /* (straight up or down: any side) */
    m->r = h.x || h.z ? h : v3(ONE, 0, 0);
    m->u = vcross(m->f, m->r);
}

static void part_pos(Foe *f)
{
    const Foe *h = &sg_foes[f->ai];
    M3 m;
    frame_of(h, &m);
    f->p = vadd(h->p, mlocal(&m, f->home));
}

/* how low a mission's foe may fly: over the roofs it is about to meet (here, and a half and a whole second on), and a
   thousand over them */
static s32 floor_now(const Foe *f)
{
    s32 g = sgi_roof(f->p.x, f->p.z);
    for (int k = 1; k <= 2; k++)
        g = imax(g, sgi_roof(f->p.x + f->v.x * 30 * k, f->p.z + f->v.z * 30 * k));
    return g + 1000;
}

u8 sgx_par;                        /* game ticks, to stagger the foes' work */

int sgx_steer(int i) { return !((sgx_par + i) & 7); }

/* (looked up once in eight ticks, a foe moves under a hundred units a tick and the look is a second ahead) */
s32 sgx_floor(Foe *f)
{
    if (f->flo == -32768 || !((sgx_par + (f - sg_foes)) & 7)) {
        s32 g = floor_now(f);
        f->flo = g > 30000 ? 30000 : g;
    }
    return f->flo;
}

/* ---- guns ---- */
static int harm(int base) { return base + sgi_tier(); }

/* a shot from `from` at the Arwing (me, moving at vel units a tick): leading it by most of the way, and off by a little */
static void aim_shot(V3 from, V3 me, V3 vel, int speed, int harm_, int spread)
{
    V3 to = vsub(me, from);
    s32 t = rough_len(to) / speed;
    to = vadd(to, v3((vel.x * t) * 3 >> 2, (vel.y * t) * 3 >> 2, (vel.z * t) * 3 >> 2));
    if (spread) {
        s32 r = sgi_rand(), q = sgi_rand();
        to = vadd(to, v3(((r & 255) - 128) * spread >> 7, ((r >> 8) - 128) * spread >> 8, ((q & 255) - 128) * spread >> 7));
    }
    sgi_enemy_shot(from, vscale(dirr(to), speed), harm_, t + 14 > 70 ? 70 : t + 14);
}

static int guards_up(const Foe *f)
{
    int n = 0;
    for (int i = 0; i < NFOE; i++)
        n += sg_foes[i].kind && sg_foes[i].tag == f->tag && is_part(&sg_foes[i]);
    return n;
}

static int turrets_up(const Foe *f)
{
    int n = 0;
    for (int i = 0; i < NFOE; i++)
        n += sg_foes[i].kind == F_TURRET && sg_foes[i].tag == f->tag && FL_BOSS(&sg_foes[i]);
    return n;
}

/* (the turrets first, then the bays, then the core) */
int sgx_shielded(int i)
{
    const Foe *f = &sg_foes[i];
    return FL_BOSS(f) && (def_of(f)->flags & BF_PHASED) && (f->kind == F_BAY ? turrets_up(f) : is_body(f) && guards_up(f));
}

int sgx_damage(int i, int dm)
{
    Foe *f = &sg_foes[i];
    if (sgx_shielded(i))
        return -1;
    f->hp -= dm;
    return f->hp <= 0;
}

/* two ticks of flying on as it was going (a foe is worked on every other tick), and not under the roofs ahead */
static void fly_on(Foe *f)
{
    f->p = vadd(f->p, vadd(f->v, f->v));
    s32 g = sgx_floor(f);
    if (f->p.y < g) {
        f->p.y = g;
        if (f->v.y < 0)
            f->v.y = -f->v.y >> 1;
    }
}

/* a body's guns and bays, where they sit on it now (once, when it thinks: they are small and it is slow) */
static void place_parts(const Foe *h, int hi, const M3 *m)
{
    for (int k = 0; k < NFOE; k++) {
        Foe *p = &sg_foes[k];
        if (p->kind && p->tag == h->tag && p->ai == hi && is_part(p) && !(p->fl & FL_FIXED))
            p->p = vadd(h->p, mlocal(m, p->home));
    }
}

/* ---- one foe of the newer kinds, a tick ---- */
void sgx_tick_foe(int i, const Ship *s)
{
    Foe *f = &sg_foes[i];
    int mobile = f->kind != F_TURRET && f->kind != F_BAY, dt = mobile ? 2 : 8;
    if (f->cool)
        f->cool = f->cool > dt ? f->cool - dt : 0;        /* (two ticks' worth, a gun's eight) */
    /* a foe thinks one tick in eight (staggered), and whenever its gun is ready; in between it flies on as it was going:
       the looks, the square roots and the divisions of its steering are the dogfight's cost */
    int turn = !f->cool || (f->kind == F_HULL ? !((sgx_par + i) & 15) : sgx_steer(i));    /* (a hull is slow: one tick in sixteen) */
    if (!turn) {
        if (mobile) {
            fly_on(f);
            if (f->kind == F_HULL) {
                V3 v2 = vadd(f->v, f->v);
                for (int k = 0; k < NFOE; k++)           /* (its guns go along with it) */
                    if (sg_foes[k].kind && sg_foes[k].tag == f->tag && sg_foes[k].ai == i && is_part(&sg_foes[k]) && !(sg_foes[k].fl & FL_FIXED))
                        sg_foes[k].p = vadd(sg_foes[k].p, v2);
            }
        }
        return;
    }
    V3 me = vshr(s->b.pos, FX), vel = vshr(s->b.vel, FX), to = vsub(me, f->p), want;
    M3 fm;
    s32 d = rough_len(to);
    int chase = sg_state == SG_FLY && d < 16000;
    switch (f->kind) {
    case F_TURRET:
    case F_BAY:
        mobile = 0;
        if (!(f->fl & FL_FIXED)) {
            const Foe *h = &sg_foes[f->ai];
            if (!h->kind || h->tag != f->tag) {           /* (its body has gone) */
                f->kind = F_NONE;
                return;
            }
            if (h->kind != F_HULL)
                part_pos(f);             /* (a hull's parts are set when it thinks) */
        }
        if (!chase || f->cool)
            break;
        if (f->kind == F_TURRET) {
            if (d < 9500 && (!(f->fl & FL_FIXED) || sgi_seen(vadd(f->p, v3(0, 200, 0)), me))) {
                aim_shot(f->p, me, vel, 150, harm(4), 220);
                f->cool = 80 + sgi_rnd(0, 50) - 10 * sgi_tier();
            } else {
                f->cool = 45;                   /* (a roof turret's look at the Arwing is a line through the city: not every few ticks) */
            }
        } else {                                          /* a bay launches a raider, while few of its own are out */
            int raiders = 0;
            for (int k = 0; k < NFOE; k++)
                raiders += sg_foes[k].kind == F_RAIDER && sg_foes[k].tag == f->tag;
            int k = sgi_free_foe();
            if (d < 14000 && raiders < 3 && k >= 0 && sgx_foes() < NFOE) {
                make(k, F_RAIDER, f->p, sg_foes[f->ai].home, default_hp(F_RAIDER), f->tag, 0);
                sg_foes[k].v = vscale(dirr(vsub(f->p, sg_foes[f->ai].p)), 40);
                f->cool = 240;
            } else {
                f->cool = 30;
            }
        }
        break;
    case F_ACE: {
        s32 sp = 92 + 8 * sgi_tier();
        if (!(f->ai & 31) && !(f->cool & 3)) {                   /* evasive: a shot of the player's coming at her, she breaks across it */
            for (int k = 0; k < NSHOT; k++) {
                const Shot *sh = &sg_shots[k];
                if (!sh->life || sh->who == S_ENEMY)
                    continue;
                V3 r = vsub(sh->p, f->p), sv = v3(sh->vx, sh->vy, sh->vz);
                if (iabs(r.x) < 900 && iabs(r.y) < 900 && iabs(r.z) < 900 && r.x * sv.x + r.y * sv.y + r.z * sv.z < 0) {
                    V3 side = vcross(dirr(sv), v3(0, ONE, 0));
                    if (sgi_rnd(0, 1))
                        side = v3(-side.x, -side.y, -side.z);
                    f->v = vadd(f->v, vscale(vadd(side, v3(0, sgi_rnd(-5000, 5000), 0)), sp));
                    f->ai = (f->ai & ~31) | 4;
                    break;
                }
            }
        }
        if (f->ai & 31) {
            f->ai--;
            want = vscale(dirr(f->v), sp);
        } else if (!chase) {
            V3 h = vsub(f->home, f->p);                   /* (circle the place she guards) */
            want = rough_len(h) > 3500 ? vscale(dirr(h), sp) : vscale(dirr(vadd(f->v, vcross(v3(0, ONE, 0), f->v))), sp);
        } else if (d > 4500) {
            want = vscale(dirr(to), sp);
        } else {                                          /* close: round the player, one way and then the other, drawing in */
            V3 tang = vcross(v3(0, ONE, 0), to);
            if (frame_count >> 7 & 1)
                tang = v3(-tang.x, -tang.y, -tang.z);
            want = vscale(dirr(vadd(dirr(tang), vshr(dirr(to), 2))), sp);
        }
        f->v = vadd(f->v, vshr(vsub(want, f->v), 1));
        if (chase && !f->cool && d < 8000 && d > 600 && vdot(dirr(f->v), dirr(to)) > 6000) {
            int burst = (f->ai >> 5) + 1;                 /* (three quick shots, then a breath) */
            aim_shot(f->p, me, vel, 170, harm(6), 120);
            f->cool = burst >= 3 ? 80 + sgi_rnd(0, 40) : 7;
            f->ai = (f->ai & 31) | (burst >= 3 ? 0 : burst << 5);
        }
        break;
    }
    case F_COURIER:
        if (f->fl & FL_GONE) {
            f->v = v3(0, 0, 0);
            mobile = 0;
            break;
        }
        if (chase)                                        /* away from the player, and up toward space */
            want = vscale(dirr(vadd(dirr(vsub(f->p, me)), v3(0, 11000, 0))), 80);
        else
            want = vscale(dirr(vadd(vsub(f->home, f->p), v3(0, 1, 0))), 20);
        f->v = vadd(f->v, vshr(vsub(want, f->v), 1));
        if (f->p.y >= SPACE_LO) {
            f->fl |= FL_GONE;
            sgi_note("THE COURIER GOT AWAY!");
        }
        break;
    case F_HULL: {
        const BossDef *b = def_of(f);
        V3 rel = vsub(f->p, f->home);                     /* round its place, the way it faces the way it goes */
        rel.y = 0;
        s32 r = rough_len(rel);
        V3 out = r > 50 ? dirr(rel) : v3(ONE, 0, 0);
        V3 tang = vcross(v3(0, ONE, 0), out);
        want = vadd(vscale(tang, b->rate), vscale(out, (b->orbit - r) / 12));
        want.y = (f->home.y + 250 - f->p.y) / 14;
        f->v = vadd(f->v, vshr(vsub(want, f->v), 1));
        frame_of(f, &fm);                                 /* (once: the guns, and where its parts sit) */
        if (chase && !f->cool && d < 12000) {
            for (int k = -1; k <= 1; k += 2)
                aim_shot(vadd(f->p, mlocal(&fm, v3(k * (b->radius >> 2), -80, b->radius >> 1))), me, vel, 140, harm(5), 200);
            int core = (b->flags & BF_PHASED) && !guards_up(f);
            f->cool = (core ? 38 : 56) - 5 * sgi_tier() + sgi_rnd(0, 12);
        }
        break;
    }
    }
    if (!f->cool)
        f->cool = chase ? 3 : 12;                         /* (ready, but with nothing to shoot at: it thinks again in four ticks, or twelve when the Arwing is far) */
    if (mobile) {
        fly_on(f);
        if (f->kind == F_HULL)
            place_parts(f, i, &fm);
    }
}

/* after the foes: the pods wait their time out, a phased boss tells which phase it is in */
void sgx_tick(void)
{
    sgx_par++;
    if (text_t < 999)
        text_t++;
    for (int i = 0; i < 2; i++)
        if (pods[i].life)
            pods[i].life--;
    const Foe *b = sgx_par & 3 ? 0 : body_of(0);          /* (a phase is told within four ticks) */
    if (b && (def_of(b)->flags & BF_PHASED)) {
        int ph = turrets_up(b) ? 1 : guards_up(b) ? 2 : 3;
        if (ph != last_phase) {
            text_t = 0;
            if (last_phase)
                sgi_note(ph == 2 ? "TURRETS DOWN! NOW THE BAYS" : "BAYS DOWN! THE CORE IS OPEN");
            last_phase = ph;
        }
    }
}

/* ---- destroyed ---- */
void sgx_killed(int i)
{
    Foe *f = &sg_foes[i];
    int tag = f->tag, kind = f->kind, body = is_body(f), pay;
    V3 at = f->p;
    switch (kind) {
    case F_CARRIER: pay = 300; break;
    case F_TURRET: pay = 25; break;
    case F_ACE: pay = 150; break;
    case F_COURIER: pay = 200; break;
    case F_HULL: pay = def_of(f)->hp * 4; break;
    case F_BAY: pay = 40; break;
    default: pay = 40;
    }
    sgi_boom(at, kind == F_CARRIER || kind == F_HULL ? 3 : 1);
    sgi_pay(pay);
    f->kind = F_NONE;
    s2_ev(EV_FOE_DOWN, tag, kind);
    if (!body)
        return;
    for (int k = 0; k < NFOE; k++)                        /* a boss takes what belongs to its mission down with it */
        if (sg_foes[k].kind && sg_foes[k].tag == tag) {
            sgi_boom(sg_foes[k].p, 1);
            sg_foes[k].kind = F_NONE;
        }
    if (kind == F_HULL) {
        sgi_boom(vadd(at, v3(700, 200, 0)), 1);
        sgi_boom(vadd(at, v3(-700, -200, 400)), 1);
    }
    pod_drop(at, tag);
    last_phase = 0;
    sgi_note("BOSS DOWN! ESCAPE POD DROPPED");
}

/* ---- drawing ---- */
/* what a frame can afford is a few models: the nearest foes get theirs, in half-models (a raider, courier, turret or bay 1, an ace 2, the
   carrier or a boss's body 4), the rest, and any that are far, are a lit diamond of their size.
   A model that is drawn costs 12 to 30 thousand cycles, a diamond one or two. */
#define BUDGET 5

static int weight(int kind)
{
    return kind == F_CARRIER || kind == F_HULL ? 4 : kind == F_ACE ? 2 : 1;
}

/* how far off (the three distances added) a foe is still worth its model: where it is about eight pixels across */
static s32 full_range(const Foe *f)
{
    return f->kind == F_HULL ? def_of(f)->radius * 12 : f->kind == F_CARRIER ? 28000 : f->kind == F_TURRET || f->kind == F_BAY ? 3500
         : f->kind == F_RAIDER ? 6500 : 9000;
}

/* what a frame costs depends on the traffic and the city round the Arwing, more than on what is built here: when frames come slower
   than 18 a second (the game ticks a frame has to catch up on tell it) the extras go, by two steps, and come back when they are
   quick again: a fight never drags the game below what it can hold */
u8 sgx_shed;
static u32 fc_last;
static u16 t_avg;                  /* the ticks a frame had, 64 times, averaged over eight frames */

static void governor(void)
{
    u32 t = frame_count - fc_last;
    fc_last = frame_count;
    if (t > 8)
        t = 8;
    t_avg += t * 8 - (t_avg >> 3);
    if (sgx_shed < 1 && t_avg > 208)
        sgx_shed = 1;
    else if (sgx_shed < 2 && t_avg > 216)
        sgx_shed = 2;
    else if (sgx_shed > 1 && t_avg < 212)
        sgx_shed = 1;
    else if (sgx_shed && t_avg < 200)
        sgx_shed = 0;
}

/* a foe's frame, kept while its way (v) is what it was: it is steered one tick in eight, drawn every frame */
static struct { V3 v; M3 m; u8 kind; } fcache[NFOE];

static const M3 *frame_c(const Foe *f)
{
    int i = f - sg_foes;
    if (fcache[i].kind != f->kind || fcache[i].v.x != f->v.x || fcache[i].v.y != f->v.y || fcache[i].v.z != f->v.z) {
        fcache[i].kind = f->kind;
        fcache[i].v = f->v;
        frame_of(f, &fcache[i].m);
    }
    return &fcache[i].m;
}

static APART void put(const Model *md, V3 p, const M3 *m, s32 scale, int *budget, int w)
{
    Place pl;
    V3 d = vsub(p, cam.pos);
    int far = iabs(d.x) > 28000 || iabs(d.y) > 28000 || iabs(d.z) > 28000 ? 2 : 0;
    if (model_place(&pl, p, m, scale, far, md->radius)) {
        model_draw(md, &pl);
        *budget -= w;
    }
}

/* a foe too far or too many for a model: a lit diamond, r units from its middle to a point, never under two pixels */
static APART void blip(V3 p, s32 r, int color)
{
    V3 d = vsub(p, cam.pos);
    if (iabs(d.x) > 28000 || iabs(d.y) > 28000 || iabs(d.z) > 28000)
        return;
    V3 t = r_cam(p);
    if (t.z < 100)
        return;
    if (r < t.z >> 6)
        r = t.z >> 6;
    if (FOCAL * t.x - 121 * t.z > r * FRX || -FOCAL * t.x - 121 * t.z > r * FRX ||
        FOCAL * t.y - 81 * t.z > r * FRY || -FOCAL * t.y - 81 * t.z > r * FRY)
        return;
    V3 q[4] = {{t.x - r, t.y, t.z}, {t.x, t.y + r, t.z}, {t.x + r, t.y, t.z}, {t.x, t.y - r, t.z}};
    r_poly(q, 4, color, -1, 0);
}

static APART void draw_gun(const Foe *f, int *budget, int w)
{
    M3 m;
    myaw(&m, 0);                                       /* (square, and too small to show which way it faces) */
    if (f->kind == F_BAY) {
        myaw(&m, frame_count * 400);
        put(&mdl_pod, f->p, &m, 700, budget, w);
    } else {
        put(&sgm_turret, f->p, &m, 256, budget, w);
    }
}

static APART void draw_foe(const Foe *f, int *budget, int *blips)
{
    const M3 *fm;
    V3 dv = vsub(f->p, cam.pos);
    s32 k = iabs(dv.x) + iabs(dv.y) + iabs(dv.z);
    int w = weight(f->kind);
    u8 hull = model_hull, body = model_body;
    if (*budget < w || k > full_range(f)) {
        if (!is_part(f) && *blips > 0 && (is_body(f) || (k < 14000 && !sgx_shed))) {   /* (a boss's guns are on its hull: no diamonds for them, two at most,
                                                                           and none for what is too far to show as more than a speck) */
            blip(f->p, sgx_radius(f) >> 1, COLOR(is_body(f) ? M_GLOW : M_STUNT, 3, 0));
            (*blips)--;
        }
        return;
    }
    switch (f->kind) {
    case F_RAIDER:
        fm = frame_c(f);
        if (k > 3500) {                                   /* (from afar a dart of four faces) */
            model_body = M_BRICK;
            put(&sgm_wing_lo, f->p, fm, 100, budget, w);
        } else {
            put(&mdl_raider, f->p, fm, 256, budget, w);
        }
        break;
    case F_CARRIER:
        fm = frame_c(f);
        if (k > 5000)
            put(&sgm_hull_lo, f->p, fm, 165, budget, w);
        else
            put(&mdl_carrier, f->p, fm, 256, budget, w);
        break;
    case F_ACE:                                           /* a dark dart with red wings (half the faces of an Arwing) */
        fm = frame_c(f);
        model_body = M_STUNT;
        put(k > 4500 ? &sgm_wing_lo : &sgm_wing, f->p, fm, 120, budget, w);
        break;
    case F_COURIER:
        fm = frame_c(f);
        if (k > 3500) {
            model_body = M_ACCENT;
            put(&sgm_wing_lo, f->p, fm, 140, budget, w);
        } else {
            put(&mdl_carrier, f->p, fm, 190, budget, w);
        }
        break;
    case F_HULL: {
        const BossDef *b = def_of(f);
        model_body = b->trim;
        put(sg_models[b->model + (k > b->radius * 2 ? SM_LO : 0)], f->p, frame_c(f), b->scale, budget, w);   /* (from more than twice its size away: the far shape) */
        break;
    }
    case F_TURRET:
    case F_BAY:
        draw_gun(f, budget, w);
        break;
    }
    model_hull = hull, model_body = body;
}

static APART void draw_pods(void)
{
    M3 m;
    myaw(&m, frame_count * 300);
    for (int i = 0; i < 2; i++)
        if (pods[i].life && sgi_near(pods[i].p, 26000)) {
            int none = 99;
            put(&mdl_pod, pods[i].p, &m, 384, &none, 0);
        }
}

static APART int sort_foes(u8 *order)
{
    s32 key[NFOE];
    int n = 0;
    for (int i = 0; i < NFOE; i++) {                      /* the nearest first: insertion sort on the way in and the way out */
        const Foe *f = &sg_foes[i];
        if (!f->kind)
            continue;
        V3 d = vsub(f->p, cam.pos);
        if (iabs(d.x) >= 34000 || iabs(d.y) >= 34000 || iabs(d.z) >= 34000)
            continue;
        s32 k = is_body(f) ? 0 : iabs(d.x) + iabs(d.y) + iabs(d.z);       /* (a boss's body first, whatever else is near) */
        int j = n++;
        for (; j > 0 && key[j - 1] > k; j--)
            order[j] = order[j - 1], key[j] = key[j - 1];
        order[j] = i, key[j] = k;
    }
    return n;
}

void sgx_draw(void)
{
    u8 order[NFOE];
    governor();
    draw_pods();
    int n = sort_foes(order);
    int budget = sgx_shed > 1 ? BUDGET - 1 : BUDGET, blips = 2;
    for (int j = 0; j < n; j++)
        draw_foe(&sg_foes[order[j]], &budget, &blips);
}

/* ---- the HUD ---- */
static int boss_pct(const Foe *b) { return b->hp <= 0 ? 0 : b->hp * 100 / def_of(b)->hp; }

int sgx_boss_text(char *b)
{
    const Foe *f = body_of(0);
    if (!f || text_t > 150)
        return 0;
    const BossDef *d = def_of(f);
    char *p = b;
    const char *t = d->name;                              /* (its health is the bar's: a letter costs a thousand cycles) */
    int n = 0;
    if (d->flags & BF_PHASED) {
        n = turrets_up(f);
        t = n ? "TURRETS " : (n = guards_up(f)) ? "BAYS " : "CORE OPEN";
    }
    for (; *t; t++)
        *p++ = *t;
    if (n)
        *p++ = '0' + n;
    *p = 0;
    return 1;
}

void sgx_boss_bar(void)
{
    const Foe *f = body_of(0);
    if (!f)
        return;
    int shield = (def_of(f)->flags & BF_PHASED) && guards_up(f);      /* (filled by DMA, a row at a time, four pixels at a go) */
    d_fill(88, 8, 64, 4, COLOR(M_ROAD, 0, 0));
    d_fill(88, 9, boss_pct(f) * 16 / 100 * 4, 2, shield ? COLOR(M_STEEL, 3, 0) : COLOR(M_STUNT, 3, 0));
}

/* ---- the debug mailbox (stage2.h; 48..63 are K's) ---- */
static V3 ahead(int dist_)
{
    s32 h = s2f.heading;
    return v3(s2f.pos.x + (fsin(h) * dist_ >> 14), s2f.pos.y, s2f.pos.z + (fcos(h) * dist_ >> 14));
}

int sg_dbg(int cmd, int arg)
{
    switch (cmd) {
    case 48: {                                            /* SPAWN boss arg, in front of the player */
        V3 p = ahead(7000);
        p.y += 1500;
        return sg_boss_spawn(arg, p, 0x5ff0 + arg);
    }
    case 49: {                                            /* KILL all foes (as the Arwing's shots would): how many */
        int n = 0;
        for (int i = 0; i < NFOE; i++)
            if (sg_foes[i].kind) {
                sg_foes[i].hp = 0;
                sgi_foe_killed(i);
                n++;
            }
        return n;
    }
    case 50:                                              /* foes alive: all (arg 0) or one tag's */
        return arg ? sg_foe_alive(arg) : sgx_foes();
    case 51: {                                            /* SPAWN a foe of kind arg (tag 0x5f00 + kind), a little off the line */
        V3 p = ahead(5000 + 400 * arg);
        p.y += 800;
        return sg_foe_spawn(arg, p, p, 0, 0x5f00 + arg);
    }
    case 52: {                                            /* the boss body's health, -1 if none */
        const Foe *b = body_of(0);
        return b ? b->hp : -1;
    }
    case 56: {                                            /* a hit of arg & 255 on the boss's body (arg >> 8 = 0), a turret (1) or a bay (2), as a shot's:
                                                             -1 shielded, 0 hurt, 1 down, -2 there is none */
        int want = arg >> 8, i;
        for (i = 0; i < NFOE; i++) {
            const Foe *f = &sg_foes[i];
            if (f->kind && FL_BOSS(f) && (want == 0 ? is_body(f) : f->kind == (want == 1 ? F_TURRET : F_BAY)))
                break;
        }
        if (i == NFOE)
            return -2;
        int r = sgx_damage(i, arg & 255);
        if (r > 0)
            sgi_foe_killed(i);
        return r;
    }
    case 57:                                              /* hold (arg bit 0) every tagged foe; how many there are */
        sg_foe_hold(0, arg & 1);
        return sg_foe_alive(0);
    case 58:                                              /* sg_foe_clear(arg), 0 all of the tagged: the foes left */
        sg_foe_clear(arg);
        return sgx_foes();
    case 59:                                              /* sg_foe_escaped(arg) */
        return sg_foe_escaped(arg);
    case 60:                                              /* slot arg's height over the least it may fly (-1 if free; 99999 a fixed part) */
        return sg_foes[arg & 7].kind ? (sg_foes[arg & 7].fl & FL_FIXED ? 99999 : sg_foes[arg & 7].p.y - floor_now(&sg_foes[arg & 7])) : -1;
    case 61:                                              /* the first pod: arg 0 how many there are, 1 2 3 its x y z */
        for (int i = 0; i < 2; i++)
            if (pods[i].life && arg) {
                const s32 *v = &pods[i].p.x;
                return v[arg - 1];
            }
        {
            int n = 0;
            for (int i = 0; i < 2; i++)
                n += pods[i].life != 0;
            return arg ? -1 : n;
        }
    case 53: {                                            /* P12: a tagged Payback vehicle of type arg, 3 cells on from the player */
        pb_spawn_tagged(0x5e00 + (arg & 255), arg, s2f.pos.x * 2 + 3 * 2048, s2f.pos.z * 2);
        return pb_ent_by_tag(0x5e00 + (arg & 255)) != 0;
    }
    case 54: {                                            /* P12: that vehicle: its descriptor number, state << 8, bit 16 its tag is at +0x14c */
        u8 *e = pb_ent_by_tag(0x5e00 + (arg & 255));
        if (!e)
            return -1;
        return (int)PB_DESC_K(*(u32 *)(e + PBE_DESC)) | e[PBE_STATE] << 8 | (*(s32 *)(e + PBE_TAG) == 0x5e00 + (arg & 255)) << 16;
    }
    case 55: {                                            /* P12: pb_kill it: its state after, bit 8 its tag is cleared (-1), -1 if none */
        u8 *e = pb_ent_by_tag(0x5e00 + (arg & 255));
        if (!e)
            return -1;
        pb_kill(0x5e00 + (arg & 255));
        return e[PBE_STATE] | (*(s32 *)(e + PBE_TAG) == -1) << 8;
    }
    }
    return -1;
}
