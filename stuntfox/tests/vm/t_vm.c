/* The mission VM on the PC (T0): src/mission.c and src/hudline.c compiled as they are, against pbmock.c's Payback.
   Three parts: golden traces of the demo missions driven by a bot, adversarial cases (a phone mission mid-act, a death
   mid-carry, game over, the pause menu, a full goal list, a bad blob ...) and a fuzz of random missions under random
   play, with the invariants checked after every step:
     - Payback's own goals are untouched, and at most one goal is ours (and none unless a mission runs)
     - no entity or foe keeps one of our tags once the mission is over; pb_kill is never called
     - a banner is a title from the blob or one of the fixed words, at most 19 letters
     - a goal on floor 0x7f never carries a marker byte (Payback would write into a cell by floor)
     - the state is in range, the objective inside the mission
     - nothing prints on the ticker: it is not in the link at all (the mock has no such function)

   t_vm <demo.bin> [trace name]     prints PASS/FAIL lines (or one golden trace) and exits 1 on a failure */
#include "stage2.h"
#include "mission.h"
#include "hudline.h"
#include "draw2d.h"
#include "render.h"
#include "palette.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

extern int pbm_job, pbm_bad, pbm_evs[EV_N], pbm_puts, pbm_ntext;
extern char pbm_text[8][64];
extern void pbm_reset(void), pbm_tick(void), pbm_add_own(int, int), pbm_del_own(int);
extern u8 s2_blob_store[];
extern struct { int tag, n; } pbm_foe[8];

static int fails, checks;
static int ck(int ok, const char *what)
{
    checks++;
    if (!ok) {
        fails++;
        printf("FAIL  %s\n", what);
    } else if (getenv("VERBOSE")) {
        printf("PASS  %s\n", what);
    }
    return ok;
}
static void ckf(int ok, const char *fmt, ...) __attribute__((format(printf, 2, 3)));
static void ckf(int ok, const char *fmt, ...)
{
    char b[256];
    __builtin_va_list ap;
    __builtin_va_start(ap, fmt);
    vsnprintf(b, sizeof b, fmt, ap);
    __builtin_va_end(ap);
    ck(ok, b);
}

/* ---- the world: the invariants ---- */
static int own_ids[128], n_own;
static char allowed[64][24];
static int n_allowed, seen_banner;
static const char *const fixed_words[] = {"ACT COMPLETE", "ACT FAILED", "CHALLENGE DONE", "CHALLENGE FAILED", "MEDAL FOUND", "MEDAL MISSED"};

static void effective(s32 *ids, int *n)               /* the goal list once the queue is applied */
{
    int k = 0;
    for (int i = 0; i < pbm.ngoals; i++)
        ids[k++] = pbm.goals[9 * i];
    for (int c = 0; c < pbm.ncmd && k < 200; c++) {
        if (pbm.cmd[c].kind == -1) {
            for (int i = 0; i < k; i++)
                if (ids[i] == pbm.cmd[c].id) {
                    memmove(ids + i, ids + i + 1, (k - i - 1) * 4);
                    k--;
                    break;
                }
        } else if (k < PB_NGOAL_MAX) {
            ids[k++] = pbm.cmd[c].id;
        }
    }
    *n = k;
}

static int bad_inv;
static char why[160];
static void inv(const char *fmt, ...)
{
    if (!bad_inv) {
        __builtin_va_list ap;
        __builtin_va_start(ap, fmt);
        vsnprintf(why, sizeof why, fmt, ap);
        __builtin_va_end(ap);
    }
    bad_inv++;
}

static void check_inv(void)
{
    s32 ids[256];
    int n, ours = 0, own = 0;
    effective(ids, &n);
    for (int i = 0; i < n; i++) {
        if (ids[i] >= 0x5000 && ids[i] < 0x5100)
            ours++;
        else {
            int f = 0;
            for (int k = 0; k < n_own; k++)
                f |= own_ids[k] == ids[i];
            if (!f)
                inv("a goal (%x) that is not Payback's own and not ours", ids[i]);
            own++;
        }
    }
    if (own != n_own)
        inv("Payback's goals: %d, expected %d", own, n_own);
    int run = ms_run.state == MS_RUN || ms_run.state == MS_PAUSED;
    if (ours > 1)
        inv("%d goals of ours", ours);
    if (ours && !run)
        inv("a goal of ours with no mission running (state %d)", ms_run.state);
    if (pbm.ngoals > PB_NGOAL_MAX)
        inv("goal count %d", pbm.ngoals);
    for (int i = 0; i < PBM_NENT; i++) {
        s32 t = *(s32 *)(pbm.ent[i] + PBE_TAG);
        if (t >= 0x5000 && t < 0x6000 && (!run || !(ms_run.spawned >> (t - ms_run.tag) & 1) || t < ms_run.tag || t >= ms_run.tag + 6))
            inv("entity %d keeps tag %x (run %d spawned %x tag %x)", i, t, run, ms_run.spawned, ms_run.tag);
    }
    if (!run)
        for (int i = 0; i < 8; i++)
            if (pbm_foe[i].tag >= 0x5000 && pbm_foe[i].tag < 0x6000 && pbm_foe[i].n)
                inv("foe tag %x alive with no mission", pbm_foe[i].tag);
    if (pbm_bad)
        inv("pbm_bad %d (1 marker on floor 0x7f, 2 banner over 19, 4 pb_kill)", pbm_bad);
    for (; seen_banner < pbm.nbanner; seen_banner++) {
        int f = 0;
        for (int k = 0; k < n_allowed; k++)
            f |= !strcmp(allowed[k], pbm.banners[seen_banner]);
        if (!f)
            inv("banner \"%s\" is not a title or a fixed word", pbm.banners[seen_banner]);
    }
    if (ms_run.state > MS_PAUSED)
        inv("state %d", ms_run.state);
    if (ms_run.state == MS_RUN || ms_run.state == MS_PAUSED) {
        const MisDef *d = ms_def(ms_run.mis);
        if (!d || ms_run.obj < d->obj0 || ms_run.obj >= d->obj0 + d->nobj)
            inv("objective %d outside mission %d", ms_run.obj, ms_run.mis);
    }
}

static void collect_allowed(void)
{
    n_allowed = 0;
    for (unsigned i = 0; i < sizeof fixed_words / sizeof *fixed_words; i++)
        snprintf(allowed[n_allowed++], 24, "%s", fixed_words[i]);
    for (int i = 0; i < ms_count() && n_allowed < 60; i++) {
        const char *t = ms_text(ms_def(i)->title);
        snprintf(allowed[n_allowed], 20, "%s", t);
        n_allowed++;
        const MisObj *o = ms_obj(ms_def(i)->obj0);
        for (int k = 0; o && k < ms_def(i)->nobj && n_allowed < 60; k++, o++)
            if (o->op == OP_BRIEF && o->a)
                snprintf(allowed[n_allowed++], 20, "%s", ms_text(o->a));
    }
}

static void world_reset(void)
{
    pbm_reset();
    n_own = 0;
    own_ids[n_own++] = 1;
    pbm_add_own(1, PBG_LEVEL);                     /* the level's own target goal */
    pbm.ngoals += 0;
    pbm.respawn = 0;
    s2f.mode = FOOT;
    s2f.pos = v3(10 * 1024, 0, 50 * 1024);
    seen_banner = 0;
    bad_inv = 0;
}

/* one frame of ours; clock: Payback ticks passed in it (0 the second frame of a tick) */
static void frame(int clock)
{
    for (int i = 0; i < clock; i++)
        pbm_tick();
    s2f.clock = pbm.clock;
    s2f.ticks++;
    s2f.paused = s2f.paused;
    ms_tick();
    check_inv();
}
static void frames(int n)                          /* n Payback ticks, 30 a second, a frame each */
{
    while (n-- > 0)
        frame(1);
}

