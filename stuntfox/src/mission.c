/* The mission engine (mission.h). One mission runs at a time, a list of objectives from the blob. Every
   frame ms_tick looks at where the player is (s2f), what Payback's goal list says (a phone mission on?), the
   clock (30 a second: the time all limits are in) and the events ms_ev was given, and moves the mission on.
   Nothing here prints on Payback's ticker: titles are its raw banner, the steady line is hudline.c's.

   Payback's arrow (probe P4, measured and read from the goal code at 0x0807aa3c): a goal of kind 4 whose floor
   is 0x7f and whose marker byte is 0 is put on the arrow's list (by its kind) and never reached (the floor is
   never the man's), and its marker path, which writes into the cell's record by floor, is not taken. Phones
   (kind 1) are on that list whatever their marker byte is (probe P7: it is 0 for them too), so the arrow is
   ours only while no green phone rings; with one ringing it is Payback's own, and our beacon and the line's
   bearing say where to go. */
#include "stage2.h"
#include "mission.h"
#include "hudline.h"

#define WEAK __attribute__((weak))

MisRun ms_run;
static const S2Head *H;            /* the blob, once checked */
static u8 H_state;                 /* 0 not looked at, 1 good, 2 none */
static s32 last_clk;
static s32 cur_dt;                 /* Payback ticks since the last tick of ours, 0..8 */
static u16 act_mis;                /* the act the campaign armed, + 1 (a challenge's beacon may stand in for it a while) */
static u16 demo_act;               /* the map's first act + 1 while no campaign has armed one: its beacon shows within ACT_ROAM_CELLS */
static u16 arrow_at;               /* the MsPlace + 1 our goal marks */
static u8 goal_seq;
static u8 roam_off;                /* (debug: no roaming, so a harness has a control run) */
static u8 g_busy, g_ring;          /* Payback's goal list now: a mission (not a phone) is on; a green phone rings */
static char hud_buf[24];
static s32 ban_at;                 /* PB_CLOCK when the last banner went up */
static u16 hold_mis;               /* the challenge just finished, + 1: its beacon stays off until the player has left it */

#define TAG_BASE 0x5000
#define GOAL_ID 0x5000             /* our arrow goals: GOAL_ID + 0..255 */
#define MS_SPACE_Y 12000           /* above this the Arwing is in space (physics.h's SPACE_LO) */
#define FLOOR_NEVER 0x7f           /* a floor no one stands on */
#define NTAG 6                     /* tagged Payback spawns alive at once */
#define ROAM_CELLS 10
#define ROAM_PER_TICK 2            /* missions the roam scan looks at a tick (a map's 30 or so: a beacon armed within 15 ticks of coming in range) */
#define ACT_ROAM_CELLS 4           /* the act of a campaign-less map is shown only this near: an act standing armed costs a line and a beacon every frame */
#define BAN_TICKS 220              /* a title banner is on the card's rows this long (measured: letters in at tick 22, out by 216) */
#define HL_RANGE 48                /* the armed line says where the beacon is within this many cells; farther it is off (a line is ~3.5k cycles) */
#define TICKS 30
#define CELL_U 1024

static inline s32 ab(s32 v) { return v < 0 ? -v : v; }

/* ---- the blob ---- */
static void validate(void)
{
    const S2Head *h = (const S2Head *)s2_blob;
    H_state = 2;
    H = 0;
    if (((unsigned long)h & 3) || h->magic != S2_MAGIC || h->ver != S2_VER || h->size < sizeof(S2Head) || h->size > 0x1000000)
        return;
    u32 sz = h->size;
    if (h->off_chap > sz || h->off_mis > sz || h->off_obj > sz || h->off_place > sz || h->off_text > sz)
        return;
    if (h->off_chap + h->nchap * sizeof(Chapter) > sz || h->off_mis + h->nmis * sizeof(MisDef) > sz ||
        h->off_obj + h->nobj * sizeof(MisObj) > sz || h->off_place + h->nplace * sizeof(MsPlace) > sz ||
        h->off_text + h->ntext * 2u > sz)
        return;
    if ((h->off_chap | h->off_mis | h->off_obj | h->off_place) & 3 || h->off_text & 1)
        return;
    const MisObj *ob = (const MisObj *)((const u8 *)h + h->off_obj);
    for (int i = 0; i < h->nobj; i++)             /* (the ghost and the HUD hold at most 16 checkpoints or rings) */
        if ((ob[i].op == OP_RACE || ob[i].op == OP_CHECK || ob[i].op == OP_RINGS) && ob[i].n > 16)
            return;
    H = h;
    H_state = 1;
}

const MisDef *ms_def(int i) { return H && (unsigned)i < H->nmis ? (const MisDef *)((const u8 *)H + H->off_mis) + i : 0; }
const Chapter *ms_chap(int i) { return H && (unsigned)i < H->nchap ? (const Chapter *)((const u8 *)H + H->off_chap) + i : 0; }
const MsPlace *ms_place(int i) { return H && (unsigned)i < H->nplace ? (const MsPlace *)((const u8 *)H + H->off_place) + i : 0; }
const MisObj *ms_obj(int i) { return H && (unsigned)i < H->nobj ? (const MisObj *)((const u8 *)H + H->off_obj) + i : 0; }
int ms_count(void) { return H ? H->nmis : 0; }
int ms_nchap(void) { return H ? H->nchap : 0; }

const char *ms_text(int id)
{
    if (!H || (unsigned)id >= H->ntext)
        return "";
    const u8 *t = (const u8 *)H + H->off_text;
    u32 off = ((const u16 *)t)[id];
    return off < H->size - H->off_text ? (const char *)t + off : "";
}

/* what the engine asks the other packages for: nothing, until one has it */
WEAK void sg_give(int credits) { (void)credits; }
WEAK int sg_foe_near(V3 p, s32 r, int tag) { (void)p; (void)r; (void)tag; return 0; }
WEAK int cp_mis_done(int mis) { (void)mis; return 0; }
WEAK void cp_unlock(int what) { (void)what; }
WEAK void cp_set(int flag, int value) { (void)flag; (void)value; }

