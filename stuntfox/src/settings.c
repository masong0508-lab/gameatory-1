/* See settings.h. */
#include "settings.h"
#include "draw2d.h"
#include "spacegame.h"

extern u16 car_vmax_k, car_grip_k;     /* car.c, 256 = as built */
extern u16 ship_speed_k;               /* ship.c */
extern u8 sg_shield_k;                 /* spacegame.c: quarters, 255 nothing hurts it */
extern u8 rag_grav_k, rag_bounce;      /* ragdoll.c */

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

enum { O_TARGET, O_TIME, O_DIFF, O_WANTED, O_LIVES, O_DAMAGE, O_CARSPD, O_GRIP, O_SHIPSPD, O_SHIELD,
       O_GRAV, O_BOUNCE, O_TICKER, O_N };
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

/* where each sits in sg_save's words: bits nothing else there uses */
static const Opt opts[O_N] = {
    {"Rampage target", l_target, 15, 0, 2, 2, 4},
    {"Rampage time", l_time, 15, 0, 2, 10, 4},
    {"Difficulty", l_diff, 7, 0, 2, 18, 3},
    {"Wanted stars", l_wanted, 7, 6, 2, 26, 3},
    {"Lives", l_lives, 7, 0, 3, 9, 3},
    {"Damage taken", l_damage, 8, 4, 3, 12, 3},
    {"Car top speed", l_scale, 6, 2, 3, 17, 3},
    {"Car grip", l_scale, 6, 2, 3, 20, 3},
    {"Arwing speed", l_scale, 6, 2, 3, 28, 3},
    {"Arwing shield", l_shield, 6, 1, 1, 12, 3},
    {"Ragdoll gravity", l_grav, 5, 2, 2, 21, 3},
    {"Ragdoll bounce", l_bounce, 4, 1, 2, 6, 2},
    {"Ticker hints", l_onoff, 2, 0, 3, 15, 1},
};
#define ROWS (O_N + 2)             /* then RESET ALL and BACK */

static u8 pos[O_N];                /* each one's place along its slider */
u8 opt_ticker = 1;
static s32 clock_t;                /* game ticks of this level's rampage clock */
static s16 hp_last = -1;           /* the man's health as we left it */
static u8 row, top, rep, hid;      /* hid: we took Payback's sprites (its HUD, its map) off for the page */

static void apply(void)
{
    car_vmax_k = v_scale[pos[O_CARSPD]];
    car_grip_k = v_scale[pos[O_GRIP]];
    ship_speed_k = v_scale[pos[O_SHIPSPD]];
    sg_shield_k = v_shield[pos[O_SHIELD]];
    rag_grav_k = v_grav[pos[O_GRAV]];
    rag_bounce = v_bounce[pos[O_BOUNCE]];
    opt_ticker = !pos[O_TICKER];
}

void opt_save(u32 *w)
{
    for (int i = 0; i < O_N; i++) {
        const Opt *o = &opts[i];
        w[o->word] |= (u32)((pos[i] + o->n - o->def) % o->n) << o->shift;
    }
}

void opt_load(const u32 *w)
{
    for (int i = 0; i < O_N; i++) {
        const Opt *o = &opts[i];
        u32 c = w[o->word] >> o->shift & ((1 << o->bits) - 1);
        pos[i] = c < o->n ? (c + o->def) % o->n : o->def;
    }
    apply();
}

void opt_level_enter(void)
{
    clock_t = 0;
    hp_last = -1;
    if (pos[O_LIVES])
        PB_LIVES = v_lives[pos[O_LIVES]];
}

static s32 target_now(void)
{
    return PB_NGOALS > 0 && PB_GOALS[1] == 0 ? PB_GOALS[2] : 0;
}

void opt_frame(u8 *me, int ticks)
{
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
    pb_text(120 - pb_text_w("<> change  A default  B back", PBF_WHITE) / 2, 146, "<> change  A default  B back", PBF_WHITE);
}