static void put(const MsPlace *p, int mode)
{
    s2f.pos = v3(p->x8 * 128, p->h, p->y8 * 128);
    s2f.mode = mode;
    s2f.speed = 0;
    s2f.airborne = 0;
}
static void put_obj(void)                          /* the bot walks to the objective's place */
{
    int t = ms_target();
    if (t >= 0)
        put(ms_place(t), s2f.mode);
}

/* ---- a blob built here: for the cases the demo has no objective for ---- */
typedef struct {
    MisDef mis[64];
    MisObj obj[128];
    MsPlace pl[128];
    Chapter ch[2];
    char *text[160];
    int nmis, nobj, npl, ntext, nch;
} Syn;
static Syn syn;
static void syn_reset(void)
{
    memset(&syn, 0, sizeof syn);
    syn.ntext = 1;
    syn.text[0] = "";
}
static int syn_text(const char *s)
{
    syn.text[syn.ntext] = (char *)s;
    return syn.ntext++;
}
static int syn_pl(int xc, int yc, int h, int r, int kind)
{
    syn.pl[syn.npl] = (MsPlace){xc * 8, yc * 8, h, r * 8, kind};
    return syn.npl++;
}
static int syn_obj(int op, int place, int mode, int n, int a, int b, int flags, const char *text)
{
    syn.obj[syn.nobj] = (MisObj){op, flags, mode, n, place, a, b, text ? syn_text(text) : 0};
    return syn.nobj++;
}
static int syn_mis(int map, int kind, const char *title, int start, int flags, int first, int n, int par, int pay, int score)
{
    MisDef *d = &syn.mis[syn.nmis];
    *d = (MisDef){syn.nmis + 1, map, kind, kind == MK_ACT, 0, flags, syn_text(title), 0, first, n, 0, start, par, pay, score};
    return syn.nmis++;
}
static void syn_pack(void)
{
    u8 *b = s2_blob_store;
    memset(b, 0, 1 << 16);
    S2Head *h = (S2Head *)b;
    u32 at = sizeof *h;
    h->magic = S2_MAGIC, h->ver = S2_VER;
    h->nchap = syn.nch, h->nmis = syn.nmis, h->nobj = syn.nobj, h->nplace = syn.npl, h->ntext = syn.ntext;
    h->off_chap = at, memcpy(b + at, syn.ch, syn.nch * sizeof(Chapter)), at += syn.nch * sizeof(Chapter);
    h->off_mis = at, memcpy(b + at, syn.mis, syn.nmis * sizeof(MisDef)), at += syn.nmis * sizeof(MisDef);
    h->off_obj = at, memcpy(b + at, syn.obj, syn.nobj * sizeof(MisObj)), at += syn.nobj * sizeof(MisObj);
    h->off_place = at, memcpy(b + at, syn.pl, syn.npl * sizeof(MsPlace)), at += syn.npl * sizeof(MsPlace);
    h->off_text = at;
    u16 *tab = (u16 *)(b + at);
    u32 off = syn.ntext * 2;
    for (int i = 0; i < syn.ntext; i++) {
        tab[i] = off;
        strcpy((char *)b + at + off, syn.text[i]);
        off += strlen(syn.text[i]) + 1;
    }
    at += (off + 3) & ~3u;
    h->size = at;
}
static void level(int map)
{
    world_reset();
    s2f.map = map;
    s2f.clock = pbm.clock;
    ms_level_enter(map);
    collect_allowed();
}

/* ---- golden traces: a bot plays the demo ---- */
static void trace_line(const char *what)
{
    s32 ids[256];
    int n;
    effective(ids, &n);
    int ours = 0;
    for (int i = 0; i < n; i++)
        ours += ids[i] >= 0x5000 && ids[i] < 0x5100;
    printf("%-14s t=%-4u state=%d mis=%-2d obj=%-2d count=%-2d goals=%d ours=%d ban=%d score=%d done=%d fail=%d line=%s\n", what,
           (unsigned)(pbm.clock), ms_run.state, ms_run.mis == 0xffff ? -1 : ms_run.mis, ms_run.state == MS_RUN || ms_run.state == MS_PAUSED ? ms_run.obj : -1,
           ms_run.count, n, ours, pbm.nbanner, pbm.score, ms_run.ndone, ms_run.nfail, pbm.nbanner ? pbm.banners[pbm.nbanner - 1] : "-");
}

static void trace_act1(void)
{
    level(0);
    trace_line("level");
    const MisDef *d = ms_def(0);
    put(ms_place(d->start), FOOT);
    frames(10);
    trace_line("dwell 10");
    frames(25);
    trace_line("started");
    for (int guard = 0; guard < 40 && ms_run.state == MS_RUN; guard++) {
        int o = ms_run.obj, c = ms_run.count;
        put_obj();
        frames(2);
        if (ms_run.obj != o || ms_run.count != c || ms_run.state != MS_RUN)
            trace_line("progress");
    }
    frames(3);
    trace_line("end");
    frames(2);
    trace_line("armed again");
}

static void trace_ring(void)
{
    level(3);
    ms_arm(4);                                     /* (what a campaign does at the level's start) */
    trace_line("level");
    s2f.map = 3;
    const MisDef *d = ms_def(4);
    const MsPlace *p = ms_place(d->start);
    s2f.mode = FLY;
    s2f.pos = v3(p->x8 * 128, p->h, p->y8 * 128 - 800);
    frames(2);
    s2f.pos.z += 1600;                             /* through the start ring */
    frames(2);
    trace_line("started");
    for (int guard = 0; guard < 80 && ms_run.state == MS_RUN; guard++) {
        int o = ms_run.obj, c = ms_run.count;
        int t = ms_target();
        const MsPlace *q = t >= 0 ? ms_place(t) : 0;
        if (q && q->kind >= PK_RING_X && q->kind <= PK_RING_H) {
            s32 cx = q->x8 * 128, cy = q->h, cz = q->y8 * 128;
            if (q->kind == PK_RING_X)
                s2f.pos = v3(cx - 600, cy, cz), frames(1), s2f.pos.x = cx + 600;
            else
                s2f.pos = v3(cx, cy, cz - 600), frames(1), s2f.pos.z = cz + 600;
            frames(1);
        } else {
            put_obj();
            if (q)
                s2f.pos.y = q->h;
            frames(2);
        }
        if (ms_run.obj != o || ms_run.count != c || ms_run.state != MS_RUN)
            trace_line("progress");
    }
    frames(2);
    trace_line("end");
}

static void trace_timeout(void)
{
    level(0);
    ms_start(1);                                   /* STUNT 300, 60 s */
    s2f.mode = DRIVE;
    frames(5);
    trace_line("started");
    ms_ev(EV_STUNT, 100, STUNT_BARREL);
    frames(1);
    trace_line("100 pts");
    frames(60 * 30 - 6);                           /* (the TIMER scope and the act's own limit are the same 60 s) */
    trace_line("at 60 s");
    frames(3);
    trace_line("+3 ticks");
    frames(2);
    trace_line("after");
}