/* ---- places and the player ---- */
static V3 wpos(const MsPlace *p)
{
    s32 ox, oy;
    pb_window_origin(&ox, &oy);
    return v3((p->x8 + ox) * 128, p->h, (p->y8 + oy) * 128);
}
static s32 rad(const MsPlace *p, s32 dflt) { return p->r8 ? p->r8 * 128 : dflt; }

/* a within r of b on the ground plane (a circle), and within tol of its height */
static int in_r(V3 a, V3 b, s32 r)
{
    s32 dx = ab(a.x - b.x), dz = ab(a.z - b.z);
    return dx <= r && dz <= r && (u32)(dx * dx) + (u32)(dz * dz) <= (u32)(r * r);
}
static int at_place(const MsPlace *p, s32 dflt, s32 tol)
{
    if (!p)
        return 0;
    V3 c = wpos(p);
    return in_r(s2f.pos, c, rad(p, dflt)) && ab(s2f.pos.y - c.y) <= tol;
}
static int mode_ok(int m) { return m == 0 || s2f.mode == m - 1; }

/* a zone: two corners in consecutive places; its cells and its rectangle in units */
static void box(int pi, s32 *x0, s32 *z0, s32 *x1, s32 *z1)
{
    const MsPlace *a = ms_place(pi), *b = ms_place(pi + 1);
    if (!a || !b) {
        *x0 = *z0 = 1;
        *x1 = *z1 = 0;
        return;
    }
    s32 ox, oy;
    pb_window_origin(&ox, &oy);
    s32 ax = (a->x8 + ox) * 128, bx = (b->x8 + ox) * 128, az = (a->y8 + oy) * 128, bz = (b->y8 + oy) * 128;
    *x0 = ax < bx ? ax : bx;
    *x1 = ax < bx ? bx : ax;
    *z0 = az < bz ? az : bz;
    *z1 = az < bz ? bz : az;
}
static int in_box(int pi, V3 p)
{
    s32 x0, z0, x1, z1;
    box(pi, &x0, &z0, &x1, &z1);
    return p.x >= x0 && p.x <= x1 && p.z >= z0 && p.z <= z1;
}

/* through a ring's plane since the last call: *side is the side last seen (0: none yet).
   1: through the ring, -1: across its plane near it but outside it, 0: no */
static int crossed(const MsPlace *p, V3 a, s32 *side)
{
    V3 c = wpos(p);
    s32 d, l1, l2;
    if (p->kind == PK_RING_X)
        d = a.x - c.x, l1 = a.y - c.y, l2 = a.z - c.z;
    else if (p->kind == PK_RING_H)
        d = a.y - c.y, l1 = a.x - c.x, l2 = a.z - c.z;
    else
        d = a.z - c.z, l1 = a.x - c.x, l2 = a.y - c.y;
    s32 s = d < 0 ? -1 : 1;
    if (!*side) {
        *side = s;
        return 0;
    }
    if (s == *side)
        return 0;
    *side = s;
    s32 r = rad(p, 1536);
    l1 = ab(l1), l2 = ab(l2);
    if (l1 <= r && l2 <= r && (u32)(l1 * l1) + (u32)(l2 * l2) <= (u32)(r * r))
        return 1;
    return l1 <= 3 * r && l2 <= 3 * r ? -1 : 0;
}

/* the compass point (0 N, 2 E ..) and the distance in cells from the player to p (north is down the grid's y) */
static void bearing(V3 to, int *dir, int *cells)
{
    s32 dx = to.x - s2f.pos.x, nz = s2f.pos.z - to.z, ax = ab(dx), az = ab(nz);
    int d;
    if (az * 1000 < ax * 414)
        d = dx > 0 ? 2 : 6;
    else if (ax * 1000 < az * 414)
        d = nz > 0 ? 0 : 4;
    else if (nz > 0)
        d = dx > 0 ? 1 : 7;
    else
        d = dx > 0 ? 3 : 5;
    s32 far = (ax > az ? ax + (az >> 1) : az + (ax >> 1)) >> 10;
    *dir = d;
    *cells = far > 999 ? 999 : far;
}

/* ---- Payback's goal list ---- */
static void scan_goals(void)
{
    int n = PB_NGOALS;
    if (n < 0 || n > PB_NGOAL_MAX)
        n = 0;
    g_busy = g_ring = 0;
    for (int i = 0; i < n; i++) {
        s32 kind = *pb_goal_w(i, PBG_KIND), id = *pb_goal_w(i, PBG_ID);
        if (kind == PBG_PHONE)
            g_ring = 1;
        if (kind != PBG_LEVEL && kind != PBG_PHONE && kind != PBG_PHONE_RED && kind != PBG_HIDDEN_PICKUP &&
            !(id >= GOAL_ID && id < GOAL_ID + 256))
            g_busy = 1;
    }
}

static void drop_goal(void)
{
    MisRun *r = &ms_run;
    if (r->goal)
        pb_goal_remove(r->goal);
    r->goal = 0;
    arrow_at = 0;
}

/* put our goal on the MsPlace pi; not on a cell the grid has a copy of in RAM (the marker code looks at the
   cell's record by floor), and not off the grid */
static void push_goal(int pi)
{
    MisRun *r = &ms_run;
    const MsPlace *p = ms_place(pi);
    if (!p)
        return;
    V3 w = wpos(p);
    int cx = w.x >> 10, cz = w.z >> 10;
    if ((unsigned)cx >= 128 || (unsigned)cz >= 128 || !PB_IN_ROM(pb_col(cx, cz)))
        return;
    r->goal = GOAL_ID + goal_seq++;
    pb_goal_add(r->goal, PBG_GOTO, w.x * 2, w.z * 2, FLOOR_NEVER, 0);
    arrow_at = pi + 1;
}

int ms_target(void)
{
    MisRun *r = &ms_run;
    if (r->state != MS_RUN && r->state != MS_PAUSED)
        return -1;
    const MisObj *o = ms_obj(r->obj);
    if (!o || (o->flags & MO_HIDDEN))
        return -1;
    int n = o->n;
    switch (o->op) {
    case OP_GOTO: case OP_LAND: case OP_DEFEND:
        return o->place;
    case OP_CHECK: case OP_RACE:
        return n ? o->place + r->count % n : -1;
    case OP_RINGS:
        return r->count < n ? o->place + r->count : -1;
    case OP_DELIVER:
        return n ? o->place + (r->count < n ? r->count : n - 1) : -1;
    case OP_ESCORT:
        return o->place + 1;
    case OP_COLLECT: case OP_CRATES:
        if (o->op == OP_CRATES && r->carry)
            return o->b;
        for (int i = 0; i < n && i < 32; i++)
            if (!(r->v[1] >> i & 1))
                return o->place + i;
        return -1;
    }
    return -1;
}

