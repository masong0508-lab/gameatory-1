/* See settings.h. */
#include "settings.h"
#include "draw2d.h"
#include "spacegame.h"
#include "tex.h"
#include "spacewalk.h"

extern u16 car_vmax_k, car_grip_k;     /* car.c, 256 = as built */
extern u16 ship_speed_k;               /* ship.c */
extern u8 sg_shield_k;                 /* spacegame.c: quarters, 255 nothing hurts it */
extern u8 rag_grav_k, rag_bounce;      /* ragdoll.c */
extern u16 draw_k;                     /* citydraw.c: the city's reach, 256 = as built */
extern u8 view_cut, far_fs;           /* citydraw.c: the reach goes by building, not by sector; sectors of flat patches seen from the air */
extern u16 ent_far;                    /* merge.c: how far people and cars are drawn */
u8 traffic_add = 8;                    /* keyhook.s: Payback's cap on the people and cars it adds, + this - 8 */
extern u16 car_accel_k, car_steer_k, car_boost_k;   /* car.c, 256 = as built */
extern u16 car_drift_mu;               /* car.c: the rear grip at the full slide (175 as built) */
extern u8 car_grav_k, car_boost_inf;   /* car.c: gravity in quarters (4 as built); the jet never runs dry */
extern u8 sg_inf_missiles;             /* spacegame.c */
u16 cam_dflt = 256;                    /* merge.c: the chase camera's distance it settles at */
u16 prop_k = 256;                      /* world.h: trees, lamps and benches drawn out to this much of their reach */
u8 opt_tex = 1;                        /* merge.c: Payback's tiles on (tex_on) */
u8 opt_planet = 1;                     /* planet.c: the world a planet from up high (off: the flat slab and sky as ever) */
static u8 fps_show;
static u8 fps_now;

/* Payback's own */
#define PB_RAMPAGE (*(volatile u8 *)0x02001d39)      /* 1 in Rampage */
#define PB_DIFF (*(volatile u8 *)0x02001d3c)         /* RAMPAGE SETUP's difficulty, 0 very low .. 5 very high */
#define PB_WANTED (*(volatile s16 *)0x02001dc6)      /* wanted stars */
#define PB_LIVES (*(volatile s16 *)0x02001e4e)
#define PB_LEVEL_END (*(volatile s16 *)0x02001e08)   /* 3: the target was reached */
#define PB_RESPAWN (*(volatile s16 *)0x02001e0c)
#define PB_NGOALS (*(volatile s16 *)0x0201a7d8)
#define PB_GOALS ((volatile s32 *)0x0201a7e0)        /* goal 0 in Rampage: kind 0, its word 2 the target score */
#define PB_MAN ((u8 *)0x02009394)
#define E_HEALTH 0x68
#define E_SCORE 0x90
#define PB_SFX ((void (*)(int, int))0x0807702d)      /* its menus' sounds: 0x20 the cursor, 0x21 a pick */
#define SFX_MOVE() PB_SFX(0x20, 0x3bbe)
#define SFX_PICK() PB_SFX(0x21, 0x3400)

enum { O_TARGET, O_TIME, O_DIFF, O_WANTED, O_LIVES, O_DAMAGE, O_SCORE,
       O_CARSPD, O_ACCEL, O_GRIP, O_DRIFT, O_STEER, O_CGRAV, O_BOOSTK, O_UNLIM,
       O_SHIPSPD, O_SHIELD, O_MISSILE, O_GRAV, O_BOUNCE, O_JET, O_CAMD, O_TICKER,
       O_SPEED, O_DRAW, O_TEX, O_PROPS, O_TRAFFIC, O_FPS, O_PLANET, O_N };
typedef struct {
    const char *name;
    const char *const *label;
    u8 n, def, word, shift, bits;
} Opt;

static const char *const l_target[] = {"Level's own", "50,000", "100,000", "250,000", "500,000", "750,000",
    "1,000,000", "1,500,000", "2,000,000", "3,000,000", "5,000,000", "7,500,000", "10,000,000", "25,000,000", "99,999,999"};
static const s32 v_target[] = {0, 50000, 100000, 250000, 500000, 750000, 1000000, 1500000, 2000000, 3000000,
    5000000, 7500000, 10000000, 25000000, 99999999};
static const char *const l_time[] = {"Off", "1 min", "2 min", "3 min", "4 min", "5 min", "7 min", "10 min",
    "15 min", "20 min", "30 min", "45 min", "60 min", "90 min", "120 min"};