/* ---- the cases ---- */
static void case_demo(void)
{
    level(0);
    ck(ms_count() == 6 && ms_nchap() == 2, "the demo blob loads: 6 missions, 2 chapters");
    ck(ms_state() == MS_IDLE && !pbm.nbanner, "map 0 starts with nothing armed (the campaign arms acts)");
    s2f.pos = v3(9 * 1024 + 512, 0, 48 * 1024);     /* (the man's start, far from the act's beacon: more than ACT_ROAM_CELLS) */
    s2f.mode = FOOT;
    frames(20);
    ck(ms_state() == MS_IDLE && !s2_hud_owned(), "an act 8 cells off is not shown: no beacon, no line");
    put(ms_place(ms_def(0)->start), FOOT);
    frames(8);
    ck(ms_state() == MS_ARMED && ms_current() == 0 && (ms_run.flags & RF_ROAM) && !pbm.nbanner, "walking up to the act arms it, no banner yet");
    frames(40);
    ck(ms_state() == MS_RUN, "standing in the beacon for a second starts the act");
    ck(pbm.nbanner == 1 && !strcmp(pbm.banners[0], "FIRST STEPS"), "the title is the one banner at the start");
    int ci = 0;
    while (ms_state() == MS_RUN && ci++ < 40) {
        put_obj();
        frames(2);
    }
    ck(ms_state() != MS_RUN && pbm.nbanner == 2 && !strcmp(pbm.banners[1], "ACT COMPLETE"), "the act ends with ACT COMPLETE");
    ck(pbm.score == 1000, "and pays the score");
    ck(pbm_evs[EV_MIS_DONE] == 1 && ms_run.ndone == 1, "one EV_MIS_DONE");
    frames(3);
    s32 ids[256];
    int n;
    effective(ids, &n);
    ck(n == 1 && ids[0] == 1, "Payback's goal list is as it was");
    ck(ms_state() == MS_ARMED, "the act stands armed again (no campaign to move on)");
}

static void case_roam(void)
{
    level(0);
    s2f.mode = DRIVE;
    s2f.pos = v3(14 * 1024, 0, 38 * 1024);
    frames(14);                                    /* (the map's missions looked at a few a tick, the nearest taken) */
    ck(ms_state() == MS_ARMED && (ms_run.flags & RF_ROAM), "driving up to a challenge's beacon (within 10 cells, nearer than the act's) arms it");
    ck(ms_current() == 1, "the near one: STUNT 300");
    s2f.pos = v3(60 * 1024, 0, 60 * 1024);
    frames(30);
    ck(ms_state() == MS_IDLE, "walked off: nothing armed (a campaign-less map's act shows only when walked up to)");
    ms_dbg(10, 1);
    s2f.pos = v3(14 * 1024, 0, 38 * 1024);
    frames(30);
    ck(ms_state() == MS_IDLE, "roaming off (dbg 10): nothing arms");
    ms_dbg(10, 0);
    frames(14);
    ck(ms_state() == MS_ARMED, "roaming on again");
}

/* a real campaign has about 30 missions a map and 300 in all: the beacon of the last mission of the map's chapter arms within 15 ticks
   whatever the other chapters hold (the scan looks at the map's own chapter only) */
static void case_roam_chapter(void)
{
    syn_reset();
    syn_pl(5, 5, 0, 1, PK_POINT);                   /* 0: the near beacon */
    syn_pl(100, 100, 0, 1, PK_POINT);               /* 1: a far one */
    syn_pl(60, 60, 0, 1, PK_POINT);                 /* 2: the objective's place */
    int o = syn_obj(OP_GOTO, 2, 0, 1, 0, 0, 0, "GO");
    static char t[64][8];
    for (int m = 0; m < 60; m++) {                  /* chapter 0 (map 0): missions 0..29, chapter 1 (map 1): 30..59, the near one the last */
        snprintf(t[m], sizeof t[m], "M%d", m);
        syn_mis(m < 30 ? 0 : 1, MK_CHAL, t[m], m == 59 ? 0 : 1, MS_FOOT, o, 1, 0, 10, 1);
    }
    syn.ch[0] = (Chapter){0, CH_STORY, 0, 0, 0, 30, 0, 0, 0, 0, 1};
    syn.ch[1] = (Chapter){1, 0, 0, 0, 30, 30, 0, 0, 0, 0, 0xffff};
    syn.nch = 2;
    syn_pack();
    level(1);
    s2f.mode = FOOT;
    s2f.pos = v3(5 * 1024 + 512, 0, 5 * 1024 + 512);
    int n = 0;
    while (ms_state() != MS_ARMED && n < 64)
        frames(1), n++;
    ck(ms_state() == MS_ARMED && ms_current() == 59, "the last mission of the map's chapter arms by itself");
    ck(n <= 16, "and within 16 ticks, not the 60 the whole blob took");
    level(0);
    s2f.pos = v3(100 * 1024 + 512, 0, 100 * 1024 + 512);
    for (n = 0; n < 64 && ms_state() != MS_ARMED; n++)
        frames(1);
    ck(ms_state() == MS_ARMED && ms_current() < 30, "on map 0 only map 0's chapter is looked at");
}

static void case_range(void)
{
    level(0);
    ms_arm(0);                                     /* (the campaign arms the act) */
    s2f.mode = FOOT;
    s2f.pos = v3(14 * 1024, 0, 58 * 1024);
    frames(4);
    ck(ms_state() == MS_ARMED && s2_hud_owned(), "an armed act in reach: the line says where");
    s2f.pos = v3(80 * 1024, 0, 20 * 1024);          /* (more than HL_RANGE cells off) */
    frames(4);
    ck(ms_state() == MS_ARMED && !s2_hud_owned(), "far off: still armed, the line is off (it costs a frame in five)");
    s2f.pos = v3(40 * 1024, 0, 56 * 1024);
    frames(4);
    ck(ms_state() == MS_ARMED && s2_hud_owned(), "back within range: the line returns");
}

static void case_phone(void)
{
    level(0);
    ms_start(0);
    frames(3);
    int obj = ms_run.obj;
    pbm_add_own(0x40, PBG_PHONE);
    n_own++, own_ids[n_own - 1] = 0x40;
    frames(3);
    ck(ms_state() == MS_PAUSED || ms_state() == MS_RUN, "a ringing phone: the mission stays up");
    s32 ids[256];
    int n, ours = 0;
    effective(ids, &n);
    for (int i = 0; i < n; i++)
        ours += ids[i] >= 0x5000 && ids[i] < 0x5100;
    ck(ours == 0, "a ringing green phone has the arrow: ours is not there");
    pbm_del_own(0x40);
    n_own--;
    frames(4);
    ck(ms_state() == MS_RUN && ms_run.obj == obj, "the phone answered: the mission goes on at the same objective");
    effective(ids, &n);
    ours = 0;
    for (int i = 0; i < n; i++)
        ours += ids[i] >= 0x5000 && ids[i] < 0x5100;
    ck(ours == 1, "and our arrow is back");
    /* a phone mission (a goal that is neither a phone nor ours) pauses ours, with its clocks standing still */
    syn_reset();
    int s = syn_pl(10, 56, 0, 2, PK_PAD), g = syn_pl(12, 60, 0, 2, 0);
    int o0 = syn_obj(OP_GOTO, g, 0, 0, 0, 0, 0, "GO THERE");
    syn_mis(0, MK_ACT, "TIMED ONE", s, FF_TIME | FF_DEATH, o0, 1, 20, 0, 0);
    syn_pack();
    level(0);
    ms_start(0);
    frames(30);
    pbm_add_own(0x77, PBG_GOTO);
    n_own++, own_ids[n_own - 1] = 0x77;
    frames(2);
    ck(ms_state() == MS_PAUSED, "a phone mission's goal pauses the act");
    frames(30 * 30);
    ck(ms_state() == MS_PAUSED, "and a long time later it is still paused, not failed by its clock");
    pbm_del_own(0x77);
    n_own--;
    frames(5);
    ck(ms_state() == MS_RUN, "the phone mission over: the act runs on");
    frames(19 * 30);
    ck(ms_state() == MS_RUN || ms_state() == MS_ARMED, "its time was not used up while paused");
    frames(5 * 30);
    ck(ms_state() == MS_ARMED && ms_run.nfail == 1, "but it does run out (then the act stands armed to retry)");
}