static void arrow_sync(void)
{
    MisRun *r = &ms_run;
    int want = r->state == MS_RUN && !g_ring ? ms_target() : -1;
    if (want < 0) {
        drop_goal();
        return;
    }
    if (r->goal && arrow_at == want + 1)
        return;
    drop_goal();
    push_goal(want);
}

/* ---- text ---- */
static void banner(const char *s)
{
    char b[PB_BANNER_LEN + 1];
    int i = 0;
    while (i < PB_BANNER_LEN && s[i])
        b[i] = s[i], i++;
    b[i] = 0;
    if (i) {
        pb_banner_raw(0, b);
        ban_at = s2f.clock;
    }
}

/* a card, once a banner that went up just before it has gone (its letters fly across the card's rows) */
static void card(const char *s)
{
    s32 d = ban_at + BAN_TICKS - s2f.clock;
    hl_card(s, d > 0 && d <= BAN_TICKS ? d : 0);
}

/* ---- tagged spawns ---- */
static void untag(int tag)                          /* the entities with this tag become the street's again */
{
    for (int k = 0; k < 4; k++) {
        u8 *e = pb_ent_by_tag(tag);
        if (!e)
            return;
        *(s32 *)(e + PBE_TAG) = -1;
    }
}
static int spawn(int i, const MsPlace *p, int type)
{
    MisRun *r = &ms_run;
    if (i >= NTAG || !p)
        return 0;
    V3 w = wpos(p);
    untag(r->tag + i);                              /* (a second spawn on the same slot lets the first go: one entity a tag) */
    pb_spawn_tagged(r->tag + i, type, w.x * 2, w.z * 2);
    if (!pb_ent_by_tag(r->tag + i))
        return 0;
    r->spawned |= 1 << i;
    return 1;
}
static int dead(const u8 *e)
{
    if (!e)
        return 1;
    int st = e[PBE_STATE];
    return *(const s16 *)(e + PBE_HEALTH) <= 0 || (st >= 5 && st <= 7 && PB_DESC_K(*(const u32 *)(e + PBE_DESC)) < 18);
}
static V3 epos(const u8 *e) { return v3(*(const s32 *)(e + PBE_X) >> 1, 0, *(const s32 *)(e + PBE_Y) >> 1); }

/* ---- the run ---- */
static void clear_run(void)
{
    MisRun *r = &ms_run;
    u8 ap = r->ap, nd = r->ndone, nf = r->nfail;
    u16 rr = r->rr;
    for (u8 *p = (u8 *)r; p < (u8 *)r + sizeof *r; p++)          /* (bytes: a wider store may be moved past the field stores below) */
        *p = 0;
    r->mis = 0xffff;
    r->ap = ap, r->ndone = nd, r->nfail = nf, r->rr = rr;
}

/* everything of ours that Payback or K holds for the mission goes: the arrow's goal, the foes, the held
   foes, the tags (the entities become the street's again, not wrecks: pb_kill is the one thing in Payback's
   image nothing calls, and one under the player's own car would blow it) */
static void cleanup(void)
{
    MisRun *r = &ms_run;
    drop_goal();
    if (r->mis != 0xffff && (r->spawned || r->tag)) {
        sg_foe_clear(r->tag);
        for (int i = 0; i < NTAG; i++)
            if (r->spawned >> i & 1)
                untag(r->tag + i);
        r->spawned = 0;
    }
    r->flags &= ~RF_HELD;
    hl_clear();
}

void ms_abort(void)
{
    MisRun *r = &ms_run;
    if (!H)
        return;
    if (r->state == MS_RUN || r->state == MS_PAUSED)
        cleanup();
    else
        hl_clear();
    act_mis = 0;
    r->state = MS_IDLE;
    r->mis = 0xffff;
    r->flags = 0;
}

int ms_state(void) { return ms_run.state; }
int ms_current(void)
{
    int s = ms_run.state;
    return s == MS_ARMED || s == MS_RUN || s == MS_PAUSED ? ms_run.mis : -1;
}
int ms_retries(void) { return ms_run.retries; }

static int group_end(int i)
{
    const MisDef *d = ms_def(ms_run.mis);
    int end = d->obj0 + d->nobj;
    for (int k = i + 1; k < end; k++)
        if (ms_obj(k)->op == OP_ENDGROUP)
            return k;
    return end;
}

