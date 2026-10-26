/* The Fox Campaign (stage 2, P; campaign.h): which chapter and act the player is in, Payback's level held open until
   the acts it carries are done, the next level, travel, unlocks, and the progress image with its saving. The mission
   engine (mission.c) runs the acts; this decides which one is armed and what finishing it means. With no campaign
   started nothing here does anything: every map plays as before.
   Payback's level ends when its kind-0 goal (the score target) is reached: while acts are left that goal's target
   is raised out of reach each frame, and when the last act is done it is put back at what the score is, so the
   level completes by Payback's own road (a story level's trophy, "Press select", the slideshow). */
#include "stage2.h"
#include "mission.h"
#include "campaign.h"
#include "save.h"
#include "spacegame.h"
#include "hudline.h"
#include "draw2d.h"
#include "render.h"
#include "palette.h"

#define INK COLOR(M_CREAM, 3, 0)
#define HI COLOR(M_ACCENT, 3, 0)
#define TITLE COLOR(M_GLOW, 3, 0)
#define DIM COLOR(M_STEEL, 1, 0)
#define PANEL COLOR(M_ROAD, 0, 0)
#define HELP COLOR(M_STEEL, 3, 0)

#define HOLD_A 0x7fffffff          /* a score target nobody reaches */
#define REL_WAIT 60                /* Payback's clock (30 a second): the act's banner is read before the level ends */
#define REL_FALLBACK 90            /* ... and a level that has not ended by then is ended by e08 */
#define PULSE 3                    /* ticks SELECT is held in 16 when travelling through "Press select" */

Prog cp_prog;

static struct {
    s32 hold_a;                    /* the level's own score target, seen under the hold */
    u32 rel_at;                    /* PB_CLOCK when the last act of the level was done */
    s16 trophy[6];                 /* PB_TROPHIES when a travel began */
    s8 chap, tgt;                  /* the chapter this level is of (-1: none, free play); where travel goes (-1: nowhere) */
    u8 loaded, hold, seen, gi;     /* the progress is in; the hold is on; a kind-0 goal was seen; its index */
    u8 rel, trav, snap, drop;      /* releasing; travel: 1 level end to be forced; trophies were snapshot; the orbital drop runs */
    u8 sub, pulse;
    u8 q, cur, top, at;            /* the quick menu: page, line, first line shown, the code's letter */
    u8 confirm, main_ok;           /* "A again" asked; the hangar's main menu is up (the menu may open) */
    u8 sv;                         /* 0 nothing, 1 saving, 2 saved, 3 failed */
    u8 proved;                     /* the chip was asked to prove itself 64 Kbit (once a boot: it writes) */
    u16 saved_crc;
    u32 sv_t;                      /* (the tick a save ended: a u32 like s2f.ticks, or the back-off ends after 45 minutes) */
    s32 m_arg, m_ret;              /* the last sf_menu question and answer (the harness reads them) */
    u8 pwi[PW_LEN];                /* the code being entered, as alphabet indices */
} C = {.chap = -1, .tgt = -1};
static SvW sw;
static SvPick spick;
enum { Q_OFF, Q_MAIN, Q_TRAVEL, Q_CODE, Q_ENTER };


static int on(void) { return cp_prog.flags & CPF_ON; }
int cp_active(void) { return on(); }

/* ---- the chapters ---- */
static int nchap(void) { int n = ms_nchap(); return n < CP_CHAPS ? n : CP_CHAPS; }
static const Chapter *chp(int c) { return c >= 0 && c < nchap() ? ms_chap(c) : 0; }

static int chap_find(int map, int story)
{
    for (int c = 0; c < nchap(); c++) {
        const Chapter *ch = ms_chap(c);
        if (!(ch->flags & CH_RESERVED) && ch->map == map && !(ch->flags & CH_STORY) == !story)
            return c;
    }
    return -1;
}

static int chap_of(int mis, int *rel)
{
    for (int c = 0; c < nchap(); c++) {
        const Chapter *ch = ms_chap(c);
        if (mis >= ch->mis0 && mis < ch->mis0 + ch->nmis) {
            *rel = mis - ch->mis0;
            return c;
        }
    }
    return -1;
}

/* the acts a Payback level of this chapter carries: a story city's first level the first `split`, the rest all of them */
static int acts_mask(const Chapter *ch, int sub)
{
    int n = ch->nact > 8 ? 8 : ch->nact, m = (1 << n) - 1;
    if ((ch->flags & CH_STORY) && sub == 0 && ch->split < n)
        m &= (1 << ch->split) - 1;
    return m;
}