static void case_carry(void)
{
    syn_reset();
    int s = syn_pl(10, 56, 0, 2, PK_PAD);
    int pick = syn_pl(12, 56, 0, 1, 0), d1 = syn_pl(16, 56, 0, 1, 0), d2 = syn_pl(20, 56, 0, 1, 0);
    syn_pl(0, 0, 0, 0, 0);
    int o0 = syn_obj(OP_DELIVER, pick, 2, 3, 0, 0, MO_CKPT, "DELIVER");
    int o1 = syn_obj(OP_FINISH, 0, 0, 0, 0, 0, 0, 0);
    (void)d1; (void)d2; (void)o1;
    syn_mis(0, MK_ACT, "THE CARRY", s, FF_DEATH | FF_VEHLOST, o0, 2, 0, 5, 5);
    syn_pack();
    level(0);
    s2f.mode = DRIVE;
    ms_start(0);
    put(ms_place(pick), DRIVE);
    frames(2);
    ck(ms_run.carry == 1 && ms_run.state == MS_RUN, "picked up: carrying");
    ms_ev(EV_DEATH, 0, 0);
    frames(1);
    ck(ms_state() == MS_ARMED && ms_run.carry == 0 && ms_run.retries == 1, "a death mid-carry fails the act; it stands armed; nothing carried");
    ck(pbm_evs[EV_MIS_FAIL] == 1, "one EV_MIS_FAIL");
    ck(!strcmp(pbm.banners[pbm.nbanner - 1], "ACT FAILED"), "ACT FAILED");
    put(ms_place(pick), DRIVE);                    /* (the checkpoint is where the retry starts) */
    frames(40);
    ck(ms_state() == MS_RUN && ms_run.obj == ms_def(0)->obj0 + 0, "armed at its checkpoint: the retry starts there");
    ms_start(0);
    ms_run.mis = 0;
    put(ms_place(pick), FOOT);
    frames(2);
    ck(ms_run.carry == 0, "the vehicle rule: on foot, nothing is picked up as a car job");
    put(ms_place(pick), DRIVE);
    frames(2);
    s2f.mode = FOOT;
    frames(2);
    ck(ms_state() == MS_ARMED, "losing the vehicle while carrying fails it (FF_VEHLOST)");
}

static void case_end(void)
{
    syn_reset();
    int s = syn_pl(10, 56, 0, 2, PK_PAD), g = syn_pl(30, 56, 0, 2, 0);
    int o0 = syn_obj(OP_FOES, g, 0, 2, 1, 5, 0, "KILL THEM");
    syn_obj(OP_DESTROY, g, 0, 2, 3, 0, 0, "WRECK THEM");
    syn_mis(0, MK_ACT, "THE FOES", s, 0, o0, 2, 0, 0, 0);
    syn_pack();
    level(0);
    ms_start(0);
    frames(3);
    ck(pbm_foe[0].tag == ms_run.tag && sg_foe_alive(ms_run.tag), "foes up");
    pbm.level_end = 2;
    frames(2);
    ck(ms_state() == MS_IDLE && !sg_foe_alive(0x5000), "game over: the run is dropped, the foes cleared");
    ck(ms_run.spawned == 0, "no spawns left");
    pbm.level_end = 0;
    level(0);
    ms_start(0);
    frames(3);
    s2f.paused = 1;
    u32 c0 = ms_run.t_step;
    frames(50);
    ck(ms_state() == MS_RUN && ms_run.t_step == c0, "the pause menu: nothing moves");
    s2f.paused = 0;
    ms_abort();
    check_inv();
    ck(bad_inv == 0, "abort leaves nothing");
}

static void case_full_and_bad(void)
{
    level(0);
    for (int i = 0; i < 99; i++) {
        pbm_add_own(0x100 + i, PBG_HIDDEN_PICKUP);
        n_own++, own_ids[n_own - 1] = 0x100 + i;
    }
    ms_start(0);
    frames(10);
    ck(pbm.ngoals <= 100 && ms_state() == MS_RUN, "a goal list with 100 in it: ours does not fit, the act still runs");
    ck(bad_inv == 0, "and nothing breaks");
    pbm_reset();
    pbm.grid_ram = 1;
    n_own = 0;
    level(0);
    pbm.grid_ram = 1;
    ms_start(0);
    frames(10);
    s32 ids[256];
    int n;
    effective(ids, &n);
    ck(n == 1, "a cell the grid keeps a RAM copy of gets no goal");
    pbm.grid_ram = 0;
    /* bad blobs */
    memset(s2_blob_store, 0, 64);
    level(0);
    frames(5);
    ck(ms_count() == 0 && ms_state() == MS_IDLE && ms_dbg(1, 0) == -2, "no content (zeros): nothing runs");
    memcpy(s2_blob_store, "S2C1", 4);
    level(0);
    frames(5);
    ck(ms_count() == 0, "a bad header: nothing");
}

static void case_ops(void)                         /* the ops the demo has no use for, one mission each */
{
    syn_reset();
    int s = syn_pl(10, 56, 0, 2, PK_PAD), q = syn_pl(11, 56, 0, 2, 0);
    int o0 = syn_obj(OP_WANTED, 0, 0, 0, 2, 2, 0, "WANTED 2");
    syn_obj(OP_FINISH, 0, 0, 0, 0, 0, 0, 0);
    syn_mis(0, MK_CHAL, "TWO STARS", s, 0, o0, 2, 0, 0, 0);
    int o1 = syn_obj(OP_SURVIVE, 0, 0, 0, 0, 3, 0, "SURVIVE 3");
    syn_obj(OP_FINISH, 0, 0, 0, 0, 0, 0, 0);
    syn_mis(0, MK_CHAL, "STAY ALIVE", s, FF_DEATH, o1, 2, 0, 0, 0);
    int o2 = syn_obj(OP_SCORE, 0, 0, 0, 5, 0, 0, "SCORE 500");
    syn_obj(OP_PHONE, 0, 0, 1, 0, 0, 0, "ONE PHONE");
    syn_obj(OP_FINISH, 0, 0, 0, 0, 0, 0, 0);
    syn_mis(0, MK_CHAL, "PHONE AND SCORE", s, MF_PHONE, o2, 3, 0, 0, 0);
    int o3 = syn_obj(OP_BLAST, q, 0, 2, 0, 0, 0, "BREAK 2");
    syn_obj(OP_FINISH, 0, 0, 0, 0, 0, 0, 0);
    syn_pl(14, 60, 0, 0, PK_BOX1);
    syn_mis(0, MK_CHAL, "BREAK BOXES", s, 0, o3, 2, 0, 0, 0);
    syn_pack();
    level(0);
    /* WANTED: the stars are the controlled record's +0x5a, held 2 s */
    ms_start(0);
    frames(3);
    pbm.me_rec[PBE_WANTED] = 1;
    frames(90);
    ck(ms_state() == MS_RUN, "WANTED 2: one star is not enough");
    pbm.me_rec[PBE_WANTED] = 2;
    frames(50);
    ck(ms_state() == MS_RUN, "two stars for under 2 s: not yet");
    frames(20);
    ck(ms_state() != MS_RUN && ms_run.ndone == 1, "two stars for 2 s: done");
    pbm.me_rec[PBE_WANTED] = 0;
    /* SURVIVE: a death restarts the count (and FF_DEATH fails it) */
    ms_start(1);
    frames(60);
    ck(ms_state() == MS_RUN, "SURVIVE 3: 2 s in");
    frames(50);
    ck(ms_state() != MS_RUN && ms_run.ndone == 2, "SURVIVE 3: 3 s alive: done");
    ms_start(1);
    frames(60);
    ms_ev(EV_DEATH, 0, 0);
    frames(2);
    ck(ms_run.nfail == 1, "SURVIVE with FF_DEATH: a death fails it");
    /* SCORE then PHONE */
    ms_start(2);
    frames(2);
    pbm.score += 400;
    frames(3);
    ck(ms_run.obj == ms_def(2)->obj0, "SCORE 500: 400 is not enough");
    pbm.score += 100;
    frames(3);
    ck(ms_run.obj == ms_def(2)->obj0 + 1, "SCORE 500 reached: on to the phone");
    s2_phones++;
    frames(3);
    ck(ms_run.ndone == 3, "one of Payback's own phone missions finished: done");
    /* BLAST: boxes broken inside the zone (cell x 128 + z) */
    ms_start(3);
    frames(2);
    ms_ev(EV_KILL, 11 << 7 | 56, EVK_BOX);
    frames(2);
    ck(ms_run.state == MS_RUN, "BREAK 2: one box inside the zone is one");
    ms_ev(EV_KILL, 40 << 7 | 40, EVK_BOX);
    frames(2);
    ck(ms_run.state == MS_RUN, "a box outside the zone does not count");
    ms_ev(EV_KILL, 12 << 7 | 57, EVK_BOX);
    frames(3);
    ck(ms_run.ndone == 4, "the second box: done");
    check_inv();
    ck(bad_inv == 0, "and nothing was left behind");
}