/* the objective at r->obj begins: its own set-up, its line, its arrow */
static void begin(void)
{
    MisRun *r = &ms_run;
    const MisDef *d = ms_def(r->mis);
    const MisObj *o = ms_obj(r->obj);
    const MsPlace *p = ms_place(o->place);
    r->count = r->need = 0;
    r->pts = 0;                                     /* (a STUNT counts the points made since it began, not an earlier one's) */
    r->v[0] = r->v[1] = r->v[2] = 0;
    r->carry = 0;
    r->group = 0;
    r->dwell = 0;
    r->t_step = s2f.clock;
    r->score0 = pb_get_score();
    r->need = s2_phones;
    if (o->flags & MO_CKPT)
        r->ckpt = r->obj - d->obj0 + 1;
    if (o->text)
        hl_text(ms_text(o->text));
    switch (o->op) {
    case OP_CHECK:
        if (o->b)
            r->v[2] = o->b * TICKS;
        break;
    case OP_CHASE:
        spawn(0, p, o->a);
        r->v[0] = r->spawned & 1;
        break;
    case OP_DESTROY: {
        int n = o->n < NTAG ? o->n : NTAG;
        for (int i = 0; i < n; i++)
            if (spawn(i, ms_place(o->place + i), o->a))
                r->v[0] |= 1 << i;
        r->v[1] = ((1 << n) - 1) & ~r->v[0];       /* (a spawn that failed counts as done: nothing to wait for) */
        break;
    }
    case OP_FOES: {
        static const s16 at[8][2] = {{0, 0}, {600, 0}, {-600, 0}, {0, 600}, {0, -600}, {450, 450}, {-450, 450}, {450, -450}};
        V3 w = p ? wpos(p) : s2f.pos;
        int up = 0;
        for (int i = 0; i < o->n && i < 8; i++)
            if (sg_foe_spawn(o->a, v3(w.x + at[i][0], w.y, w.z + at[i][1]), w, o->b, r->tag) >= 0)
                up++;
        r->v[0] = up;
        break;
    }
    case OP_BOSS:
        r->v[0] = p && sg_boss_spawn(o->a, wpos(p), r->tag) >= 0;
        break;
    case OP_ESCORT:
        r->v[0] = spawn(0, p, o->a);
        break;
    case OP_DEFEND:
        r->count = o->a;
        r->v[0] = o->b * TICKS;
        break;
    case OP_TALK:
        if (!s2f.docked)
            card(ms_text(o->text));
        break;
    case OP_BRIEF:
        if (o->a)
            banner(ms_text(o->a));
        card(ms_text(o->text));
        break;
    case OP_CARD:
        card(ms_text(o->text));
        break;
    case OP_TIMER:
        r->timer = o->b * TICKS;
        break;
    case OP_ENDTIMER:
        r->timer = 0;
        break;
    case OP_SPAWNVEH:
        spawn(1, p, o->a);
        break;
    case OP_CEIL:
        r->ceil_h = o->a;
        r->ceil_zone = o->place + 1;
        break;
    case OP_ZONE:
        r->zone = o->place + 1;
        break;
    case OP_GIVE:
        sg_give(o->a);
        break;
    case OP_UNLOCK:
        cp_unlock(o->a);
        break;
    case OP_SET:
        cp_set(o->a, o->b);
        break;
    case OP_GATEWAY:
        bigmap_enter(o->a);
        break;
    }
}

static void begin_mission(int mis, int obj)
{
    MisRun *r = &ms_run;
    u8 retries = r->mis == mis ? r->retries : 0, ckpt = r->mis == mis ? r->ckpt : 0;
    int resume = obj != ms_def(mis)->obj0;
    if (r->state == MS_RUN || r->state == MS_PAUSED)
        cleanup();
    clear_run();
    r->mis = mis;
    r->retries = retries;
    r->ckpt = resume ? ckpt : 0;
    r->tag = TAG_BASE + mis * 8;
    r->state = MS_RUN;
    r->obj = obj;
    r->t_start = r->t_step = s2f.clock;
    if (act_mis == mis + 1)                         /* (the act itself began; a challenge in the meantime leaves it armed for after) */
        act_mis = 0;
    hl_clear();
    if (!resume)
        banner(ms_text(ms_def(mis)->title));
    begin();
}

void ms_start(int mis)
{
    if (!H || !ms_def(mis) || !ms_def(mis)->nobj)
        return;
    begin_mission(mis, ms_def(mis)->obj0);
}

static void arm(int mis, int roam)
{
    MisRun *r = &ms_run;
    const MisDef *d = ms_def(mis);
    if (!d || d->start == NOPLACE || !ms_place(d->start))
        return;
    u8 retries = r->mis == mis ? r->retries : 0;
    u8 ckpt = r->mis == mis ? r->ckpt : 0;
    if (r->state == MS_RUN || r->state == MS_PAUSED)
        return;
    clear_run();
    r->mis = mis;
    r->retries = retries;
    r->ckpt = ckpt;
    r->state = MS_ARMED;
    r->flags = roam ? RF_ROAM : 0;
    if (!roam)
        act_mis = mis + 1;
}

void ms_arm(int mis)
{
    if (H)
        arm(mis, 0);
}

/* finished: the goals and the foes go, the banner says how it went, and (done) the score and credits are paid;
   a failed one is armed again, at its last checkpoint or its start */
static void finish(int ok)
{
    MisRun *r = &ms_run;
    const MisDef *d = ms_def(r->mis);
    int kind = d->kind, mis = r->mis;
    if (kind == MK_CHAL || kind == MK_MEDAL)
        hold_mis = mis + 1;                         /* (standing in its beacon after must not start it again and pay twice) */
    s32 secs = (s2f.clock - r->t_start) / TICKS;
    if (secs < 0) secs = 0;
    if (secs > 0xffff) secs = 0xffff;
    cleanup();
    r->state = ok ? MS_DONE : MS_FAIL;
    if (ok) {
        banner(kind == MK_MEDAL ? "MEDAL FOUND" : kind == MK_CHAL ? "CHALLENGE DONE" : "ACT COMPLETE");
        int m = PB_MULT;
        if (m < 1) m = 1;
        if (d->score)
            pb_add_score(d->score * 100 / m);
        if (d->pay)
            sg_give(d->pay);
        if (r->ndone < 255) r->ndone++;
        if (d->flags & MS_REPEAT)                   /* (a repeatable act stands armed again unless the campaign arms another) */
            act_mis = mis + 1;
        s2_ev(EV_MIS_DONE, mis, secs);
        return;
    }
    banner(kind == MK_MEDAL ? "MEDAL MISSED" : kind == MK_CHAL ? "CHALLENGE FAILED" : "ACT FAILED");
    if (r->nfail < 255) r->nfail++;
    if (r->retries < 255) r->retries++;
    s2_ev(EV_MIS_FAIL, mis, secs);
    if (r->state != MS_FAIL)
        return;                                    /* (the campaign took it: armed something else) */
    if (d->start != NOPLACE && (kind == MK_ACT || kind == MK_CONTRACT)) {
        u8 ck = r->ckpt;                           /* (arm keeps it) */
        arm(mis, 0);
        card("RETRY: GO TO THE BEACON");
        /* in the Arwing it is put back at a start that is not a ring (a ring starts it by flying through) */
        const MsPlace *p = ms_place(ck ? ms_obj(d->obj0 + ck - 1)->place : d->start);
        if (p && s2f.mode == FLY && (p->kind < PK_RING_X || p->kind > PK_RING_H))
            s2_put_player(wpos(p), 0, FLY);
    } else {
        r->state = MS_IDLE;
        r->mis = 0xffff;
    }
}