static int left(int c, int sub) { return acts_mask(chp(c), sub) & ~cp_prog.acts[c]; }
static int chap_done(int c) { return !left(c, 1); }

static int ordinal(const Chapter *ch, int mis, int kind)
{
    int n = 0;
    for (int i = ch->mis0; i < mis; i++) {
        const MisDef *d = ms_def(i);
        n += d && d->kind == kind;
    }
    return n;
}

static int act_mis(const Chapter *ch, int i)
{
    for (int m = ch->mis0; m < ch->mis0 + ch->nmis; m++) {
        const MisDef *d = ms_def(m);
        if (d && d->kind == MK_ACT && d->act == i + 1)
            return m;
    }
    return -1;
}

/* the level now: its first act not done is armed, and the hold is on while this level has acts left */
static void arm_here(void)
{
    int c = C.chap;
    C.hold = c >= 0 && left(c, C.sub);
    if (!C.hold)
        return;
    int l = left(c, C.sub), i = 0;
    while (!(l >> i & 1))
        i++;
    int m = act_mis(chp(c), i);
    if (m >= 0)
        ms_arm(m);
}

static void unhold(void);

static void enter(int map)
{
    if (C.hold)
        unhold();                  /* (a campaign stopped or started over in the level: the target back where Payback had it) */
    C.hold = C.rel = C.seen = C.gi = 0;
    C.sub = PB_RAMPAGE ? 0 : PB_SUB;
    int c = on() ? chap_find(map, !PB_RAMPAGE) : -1;
    C.chap = c >= 0 && c <= cp_prog.chap_unlocked ? c : -1;       /* (a chapter not yet open is played free) */
    if (C.chap >= 0)
        cp_prog.chap_cur = C.chap;
    arm_here();
}

/* ---- the progress: in and out ---- */
void s2_progress_keep(void);
static void apply(void)            /* the image's own part of the game's state */
{
    sg_set_progress(cp_prog.sg);
    s2_progress_keep();            /* (or the next frame's check takes it for a stray write and puts the old one back) */
}

static void sync(void)
{
    sg_get_progress(cp_prog.sg);
    prog_seal(&cp_prog);
}

static void load(void)
{
    C.loaded = 1;
    C.tgt = -1;
    C.saved_crc = 0;
    if (sv_mode() == SV_64K && sv_load(&sv_eeprom, (u8 *)&cp_prog, sizeof cp_prog, &spick)) {
        if (prog_ok(&cp_prog)) {
            if (on())
                apply();       /* (a campaign that was stopped leaves what the player owns now alone) */
            C.saved_crc = sv_img_crc((u8 *)&cp_prog, sizeof cp_prog);
            return;
        }
        for (u8 *p = (u8 *)&cp_prog; p < (u8 *)&cp_prog + sizeof cp_prog; p++)
            *p = 0;            /* (whole but not ours to read, say a newer version's: nothing of it may switch the campaign on) */
    }
    spick.valid = 0;               /* (no good save: the image in the keep, if any, is a code that was typed in) */
}

/* the chip is only asked to prove it is 64 Kbit when the player first wants a save: it writes (save.c), and a game with no
   campaign must leave the player's file as it found it. Once a boot; 1 if blocks 64 and up are ours now */
static int prove(void)
{
    if (sv_mode() == SV_64K)
        return 1;
    if (!C.proved) {
        C.proved = 1;
        sv_prove();
    }
    return sv_mode() == SV_64K;
}

static void unsave(void)           /* the image changes under a save that is under way: it would not match its checksum */
{
    sw.busy = 0;
    C.sv = 0;
}

static void save_start(void)
{
    sync();
    sv_begin(&sw, (u8 *)&cp_prog, sizeof cp_prog, &spick);
    C.sv = 1;
}

/* a block a tick, in the hangar (nothing there moves) */
static void save_tick(void)
{
    if (sv_mode() != SV_64K || (!on() && !sw.busy))
        return;
    if (sw.busy) {
        int r = sv_step(&sv_eeprom, &sw, (u8 *)&cp_prog, sizeof cp_prog);
        if (r > 0)
            return;
        C.sv = r ? 3 : 2;
        C.sv_t = s2f.ticks;
        if (!r) {
            spick.seq = sw.seq, spick.slot = sw.slot, spick.valid = 1;
            C.saved_crc = sw.crc;
        }
        return;
    }
    if (!on())
        return;
    if (C.sv == 3 && s2f.ticks - C.sv_t < 600)
        return;                    /* (a failed save is tried again every ten seconds, not every frame) */
    if (!(s2f.docked || st_active()) || (s2f.ticks & 31))
        return;
    sync();
    if (sv_img_crc((u8 *)&cp_prog, sizeof cp_prog) != C.saved_crc)
        save_start();
}