static void case_dbg(void)
{
    level(0);
    ck(ms_dbg(1, 0) == 1 && ms_state() == MS_RUN, "dbg 1 starts an act");
    ck(ms_dbg(2, 0) == 0, "dbg 2");
    frames(2);
    int o = (ms_dbg(7, 0) >> 8) & 255;
    ck(o >= 1, "dbg 2 completed the objective");
    ms_dbg(4, 1);
    frames(30 * 30);
    ck(ms_state() == MS_ARMED || ms_state() == MS_DONE || ms_state() == MS_IDLE, "dbg 4 (autopilot) drives the act to its end");
    ck(ms_run.ndone == 1, "and it was done");
    ms_dbg(4, 0);
    ms_dbg(1, 0);
    frames(2);
    ms_dbg(3, 0);
    frames(2);
    ck(ms_run.nfail == 1 && ms_dbg(8, 3) == 1, "dbg 3 fails it");
    u32 h1 = ms_dbg(5, 0), h2 = ms_dbg(5, 0);
    ck(h1 == h2, "dbg 5 (hash) is stable");
    ck(ms_dbg(9, 0) == 0 && ms_state() == MS_IDLE, "dbg 9 aborts");
    ck(ms_dbg(44, 0) == -1 && ms_dbg(1, 999) == -1, "an unknown command or mission answers -1");
}

/* ---- the HUD line and cards, pixel for pixel against the way d_text drew them letter by letter (draw2d.c) ---- */
extern u8 pbm_page[240 * 160];
extern const u32 font_tiles[];
#define T_INK COLOR(M_CREAM, 3, 0)
#define T_AMBER COLOR(M_GLOW, 3, 0)
#define T_PANEL COLOR(M_ROAD, 0, 0)

static void ref_fill(u8 *pg, int x, int y, int w, int h, int color)
{
    for (int j = 0; j < h; j++)
        memset(pg + (y + j) * 240 + x, d_pal(color), w);
}
static void ref_text(u8 *pg, int x, int y, const char *s, int ink)          /* draw2d.c's d_text, a pixel at a time */
{
    int sh = d_pal(T_PANEL), in = d_pal(ink);
    for (; *s; s++, x += 6) {
        int ch = *s;
        if (ch >= 'a' && ch <= 'z')
            ch -= 32;
        if (ch <= 32 || ch > 95)
            continue;
        const u32 *g = &font_tiles[(ch - 32) * 8];
        for (int r = 0; r < 8; r++) {
            u32 w = g[r];
            for (int k = 0; w; k++, w >>= 4)
                if (w & 15)
                    pg[(y + r) * 240 + x - 1 + k] = (w & 15) == 1 ? in : sh;
        }
    }
}

static u8 ref_pg[240 * 160];
static void pg_clear_all(void) { memset(pbm_page, 0xAB, sizeof pbm_page); }
static int pg_same(const char *what)
{
    int bad = -1;
    for (int i = 0; i < 240 * 160 && bad < 0; i++)
        if (pbm_page[i] != ref_pg[i])
            bad = i;
    if (bad >= 0)
        ckf(0, "%s: pixel (%d, %d) is %d, expected %d", what, bad % 240, bad / 240, pbm_page[bad], ref_pg[bad]);
    else
        ck(1, what);
    return bad < 0;
}
static void pg_clear(void)
{
    memset(pbm_page, 0xAB, sizeof pbm_page);
    memset(ref_pg, 0xAB, sizeof ref_pg);
}
/* the line the engine draws for left, status st (the whole line amber at the last 10 s): the panel 8 nb + 8 wide,
   the status after the text and a space */
static void ref_line(const char *left, const char *st, int amber)
{
    int n = strlen(left), ns = strlen(st), nb = ((n + (ns ? ns + 1 : 0)) * 6 + 7) / 8;
    ref_fill(ref_pg, 0, 117, nb * 8 + 8, 7, T_PANEL);
    ref_text(ref_pg, 4, 117, left, amber ? T_AMBER : T_INK);
    if (ns)
        ref_text(ref_pg, 4 + (n + 1) * 6, 117, st, amber ? T_AMBER : T_INK);
    for (int x = 0; x < 240; x++)                   /* (the old text's shadow row: the panel is the seven rows of ink only) */
        ref_pg[124 * 240 + x] = 0xAB;
}
static void line_is(const char *what, const char *left, const char *st, int amber)
{
    pg_clear();
    ref_line(left, st, amber);
    hl_draw();
    pg_same(what);
}