static const u8 v_time[] = {0, 1, 2, 3, 4, 5, 7, 10, 15, 20, 30, 45, 60, 90, 120};
static const char *const l_diff[] = {"Setup's", "Very low", "Low", "Average", "Above average", "High", "Very high"};
static const char *const l_wanted[] = {"Never", "1 at most", "2 at most", "3 at most", "4 at most", "5 at most", "Normal"};
static const char *const l_lives[] = {"Level's own", "1", "2", "3", "5", "9", "Endless"};
static const u8 v_lives[] = {0, 1, 2, 3, 5, 9, 9};
static const char *const l_damage[] = {"None", "x0.25", "x0.5", "x0.75", "Normal", "x1.5", "x2", "x3"};
static const u8 v_damage[] = {0, 1, 2, 3, 4, 6, 8, 12};                 /* quarters */
static const char *const l_scale[] = {"x0.5", "x0.75", "Normal", "x1.25", "x1.5", "x2"};
static const u16 v_scale[] = {128, 192, 256, 320, 384, 512};
static const char *const l_shield[] = {"x0.5", "Normal", "x1.5", "x2", "x3", "Invincible"};
static const u8 v_shield[] = {2, 4, 6, 8, 12, 255};
static const char *const l_grav[] = {"Moon", "Low", "Normal", "Heavy", "x2"};
static const u8 v_grav[] = {1, 2, 4, 6, 8};                            /* quarters */
static const char *const l_bounce[] = {"Dead", "Normal", "Bouncy", "Superball"};
static const u8 v_bounce[] = {4, 0, 12, 15};                           /* sixteenths, 0 as it was */
static const char *const l_onoff[] = {"On", "Off"};
static const char *const l_speed[] = {"Normal", "Fast", "Fastest"};
/* Speed: Fast and Fastest give up, a step at a time and only while frames come at 25 a second or less (and back once they
   come fast again), what each row lists: the city's reach in 256ths, the trees' (of the Trees setting's), how far people
   and cars are drawn, how many fewer of them Payback adds, how far its tiles go on walls, on roofs and on the ground,
   and how many 8-cell sectors of flat patches are seen from the air. Row 0 is the game as it was. */
typedef struct { u16 view, prop, ent; s16 wall, roof, far; u8 cars, fs; } SpLv;
#define SP_FAST 7                  /* the last row Fast goes down to */
static const SpLv sp_tab[] = {
    {256, 256, 20000, TEX_WALL_FAR, 0x7fff, TEX_FAR, 0, 9},
    {256, 160, 14000, 3600, 5200, 4800, 2, 8},
    {220, 100, 11000, 2800, 3800, 3600, 3, 7},
    {185, 64, 9000, 2200, 3000, 2600, 4, 6},
    {155, 32, 7000, 1700, 2300, 1800, 4, 5},
    {130, 0, 5500, 1300, 1700, 1000, 4, 4},
    {105, 0, 4500, 900, 1200, 500, 4, 3},
    {80, 0, 3500, 400, 600, 250, 4, 2},
    {55, 0, 3000, 0, 0, 1, 4, 0},
    {40, 0, 3000, 0, 0, 1, 4, 0},
    {28, 0, 2000, 0, 0, 1, 4, 0},
};
#define SP_N (int)(sizeof sp_tab / sizeof *sp_tab)
static u8 sp_cap, sp_lv;           /* the deepest row allowed (0: Normal), the row in use */
static u16 sp_dk = 256, sp_pk = 256, sp_tr = 8;    /* the reach, trees and traffic the other settings ask for */
static u8 sp_n, sp_sum, sp_good, sp_wait = 3, sp_up;   /* frames and ticks in this look, calm looks, those to wait, raised lately */
static u8 sp_tw = 48;              /* the looks to wait before row 8 gives its tiles back (they come and go over the whole city) */
static const char *const l_draw[] = {"Near", "Normal", "Far", "Max"};
static const u16 v_draw[] = {180, 256, 332, 410};
static const char *const l_traffic[] = {"None", "Low", "Normal", "High", "Very high"};
static const u8 v_traffic[] = {0, 4, 8, 14, 20};                      /* 8 as it was: at most 20 + 12 of 63 */