/* ---- what the mission engine asks ---- */
int cp_mis_done(int mis)
{
    int rel, c = chap_of(mis, &rel);
    const MisDef *d = ms_def(mis);
    if (c < 0 || !d || !on())
        return 0;
    if (d->kind == MK_ACT)
        return (unsigned)(d->act - 1) < 8 && (cp_prog.acts[c] >> (d->act - 1) & 1);
    int o = ordinal(chp(c), mis, d->kind);
    if (d->kind == MK_CHAL)
        return o < 16 && (cp_prog.chal[c] >> o & 1);
    return d->kind == MK_MEDAL && o < 8 && (cp_prog.medals[c] >> o & 1);
}

void cp_unlock(int what)
{
    if (what == CP_UNLOCK_QUARTERS || what == CP_UNLOCK_GHOST)
        cp_prog.story[1] |= 1 << (what - 1);
    else if (what >= 16)
        sg_unlock_paint(what - 16);
}

void cp_set(int flag, int value)
{
    if (flag < 1 || flag > 8)
        return;
    if (value)
        cp_prog.story[0] |= 1 << (flag - 1);
    else
        cp_prog.story[0] &= ~(1 << (flag - 1));
    if (flag == CP_FLAG_FINALE && value)
        cp_prog.ace = 1;
}

int cp_flag(int f) { return f >= 1 && f <= 8 && (cp_prog.story[0] >> (f - 1) & 1); }
int cp_unlocked(int what) { return what >= 1 && what <= 8 && (cp_prog.story[1] >> (what - 1) & 1); }
int cp_ace(void) { return on() && cp_prog.ace; }

/* ---- acts done ---- */
static void card_next(int c)
{
    static char t[40];
    char *p = t;
    for (const char *s = "CHAPTER COMPLETE\nNEXT: "; (*p = *s); s++, p++)
        ;
    const Chapter *n = chp(cp_prog.chap_unlocked);
    for (const char *s = n ? ms_text(n->title) : ""; *s && p < t + 38; s++)
        *p++ = *s;
    *p = 0;
    (void)c;
    hl_card(t, 90);
}

static void act_done(int c, int i)
{
    const Chapter *ch = chp(c);
    int was = chap_done(c);
    cp_prog.acts[c] |= 1 << i;
    if (!was && chap_done(c)) {
        int n = ch->next != 0xffff ? ch->next : c + 1;
        if (n < nchap() && !(ms_chap(n)->flags & CH_RESERVED) && n > cp_prog.chap_unlocked) {
            cp_prog.chap_unlocked = n;
            card_next(c);
        }
    }
    if (i == 0 && C.drop)
        pl_drop_end(), C.drop = 0;
    if (c != C.chap)
        return;
    if (left(c, C.sub)) {
        arm_here();
        return;
    }
    C.hold = 0;
    C.rel = 1, C.rel_at = PB_CLOCK;
}

static void mis_done(int mis, int secs)
{
    int rel, c = chap_of(mis, &rel);
    const MisDef *d = ms_def(mis);
    if (c < 0 || !d || !on())
        return;
    Prog *p = &cp_prog;
    int o = ordinal(chp(c), mis, d->kind);
    switch (d->kind) {
    case MK_ACT:
        if ((unsigned)(d->act - 1) < 8)
            act_done(c, d->act - 1);
        break;
    case MK_CONTRACT:
        if (p->contracts[c] < 255)
            p->contracts[c]++;
        break;
    case MK_CHAL:
        if (o < 16) {
            if (p->chal[c] >> o & 1)
                sg_give(25 - d->pay);          /* (Payback paid the full price; a second time is 25) */
            p->chal[c] |= 1 << o;
        }
        st_chal_done(c, o);
        if (o < 5) {
            u16 *b = &p->best[c * 5 + o];
            u32 t = secs > 6000 ? 60000 : secs * 10;
            if (!*b || t < *b)
                *b = t;
        }
        break;
    case MK_MEDAL:
        if (o < 8)
            p->medals[c] |= 1 << o;
        break;
    }
}