/* the next objective, or the end */
static void next_obj(void)
{
    MisRun *r = &ms_run;
    const MisDef *d = ms_def(r->mis);
    const MisObj *o = ms_obj(r->obj);
    int nxt = o->op == OP_GROUP ? group_end(r->obj) + 1 : r->obj + 1;
    if (nxt >= d->obj0 + d->nobj) {
        finish(1);
        return;
    }
    r->obj = nxt;
    begin();
}

/* ---- the objectives: 1 done, 0 not yet, -1 failed, 2 finish the mission. member: inside a GROUP, with a scratch of its own ---- */
static int eval(const MisObj *o, int member)
{
    MisRun *r = &ms_run;
    const MisDef *d = ms_def(r->mis);
    u16 lc = 0;
    s32 lv[3] = {0, 0, 0};
    u16 *cnt = member ? &lc : &r->count;
    s32 *v = member ? lv : r->v;
    const MsPlace *p = ms_place(o->place);
    V3 me = s2f.pos;
    s32 tol = o->a > 0 ? o->a : 512;
    int n = o->n;
    s32 el = s2f.clock - r->t_step;
    switch (o->op) {
    case OP_NOP: case OP_TIMER: case OP_ENDTIMER: case OP_CARD: case OP_BRIEF: case OP_SPAWNVEH: case OP_CEIL: case OP_ZONE:
    case OP_GIVE: case OP_UNLOCK: case OP_SET: case OP_GATEWAY: case OP_ENDGROUP:
        return 1;                                  /* (their work is done as they begin) */
    case OP_FINISH:
        return 2;
    case OP_GOTO:
        return p && mode_ok(o->mode) && at_place(p, 1024, tol);
    case OP_CHECK: case OP_RACE: {
        int total = o->op == OP_RACE ? n * (o->b > 0 ? o->b : 1) : n;
        if (o->op == OP_CHECK && o->b && !member) {
            v[2] -= cur_dt;
            if (v[2] <= 0)
                return -1;
        }
        if (n && mode_ok(o->mode) && at_place(ms_place(o->place + *cnt % n), 1024, 1024))
            ++*cnt;
        return *cnt >= total;
    }
    case OP_RINGS: {
        if (*cnt >= n)
            return 1;
        int c = crossed(ms_place(o->place + *cnt), me, &v[0]);
        if (c > 0) {
            ++*cnt;
            v[0] = 0;
        } else if (c < 0 && (o->flags & MO_STRICT)) {
            return -1;
        }
        return *cnt >= n;
    }
    case OP_LAND: {
        if (s2f.mode == FLY)
            v[0] |= 2;
        if (s2f.mode == FLY || s2f.airborne)
            v[0] |= 1;
        if (!p || !at_place(p, 1536, tol))
            return 0;
        return (s2f.mode == FOOT && (v[0] & 2)) || (s2f.mode != FOOT && !s2f.airborne && (v[0] & 1) && s2f.speed < 600);
    }
    case OP_ENTER:
        return mode_ok(o->mode) && (!o->a || s2f.veh == o->a);
    case OP_DELIVER: {
        if (r->carry && (d->flags & FF_VEHLOST) && o->mode && !mode_ok(o->mode))
            return -1;
        if (n && mode_ok(o->mode) && at_place(ms_place(o->place + *cnt), 1024, 1024)) {
            if (++*cnt == 1)
                r->carry = 1;
        }
        return *cnt >= n;
    }
    case OP_CHASE: {
        const u8 *e = pb_ent_by_tag(r->tag);
        if (!e || dead(e))
            return v[0] ? 1 : 0;                   /* (gone: done, if it was ever up) */
        if (p && in_r(me, epos(e), rad(p, 2048)))
            *cnt += cur_dt;
        else
            *cnt = 0;
        return *cnt >= (o->b > 0 ? o->b : 90);
    }
    case OP_DESTROY: {
        int k = n < NTAG ? n : NTAG;
        v[2] += cur_dt;
        if (v[2] >= 8) {                           /* (the entity list is long: not every tick) */
            v[2] = 0;
            for (int i = 0; i < k; i++)
                if ((v[0] >> i & 1) && !(v[1] >> i & 1) && dead(pb_ent_by_tag(r->tag + i)))
                    v[1] |= 1 << i;
        }
        return (v[1] & ((1 << k) - 1)) == (1 << k) - 1;
    }
    case OP_BLAST:
        return *cnt >= n;
    case OP_FOES:
        return (!v[0] || (el >= 5 && !sg_foe_alive(r->tag)));
    case OP_BOSS:
        return !v[0] || (el >= 5 && !sg_boss_alive(r->tag));
    case OP_ESCORT: {
        const u8 *e = pb_ent_by_tag(r->tag);
        const MsPlace *q = ms_place(o->place + 1);
        if (!v[0] || !q)
            return 1;                              /* (nothing came up: nothing to escort) */
        if (dead(e))
            return -1;
        return in_r(epos(e), wpos(q), rad(q, 2048));
    }
    case OP_DEFEND: {
        int foes = p ? sg_foe_near(wpos(p), rad(p, 3072), r->tag) : 0;
        v[0] -= cur_dt;
        v[1] += foes * cur_dt;
        while (v[1] >= TICKS) {
            v[1] -= TICKS;
            if (r->count)
                r->count--;
        }
        if (!r->count)
            return -1;
        return v[0] <= 0;
    }
    case OP_COLLECT: {
        if (!mode_ok(o->mode))
            return 0;
        for (int i = 0; i < n && i < 32; i++)
            if (!(v[1] >> i & 1) && at_place(ms_place(o->place + i), 768, 1024)) {
                v[1] |= 1 << i;
                ++*cnt;
            }
        return *cnt >= n;
    }
    case OP_CRATES: {
        if (!r->carry) {
            for (int i = 0; i < n && i < 32; i++)
                if (!(v[1] >> i & 1) && at_place(ms_place(o->place + i), 768, 1024)) {
                    v[1] |= 1 << i;
                    r->carry = 1;
                    break;
                }
        } else if (ms_place(o->b) && at_place(ms_place(o->b), 1024, 1024)) {
            r->carry = 0;
            ++*cnt;
        }
        return *cnt >= n;
    }
    case OP_STUNT:
        return r->pts >= o->a;
    case OP_JUMP:
        return (r->evm & EVM_JUMP) != 0;
    case OP_SCORE:
        return pb_get_score() - r->score0 >= o->a * 100;
    case OP_WANTED:
        if (pb_wanted(s2f.me) >= o->a)
            *cnt += cur_dt;
        else
            *cnt = 0;
        return *cnt >= o->b * TICKS;
    case OP_PHONE:
        return (u16)(s2_phones - r->need) >= n;
    case OP_SURVIVE:
        if (r->evm & EVM_DEATH)
            *cnt = 0;
        else
            *cnt += cur_dt;
        return *cnt >= o->b * TICKS;
    case OP_SPACE:
        return (r->evm & EVM_SPACE) || me.y > MS_SPACE_Y;
    case OP_DOCK:
        return s2f.docked || (r->evm & EVM_DOCK);
    case OP_TALK:
        return s2f.docked ? (r->evm & EVM_TALK) != 0 : el >= HL_CARD_TICKS;
    case OP_WAIT:
        return el >= o->b;
    case OP_GROUP: {
        int end = group_end(r->obj), k = 0, all = 1;
        for (int i = r->obj + 1; i < end && k < 16; i++, k++) {
            if (r->group >> k & 1)
                continue;
            int res = eval(ms_obj(i), 1);
            if (res < 0)
                return -1;
            if (res == 1)
                r->group |= 1 << k;
            else {
                all = 0;
                if (o->flags & MO_ORDER)
                    break;
            }
        }
        return all;
    }
    }
    return 1;
}