static const char *const l_score[] = {"x1", "x2", "x3", "x5", "x10", "x25"};
static const u8 v_score[] = {1, 2, 3, 5, 10, 25};
static const char *const l_drift[] = {"Grippy", "Normal", "Drifty", "Ice"};
static const u16 v_drift[] = {250, 175, 115, 70};
static const char *const l_steer[] = {"Careful", "Normal", "Sharp", "Twitchy"};
static const u16 v_steer[] = {192, 256, 320, 400};
static const char *const l_cgrav[] = {"Moon", "Low", "Normal", "Heavy"};
static const u8 v_cgrav[] = {1, 2, 4, 5};                              /* quarters */
static const char *const l_offon[] = {"Off", "On"};
static const char *const l_camd[] = {"Close", "Normal", "Far", "Farthest"};
static const u16 v_camd[] = {190, 256, 330, 400};
static const char *const l_props[] = {"None", "Fewer", "Normal"};
static const u16 v_props[] = {0, 128, 256};
static const char *const l_boost[] = {"x0.5", "x0.75", "Normal", "x1.5", "x2", "x4"};
static const u16 v_boost[] = {128, 192, 256, 384, 512, 1024};

/* where each sits in sg_save's words: 0..3 those, 4 the extras' word (XM, kept apart: no room left
   in those) -- bits nothing else there uses: bits nothing else there uses */
static const Opt opts[O_N] = {
    [O_TARGET] = {"Rampage target", l_target, 15, 0, 2, 2, 4},
    [O_TIME] = {"Rampage time", l_time, 15, 0, 2, 10, 4},
    [O_DIFF] = {"Difficulty", l_diff, 7, 0, 2, 18, 3},
    [O_WANTED] = {"Wanted stars", l_wanted, 7, 6, 2, 26, 3},
    [O_LIVES] = {"Lives", l_lives, 7, 0, 3, 9, 3},
    [O_DAMAGE] = {"Damage taken", l_damage, 8, 4, 3, 12, 3},
    [O_SCORE] = {"Score multiplier", l_score, 6, 0, 4, 0, 3},
    [O_CARSPD] = {"Car top speed", l_scale, 6, 2, 3, 17, 3},
    [O_ACCEL] = {"Car acceleration", l_scale, 6, 2, 4, 3, 3},
    [O_GRIP] = {"Car grip", l_scale, 6, 2, 3, 20, 3},
    [O_DRIFT] = {"Handbrake slide", l_drift, 4, 1, 4, 6, 2},
    [O_STEER] = {"Steering", l_steer, 4, 1, 4, 8, 2},
    [O_CGRAV] = {"Car gravity", l_cgrav, 4, 2, 4, 10, 2},
    [O_BOOSTK] = {"Boost power", l_boost, 6, 2, 4, 12, 3},
    [O_UNLIM] = {"Endless boost", l_offon, 2, 0, 4, 15, 1},
    [O_SHIPSPD] = {"Arwing speed", l_scale, 6, 2, 3, 28, 3},
    [O_SHIELD] = {"Arwing shield", l_shield, 6, 1, 1, 12, 3},
    [O_MISSILE] = {"Endless missiles", l_offon, 2, 0, 4, 16, 1},
    [O_GRAV] = {"Ragdoll gravity", l_grav, 5, 2, 2, 21, 3},
    [O_BOUNCE] = {"Ragdoll bounce", l_bounce, 4, 1, 2, 6, 2},
    [O_JET] = {"Jet pack strength", l_scale, 6, 2, 4, 25, 3},
    [O_CAMD] = {"Chase camera", l_camd, 4, 1, 4, 17, 2},
    [O_TICKER] = {"Ticker hints", l_onoff, 2, 0, 3, 15, 1},
    [O_SPEED] = {"Speed", l_speed, 3, 0, 4, 23, 2},
    [O_DRAW] = {"Draw distance", l_draw, 4, 1, 2, 14, 2},
    [O_TEX] = {"Textures", l_onoff, 2, 0, 4, 20, 1},
    [O_PROPS] = {"Trees and lamps", l_props, 3, 2, 4, 21, 2},
    [O_TRAFFIC] = {"Traffic", l_traffic, 5, 2, 2, 29, 3},
    [O_FPS] = {"Frame counter", l_offon, 2, 0, 4, 19, 1},
    [O_PLANET] = {"Planet view", l_offon, 2, 1, 4, 28, 1},
};
#define ROWS (O_N + 2)             /* then RESET ALL and BACK */

static u8 pos[O_N];                /* each one's place along its slider */
u8 opt_ticker = 1;
static s32 clock_t;                /* game ticks of this level's rampage clock */
static s32 score_last;             /* the score as we left it, for the multiplier (-1: not seen yet) */
static u8 *score_me;               /* ... and whose */
static u16 fps_t, fps_f;           /* game ticks and frames since the counter last looked */
static s16 hp_last = -1;           /* the man's health as we left it */
static u8 row, top, rep, hid;      /* hid: we took Payback's sprites (its HUD, its map) off for the page */