void cp_ev(int ev, int a, int b)
{
    if (ev == EV_MIS_DONE)
        mis_done(a, b);
    else if (ev == EV_SPACE && !a && C.drop)
        pl_drop_end(), C.drop = 0;     /* (below the edge of space: the city is the world again) */
}

/* ---- Payback's level: the hold and the release ---- */
static int goal_zero(void)             /* the index of the kind-0 goal, or -1 */
{
    int n = PB_NGOALS;
    if (n > PB_NGOAL_MAX)
        n = PB_NGOAL_MAX;
    if (C.gi < n && !*pb_goal_w(C.gi, PBG_KIND))
        return C.gi;
    for (int i = 0; i < n; i++)
        if (!*pb_goal_w(i, PBG_KIND))
            return C.gi = i;
    return -1;
}

static void unhold(void)
{
    int i = C.seen ? goal_zero() : -1;
    if (i >= 0 && *pb_goal_w(i, PBG_A) == HOLD_A)
        *pb_goal_w(i, PBG_A) = C.hold_a;
}

static void hold_goal(void)
{
    int i = goal_zero();
    if (i < 0)
        return;
    volatile s32 *a = pb_goal_w(i, PBG_A);
    if (*a != HOLD_A) {                /* (first sight, or another writer put its target back: ours now) */
        C.hold_a = *a;
        *a = HOLD_A;
    }
    C.seen = 1;
}

static void release_tick(void)
{
    if (PB_LEVEL_END) {
        C.rel = 0;
        return;
    }
    u32 t = PB_CLOCK - C.rel_at;
    if (C.rel == 1 && t >= REL_WAIT) {
        int i = C.seen ? goal_zero() : -1;
        if (i < 0) {
            PB_LEVEL_END = 3;          /* (never saw it, or it is gone: the level ends by our word) */
            C.rel = 0;
            return;
        }
        int s = pb_get_score();
        *pb_goal_w(i, PBG_A) = s < C.hold_a ? s : C.hold_a;
        C.rel = 2;
    } else if (C.rel == 2 && t >= REL_FALLBACK) {
        PB_LEVEL_END = 3;
        C.rel = 0;
    }
}

/* ---- the next level ---- */
static int level_of(int c, int story_sub)
{
    const Chapter *ch = chp(c);
    PB_WAS_RAMPAGE = 0;
    PB_RAMPAGE = !(ch->flags & CH_STORY);
    if (PB_RAMPAGE)
        PB_MAP = ch->map;
    return ch->map * 2 + story_sub;
}

static int first_sub(int c)            /* the level of a chapter to begin at: a story city's second if the first has nothing left */
{
    return (chp(c)->flags & CH_STORY) && !left(c, 0) && left(c, 1);
}

static int menu_pick(void)
{
    int end = PB_LEVEL_END, c = C.chap;
    if (end == 3 && C.tgt >= 0 && C.tgt < nchap() && C.tgt <= cp_prog.chap_unlocked)
        return level_of(C.tgt, first_sub(C.tgt));
    if (c < 0 || (end != 2 && end != 3))
        return -1;
    const Chapter *ch = chp(c);
    int story = ch->flags & CH_STORY;
    if (end == 2)
        return level_of(c, story ? C.sub : 0);       /* a game over: this level again */
    if (story && C.sub == 0)
        return level_of(c, 1);                       /* (what is left of the first level's acts goes on to the second) */
    if (left(c, 1))
        return level_of(c, story ? C.sub : 0);       /* ended by something else with acts left: again */
    int n = ch->next != 0xffff ? ch->next : c + 1;
    if (n < nchap() && n <= cp_prog.chap_unlocked && !(ms_chap(n)->flags & CH_RESERVED))
        return level_of(n, first_sub(n));
    return -1;                                       /* (the end of the campaign: Payback's own menu) */
}

int cp_menu(int arg)
{
    C.m_arg = arg;
    C.m_ret = on() ? menu_pick() : -1;
    return C.m_ret;
}

/* travel: a rampage level can be left at any time (the level is ended, SELECT is pressed for the player through the
   "Press select" screen, and the trophies that ending paid go back); a story level only when it ends of itself, so the
   place is booked and cp_menu takes it there */
int cp_travel(int c)
{
    if (!on() || !chp(c) || c > cp_prog.chap_unlocked || (chp(c)->flags & CH_RESERVED))
        return 0;
    C.tgt = c;
    if (C.trav)
        return 1;                  /* (asked twice: the trophies of the first ask are the ones to put back, not what the ending paid) */
    if (PB_RAMPAGE || PB_LEVEL_END == 3) {
        for (int i = 0; i < 6; i++)
            C.trophy[i] = PB_TROPHIES[i];
        C.snap = 1;
        C.trav = 1;
        return 1;
    }
    return 2;
}