/* the line's status: the shortest clock running, else the count */
static void hud_sync(void)
{
    MisRun *r = &ms_run;
    const MisDef *d = ms_def(r->mis);
    const MisObj *o = ms_obj(r->obj);
    s32 left = -1;
    if (r->timer)
        left = r->timer;
    if ((d->flags & FF_TIME) && d->par) {
        s32 l = d->par * TICKS - (s2f.clock - r->t_start);
        if (left < 0 || l < left)
            left = l;
    }
    int n = o->n, c = r->count, of = n, hp = 0;
    switch (o->op) {
    case OP_CHECK:
        if (o->b && (left < 0 || r->v[2] < left))
            left = r->v[2];
        break;
    case OP_RACE:
        of = n * (o->b > 0 ? o->b : 1);
        break;
    case OP_SURVIVE: case OP_WANTED:
        if (o->b && (left < 0 || o->b * TICKS - c < left))
            left = o->b * TICKS - c;
        of = 0;
        break;
    case OP_DESTROY:
        of = n < NTAG ? n : NTAG;
        c = 0;
        for (int i = 0; i < of; i++)
            c += r->v[1] >> i & 1;
        break;
    case OP_DEFEND:
        hp = 1;
        of = 0;
        break;
    case OP_RINGS: case OP_COLLECT: case OP_CRATES: case OP_BLAST:
        break;
    default:
        of = 0;
    }
    int t = g_ring ? ms_target() : -1;              /* (a ringing phone has the arrow: the line says where instead) */
    if (hp)
        hl_stat(HLS_HP, c, 0);
    else if (left >= 0)
        hl_stat(HLS_TIME, (left + TICKS - 1) / TICKS, 0);
    else if (t >= 0 && ms_place(t)) {
        int dir, cells;
        bearing(wpos(ms_place(t)), &dir, &cells);
        hl_stat(HLS_BEAR, dir, cells);
    } else if (of > 1)
        hl_stat(HLS_COUNT, c, of);
    else
        hl_stat(HLS_NONE, 0, 0);
}

static void pause_run(void)
{
    MisRun *r = &ms_run;
    drop_goal();
    sg_foe_hold(r->tag, 1);
    r->flags |= RF_HELD;
    r->state = MS_PAUSED;
    hl_text("PAUSED: PHONE JOB");
    hl_stat(HLS_NONE, 0, 0);
}

static void run_tick(void)
{
    MisRun *r = &ms_run;
    const MisDef *d = ms_def(r->mis);
    const MisObj *o = ms_obj(r->obj);
    if (!d || !o) {
        ms_abort();
        return;
    }
    if (g_busy && !(d->flags & MF_PHONE)) {         /* a phone mission has the arrow, the HUD and the player */
        pause_run();
        return;
    }
    if (r->evm & EVM_FAIL) {
        finish(0);
        return;
    }
    if ((r->evm & EVM_DEATH) && (d->flags & FF_DEATH)) {
        finish(0);
        return;
    }
    if ((d->flags & FF_TIME) && d->par && s2f.clock - r->t_start >= d->par * TICKS) {
        finish(0);
        return;
    }
    if (r->timer) {
        r->timer -= cur_dt;
        if (r->timer <= 0) {
            finish(0);
            return;
        }
    }
    int alive = PB_RESPAWN <= 0;                    /* (while he is brought back his place is not his own) */
    if (alive && r->zone && !in_box(r->zone - 1, s2f.pos)) {
        finish(0);
        return;
    }
    if (alive && r->ceil_zone && s2f.pos.y > r->ceil_h && in_box(r->ceil_zone - 1, s2f.pos)) {
        finish(0);
        return;
    }
    int force = (r->evm & EVM_FORCE) || (r->ap && s2f.clock - r->t_step >= TICKS);
    for (int guard = 0; alive && guard < 16 && r->state == MS_RUN; guard++) {
        o = ms_obj(r->obj);
        int res = force ? 1 : eval(o, 0);
        force = 0;
        if (res < 0) {
            finish(0);
            return;
        }
        if (res == 2) {
            finish(1);
            return;
        }
        if (!res)
            break;
        next_obj();
    }
    if (r->state != MS_RUN)
        return;
    arrow_sync();
    hud_sync();
}

/* ---- the start beacon ---- */
static const MsPlace *start_place(void)
{
    MisRun *r = &ms_run;
    const MisDef *d = ms_def(r->mis);
    if (!d)
        return 0;
    if (r->ckpt)
        return ms_place(ms_obj(d->obj0 + r->ckpt - 1)->place);
    return ms_place(d->start);
}

static int start_ok(const MisDef *d)
{
    if (s2f.docked || PB_RESPAWN > 0 || sg_job_active())
        return 0;
    if (g_busy && !(d->flags & MF_PHONE))
        return 0;
    int f = d->flags & (MS_FOOT | MS_DRIVE | MS_FLY);
    if (f && !(f & (MS_FOOT << s2f.mode)))
        return 0;
    return !(d->flags & MS_SPACE) || s2f.pos.y > MS_SPACE_Y;
}