static void speed_set(int lv)
{
    const SpLv *l = &sp_tab[sp_lv = lv];
    int t = sp_tr - l->cars;
    draw_k = sp_dk * l->view >> 8;
    prop_k = sp_pk * l->prop >> 8;
    traffic_add = t < 0 ? 0 : t;
    tex_wall_far = l->wall;
    tex_floor_far = lv ? l->roof : 1 << 30;
    tex_far = l->far;
    view_cut = lv > 1;
    far_fs = l->fs;
    ent_far = l->ent;
}

/* each frame: eight of them, and their ticks (4 at most, a slow one is a load, not the scene) */
static void speed_tick(int ticks)
{
    if (!sp_cap || !ticks)
        return;
    sp_sum += ticks < 4 ? ticks : 4;
    if (++sp_n < 8)
        return;
    int sum = sp_sum, lv = sp_lv, bounced = sp_up;
    sp_n = sp_sum = sp_up = 0;
    if (sum >= 19) {                                   /* 25 a second or less: down a row, two when it is far off */
        if (lv < sp_cap)
            speed_set(lv + 1 + (sum >= 24 && lv + 1 < sp_cap));
        if (bounced && sp_wait < 96)
            sp_wait *= 2;                              /* (back down soon after a raise: wait longer for the next) */
        if (bounced && lv == 7 && sp_tw < 96)
            sp_tw *= 2;
        sp_good = 0;
    } else if (sum <= 16 && lv) {                      /* 30 a second (no frame over 2 ticks): one row back, once it has been so a while */
        if (++sp_good >= (lv == 8 && sp_tw > sp_wait ? sp_tw : sp_wait))
            speed_set(lv - 1), sp_good = 0, sp_up = 1;
    } else {
        sp_good = 0;
    }
}

static void apply(void)
{
    car_vmax_k = v_scale[pos[O_CARSPD]];
    car_grip_k = v_scale[pos[O_GRIP]];
    ship_speed_k = v_scale[pos[O_SHIPSPD]];
    sg_shield_k = v_shield[pos[O_SHIELD]];
    rag_grav_k = v_grav[pos[O_GRAV]];
    rag_bounce = v_bounce[pos[O_BOUNCE]];
    sw_pack_k = v_scale[pos[O_JET]];
    opt_ticker = !pos[O_TICKER];
    sp_dk = v_draw[pos[O_DRAW]], sp_pk = v_props[pos[O_PROPS]], sp_tr = v_traffic[pos[O_TRAFFIC]];
    sp_cap = pos[O_SPEED] ? pos[O_SPEED] == 1 ? SP_FAST : SP_N - 1 : 0;
    speed_set(sp_lv < sp_cap ? sp_lv : sp_cap);
    car_accel_k = v_scale[pos[O_ACCEL]];
    car_drift_mu = v_drift[pos[O_DRIFT]];
    car_steer_k = v_steer[pos[O_STEER]];
    car_grav_k = v_cgrav[pos[O_CGRAV]];
    car_boost_k = v_boost[pos[O_BOOSTK]];
    car_boost_inf = pos[O_UNLIM];
    sg_inf_missiles = pos[O_MISSILE];
    cam_dflt = v_camd[pos[O_CAMD]];
    opt_tex = !pos[O_TEX];
    opt_planet = pos[O_PLANET];
    prop_k = v_props[pos[O_PROPS]];
    fps_show = pos[O_FPS];
}

/* The extras' word lives in XM, above the keep and below STATE, checked by its second word (the
   keep is cleared at each start: it is the copy that brings them back, as the progress copy does
   the rest) */
#define XM ((volatile u32 *)0x0203ff90)
#define XM_SUM(x) (((x) * 0x01000193u) ^ 0x53465832u)

/* where an option's choice is kept: its place from the default, round the ring (no division: it ran every frame) */
static u32 code(const Opt *o, int p)
{
    int c = p + o->n - o->def;
    return c >= o->n ? c - o->n : c;
}

static u32 pack_x(void)
{
    u32 x = 0;
    for (int i = 0; i < O_N; i++) {
        const Opt *o = &opts[i];
        if (o->word == 4)
            x |= code(o, pos[i]) << o->shift;
    }
    return x;
}