u32 cp_keys(void)
{
    if (!C.trav || PB_LEVEL_END != 3)
        return 0;
    return (C.pulse++ & 15) < PULSE ? 1u << B_SELECT | 1u << B_SELECT2 : 0;
}

/* ---- the level is entered ---- */
void cp_level_enter(int map)
{
    if (!C.loaded)
        load();
    if (C.snap)
        for (int i = 0; i < 6; i++)
            PB_TROPHIES[i] = C.trophy[i];
    C.snap = C.trav = 0;
    C.tgt = -1;
    if (C.drop)
        pl_drop_end();
    C.drop = 0;
    enter(map);
    const Chapter *ch = chp(C.chap);
    if (ch && (ch->flags & CH_DROP) && !(cp_prog.acts[C.chap] & 1) && !C.sub) {
        s2_dock_start();               /* act 1 is the way down from the station: launch, dive, land */
        pl_drop_begin(ch->map, ch->hx2, ch->hy2);
        C.drop = 1;
    }
}

void cp_tick(void)
{
    if (!C.loaded)
        return;
    if (!s2f.paused) {
        if (C.hold)
            hold_goal();
        if (C.rel)
            release_tick();
        if (C.trav == 1 && !PB_LEVEL_END && PB_RESPAWN <= 0)
            PB_LEVEL_END = 3;
    }
    save_tick();
}

int cp_act_running(void)
{
    return C.drop;
}

/* ---- the quick menu (in the hangar: L opens it) ---- */
static const char *msg;            /* a line of news for the player, a few seconds under the menu's place (ROM text) */
static u32 msg_end;
static void note(const char *s) { msg = s, msg_end = s2f.ticks + 180; }

static void camp_start(int reset)
{
    if (!nchap()) {
        note("NO CAMPAIGN DATA IN THIS ROM");
        return;
    }
    unsave();
    prove();
    if (reset || !prog_ok(&cp_prog)) {
        for (u8 *p = (u8 *)&cp_prog; p < (u8 *)&cp_prog + sizeof cp_prog; p++)
            *p = 0;
        cp_prog.flags = CPF_ON;
    } else
        cp_prog.flags |= CPF_ON;       /* (a stopped campaign goes on where it was) */
    sg_get_progress(cp_prog.sg);       /* (what you own stays yours) */
    prog_seal(&cp_prog);
    enter(s2f.map);
    note(C.chap >= 0 ? "CAMPAIGN STARTED" : "CAMPAIGN STARTED: TRAVEL TO A CHAPTER");
}

/* the campaign stops: nothing is erased (START CAMPAIGN takes it up again), and the stop is saved, or the next boot would
   switch it on again */
static void camp_stop(void)
{
    cp_prog.flags &= ~CPF_ON;
    unsave();
    enter(s2f.map);
    sync();                        /* (sealed: START CAMPAIGN takes up a whole image, and only a sealed one) */
    if (sv_mode() == SV_64K)
        save_start();
    note("CAMPAIGN STOPPED");
}

_Static_assert(__builtin_offsetof(SgProgress, missiles) == 12 && sizeof(SgProgress) == 32, "SgProgress");

int cp_pw_apply(const char *s)
{
    Prog t;
    SgProgress cur;
    C.tgt = -1;
    if (!pw_decode(s, &t) || !nchap())
        return 0;
    unsave();
    prove();
    sg_get_progress(&cur);             /* (a code has no stick, aim, missiles, jobs or paint: those stay the player's) */
    for (int i = 12; i < 16; i++)      /* (missiles, paint, jobs, flags: SgProgress's last four) */
        t.sg[i] = ((u8 *)&cur)[i];
    cp_prog = t;
    cp_prog.flags |= CPF_ON | CPF_PW;
    prog_seal(&cp_prog);
    apply();
    enter(s2f.map);
    return 1;
}

void cp_open(void)
{
    C.q = Q_MAIN, C.cur = C.top = C.confirm = 0;
}

void cp_open_at(int line)
{
    C.q = Q_MAIN, C.cur = line, C.top = C.confirm = 0;
    if (line == 2) {                   /* (the station's SAVE...: one press does it, the menu stays up to show how it went) */
        if (!on())
            note("START THE CAMPAIGN FIRST");
        else if (!prove())
            note("NO SAVE CHIP: USE THE CODE");
        else if (!sw.busy)
            save_start(), note("SAVING...");
    } else if (line == 3 && on())
        C.q = Q_CODE;
    else if (line == 4 && !on())
        C.q = Q_ENTER, C.at = 0;
}