static void case_hud(void)
{
    level(0);
    ms_start(0);
    frames(2);
    s2f.paused = 0;
    hl_draw();
    ck(s2_hud_owned() == 1, "hl_up while a line is up");
    ms_abort();
    pg_clear();
    hl_draw();
    ck(memcmp(pbm_page, ref_pg, sizeof ref_pg) == 0 && s2_hud_owned() == 0, "after an abort: nothing drawn, the old line is K's again");
    ms_start(0);
    frames(2);
    s2f.paused = 1;
    pg_clear();
    hl_draw();
    ck(memcmp(pbm_page, ref_pg, sizeof ref_pg) == 0, "no line in Payback's pause menu");
    s2f.paused = 0;
    ms_abort();

    /* the line and the status, against the old way */
    s2f.paused = 0, s2f.docked = 0, pbm.level_end = 0, pbm.respawn = 0;
    hl_clear();
    hl_text("RING RUN");
    line_is("the line alone", "RING RUN", "", 0);
    hl_stat(HLS_COUNT, 3, 8);
    line_is("the line with a count", "RING RUN", "3/8", 0);
    hl_text("ACT 1 LONG TITLE XY");
    line_is("18 letters with a count", "ACT 1 LONG TITLE X", "3/8", 0);
    hl_stat(HLS_COUNT, 100, 200);
    line_is("18 letters with the longest status", "ACT 1 LONG TITLE X", "100/200", 0);
    hl_text("LAP");
    line_is("a shorter text leaves nothing of the longer one", "LAP", "100/200", 0);
    hl_stat(HLS_TIME, 65, 0);
    line_is("a clock", "LAP", "1:05", 0);
    hl_stat(HLS_TIME, 9, 0);
    line_is("the clock turns amber at 10 s", "LAP", "0:09", 1);
    hl_stat(HLS_TIME, 10, 0);
    line_is("amber at 10", "LAP", "0:10", 1);
    hl_stat(HLS_TIME, 11, 0);
    line_is("not at 11", "LAP", "0:11", 0);
    hl_stat(HLS_HP, 7, 0);
    line_is("hit points", "LAP", "HP 7", 0);
    hl_stat(HLS_BEAR, 1, 34);
    line_is("a bearing", "LAP", "NE 34", 0);
    hl_stat(HLS_NONE, 0, 0);
    line_is("no status again: nothing of the last one stays", "LAP", "", 0);
    hl_text("ACT 1 LONG TITLE XY");
    hl_stat(HLS_COUNT, 100, 200);
    hl_clear();
    hl_text("ONE");
    line_is("after a clear: no stale status in the left text's last byte", "ONE", "", 0);
    hl_clear();
    hl_text("ACT 1 LONG TITLE XY");
    line_is("a cleared 18-letter line", "ACT 1 LONG TITLE X", "", 0);
    hl_text("lower case, and a\nnewline");
    line_is("lower case is upper, a newline ends it", "LOWER CASE, AND A", "", 0);
    hl_text("");
    pg_clear();
    hl_draw();
    ck(memcmp(pbm_page, ref_pg, sizeof ref_pg) == 0 && !hl_up(), "an empty text is no line");
    hl_clear();

    /* a card: two lines of 38, after its delay, for three seconds */
    s2f.clock = 1000;
    hl_card("FLY THROUGH EACH RING IN ORDER, THEN\nSET DOWN ON THE PAD AT THE END.", 60);
    pg_clear();
    hl_draw();
    ck(memcmp(pbm_page, ref_pg, sizeof ref_pg) == 0 && !hl_up(), "a card with a delay is not up before it");
    s2f.clock = 1060;
    pg_clear();
    ref_fill(ref_pg, 0, 98, 240, 19, T_PANEL);
    ref_text(ref_pg, 4, 100, "FLY THROUGH EACH RING IN ORDER, THEN", T_INK);
    ref_text(ref_pg, 4, 108, "SET DOWN ON THE PAD AT THE END.", T_INK);
    hl_draw();
    pg_same("a two-line card");
    ck(hl_up() == 1, "hl_up while a card shows");
    s2f.clock = 1060 + HL_CARD_TICKS - 1;
    pg_clear();
    ref_fill(ref_pg, 0, 98, 240, 19, T_PANEL);
    ref_text(ref_pg, 4, 100, "FLY THROUGH EACH RING IN ORDER, THEN", T_INK);
    ref_text(ref_pg, 4, 108, "SET DOWN ON THE PAD AT THE END.", T_INK);
    hl_draw();
    pg_same("still up on its last tick");
    s2f.clock = 1060 + HL_CARD_TICKS;
    pg_clear();
    hl_draw();
    ck(memcmp(pbm_page, ref_pg, sizeof ref_pg) == 0 && !hl_up(), "gone after three seconds");
    hl_card("RETRY: GO TO THE BEACON", 0);
    pg_clear();
    ref_fill(ref_pg, 0, 98, 240, 11, T_PANEL);
    ref_text(ref_pg, 4, 100, "RETRY: GO TO THE BEACON", T_INK);
    hl_draw();
    pg_same("a one-line card");
    hl_text("GO");
    hl_off();
    ck(hl_up() == 1, "hl_off leaves a card");
    hl_clear();
    ck(hl_up() == 0, "hl_clear takes it");
    s2f.clock = 65530;                                  /* (the 16-bit clock turns over mid-card) */
    hl_card("WRAP", 0);
    s2f.clock = 65530 + 40;
    ck(hl_up() == 1, "a card runs on across the clock's turn-over");
    s2f.clock = 65530 + HL_CARD_TICKS + 1;
    ck(hl_up() == 0, "and ends");
    hl_clear();
    /* a card and a line together: the line over the card's last rows, as the engine draws them */
    s2f.clock = 5000;
    hl_card("TWO\nLINES", 0);
    hl_text("OBJ");
    hl_stat(HLS_COUNT, 1, 2);
    pg_clear();
    ref_fill(ref_pg, 0, 98, 240, 19, T_PANEL);
    ref_text(ref_pg, 4, 100, "TWO", T_INK);
    ref_text(ref_pg, 4, 108, "LINES", T_INK);
    ref_line("OBJ", "1/2", 0);
    hl_draw();
    pg_same("a card and the line");
    hl_clear();
    s2f.clock = 0;
}

/* ---- the second round of fixes ---- */
static void case_fixes(void)
{
    /* the armed line gives way to K's job line, and to a Payback mission */
    level(0);
    ms_arm(0);
    s2f.mode = FOOT;
    s2f.pos = v3(14 * 1024, 0, 58 * 1024);
    frames(4);
    ck(ms_state() == MS_ARMED && s2_hud_owned() && !(ms_run.flags & RF_QUIET), "armed in reach: the line is up");
    pbm_job = 1;
    frames(3);
    ck(!s2_hud_owned() && (ms_run.flags & RF_QUIET), "a K job on: our line is off and K's own shows");
    pbm_job = 0;
    frames(3);
    ck(s2_hud_owned() && !(ms_run.flags & RF_QUIET), "the job over: ours returns");
    pbm_add_own(0x333, 3);                          /* (a Payback mission's goal) */
    n_own++, own_ids[n_own - 1] = 0x333;
    frames(3);
    ck(!s2_hud_owned() && (ms_run.flags & RF_QUIET), "a Payback mission on: our line and beacon are off");
    pbm_del_own(0x333);
    n_own--;
    frames(3);
    ck(s2_hud_owned(), "and back after it");

    /* a ringing phone has the arrow: the line says where the objective is */
    level(0);
    ms_start(0);
    frames(40);
    ckf(hl_status()[0] == 0 || (hl_status()[0] >= '0' && hl_status()[0] <= '9'), "no phone ringing: a count (or none) [state %d obj %d status \"%s\"]", ms_run.state, ms_run.obj, hl_status());
    pbm_add_own(0x444, PBG_PHONE);
    n_own++, own_ids[n_own - 1] = 0x444;
    frames(4);
    const char *st = hl_status();
    ck(strchr("NESW", st[0]) && (st[1] == ' ' || strchr("EW", st[1])), "a phone rings: the line gives a compass point and the distance");
    ckf(st[0] != 0 && strchr(st, ' ') != 0, "the status is \"%s\" (ring %d busy %d)", st, (int)ms_dbg(8, 13), (int)ms_dbg(8, 8));
    pbm_del_own(0x444);
    n_own--;
    frames(4);

    /* a title banner is up first: the card waits for it to go */
    level(0);
    ms_start(0);
    pg_clear_all();
    frames(10);
    hl_draw();
    ck(pbm_page[99 * 240 + 3] == 0xAB, "the act's card is not drawn under its title banner");
    frames(150);
    pg_clear_all();
    hl_draw();
    ck(pbm_page[99 * 240 + 3] == 0xAB, "nor while the banner is still up (160 ticks in of 220)");
    frames(65);
    pg_clear_all();
    hl_draw();
    ck(pbm_page[99 * 240 + 3] != 0xAB, "and shows after it");
    ms_abort();

    /* STUNT points do not carry from one objective to the next */
    syn_reset();
    int s = syn_pl(10, 56, 0, 2, PK_PAD);
    int o0 = syn_obj(OP_STUNT, 0, 0, 0, 300, -1, 0, "STUNT A");
    syn_obj(OP_STUNT, 0, 0, 0, 300, -1, 0, "STUNT B");
    syn_obj(OP_FINISH, 0, 0, 0, 0, 0, 0, 0);
    syn_mis(0, MK_CHAL, "TWO STUNTS", s, 0, o0, 3, 0, 0, 0);
    int o1 = syn_obj(OP_WAIT, 0, 0, 0, 0, 3, 0, "WAIT");
    syn_obj(OP_FINISH, 0, 0, 0, 0, 0, 0, 0);
    syn_mis(0, MK_CHAL, "QUICK ONE", syn_pl(40, 56, 0, 2, PK_PAD), 0, o1, 2, 0, 0, 0);
    syn_pack();
    level(0);
    ms_start(0);
    frames(3);
    ms_ev(EV_STUNT, 300, STUNT_BARREL);
    frames(3);
    ck(ms_run.state == MS_RUN && ms_run.obj == ms_def(0)->obj0 + 1, "two STUNT objectives: the first is done by 300 points");
    frames(10);
    ck(ms_run.state == MS_RUN && ms_run.obj == ms_def(0)->obj0 + 1, "the second is not satisfied by the first's points");
    ms_ev(EV_STUNT, 300, STUNT_BARREL);
    frames(3);
    ck(ms_run.ndone == 1, "300 more finish it");

    /* a challenge just finished is not started again by standing in its beacon */
    ms_start(1);
    s2f.pos = v3(40 * 1024, 0, 56 * 1024);
    frames(2 * 30 + 3);
    ck(ms_run.ndone == 2, "a challenge: done");
    frames(100);
    ck(ms_run.ndone == 2 && ms_state() != MS_RUN && !(ms_state() == MS_ARMED && ms_current() == 1), "standing in its beacon does not arm it again");
    s2f.pos = v3(70 * 1024, 0, 56 * 1024);
    frames(40);
    s2f.pos = v3(41 * 1024, 0, 56 * 1024);
    frames(30);
    ck(ms_state() == MS_ARMED && ms_current() == 1, "after leaving it and coming back, it is there again");

    /* checkpoints and rings: at most 16 */
    syn_reset();
    s = syn_pl(10, 56, 0, 2, PK_PAD);
    for (int i = 0; i < 17; i++)
        syn_pl(11 + i, 56, 0, 2, 0);
    o0 = syn_obj(OP_RACE, 1, 0, 17, 0, 1, 0, "17");
    syn_obj(OP_FINISH, 0, 0, 0, 0, 0, 0, 0);
    syn_mis(0, MK_CHAL, "TOO MANY", s, 0, o0, 2, 40, 0, 0);
    syn_pack();
    level(0);
    frames(3);
    ck(ms_count() == 0, "a race of 17 checkpoints: the blob is refused");
    syn.obj[0].n = 16;
    syn_pack();
    level(0);
    frames(3);
    ck(ms_count() == 1, "16 is fine");
}