void opt_save(u32 *w)
{
    for (int i = 0; i < O_N; i++) {
        const Opt *o = &opts[i];
        if (o->word < 4)
            w[o->word] |= code(o, pos[i]) << o->shift;
    }
}

void opt_load(const u32 *w)
{
    u32 x[5] = {0, 0, 0, 0, XM[1] == XM_SUM(XM[0]) ? XM[0] : 0};   /* (a copy that is not good: defaults) */
    for (int i = 0; i < O_N; i++) {
        const Opt *o = &opts[i];
        u32 c = (o->word == 4 ? x[4] : w[o->word]) >> o->shift & ((1 << o->bits) - 1);
        pos[i] = c < o->n ? (c + o->def) % o->n : o->def;
    }
    apply();
}

int opt_x_bad(void)
{
    return XM[1] == XM_SUM(XM[0]) && XM[0] != pack_x();
}

void opt_x_keep(void)
{
    u32 x = pack_x();
    XM[0] = x;
    XM[1] = XM_SUM(x);
}

void opt_level_enter(void)
{
    clock_t = 0;
    hp_last = -1;
    score_last = -1;
    fps_t = fps_f = 0;
    sp_n = sp_sum = sp_good = sp_up = 0, sp_wait = 3, sp_tw = 48;
    speed_set(0);
    if (pos[O_LIVES])
        PB_LIVES = v_lives[pos[O_LIVES]];
}

static s32 target_now(void)
{
    return PB_NGOALS > 0 && PB_GOALS[1] == 0 ? PB_GOALS[2] : 0;
}

void opt_frame(u8 *me, int ticks)
{
    speed_tick(ticks);
    if (pos[O_DIFF])
        PB_DIFF = pos[O_DIFF] - 1;
    if (pos[O_WANTED] < 6 && PB_WANTED > pos[O_WANTED])
        PB_WANTED = pos[O_WANTED];
    if (pos[O_LIVES] == 6 && PB_LIVES < 9)
        PB_LIVES = 9;
    /* the damage he takes: what Payback took off since our last frame, scaled (a fall to 0 stands:
       Payback has begun his death by then) */
    s16 *hp = (s16 *)(PB_MAN + E_HEALTH);
    if (PB_RESPAWN > 0 || *hp <= 0)
        hp_last = -1;
    else {
        int k = v_damage[pos[O_DAMAGE]];
        if (hp_last > 0 && *hp < hp_last && k != 4) {
            int nd = ((hp_last - *hp) * k + 2) >> 2, v = hp_last - nd;
            *hp = v < 0 ? 0 : v;
        }
        hp_last = *hp;
    }
    /* the score multiplier: what Payback added since our last frame, times more */
    if (!me || me != score_me)
        score_last = -1, score_me = me;
    if (me) {
        s32 sc = *(s32 *)(me + E_SCORE);
        int k = v_score[pos[O_SCORE]];
        if (score_last >= 0 && sc > score_last && k > 1) {
            s32 add = (sc - score_last) * (k - 1);
            sc = add / (k - 1) != sc - score_last || sc > 99999999 - add ? 99999999 : sc + add;
            *(s32 *)(me + E_SCORE) = sc;
        }
        score_last = sc;
    }
    if (ticks) {
        fps_f++;
        fps_t += ticks;
        if (fps_t >= 60) {
            fps_now = (fps_f * 60 + (fps_t >> 1)) / fps_t;
            fps_t = fps_f = 0;
        }
    }
    if (PB_RAMPAGE != 1)
        return;
    if (pos[O_TARGET] && PB_NGOALS > 0 && PB_GOALS[1] == 0)
        PB_GOALS[2] = v_target[pos[O_TARGET]];
    /* the time limit: missed, the score starts again from 0 and so does the clock */
    if (!pos[O_TIME] || PB_LEVEL_END == 3 || !me)
        return;
    clock_t += ticks;
    if (clock_t < v_time[pos[O_TIME]] * 3600)
        return;
    clock_t = 0;
    if (*(s32 *)(me + E_SCORE) < target_now()) {
        *(s32 *)(me + E_SCORE) = 0;
        sg_note("TIME OUT! Score back to 0.");
    }
}