int cp_dock_keys(u16 hit, u16 keys, int main_ok)
{
    (void)keys;
    C.main_ok = main_ok;
    if (!C.q) {
        if (main_ok && (hit & KEY_L) && !st_active())     /* (in the station's rooms the walker's L is its own quick menu, which opens ours) */
            cp_open();
        return C.q != 0;
    }
    int n = C.q == Q_MAIN ? 7 : C.q == Q_TRAVEL ? cp_prog.chap_unlocked + 1 : 0;
    if (n > nchap())
        n = nchap();
    if (C.q == Q_ENTER) {
        u8 *l = &C.pwi[C.at];
        if (hit & KEY_UP) *l = (*l + 1) & 31;
        if (hit & KEY_DOWN) *l = (*l + 31) & 31;
        if (hit & (KEY_RIGHT | KEY_R)) C.at = (C.at + 1) % PW_LEN;
        if (hit & (KEY_LEFT | KEY_L)) C.at = (C.at + PW_LEN - 1) % PW_LEN;
        if (hit & KEY_B)
            C.q = Q_MAIN, C.cur = 4;
        if (hit & KEY_A) {
            char s[PW_LEN + 1];
            for (int i = 0; i < PW_LEN; i++)
                s[i] = PW_ALPHA[C.pwi[i]];
            s[PW_LEN] = 0;
            if (cp_pw_apply(s)) {
                note("CODE ACCEPTED");
                C.q = Q_MAIN, C.cur = 0;
            } else
                note("THAT CODE IS NOT RIGHT");
        }
        return 1;
    }
    if (C.q == Q_CODE) {
        if (hit & (KEY_B | KEY_A))
            C.q = Q_MAIN, C.cur = 3;
        return 1;
    }
    if (hit & KEY_UP)
        C.cur = C.cur ? C.cur - 1 : n - 1, C.confirm = 0;
    if (hit & KEY_DOWN)
        C.cur = C.cur + 1 < n ? C.cur + 1 : 0, C.confirm = 0;
    C.top = C.cur < C.top ? C.cur : C.cur > C.top + 5 ? C.cur - 5 : C.top;
    if (hit & (KEY_B | KEY_L)) {
        if (C.q == Q_TRAVEL)
            C.q = Q_MAIN, C.cur = 1;
        else
            C.q = Q_OFF;
        C.confirm = 0;
        return C.q != 0;
    }
    if (!(hit & KEY_A))
        return 1;
    if (C.q == Q_TRAVEL) {
        int r = cp_travel(C.cur);
        note(r == 1 ? "TRAVELLING..." : r == 2 ? "BOOKED: GO WHEN THIS LEVEL ENDS" : "NOT YET OPEN");
        if (r == 1)
            C.q = Q_OFF;
        return 1;
    }
    switch (C.cur) {
    case 0:
        if (on() && !C.confirm)
            C.confirm = 1;
        else
            camp_start(C.confirm), C.confirm = 0, C.q = Q_OFF;
        break;
    case 1:
        if (!on())
            note("START THE CAMPAIGN FIRST");
        else
            C.q = Q_TRAVEL, C.cur = C.top = cp_prog.chap_cur < nchap() ? cp_prog.chap_cur : 0;
        break;
    case 2:
        if (!on())
            note("START THE CAMPAIGN FIRST");
        else if (!prove())
            note("NO SAVE CHIP: USE THE CODE");
        else if (!sw.busy)
            save_start(), note("SAVING...");
        break;
    case 3:
        if (on())
            C.q = Q_CODE;
        else
            note("START THE CAMPAIGN FIRST");
        break;
    case 4:
        if (on() && !C.confirm)        /* (a code replaces the campaign that is running, and its save with it) */
            C.confirm = 1;
        else
            C.q = Q_ENTER, C.at = 0, C.confirm = 0;
        break;
    case 5:
        if (on())
            camp_stop();
        else
            note("NO CAMPAIGN IS RUNNING");
        C.q = Q_OFF;
        break;
    default:
        C.q = Q_OFF;
    }
    return 1;
}

u32 cp_sig(void)
{
    return C.q | C.cur << 4 | C.top << 8 | C.at << 12 | C.confirm << 16 | C.sv << 17 | C.pwi[C.at] << 20 | (u32)on() << 26 |
           (u32)(msg && s2f.ticks < msg_end) << 27 | ((u32)msg & 0xff) << 28;
}