static void armed_hud(const MisDef *d, const MsPlace *p)
{
    MisRun *r = &ms_run;
    int dir, cells;
    bearing(wpos(p), &dir, &cells);
    if (cells > HL_RANGE) {
        hl_off();
        return;
    }
    const char *t = ms_text(d->title);
    int tl = 0;
    while (t[tl])
        tl++;
    if (d->kind == MK_ACT && d->act && !(r->flags & RF_ROAM) && tl + 6 <= HL_LEFT_MAX) {     /* ("ACT 3 " only where the whole title fits after it) */
        char *b = hud_buf;
        *b++ = 'A', *b++ = 'C', *b++ = 'T', *b++ = ' ', *b++ = '0' + d->act % 10, *b++ = ' ';
        for (int i = 0; t[i]; i++)
            *b++ = t[i];
        *b = 0;
        hl_text(hud_buf);
    } else {
        hl_text(t);
    }
    hl_stat(HLS_BEAR, dir, cells);
}

static void armed_tick(void)
{
    MisRun *r = &ms_run;
    const MisDef *d = ms_def(r->mis);
    const MsPlace *p = start_place();
    if (!d || !p) {
        r->state = MS_IDLE;
        r->mis = 0xffff;
        hl_clear();
        return;
    }
    int go = 0;
    if (p->kind >= PK_RING_X && p->kind <= PK_RING_H) {
        go = crossed(p, s2f.pos, &r->v[0]) == 1;
    } else if (at_place(p, 1024, 768) && s2f.speed < 300) {
        r->dwell = r->dwell + cur_dt > 255 ? 255 : r->dwell + cur_dt;
        go = r->dwell >= TICKS;
    } else {
        r->dwell = 0;
    }
    if (go && start_ok(d)) {
        int ck = r->ckpt;
        begin_mission(r->mis, ck ? d->obj0 + ck - 1 : d->obj0);
        return;
    }
    /* K's job line (pirates, courier or race clock, salvage), a talk in the station and a Payback phone mission have y117 and the player */
    int quiet = s2f.docked || sg_job_active() || (g_busy && !(d->flags & MF_PHONE));
    if (quiet) {
        r->flags |= RF_QUIET;
        hl_off();
        return;
    }
    r->flags &= ~RF_QUIET;
    armed_hud(d, p);
}

/* one mission of the roam scan: arms it when it is a challenge or medal (or the demo act) whose beacon is within reach and nearer than cur; 1 when it did */
static int roam_look(int i, s32 cur)
{
    MisRun *r = &ms_run;
    const MisDef *d = ms_def(i);
    int lim = ROAM_CELLS;
    if (d && d->kind == MK_ACT && i + 1 == demo_act && !act_mis && !cp_mis_done(i))
        lim = ACT_ROAM_CELLS;
    else if (!d || (d->kind != MK_CHAL && d->kind != MK_MEDAL))
        return 0;
    if (d->map != s2f.map || d->start == NOPLACE || !d->nobj)
        return 0;
    if (d->kind == MK_MEDAL && cp_mis_done(i))
        return 0;
    const MsPlace *p = ms_place(d->start);
    if (!p)
        return 0;
    V3 c = wpos(p);
    s32 dd = ab(c.x - s2f.pos.x) + ab(c.z - s2f.pos.z);
    if (hold_mis == i + 1) {                        /* (just finished: back only after the player has left its beacon) */
        if (dd > lim * CELL_U)
            hold_mis = 0;
        return 0;
    }
    if (dd > lim * CELL_U || dd >= cur || (r->state == MS_ARMED && r->mis == i))
        return 0;
    arm(i, 1);
    return 1;
}

/* the beacons of challenges and medals (and of a campaign-less map's first act, nearer in): one within ROAM_CELLS of the player and nearer than the one now armed takes the
   stage (two of the map's missions looked at a tick); walk away, or nearer to the act's own beacon, and the act's comes back */
static void roam_scan(void)
{
    MisRun *r = &ms_run;
    int n = H->nmis;
    s32 cur = 0x7fffffff;
    const MsPlace *cp = 0;
    if (r->state == MS_ARMED && (cp = start_place()) != 0) {
        V3 c = wpos(cp);
        cur = ab(c.x - s2f.pos.x) + ab(c.z - s2f.pos.z);
        if (r->flags & RF_ROAM) {
            const MisDef *ad = act_mis ? ms_def(act_mis - 1) : 0;
            const MsPlace *ap = ad && ad->start != NOPLACE ? ms_place(ad->start) : 0;
            s32 adist = ap ? ab(wpos(ap).x - s2f.pos.x) + ab(wpos(ap).z - s2f.pos.z) : 0x7fffffff;
            if (cur > ((r->mis + 1 == demo_act ? ACT_ROAM_CELLS : ROAM_CELLS) + 2) * CELL_U || adist < cur) {      /* walked away, or the act's beacon is nearer */
                r->state = MS_IDLE;
                r->mis = 0xffff;
                hl_clear();
                if (act_mis)
                    arm(act_mis - 1, 0);
                return;
            }
        }
    }
    if (roam_off)
        return;
    int lo = 0, hi = n;                             /* (this map's missions: its chapter's range, about 30, so a beacon is found within a second) */
    for (int c = 0; c < H->nchap; c++) {
        const Chapter *ch = ms_chap(c);
        if (ch->map == s2f.map && !(ch->flags & CH_RESERVED)) {
            lo = ch->mis0, hi = lo + ch->nmis;
            if (hi > n)
                hi = n;
            break;
        }
    }
    for (int k = 0; k < ROAM_PER_TICK && lo < hi; k++) {
        int i = r->rr;
        if (i < lo || i >= hi)
            i = lo;
        r->rr = i + 1 >= hi ? lo : i + 1;
        if (roam_look(i, cur))
            break;
    }
}