/* ---- the fuzz ---- */
static u32 rng_s;
static u32 rnd(void)
{
    rng_s ^= rng_s << 13, rng_s ^= rng_s >> 17, rng_s ^= rng_s << 5;
    return rng_s;
}
static int rr(int n) { return n ? (int)(rnd() % n) : 0; }

static void gen_blob(void)
{
    syn_reset();
    for (int i = 0; i < 40; i++) {
        int px = 8 + rr(50), py = 30 + rr(40), ph = rr(3) ? 0 : 1500, pr = 1 + rr(3), pk = rr(9);
        syn_pl(px, py, ph, pr, pk);
    }
    syn.ch[0] = (Chapter){0, CH_STORY, 3, 3, 0, 0, 0, 0, 0, 0, 0xffff};
    syn.nch = 1;
    static const char *const words[] = {"ONE", "TWO", "THREE", "FOUR", "FIVE", "SIX", "SEVEN", "EIGHT"};
    for (int m = 0; m < 8; m++) {
        int first = syn.nobj, n = 1 + rr(7), grp = 0;
        for (int k = 0; k < n; k++) {
            int op = 1 + rr(OP_N - 1), pl = rr(36), nn = 1 + rr(4), md = rr(4), a = rr(50) - 5, b = rr(10) - 2;
            if (op == OP_GROUP) {
                if (grp)
                    op = OP_GOTO;
                else
                    grp = 1;
            }
            if (op == OP_ENDGROUP) {
                if (!grp)
                    op = OP_WAIT;
                else
                    grp = 0;
            }
            if (op == OP_GATEWAY || op == OP_SPACE)
                op = OP_WAIT;
            if (op == OP_SPAWNVEH || op == OP_CHASE || op == OP_ESCORT || op == OP_DESTROY)
                a = rr(4);
            if (op == OP_CRATES)
                b = rr(40);
            if (op == OP_STUNT || op == OP_BLAST)
                b = op == OP_STUNT ? -1 : 0;
            if (op == OP_RINGS && nn > 16)
                nn = 16;
            int w_b = op == OP_WAIT ? rr(40) : b;          /* (one call at a time: the order of arguments differs between compilers) */
            int fl = rr(8) ? 0 : (rr(2) ? MO_CKPT : MO_ORDER);
            const char *tx = rr(2) ? words[rr(8)] : 0;
            syn_obj(op, pl, md, nn, op == OP_WAIT ? 0 : a, w_b, fl, tx);
        }
        if (grp)
            syn_obj(OP_ENDGROUP, 0, 0, 0, 0, 0, 0, 0);
        syn_obj(OP_FINISH, 0, 0, 0, 0, 0, 0, 0);
        int fl = 0, mp = rr(2) ? 0 : 3, st, par, pay, sc;
        fl |= rr(3) ? FF_DEATH : 0;
        fl |= rr(4) == 0 ? FF_TIME : 0;
        fl |= rr(5) == 0 ? MF_PHONE : 0;
        fl |= rr(4) == 0 ? MS_DRIVE : 0;
        fl |= rr(6) == 0 ? FF_VEHLOST : 0;
        int kind = m < 3 ? MK_ACT : MK_CHAL + rr(2);
        st = rr(10) ? rr(40) : NOPLACE;
        par = rr(3) ? 10 + rr(60) : 0;
        pay = rr(50);
        sc = rr(20);
        syn_mis(mp, kind, words[m], st, fl, first, syn.nobj - first, par, pay, sc);
    }
    syn_pack();
}

static long st_state[6], st_done, st_fail, st_op[OP_N];