static void code_text(char *l1, char *l2)   /* the code as two lines: "ABCD EFGH" and "JKLM NPQR" */
{
    char c[PW_LEN + 1];
    sync();
    pw_encode(&cp_prog, c);
    for (int i = 0; i < PW_LEN / 2; i++) {
        char *o = i < 4 ? l1 + i : l1 + i + 1, *o2 = i < 4 ? l2 + i : l2 + i + 1;
        *o = c[i], *o2 = c[i + 8];
    }
    l1[4] = l2[4] = ' ';
    l1[9] = l2[9] = 0;
}

static int news_draw(int y)          /* the line of news, if there is one now: under the menu when it is open */
{
    if (!msg || s2f.ticks >= msg_end)
        return 0;
    int w = 0;
    while (msg[w])
        w++;
    d_fill(4, y, w * TEXT_W + 8, 12, PANEL);
    d_text(8, y + 2, msg, INK);
    return 1;
}

void cp_hud(void)
{
    if (!C.q) {
        int news = news_draw(124);
        if (!news && C.main_ok && s2f.docked && !st_active())
            d_text(8, 127, "L: CAMPAIGN", HELP);
        return;
    }
    char b[48], *p;
    const int x = 8, y0 = 40, w = 152;
    d_fill(x - 4, y0 - 3, w, 96, PANEL);
    d_hline(x - 4, x + w - 5, y0 + 9, DIM);
    d_text(x, y0, C.q == Q_TRAVEL ? "TRAVEL" : C.q == Q_CODE ? "YOUR CODE" : C.q == Q_ENTER ? "ENTER CODE" : "FOX CAMPAIGN", TITLE);
    if (C.q == Q_MAIN) {
        static const char *const it[] = {"START CAMPAIGN", "TRAVEL", "SAVE NOW", "SHOW CODE", "ENTER CODE", "STOP CAMPAIGN", "BACK"};
        for (int i = 0; i < 7; i++) {
            const char *s = i == 0 && on() ? (C.confirm ? "A AGAIN: START OVER" : "START OVER") :
                            i == 0 && cp_prog.magic == PROG_MAGIC ? "CONTINUE CAMPAIGN" :
                            i == 4 && on() && C.confirm ? "A AGAIN: REPLACE" : it[i];
            if (i == C.cur)
                d_text(x - 2, y0 + 12 + i * 10, ">", HI);
            d_text(x + 6, y0 + 12 + i * 10, s, i == C.cur ? HI : INK);
        }
        const Chapter *ch = on() ? chp(cp_prog.chap_cur) : 0;
        if (ch) {
            p = d_cat(b, "CH ");
            p = d_num(p, cp_prog.chap_cur + 1);
            p = d_cat(p, " ");
            d_cat(p, ms_text(ch->title));
        } else
            d_cat(b, "NOT STARTED");
        d_text(x, y0 + 84, b, HELP);
        d_text(x + 84, y0, sv_mode() == SV_64K ? (C.sv == 1 ? "SAVING" : C.sv == 2 ? "SAVED" : C.sv == 3 ? "SAVE FAILED" : "EEPROM") : "CODE ONLY", HELP);
    } else if (C.q == Q_TRAVEL) {
        int n = cp_prog.chap_unlocked + 1;
        for (int i = C.top; i < n && i < nchap() && i < C.top + 6; i++) {
            const Chapter *ch = chp(i);
            int y = y0 + 12 + (i - C.top) * 10;
            p = d_num(b, i + 1);
            p = d_cat(p, " ");
            p = d_cat(p, ms_text(ch->title));
            if (chap_done(i))
                d_cat(p, " *");
            if (i == C.cur)
                d_text(x - 2, y, ">", HI);
            d_text(x + 6, y, b, i == C.cur ? HI : INK);
        }
        d_text(x, y0 + 84, PB_RAMPAGE ? "A: GO NOW  B: BACK" : "A: GO WHEN LEVEL ENDS", HELP);
    } else if (C.q == Q_CODE) {
        char t1[10], t2[10];
        code_text(t1, t2);
        d_text(x + 6, y0 + 20, t1, TITLE);
        d_text(x + 6, y0 + 32, t2, TITLE);
        d_text(x, y0 + 50, "WRITE IT DOWN: IT BRINGS", INK);
        d_text(x, y0 + 60, "THE CAMPAIGN BACK", INK);
        d_text(x, y0 + 84, "B: BACK", HELP);
    } else {
        for (int i = 0; i < PW_LEN; i++) {
            int cx = x + 6 + (i % 8) * 14 + (i % 8 >= 4) * 6, cy = y0 + 22 + (i / 8) * 14;
            char s[2] = {PW_ALPHA[C.pwi[i]], 0};
            d_text(cx, cy, s, i == C.at ? HI : INK);
            if (i == C.at)
                d_hline(cx - 1, cx + 6, cy + 9, HI);
        }
        d_text(x, y0 + 54, "UP DOWN: LETTER", INK);
        d_text(x, y0 + 64, "LEFT RIGHT: MOVE", INK);
        d_text(x, y0 + 84, "A: OK  B: BACK", HELP);
    }
    news_draw(137);
}