void ms_tick(void)
{
    MisRun *r = &ms_run;
    if (!H_state)
        validate();
    if (!H)
        return;
    s32 c = s2f.clock;
    cur_dt = c - last_clk;
    last_clk = c;
    if (cur_dt < 0 || cur_dt > 8)
        cur_dt = 0;
    if (s2f.paused)                                 /* Payback's pause menu: nothing moves, our line stays off */
        return;
    if (PB_LEVEL_END) {                             /* the level is over (target reached or game over) */
        if (r->state != MS_IDLE)
            ms_abort();
        return;
    }
    scan_goals();
    switch (r->state) {
    case MS_DONE: case MS_FAIL:
        r->state = MS_IDLE;
        r->mis = 0xffff;
        if (act_mis)
            arm(act_mis - 1, 0);
        break;
    case MS_IDLE:
        roam_scan();
        break;
    case MS_ARMED:
        roam_scan();
        if (r->state == MS_ARMED)
            armed_tick();
        break;
    case MS_RUN:
        run_tick();
        break;
    case MS_PAUSED:
        if (g_busy && !(ms_def(r->mis)->flags & MF_PHONE)) {
            r->t_start += cur_dt;                   /* (its clocks stand still) */
            r->t_step += cur_dt;
        } else {
            sg_foe_hold(r->tag, 0);
            r->flags &= ~RF_HELD;
            r->state = MS_RUN;
            hl_text(ms_text(ms_obj(r->obj)->text));
            hl_stat(HLS_NONE, 0, 0);
        }
        break;
    }
    r->evm = 0;                                     /* (an event counts for the tick after it came) */
}

/* ---- events ---- */
void ms_ev(int ev, int a, int b)
{
    MisRun *r = &ms_run;
    switch (ev) {
    case EV_DEATH: case EV_ARWING_DOWN:
        r->evm |= EVM_DEATH;
        break;
    case EV_SPACE:
        if (a)
            r->evm |= EVM_SPACE;
        break;
    case EV_DOCK:
        r->evm |= EVM_DOCK;
        break;
    }
    if (r->state != MS_RUN)
        return;
    const MisObj *o = ms_obj(r->obj);
    if (!o)
        return;
    switch (ev) {
    case EV_STUNT:
        if (o->op == OP_GROUP || (o->op == OP_STUNT && (o->b < 0 || in_box(o->b, s2f.pos))))
            r->pts = r->pts + a > 0xffff ? 0xffff : r->pts + a;
        break;
    case EV_LAND:
        if (o->op == OP_JUMP && a >= o->a)
            r->evm |= EVM_JUMP;
        break;
    case EV_KILL:
        if (o->op == OP_DESTROY && a >= r->tag && a < r->tag + NTAG)
            r->v[1] |= 1 << (a - r->tag);
        else if (o->op == OP_BLAST && b == EVK_BOX) {
            s32 x0, z0, x1, z1;
            box(o->place, &x0, &z0, &x1, &z1);
            s32 cx = (a >> 7) * CELL_U + CELL_U / 2, cz = (a & 127) * CELL_U + CELL_U / 2;
            if (cx >= x0 && cx <= x1 && cz >= z0 && cz <= z1)
                r->count++;
        }
        break;
    case EV_TALK:
        if (o->op == OP_TALK && a == o->a && b == o->b)
            r->evm |= EVM_TALK;
        break;
    }
}

void ms_level_enter(int map)
{
    validate();
    clear_run();
    ms_run.ndone = ms_run.nfail = 0;
    act_mis = arrow_at = demo_act = hold_mis = 0;
    ban_at = s2f.clock - 2 * BAN_TICKS;
    last_clk = s2f.clock;
    hl_clear();
    for (int i = 0; H && i < H->nmis; i++) {        /* the map's first act: shown when walked up to unless the campaign (which runs next) arms one */
        const MisDef *d = ms_def(i);
        if (d->map == map && d->kind == MK_ACT && !cp_mis_done(i)) {
            demo_act = i + 1;
            break;
        }
    }
}

/* ---- the debug mailbox (stage2.h): 1 start arg, 2 complete the objective, 3 fail, 4 autopilot arg, 5 hash of the run,
   6 arm arg, 7 state (state | objective in the act << 8 | mission << 16), 8 info arg, 9 abort, 10 roaming off (arg 1) or on,
   11 set the running objective's count to arg ---- */
int ms_dbg(int cmd, int arg)
{
    MisRun *r = &ms_run;
    if (!H_state)
        validate();
    if (!H)
        return -2;
    switch (cmd) {
    case 1:
        if (!ms_def(arg) || !ms_def(arg)->nobj)
            return -1;
        ms_start(arg);
        return 1;
    case 2:
        r->evm |= EVM_FORCE;
        return 0;
    case 3:
        r->evm |= EVM_FAIL;
        return 0;
    case 4:
        r->ap = arg != 0;
        return r->ap;
    case 5: {
        u32 h = 2166136261u;
        for (const u8 *p = (const u8 *)r; p < (const u8 *)r + sizeof *r; p++)
            h = (h ^ *p) * 16777619u;
        return (s32)h;
    }
    case 6:
        if (!ms_def(arg))
            return -1;
        ms_arm(arg);
        return r->state;
    case 7: {
        const MisDef *d = ms_def(r->mis);
        int in = d && (r->state == MS_RUN || r->state == MS_PAUSED) ? r->obj - d->obj0 : 0;
        return r->state | in << 8 | (int)((u32)(d ? r->mis : 0xffff) << 16);
    }
    case 8:
        switch (arg) {
        case 0: return H->nmis;
        case 1: return H->nchap;
        case 2: return r->ndone;
        case 3: return r->nfail;
        case 4: return r->goal;
        case 5: return r->retries;
        case 6: return r->timer;
        case 7: return r->count;
        case 8: return g_busy;
        case 9: {                                   /* our goals in Payback's list and its queue */
            int k = 0, n = PB_NGOALS;
            for (int i = 0; i < n && i < PB_NGOAL_MAX; i++) {
                s32 id = *pb_goal_w(i, PBG_ID);
                k += id >= GOAL_ID && id < GOAL_ID + 256;
            }
            return k;
        }
        case 10: return r->spawned;
        case 11: return r->flags;
        case 12: return r->mis;
        case 13: return g_ring;
        }
        return -1;
    case 9:
        ms_abort();
        return 0;
    case 10:
        roam_off = arg != 0;
        return roam_off;
    case 11:                                        /* the running objective's count (a harness holds a ring run at its first ring) */
        if (r->state == MS_RUN)
            r->count = arg;
        return r->count;
    }
    return -1;
}