static int fuzz(u32 seed, int steps, u32 *hash_out)
{
    rng_s = seed ? seed : 1;
    gen_blob();
    level(0);
    int fails0 = fails;
    u32 hash = 2166136261u;
    struct { int i, k, state, mis, obj, spawned, tag; } hist[12];
    for (int i = 0; i < steps && !bad_inv; i++) {
        int k = rr(100);
        hist[i % 12] = (typeof(hist[0])){i, k, ms_run.state, ms_run.mis, ms_run.obj, ms_run.spawned, ms_run.tag};
        const MsPlace *p;
        if (k < 40) {
            frame(rr(3) ? 1 : 0);
        } else if (k < 52) {
            int t = ms_target();
            if (t >= 0 && (p = ms_place(t)) != 0 && rr(4)) {
                int jx = rr(200) - 100, jy = rr(300), jz = rr(200) - 100;
                s2f.pos = v3(p->x8 * 128 + jx, p->h + jy, p->y8 * 128 + jz);
            } else {
                int qx = rr(70 * 1024), qy = rr(3) ? 0 : rr(14000), qz = rr(100 * 1024);
                s2f.pos = v3(qx, qy, qz);
            }
            s2f.speed = rr(3) ? 0 : rr(2000);
            s2f.airborne = rr(2);
        } else if (k < 56) {
            s2f.mode = rr(3);
        } else if (k < 68) {
            static const int evs[] = {EV_STUNT, EV_KILL, EV_LAND, EV_DEATH, EV_SPACE, EV_DOCK, EV_TALK, EV_ARWING_DOWN, EV_FOE_DOWN, EV_PICKUP, EV_MODE};
            int ev = evs[rr(11)];
            int ea = rr(200), eb = rr(30);
            if (ev == EV_KILL) {
                int cell = rr(128) << 7, tg = rr(100);
                cell |= rr(128);
                ea = rr(2) ? 0x5000 + tg : cell;
                eb = rr(3) == 0 ? EVK_BOX : eb;
            }
            ms_ev(ev, ea, eb);
            s2_ev(EV_NONE, 0, 0);
        } else if (k < 74) {
            if (rr(2) && n_own < 20) {
                int id = 0x40 + n_own, kind = rr(4) == 0 ? PBG_GOTO : rr(2) ? PBG_PHONE : PBG_PHONE_RED;
                pbm_add_own(id, kind);
                own_ids[n_own++] = id;
            } else if (n_own > 1) {
                pbm_del_own(own_ids[n_own - 1]);
                n_own--;
            }
        } else if (k < 78) {
            pbm.respawn = rr(3) ? 0 : 80;
        } else if (k < 80) {
            s2f.paused = rr(2);
        } else if (k < 82) {
            for (int e = 0; e < PBM_NENT; e++)
                if (*(s32 *)(pbm.ent[e] + PBE_TAG) >= 0 && rr(2))
                    *(s16 *)(pbm.ent[e] + PBE_HEALTH) = rr(2) ? 0 : 50;
        } else if (k < 92) {
            int c = 1 + rr(9);
            int r = ms_dbg(c, c == 1 || c == 6 ? rr(10) : c == 8 ? rr(15) : rr(2));
            if (c != 8 && c != 4 && c != 5)
                hash = (hash ^ (u32)r) * 16777619u;
            if (c == 8 || c == 4)
                hash = (hash ^ (u32)r) * 16777619u, r = 0;            /* (goal ids and the autopilot flag go on across runs) */
            if (r == -1 && c != 8 && c != 1 && c != 6)
                inv("dbg %d answered -1", c);
        } else if (k < 94) {
            ms_arm(rr(10));
        } else if (k < 95) {
            ms_abort();
        } else if (k < 96) {
            pbm.level_end = rr(2) ? 0 : 2 + rr(2);
        } else if (k < 97) {
            for (int j = 0; j < 40 && pbm.ngoals < PB_NGOAL_MAX - 2 && n_own < 30; j++) {
                pbm_add_own(0x200 + n_own, PBG_HIDDEN_PICKUP);
                own_ids[n_own] = 0x200 + n_own;
                n_own++;
            }
        } else if (k < 98) {
            pbm.level_end = 0;
            int m = rr(2) ? 0 : 3;
            for (int e = 0; e < PBM_NENT; e++)
                *(s32 *)(pbm.ent[e] + PBE_TAG) = -1, *(s16 *)(pbm.ent[e] + PBE_HEALTH) = 0;
            pbm.ngoals = 0, pbm.ncmd = 0;
            n_own = 0;
            own_ids[n_own++] = 1;
            pbm_add_own(1, PBG_LEVEL);
            for (int j = 0; j < 8; j++)
                pbm_foe[j].tag = -1, pbm_foe[j].n = 0;
            s2f.map = m;
            ms_level_enter(m);
        } else {
            frame(1);
        }
        if (s2f.paused && rr(3) == 0)
            s2f.paused = 0;
        if (rr(7) == 0) {
            memset(pbm_page, 0xAB, sizeof pbm_page);
            hl_draw();
            for (int y = 0; y < 160; y++)             /* (only the card's rows 98..116 and the line's 115..125 are ever touched) */
                for (int x = 0; x < 240; x++)
                    if (pbm_page[y * 240 + x] != 0xAB && (y < 98 || y > 125))
                        inv("hl_draw touched (%d, %d)", x, y);
        }
        if (getenv("TRACE") && i >= atoi(getenv("TRACE")) && i < atoi(getenv("TRACE")) + 12) {
            printf("  [%d] k=%d -> state %d mis %d obj %d op %d spawned %x tag %x ents", i, k, ms_run.state, ms_run.mis, ms_run.obj, ms_obj(ms_run.obj) ? ms_obj(ms_run.obj)->op : -1, ms_run.spawned, ms_run.tag);
            for (int e2 = 0; e2 < 4; e2++)
                printf(" %x", *(s32 *)(pbm.ent[e2] + PBE_TAG));
            printf("\n");
        }
        if (rr(3) == 0)
            check_inv();
        hash = (hash ^ (u32)ms_run.state ^ (u32)ms_run.obj << 3 ^ (u32)ms_run.count << 9) * 16777619u;
        if (ms_run.state < 6)
            st_state[ms_run.state]++;
        if (ms_run.state == MS_RUN && ms_obj(ms_run.obj))
            st_op[ms_obj(ms_run.obj)->op]++;
    }
    st_done += pbm_evs[EV_MIS_DONE], st_fail += pbm_evs[EV_MIS_FAIL];
    if (bad_inv) {
        printf("seed %u: %s\n", seed, why);
        if (getenv("VERBOSE"))
            for (int j = 1; j <= 12 && j <= steps; j++) {
                int at = (steps + 24 - j) % 12;
                (void)at;
            }
        for (int j = 0; j < 12; j++)
            if (getenv("HIST"))
                printf("  step %d action %d before: state %d mis %d obj %d spawned %x tag %x\n", hist[j].i, hist[j].k, hist[j].state, hist[j].mis, hist[j].obj, hist[j].spawned, hist[j].tag);
    }
    if (hash_out)
        *hash_out = hash;
    return fails == fails0 && !bad_inv;
}

static void case_fuzz(void)
{
    for (u32 seed = 1; seed <= 8; seed++) {
        u32 h;
        ckf(fuzz(seed * 2654435761u, 10000, &h), "fuzz seed %u: 10000 steps, every invariant held", seed);
    }
    int ops = 0;
    for (int i = 0; i < OP_N; i++)
        ops += st_op[i] > 0;
    printf("fuzz coverage: %ld missions done, %ld failed; frames idle/armed/run/done/fail/paused %ld/%ld/%ld/%ld/%ld/%ld; %d of %d ops ran\n",
           st_done, st_fail, st_state[0], st_state[1], st_state[2], st_state[3], st_state[4], st_state[5], ops, OP_N - 1);
    ck(st_done > 20 && st_fail > 20 && st_state[MS_PAUSED] > 100 && ops > 25, "the fuzz reached missions finished, failed, paused, and most ops");
}

int main(int argc, char **argv)
{
    setvbuf(stdout, 0, _IOLBF, 0);
    FILE *f = fopen(argc > 1 ? argv[1] : "demo.bin", "rb");
    if (!f) {
        printf("no blob\n");
        return 2;
    }
    size_t n = fread(s2_blob_store, 1, 1 << 16, f);
    fclose(f);
    if (argc > 2) {                                // a golden trace
        if (!strcmp(argv[2], "act1")) trace_act1();
        else if (!strcmp(argv[2], "ring")) trace_ring();
        else if (!strcmp(argv[2], "timeout")) trace_timeout();
        else if (!strcmp(argv[2], "fuzz")) {
            u32 h;
            fuzz(2654435761u, 10000, &h);
            printf("hash %08x\n", h);
        }
        return 0;
    }
    ckf(n > 56, "the demo blob has %zu bytes", n);
    case_demo();
    case_roam();
    case_range();
    static u8 demo[1 << 16];
    memcpy(demo, s2_blob_store, 1 << 16);
    case_roam_chapter();
    memcpy(s2_blob_store, demo, 1 << 16);
    case_phone();
    case_carry();
    case_end();
    case_full_and_bad();
    case_ops();
    memcpy(s2_blob_store, demo, 1 << 16);
    case_dbg();
    case_hud();
    case_fixes();
    case_fuzz();
    printf("%d checks, %d failed\n", checks, fails);
    printf("%s\n", fails ? "FAILED" : "ALL PASS");
    return fails != 0;
}