/* ---- the debug mailbox: 16 start (arg 1: off, 2: over, 3: look again, 4: stop and save) 17 state 18 acts of a chapter (arg: chapter << 8 | bits) 19 travel 20 save
   21 the last menu question and answer 22 the code 23 reload as after a power cycle 24 unlock to arg 25 an act done
   (arg: the mission) 26 keys into the quick menu 27 the pending save's state 28 credits given ---- */
int cp_dbg(int cmd, int arg)
{
    switch (cmd) {
    case 16:
        if (arg == 1) {
            cp_prog.flags &= ~CPF_ON;
            enter(s2f.map);
        } else if (arg == 3)
            enter(s2f.map);
        else if (arg == 4)
            camp_stop();
        else
            camp_start(arg == 2);
        return on();
    case 17:
        if (arg >= 32 && arg < 32 + CP_CHAPS)
            return cp_prog.acts[arg - 32];
        switch (arg) {
        case 0: return cp_prog.flags;
        case 1: return C.chap;
        case 2: return cp_prog.chap_unlocked;
        case 3: return C.chap >= 0 ? cp_prog.acts[C.chap] : -1;
        case 4: return C.hold | C.rel << 1 | C.trav << 3 | C.drop << 5 | C.seen << 6;
        case 5: return C.hold_a;
        case 6: return sg_credits();
        case 7: return C.sv | sw.busy << 4 | sw.k << 8;
        case 8: return sv_mode();
        case 9: return spick.valid ? spick.seq | spick.slot << 16 | 1 << 17 : 0;
        case 10: return C.tgt;
        case 11: return C.q | C.cur << 4;
        case 12: return cp_prog.chap_cur;
        case 13: return cp_prog.ace;
        case 14: return C.sub;
        case 15: return C.loaded;
        case 16: {                 /* what the Arwing keeps that a code does not carry: flags, missiles, paint, jobs */
            SgProgress c;
            sg_get_progress(&c);
            return c.flags | c.missiles << 8 | c.paint << 16 | c.jobs << 24;
        }
        case 17: return C.confirm | C.proved << 1 | sw.busy << 2;
        }
        return -1;
    case 18:
        if ((arg >> 8) >= CP_CHAPS)
            return -1;
        cp_prog.acts[arg >> 8] = arg;
        if (C.chap == arg >> 8)
            arm_here();
        return cp_prog.acts[arg >> 8];
    case 19:
        return cp_travel(arg);
    case 20:
        if (!prove())
            return -1;
        save_start();
        return 0;
    case 21:
        return arg ? C.m_ret : C.m_arg;
    case 22: {
        char c[PW_LEN + 1];
        sync();
        pw_encode(&cp_prog, c);
        return arg >= 0 && arg < PW_LEN / 4 ? c[arg * 4] | c[arg * 4 + 1] << 8 | c[arg * 4 + 2] << 16 | c[arg * 4 + 3] << 24 : -1;
    }
    case 23:
        for (u8 *p = (u8 *)&cp_prog; p < (u8 *)&cp_prog + sizeof cp_prog; p++)
            *p = 0;
        sw.busy = 0;
        spick.valid = 0;
        C.loaded = 0;
        load();
        return on() | cp_prog.chap_unlocked << 1;
    case 24:
        cp_prog.chap_unlocked = arg;
        return arg;
    case 25:
        mis_done(arg, 30);
        return cp_prog.acts[C.chap < 0 ? 0 : C.chap];
    case 26:
        return cp_dock_keys(arg, arg, 1);
    case 27:
        return C.sv | sw.busy << 4;
    case 28:
        sg_give(arg);
        return sg_credits();
    }
    return -1;
}