void opt_hud(int paused_now)
{
    if (hid)
        REG_DISPCNT |= 0x1000, hid = 0;                /* (the page has gone: its sprites back) */
    if (fps_show && !paused_now) {
        char f[16], *q = d_num(f, fps_now);
        d_cat(q, " FPS");
        pb_text(120 - pb_text_w(f, PBF_WHITE) / 2, 14, f, PBF_WHITE);
    }
    if (!pos[O_TIME] || PB_RAMPAGE != 1 || PB_LEVEL_END == 3 || paused_now)
        return;
    char b[24], *p = d_cat(b, "Time ");
    int left = (v_time[pos[O_TIME]] * 3600 - clock_t + 59) / 60;
    d_time(p, left < 0 ? 0 : left);
    pb_text(120 - pb_text_w(b, PBF_WHITE) / 2, 2, b, left <= 30 ? PBF_RED : PBF_WHITE);   /* (steady red, never a blink) */
}

/* ---- the page ---- */

void opt_open(void)
{
    row = top = rep = 0;
    SFX_PICK();
}

static void change(int d)
{
    int n = opts[row].n, p = pos[row] + d;
    p = p < 0 ? 0 : p >= n ? n - 1 : p;
    if (p == pos[row])
        return;
    pos[row] = p;
    apply();
    sg_sane();
    SFX_MOVE();
}

int opt_input(u16 hit, u16 keys)
{
    if (hit & KEY_B) {
        SFX_PICK();
        return 1;
    }
    if (hit & (KEY_UP | KEY_DOWN)) {
        row = hit & KEY_UP ? (row ? row - 1 : ROWS - 1) : (row + 1 < ROWS ? row + 1 : 0);
        SFX_MOVE();
    }
    if (row < top) top = row;
    if (row >= top + 8) top = row - 7;
    /* left and right: once, then on after a moment held */
    int lr = keys & (KEY_LEFT | KEY_RIGHT);
    rep = lr ? rep + (rep < 255) : 0;
    int go = (hit & (KEY_LEFT | KEY_RIGHT)) || (rep > 24 && rep % 6 == 0);
    if (go && row < O_N && lr)
        change(lr & KEY_LEFT ? -1 : 1);
    if (!(hit & KEY_A))
        return 0;
    if (row == O_N + 1) {
        SFX_PICK();
        return 1;
    }
    for (int i = 0; i < O_N; i++)
        if (row == O_N || row == i)
            pos[i] = opts[i].def;
    apply();
    sg_sane();
    SFX_PICK();
    if (row == O_N)
        sg_note("Settings back to normal.");
    return 0;
}

static void arrow(int x, int y, int dir)
{
    for (int i = 0; i < 4; i++)
        d_vline(x + (dir > 0 ? i : 3 - i), y + i, y + 8 - i, 0x100 | 162);   /* (Payback's gold) */
}

void opt_draw(void)
{
    char b[48], *p;
    if (!hid)
        REG_DISPCNT &= ~0x1000, hid = 1;
    d_fill(0, 0, 240, 160, 0x100 | 8);
    pb_text(120 - pb_text_w("SETTINGS", PBF_TITLE) / 2 - 4, 4, "SETTINGS", PBF_TITLE);
    for (int i = top; i < top + 8 && i < ROWS; i++) {
        int y = 32 + (i - top) * 11;
        if (i < O_N) {
            p = d_cat(b, opts[i].name);
            p = d_cat(p, ": ");
            d_cat(p, opts[i].label[pos[i]]);
        } else
            d_cat(b, i == O_N ? "Reset all" : "Back");
        pb_text(120 - pb_text_w(b, PBF_WHITE) / 2, y, b, i == row ? PBF_RED : PBF_WHITE);
        if (i == row && i < O_N)
            arrow(4, y, -1), arrow(232, y, 1);
    }
    if (top > 0) pb_text(116, 24, "^", PBF_WHITE);
    if (top + 8 < ROWS) pb_text(116, 120, "v", PBF_WHITE);
    /* the slider of the line picked: gold up to where it is, a white mark at its default */
    if (row < O_N) {
        int n = opts[row].n, x0 = 40, wd = 160;
        int kx = x0 + pos[row] * wd / (n - 1), dx = x0 + opts[row].def * wd / (n - 1);
        d_rect(x0, 131, wd, 3, 0x100 | 109);
        d_rect(x0, 131, kx - x0, 3, 0x100 | 162);
        d_rect(dx, 135, 1, 3, 0x100 | 193);
        d_rect(kx - 2, 128, 5, 9, 0x100 | 193);
    }
    {
        const char *h = row == O_SPEED && pos[O_SPEED] ? "Less reach and tiles when slow" : "<> change  A default  B back";
        pb_text(120 - pb_text_w(h, PBF_WHITE) / 2, 146, h, PBF_WHITE);
    }
}
