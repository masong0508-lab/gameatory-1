/* Stunt Fox inside Payback (the MERGE build, see build.py --merge).

   Like SkyCraft running Minecraft's player inside Skyrim's world, the two games share one
   cartridge and each does what it is good at. Payback keeps running everything it owns:
   the city's traffic and people, the police, missions, the phone ticker, the minimap,
   music and sound. Its world renderer is gone: where Payback used to draw its 3D view it now
   calls sf_frame() (keyhook.s), and Stunt Fox draws the city and everyone in it from a chase
   camera with its own faster renderer.

   The player's car is a Stunt Fox car (springs, loops, ramps, boost) that Payback sees as its
   own: we write its position back into Payback's record, so traffic, police and missions keep
   working around it. Hold SELECT anywhere and the Arwing lands next to you; Payback's man rides
   along under it so the city, the minimap and the police follow you into the sky.

   Payback's code is never copied: the build patches the player's own ROM and reads the
   city's layout from it. */
#include "gba.h"
#include "fx.h"
#include "render.h"
#include "world.h"
#include "palette.h"
#include "tex.h"
#include "physics.h"
#include "car.h"
#include "ship.h"
#include "spacegame.h"
#include "draw2d.h"
#include "traffic.h"
#include "model.h"
#include "space.h"
#include "ragdoll.h"
#include "radio.h"
#include "settings.h"

/* ---- Payback (Europe), see payback-mod/docs/payback-notes.md ---- */

#define PB_GRID (*(const u32 *volatile *)0x03000d60)       /* level cells: column pointers */
#define PB_ENTITY ((u8 *const volatile *)0x03000c60)        /* the entity list */
#define PB_NENTITY (*(volatile s16 *)0x0300000c)            /* the LAST INDEX in that list, not a count:
                                                               list[0..PB_NENTITY] are all live (loop <=) */
#define PB_CONTROLLED (*(volatile s16 *)0x02001db8)         /* the entity the player is or drives */
#define PB_RESPAWN (*(volatile s16 *)0x02001e0c)            /* the player's respawn countdown: from 80 when
                                                               Payback's death (or arrest) of the player
                                                               starts, 0 once a new man stands there */
#define PB_LEVEL_CLOCK (*(volatile u32 *)0x02001e00)        /* 30 a second; a level (or replay) starts it at 0 */
#define PB_ARROW ((volatile s32 *)0x020025f0)               /* where the arrow over the player points (x, y) */
#define PB_STREET 0x100                                     /* a column's height at street level (yoff: one map is lower) */
#define PB_TILE_WATER 0x311                                 /* the tile of water (Payback's man sinks in it) */
#define PB_IWRAM_IMAGE ((const u8 *)0x087d9ab8)             /* the ROM copy of Payback's IWRAM code */
typedef void (*Fade)(int);
#define PB_FADE ((Fade)0x0806c82d)                          /* palette brightness, 256 = normal */

/* entity record */
#define E_X 4                      /* s32, 2048 per cell */
#define E_Y 8
#define E_Z 0xc                    /* low 16 bits: 19904 at street level, 16 per height step */
#define E_HEAD 0x12                /* s16, 5760 per turn, 0 = +y */
#define E_DESC 0x1c                /* descriptor: vehicles are 0x3c-byte records */
#define E_STATE 0x10f
#define ST_HIT 18                  /* a person: staggering from a blow */
#define ST_DOWN 7                  /* a person: knocked down */
#define PED_DESC0 0x08354af4u      /* the descriptor table (vehicles 0..17, then animations) */
#define ANIM_ATTACK0 38            /* 38: a punch (seen); 39..47 taken to be the other attacks */
#define ANIM_ATTACK1 47
#define E_VX 0x40                  /* s16 velocity, units per 1/30 s */
#define E_VY 0x42
#define E_VZ 0x44                  /* s16, z per tick: under 0 it is in the air going up */
#define E_SPEED 0xba               /* s16 speeds */
#define E_PREV1 0xe4               /* earlier positions (x, y) */
#define E_PREV2 0xf0
#define VEH_HELI 0x08354ef0
#define VEH_SIZE 0x3c
#define D_CLASS 0x26               /* descriptor: 0 vehicle, 1 person, 2-3 phones, crates, pickups */
#define D_POLICE 0x27              /* 1: the police (cars, vans and officers) */
#define D_LOOK 0x38                /* a vehicle's picture: LOOK0 + its place in looks[] (police cars share one) */
#define LOOK0 0x1a

/* the buttons Payback decoded this tick (its keypad reader, 0x08072f68, which the build
   hooks): one byte each, 1 = held */
#define PB_BTN ((volatile u8 *)0x0200c3e4)
enum { B_UP = 0, B_DOWN = 1, B_SELECT = 2, B_LEFT = 4, B_RIGHT = 5, B_A = 6, B_B = 7, B_R = 8,
       B_START = 9, B_L = 10, B_SELECT2 = 11, B_N = 14 };

/* the phone ticker at the bottom of the screen: ten 500-byte message slots, and the call that
   queues one (from payback-mod/asm/editor.c) */
#define TICK_IDX (*(volatile s16 *)0x02019424)
#define TICK_SLOTS ((char *)0x02019450)
#define TICK_QUEUE ((void (*)(char *, int))0x08039871)
/* the phone's past: the queue call also keeps each line here (16 of 8 bytes: the text, its
   kind), and a press of SELECT has Payback's keypad reader queue them all again (0x0803962c,
   the bl at 0x08073134, which the build points at sf_hook_select) */
#define TICK_HIST_N (*(volatile s32 *)0x02002688)
#define TICK_HIST ((volatile u32 *)0x02002900)
#define TICK_REPLAY ((void (*)(void))0x0803962d)

/* a few words at the top of EWRAM that Payback leaves alone in play (the old patch mod kept its
   flags here); only switching on clears them. Our memory stays set up from level to level. */
#define STATE ((volatile u32 *)0x0203ffd0)
#define MAGIC 0x53465831           /* "SFX1": our memory is set up */

/* for each of Payback's maps: cells of it and their column pointers, written by build.py */
extern const u32 merge_sig[NWORLD][32][2];

/* linker symbols, merge.ld */
extern u8 __hot_start[], __hot_end[], __hot_lma[], __hot2_start[], __hot2_end[], __hot2_lma[];
extern u8 __hot3_start[], __hot3_end[], __hot3_lma[], __hot4_start[], __hot4_end[], __hot4_lma[];
extern u8 __hot5_start[], __hot5_end[], __hot5_lma[], __hot6_start[], __hot6_end[], __hot6_lma[];
extern u8 __hot6b_start[], __hot6b_end[], __hot6b_lma[], __hot6b_save[];
extern u8 __hot7_start[], __hot7_end[], __hot7_lma[], __hot8_start[], __hot8_end[], __hot8_lma[];
extern u8 __hot9_start[], __hot9_end[], __hot9_lma[], __hot10_start[], __hot10_end[], __hot10_lma[];
extern u8 __hot11_start[], __hot11_end[], __hot11_lma[];
static u32 hot3_save[0x2f0 / 4] __attribute__((section(".noinit")));   /* (start() must not clear it) */
extern u8 __data_start[], __data_end[], __data_lma[];
extern u8 __bss_start[], __bss_end[];
extern u32 __keep_canary[];
#define CANARY 0x4b454550          /* "KEEP" */

u32 frame_count;

#define REG_DMA3SAD (*(volatile u32 *)0x040000d4)
#define REG_DMA3DAD (*(volatile u32 *)0x040000d8)
#define REG_DMA3CNT (*(volatile u32 *)0x040000dc)

/* DMA 3 copy. Payback's sound interrupt uses DMA 3 too, so interrupts wait meanwhile. */
static void copy32(void *d, const void *s, u32 bytes)
{
    if (!bytes)
        return;                        /* (a count of 0 would copy 64 KiB) */
    u16 ime = REG_IME;
    REG_IME = 0;
    REG_DMA3CNT = 0;
    REG_DMA3SAD = (u32)s;
    REG_DMA3DAD = (u32)d;
    REG_DMA3CNT = (bytes >> 2) | 0x84000000;
    REG_IME = ime;
}

/* DMA 3 fill of whole words with v, as copy32. */
static void fill32(void *d, u32 v, u32 bytes)
{
    static volatile u32 src;
    if (!bytes)
        return;
    src = v;
    u16 ime = REG_IME;
    REG_IME = 0;
    REG_DMA3CNT = 0;
    REG_DMA3SAD = (u32)&src;
    REG_DMA3DAD = (u32)d;
    REG_DMA3CNT = (bytes >> 2) | 0x85000000;  /* (source fixed) */
    REG_IME = ime;
}

/* Our hottest code borrows the IWRAM that Payback's world renderer runs from. Nothing but that
   renderer (only ever called through sf_frame) runs or reads it, bar five words: the last
   instruction of Payback's banner blitter (0x03002920..0x030030b0) and that blitter's jump
   table. So our code stays there between frames with only those five words swapped, and all of
   Payback's code goes back before its renderer runs. So do hot4, hot6, hot7, hot8, hot10 and hot11,
   which Payback leaves alone everywhere else (merge.ld). hot2, hot3, hot5, hot6b and hot9 hold
   code Payback runs outside our frame: they are lent for the length of our frame only. */
static const u16 pb_hot_words[] = {0x30b0, 0x3c04, 0x3c08, 0x3c0c, 0x3c10};   /* - 0x03000000 */

/* is our code in hot (bar those words)? build.py checks that Payback's words here differ */
static int hot_mine(void)
{
    const u32 *h = (const u32 *)__hot_start, *l = (const u32 *)__hot_lma;
    u32 n = (__hot_end - __hot_start) >> 2;
    return h[1] == l[1] && h[n - 1] == l[n - 1];
}

#define REGION(k) {__hot##k##_start, __hot##k##_end, __hot##k##_lma}
static const struct { u8 *at, *end; const u8 *lma; } stay[] = {
    REGION(4), REGION(6), REGION(7), REGION(8), REGION(10), REGION(11)};

/* is our code in stay[i]? (its first and last words: build.py checks that Payback's first word differs) */
static int stay_mine(unsigned i)
{
    const u32 *h = (const u32 *)stay[i].at, *l = (const u32 *)stay[i].lma;
    u32 n = (stay[i].end - stay[i].at) >> 2;
    return h[0] == l[0] && h[n - 1] == l[n - 1];
}

static void hot_words(const u8 *from)
{
    for (unsigned i = 0; i < sizeof pb_hot_words / sizeof *pb_hot_words; i++)
        *(u32 *)(0x03000000 + pb_hot_words[i]) = *(const u32 *)(from + pb_hot_words[i]);
}

static void hot_install(void)
{
    if (!hot_mine())
        copy32(__hot_start, __hot_lma, __hot_end - __hot_start);
    else
        hot_words(__hot_lma - ((u32)__hot_start - 0x03000000));
    for (unsigned i = 0; i < sizeof stay / sizeof *stay; i++)
        if (!stay_mine(i))
            copy32(stay[i].at, stay[i].lma, stay[i].end - stay[i].at);
    if (*(u32 *)__hot2_start != *(const u32 *)__hot2_lma) {
        copy32(__hot2_start, __hot2_lma, __hot2_end - __hot2_start);
        copy32(hot3_save, __hot3_start, __hot3_end - __hot3_start);
        copy32(__hot3_start, __hot3_lma, __hot3_end - __hot3_start);
        copy32(__hot5_start, __hot5_lma, __hot5_end - __hot5_start);
        copy32(__hot6b_save, __hot6b_start, __hot6b_end - __hot6b_start);
        copy32(__hot6b_start, __hot6b_lma, __hot6b_end - __hot6b_start);
        copy32(__hot9_start, __hot9_lma, __hot9_end - __hot9_start);
    }
}

#define PUT_BACK(at, end) copy32(at, PB_IWRAM_IMAGE + ((u32)(at) - 0x03000000), (end) - (at))

/* all: Payback's world renderer is about to run */
static void hot_restore(int all)
{
    if (all) {
        if (hot_mine())
            PUT_BACK(__hot_start, __hot_end);
        for (unsigned i = 0; i < sizeof stay / sizeof *stay; i++)
            if (stay_mine(i))
                PUT_BACK(stay[i].at, stay[i].end);
    } else {
        hot_words(PB_IWRAM_IMAGE);
    }
    if (*(u32 *)__hot2_start == *(const u32 *)__hot2_lma) {      /* (hot2 last: it says lent) */
        copy32(__hot3_start, hot3_save, __hot3_end - __hot3_start);
        PUT_BACK(__hot5_start, __hot5_end);
        copy32(__hot6b_start, __hot6b_save, __hot6b_end - __hot6b_start);
        PUT_BACK(__hot9_start, __hot9_end);
        PUT_BACK(__hot2_start, __hot2_end);
    }
}

/* which of Payback's maps is loaded (the grid its loader 0x0803c580 was given), or -1: its
   cells say so, whatever path loaded it (the map we drew last is tried first) */
static int map_is(const u32 *g, int m)
{
    int ok = 0;
    for (int i = 0; i < 32; i++)
        ok += g[merge_sig[m][i][0]] == merge_sig[m][i][1];
    return ok >= 28;
}

static int which_map(int last)
{
    const u32 *g = PB_GRID;
    if ((u32)g < 0x02000000 || (u32)g >= 0x0203c000)
        return -1;
    if (last >= 0 && last < NWORLD && map_is(g, last))
        return last;
    for (int m = 0; m < NWORLD; m++)
        if (m != last && map_is(g, m))
            return m;
    return -1;
}

/* Payback's free-running clock: timers 2 and 3, 16384 counts a second */
static u32 pb_clock(void)
{
    u32 hi = REG_TM3D, lo = REG_TM2D;
    if (REG_TM3D != hi) { hi = REG_TM3D; lo = REG_TM2D; }
    return hi << 16 | lo;
}

/* ---- our side ---- */

enum { FOOT, DRIVE, FLY };         /* FOOT: Payback moves the player (walking, its helicopter) */

static u32 last_clock, tick_acc;
static V3 cam_off, cam_up;
static int mode, parked;           /* parked: the Arwing waits where we left it */
static Car car;
static Ship ship;
static u8 *car_ent;                /* Payback's record of the car we drive */
static u8 *hero;                   /* Payback's man, the player (a respawn may give him a new record) */
static int car_kind;               /* which of Payback's vehicles it is */
#define TANK 11                    /* (its look: the tank fires on R, so R is not our boost there) */
static u8 car_boom;                /* ticks since it blew up (see draw_car) */
static u8 car_wet;                 /* ticks it has been in the water */
static u8 swimming, swim_lad;      /* the player swims (see swim_in); swim_lad: up that ladder (+ 1) */
static u16 swim_hint;              /* ticks left of a hint over the picture (the first swim's, or */
static u8 swim_msg, swim_far;      /* swim_msg 1: the way out is far off, see swim_way) */
static int vehicle_kind(const u8 *e);
static u16 keys, prev_keys, hits;
static u8 want_ship, told;
static u8 bail, ghost;             /* bailing out (see bail_car) */
enum { GH_NONE, GH_CAR, GH_SHIP };
static void bail_press(void);
static int bail_camera(void);

/* SELECT, as sf_keys sees it */
static u32 key_calls, frame_calls, sel_since;
static u8 sel_down, sel_used, sel_replay, inject_l, call_req, r_chord;
static u8 sel_chord;               /* SELECT still down since it made the radio's chord: the D-pad steers */
static u8 sel_seen;                /* SELECT seen down while we drew (see sel_look) */

/* the player's camera: hold SELECT and the D-pad swings it round (LEFT, RIGHT) or pulls it in
   and out (UP, DOWN) instead of moving you; a quick tap of SELECT brings it back behind you */
#define PAD_ALL (KEY_UP | KEY_DOWN | KEY_LEFT | KEY_RIGHT)
#define ZOOM_NEAR 170              /* (the closest the chase views come: 256 = the usual distance) */
#define ZOOM_IN 90                 /* zoomed in past ZOOM_FP on foot or in a car it is first person */
#define ZOOM_FP 140
static u8 fp_view;                 /* first person this frame: the camera is the man's or the driver's eyes */
#define ZOOM_OUT 440                /* (further out shows more city and costs fps) */
static s32 cam_yaw, cam_zoom;      /* orbit (65536 per turn, from behind) and distance */
static u16 cam_pad;                /* the D-pad, while it is the camera's */
static u8 cam_lock, cam_home;      /* cam_home: on its way back behind you */
static u8 cam_cut;                 /* straight to the new place, no swing (boarding) */
static u8 cam_keep;                /* on foot: it swings round you at its distance (see camera_look) */

#define PAD_TAP 4                  /* game frames (about a fifth of a second): a shorter press of UP or DOWN on foot is a tap */
static s32 fade_d;                 /* Payback's last fade (0: none), see sf_fade */

static int map_now;                /* the map whose world is loaded */
static u8 chain_to;                /* 1 + the map the rampage campaign goes on to (sf_menu) */
static u32 level_clock;            /* Payback's level clock at our last frame */
static int mirror_load(void);

static void start(int map)
{
    copy32(__data_start, __data_lma, __data_end - __data_start);
    for (u32 *p = (u32 *)__bss_start; p < (u32 *)__bss_end; p++)
        *p = 0;
    r_init();
    world_select(map_now = map);
    ramp_grip = 1;
    models_init();
    traffic_init();
    space_init();
    sg_init();
    cam_off = v3(0, 400, -800);
    cam_up = v3(0, ONE, 0);
    cam_zoom = 256;
    last_clock = pb_clock();
    level_clock = PB_LEVEL_CLOCK;
    mirror_load();                 /* (the progress so far, if its copy is good) */
    __keep_canary[0] = CANARY;
    STATE[0] = MAGIC;
}

static s32 iabs(s32 v) { return v < 0 ? -v : v; }
static s32 clamp(s32 v, s32 lo, s32 hi) { return v < lo ? lo : v > hi ? hi : v; }

/* ---- our hints on Payback's ticker ----
   The ticker is Payback's phone: its missions talk there. Our hints are few and short, each said
   once, and only while it fits what you are doing (calling the Arwing on foot, docking in space),
   and only once the ticker has been quiet for two seconds with nothing queued, no mission running
   and no ringing phone near: Payback's lines never wait behind ours. Everything else (stunts,
   landings, the space game) is news on our own HUD (sg_note). */
#define TICK_STATE (*(volatile u8 *)0x02002674)    /* 2: idle, else typing a line out */
#define TICK_WAITING (*(volatile s32 *)0x02002684) /* lines queued behind that one */
enum { H_FOOT, H_CAR, H_ARWING, H_CLIMB, H_SPACE, H_CAMERA, H_N };
static const char *const hint_text[H_N] = {
    "Hold SELECT to call your Arwing.",
    "Stunt car: A gas, B brake, A+B slides, R boost.",
    "Arwing: A thrust, R laser, L missile.",
    "Climb high for space and Fox Station.",
    "Hold SELECT near Fox Station to dock.",
    "SELECT + D-pad turns the camera.",
};
static s8 hint_now = -1;           /* the hint that fits this frame, if not said yet */
static u8 last_mode, phone_near, on_mission;
static u32 tick_busy, mode_since, flew_at;
static u8 tick_quiet;

static void news_send(void)
{
    /* (SELECT held: calling the Arwing, or the camera.) This looks once a game frame, so a busy
       spell ended somewhere since the last look: the quiet counts from the first look that finds it */
    int busy = TICK_STATE != 2 || TICK_WAITING || on_mission || phone_near || fade_d || keys & KEY_SELECT;
    if (busy || !tick_quiet)
        tick_busy = frame_count;
    tick_quiet = !busy;
    if (hint_now < 0 || frame_count - tick_busy < 120 || !opt_ticker)
        return;
    const char *s = hint_text[(int)hint_now];
    told |= 1 << hint_now;
    hint_now = -1;
    int i = TICK_IDX;
    if (i < 0 || i > 9)
        i = 0;
    char *dst = TICK_SLOTS + i * 500;
    while ((*dst++ = *s++))
        ;
    TICK_QUEUE(TICK_SLOTS + i * 500, 2);
    TICK_IDX = i >= 9 ? 0 : i + 1;
    /* and out of the phone's past again: a tap of SELECT replays Payback's own lines, not ours */
    int n = TICK_HIST_N;
    if (n > 0 && n <= 16 && TICK_HIST[2 * (n - 1)] == (u32)(TICK_SLOTS + i * 500))
        TICK_HIST_N = n - 1;
}

/* stunts and knocks: as often as they happen, but one every two seconds at most */
static u32 shout_at;
static void shout(const char *s)
{
    if (frame_count - shout_at < 120)
        return;
    shout_at = frame_count;
    sg_note(s);
}

void props_draw(void);             /* props.c: Payback's phones, crates and the like, as they are now */

/* ---- Payback's entities ---- */

static int valid(const u8 *e) { return (u32)e >= 0x02000000 && (u32)e < 0x02040000; }

static V3 entity_pos(const u8 *e)
{
    s32 x = *(const s32 *)(e + E_X), y = *(const s32 *)(e + E_Y);
    s32 z = *(const u16 *)(e + E_Z);
    return v3(x >> 1, ((19904 - z) >> 1) + world.yoff, y >> 1);
}

static s32 entity_heading(const u8 *e)
{
    return (*(const s16 *)(e + E_HEAD) * 11651) >> 10;      /* 5760 -> 65536 per turn */
}

static int is_vehicle(const u8 *e);

/* move Payback's record to where we are (units, our heading, fine/tick) */
static void entity_put(u8 *e, V3 p, s32 heading, V3 vel)
{
    s32 *w = (s32 *)e;
    w[E_PREV1 / 4] = w[E_PREV2 / 4] = w[E_X / 4];
    w[E_PREV1 / 4 + 1] = w[E_PREV2 / 4 + 1] = w[E_Y / 4];
    w[E_X / 4] = clamp(p.x, 2 * CELL, (CITY - 2) * CELL) * 2;
    w[E_Y / 4] = clamp(p.z, 2 * CELL, (CITY - 2) * CELL) * 2;
    /* the heading alone: the s16 before it is a vehicle's roll (0xe its pitch), the box Payback's
       wall test sweeps, and is Payback's to set */
    *(s16 *)(e + E_HEAD) = (heading & 0xffff) * 5760 >> 16;
    *(s16 *)(e + E_VX) = vel.x >> 6;
    *(s16 *)(e + E_VY) = vel.z >> 6;
    if (is_vehicle(e)) {
        /* and a vehicle's speed, as Payback's own car keeps it (about 230 at 48 a tick): its people
           walk round a car without one as round a parked car, so ours never ran anyone over; its
           knock and its police read it too */
        s32 a = iabs(vel.x), b = iabs(vel.z), v = a > b ? a + (b * 3 >> 3) : b + (a * 3 >> 3);
        *(s16 *)(e + E_SPEED) = *(s16 *)(e + E_SPEED + 2) = v * 5 >> 8;
    }
}

/* the same for Payback's man under the Arwing: he is set down there (a move would be swept
   through the walls between, and pushed back) */
static void man_put(u8 *e, V3 p, s32 heading)
{
    s32 *w = (s32 *)e;
    entity_put(e, p, heading, v3(0, 0, 0));
    w[E_PREV1 / 4] = w[E_PREV2 / 4] = w[E_X / 4];
    w[E_PREV1 / 4 + 1] = w[E_PREV2 / 4 + 1] = w[E_Y / 4];
}

/* can Payback's man stand at (x, z) (units) at street level: not inside a building, up on a
   roof or a bridge, or down in the water? (Payback's own map, so it agrees with Payback) */
static int street_at(s32 x, s32 z)
{
    u32 cx = (x >> 10) - 2, cy = (z >> 10) - 2;
    const u32 *g = PB_GRID;
    if (cx >= CITY - 4 || cy >= CITY - 4 || (u32)g - 0x02000000 >= 0x40000)
        return 0;                                      /* (Payback keeps everyone 2 cells in from the rim) */
    cx += 2, cy += 2;
    const u8 *col = (const u8 *)g[cx * CITY + cy];
    if ((u32)col - 0x02000000 >= 0x08000000)
        return 0;
    u32 top = PB_STREET + 16 - (world.yoff >> 3);       /* (this map's street level: see world.h) */
    for (int k = 0; k < 3; k++, col += 20)
        if (col[8] && (*(const u16 *)(col + 4) > top || *(const u16 *)(col + 6) > top
                       || (col[10] | (col[11] & 3) << 8) == PB_TILE_WATER))
            return 0;
    return 1;
}

/* Payback's floor under feet at h (its steps, 8 units) in a column: the record whose top is
   nearest, as its own collision picks it (tools/mkworld.py pb_floor); -1 with none. The three
   records stand on each other: each one's heights are over the one below's first. */
static int pb_floor_at(const u8 *col, s32 h, s32 *floor, int *flat, int *tile)
{
    s32 base = 0, best = 1 << 30;
    int out = -1;
    for (int k = 0; k < 3; k++, col += 20) {
        s32 h0 = *(const s16 *)(col + 4), h1 = *(const s16 *)(col + 6), t0 = base + h0, t1 = base + h1;
        int shape = col[8], typ = col[11] & 0x70;
        base += h0;
        if (!shape || !typ)
            continue;
        s32 ref = typ == 0x40 || (shape != 1 && t1 <= t0) ? t1 : t0, d = iabs(ref - h);
        if ((out >= 0 && ref - h > 0x80) || d > best)
            continue;
        best = d + 0x40;
        out = k;
        *floor = ref;
        *flat = shape == 1;
        *tile = col[10] | (col[11] & 3) << 8;
    }
    return out;
}

/* can Payback's man stand at (x, z) (units) with his feet at y: on a flat top of that column
   there (the street, a raised plaza, a car park's deck, a roof), not in the water */
static int stand_at(s32 x, s32 z, s32 y)
{
    u32 cx = x >> 10, cy = z >> 10;
    const u32 *g = PB_GRID;
    if (cx >= CITY || cy >= CITY || (u32)g - 0x02000000 >= 0x40000)
        return 0;
    const u8 *col = (const u8 *)g[cx * CITY + cy];
    if ((u32)col - 0x02000000 >= 0x08000000)
        return 0;
    s32 h = ((y - world.yoff) >> 3) + PB_STREET, fl = 0;
    int flat = 0, tile = 0;
    return pb_floor_at(col, h, &fl, &flat, &tile) >= 0 && flat && iabs(fl - h) <= 4 && tile != PB_TILE_WATER;
}

/* the nearest street spot to p (units) within a few cells: a cell's centre, as Payback's man
   can stand on it; 0 with none */
static int nearest_street(V3 p, V3 *out)
{
    s32 cx = p.x >> 10, cz = p.z >> 10, best = 1 << 30;
    for (int dx = -4; dx <= 4; dx++)
        for (int dz = -4; dz <= 4; dz++) {
            s32 x = ((cx + dx) << 10) + 512, z = ((cz + dz) << 10) + 512, d = iabs(x - p.x) + iabs(z - p.z);
            if (d < best && street_at(x, z))
                best = d, *out = v3(x, 0, z);
        }
    return best < 1 << 30;
}

static u32 entity_desc(const u8 *e) { return *(const u32 *)(e + E_DESC); }

/* what an entity is, as its descriptor says (not where it sits in the table: the police cars
   and some vehicles of other cities sit among the people): 0 vehicle, 1 person, 2-3 objects */
static const u8 *desc_of(const u8 *e)
{
    u32 d = entity_desc(e);
    return d - PED_DESC0 < 128 * VEH_SIZE ? (const u8 *)d : 0;
}

static int ent_class(const u8 *e)
{
    const u8 *d = desc_of(e);
    return d ? d[D_CLASS] : -1;
}

static int is_vehicle(const u8 *e) { return ent_class(e) == 0; }
static int is_person(const u8 *e) { return ent_class(e) == 1; }
static int is_car(const u8 *e) { return is_vehicle(e) && entity_desc(e) != VEH_HELI; }

/* burnt out, or burning down to it */
#define E_HEALTH 0x68
static int wrecked(const u8 *e)
{
    return *(const s16 *)(e + E_HEALTH) <= 0 || e[E_STATE] == 6 || e[E_STATE] == 7;
}

#define ST_WALK 2                  /* the player on foot */
static u8 *controlled(void)
{
    int i = PB_CONTROLLED, n = PB_NENTITY;
    if (i < 0 || i > n)
        return 0;
    u8 *e = PB_ENTITY[i];
    return valid(e) ? e : 0;                       /* (n is the list's last index, a live record: out of a
                                                      parked car, the tank or the hot rod, the man is put there) */
}

/* Payback's arrow over the player takes its angle from a table of reciprocals (0x0806ca44):
   within 8 of the target's line on one axis and over 64 cells from it on the other, the
   product overflows, the angle is garbage and its arrow code (0x0806d820) then crashes the
   game. Its own walking hardly ever sits on such a line; a swimmer on a straight course, or
   one put at a ladder (a cell's middle), can, so he is moved off it by a hair. */
#define APART __attribute__((noinline))   /* (their locals kept off sf_draw's frame, deep in every frame's stack) */
static APART void off_arrow_line(u8 *e)
{
    if (!e)
        return;
    s32 *p = (s32 *)(e + E_X);
    for (int a = 0; a < 2; a++) {
        s32 d = p[a] - PB_ARROW[a], o = p[a ^ 1] - PB_ARROW[a ^ 1];
        if (d > -8 && d < 8 && (o > 64 * 2048 || o < -64 * 2048))
            p[a] = PB_ARROW[a] + (d < 0 ? -8 : 8);
    }
}

/* Who Payback must let be: [0] the man under the Arwing, not hurt at all nor arrested (he can't
   see what comes at him, so a car running into him, one blowing up nearby or an officer
   walking up would end the player's flight out of nowhere), [1] the car we drive, not by its
   wall, knock and street-object checks: Payback runs them on our car's long steps and finds
   crashes on an empty road, and its objects are wider than what we draw (we do our own crashes,
   see car_crash), and [2] the man on foot, by one blast or shot from full health: left at 1
   (we draw neither). [3] is set (non-zero) once that has left him at 1 in this tick of
   Payback's, so the rest of the same blast or bullet (a police bullet hits twice in one tick)
   leaves him there too; each tick starts with it clear (sf_keys).
   Payback's code reads these through the build's hooks (sf_hook_wall here, guard.s). */
u8 *sf_guard[4];

/* what Payback's knocks have added to the velocity of our car's record ([1]) since our last frame,
   x and y (guard.s, sf_hook_kick): see car_knocked */
s16 sf_knock[2];

/* in place of Payback's call to its wall response for a vehicle on the move (0x0807050c: a
   knock back, and health off by the square of the speed it finds in the record) */
void sf_hook_wall(u8 *e, int hx, int hy)
{
    if (e != sf_guard[0] && e != sf_guard[1])
        ((void (*)(u8 *, int, int))0x0807050d)(e, hx, hy);
}

/* ---- Payback's goals: is a mission on, which phones ring ----
   A ringing phone is a goal of kind 1 (green) or 7 (red) at its cell's centre, there for as long
   as it rings: so it gets a steady column of light over it (never the flicker of its object byte,
   which flips every tick), and a pointer at the edge of the screen while it is out of sight. Any
   goal but those, the level's target (0) and a hidden pickup (47) means a mission is on. */
#define PB_GOALS ((const s32 *)0x0201a7e0)          /* 9 words a goal: id, kind, x, y (2048 a cell), floor, ... */
#define PB_NGOALS (*(volatile s16 *)0x0201a7d8)
#define RINGS 4
static s32 ring_x[RINGS], ring_z[RINGS];           /* units */
static u8 nring, ring_red;                         /* ring_red: bit i, phone i is a red one */

static void goals_scan(const u8 *me)
{
    int n = PB_NGOALS;
    if (n < 0 || n > 64)
        n = 0;
    nring = ring_red = on_mission = 0;
    for (int i = 0; i < n; i++) {
        const s32 *g = PB_GOALS + 9 * i;
        if ((g[1] == 1 || g[1] == 7) && nring < RINGS) {
            ring_red |= (g[1] == 7) << nring;
            ring_x[nring] = g[2] >> 1;
            ring_z[nring++] = g[3] >> 1;
        } else if (g[1] != 0 && g[1] != 1 && g[1] != 7 && g[1] != 47) {
            on_mission = 1;
        }
    }
    phone_near = 0;
    V3 p = me ? entity_pos(me) : v3(-9 * CELL, 0, 0);
    for (int i = 0; i < nring; i++)
        if (iabs(p.x - ring_x[i]) < 3 * CELL && iabs(p.z - ring_z[i]) < 3 * CELL)
            phone_near = 1;                        /* (its call is about to come on the ticker) */
}

/* a shaft from a to b (camera space), w wide, wholly past one side of the view: model_place's
   test for a line, as the shaft's ball is as wide as it is tall and takes in most of the view */
static int shaft_out(V3 a, V3 b, s32 w)
{
    s32 x = w * 182, y = w * 158;
    return (a.z < -w && b.z < -w) || (FOCAL * a.x - 121 * a.z > x && FOCAL * b.x - 121 * b.z > x) ||
           (-FOCAL * a.x - 121 * a.z > x && -FOCAL * b.x - 121 * b.z > x) ||
           (FOCAL * a.y - 81 * a.z > y && FOCAL * b.y - 81 * b.z > y) ||
           (-FOCAL * a.y - 81 * a.z > y && -FOCAL * b.y - 81 * b.z > y);
}

static void rings_draw(void)
{
    M3 m;
    Place pl;
    myaw(&m, 0);
    for (int i = 0; i < nring; i++) {
        V3 p = v3(ring_x[i], world_ground(ring_x[i], ring_z[i]) + 340, ring_z[i]), d = vsub(p, cam.pos);
        s32 far = iabs(d.x) > iabs(d.z) ? iabs(d.x) : iabs(d.z);
        if (far > 36000)
            continue;
        s32 s = 384 + (far > 18000 ? 18000 : far) / 16, h = 6000 * s >> 8;   /* (wider far off) */
        V3 a = r_cam(p);
        if (shaft_out(a, vadd(a, v3(cam.m.r.y * h >> 14, cam.m.u.y * h >> 14, cam.m.f.y * h >> 14)), 80 * s >> 8))
            continue;
        model_body = ring_red >> i & 1 ? M_STUNT : M_GRASS;
        if (model_place(&pl, p, &m, s, 0, 6000))
            model_draw(&mdl_beacon, &pl);
    }
    model_body = M_CAR;
}

/* the nearest ringing phone, when out of sight: an arrow at the side of the screen it is on,
   drawn with the scene (two polygons cost less than lines of pixels), and named for its first
   3 s after it (text costs frame time too) */
static u32 pointed;                                /* frame_count + 1 when it came up */
static int point_x, point_c;                       /* the name's place (0: none) and colour */
static void ring_pointer(const u8 *me)
{
    point_x = 0;
    if (!me || !nring) {
        pointed = 0;
        return;
    }
    V3 at = entity_pos(me);
    int best = 0;
    for (int i = 1; i < nring; i++)
        if (iabs(ring_x[i] - at.x) + iabs(ring_z[i] - at.z) < iabs(ring_x[best] - at.x) + iabs(ring_z[best] - at.z))
            best = i;
    V3 d = vsub(v3(ring_x[best], world_ground(ring_x[best], ring_z[best]) + 300, ring_z[best]), cam.pos);
    while (iabs(d.x) > 30000 || iabs(d.y) > 30000 || iabs(d.z) > 30000)
        d = vshr(d, 1);
    s32 rx = vdot(cam.m.r, d), rz = vdot(cam.m.f, d);
    if (rz > 64 && iabs(FOCAL * rx / rz) < 112) {
        pointed = 0;
        return;                                    /* on screen: its light shows it */
    }
    if (!pointed)
        pointed = frame_count + 1;
    int c = ring_red >> best & 1 ? COLOR(M_STUNT, 3, 0) : COLOR(M_GRASS, 3, 0), left = rx < 0;
    s32 x = left ? 8 * 16 : 154 * 16, s = left ? 16 : -16, y = 72 * 16;     /* (28.4) */
    /* a dark-edged triangle, its tip toward the phone (of two in the nearest bucket, the one
       queued last is drawn first) */
    s32 lit[6] = {x + 2 * s, y, x + 6 * s, y - 5 * 16, x + 6 * s, y + 5 * 16};
    s32 rim[6] = {x, y, x + 7 * s, y - 8 * 16, x + 7 * s, y + 8 * 16};
    r_poly2d(lit, 3, c, 0, 0);
    r_poly2d(rim, 3, COLOR(M_ROAD, 0, 0), 0, 0);
    if (frame_count + 1 - pointed < 180)
        point_x = left ? 18 : 108, point_c = c;
}


/* ---- the Arwing's shots into the city (spacegame.c fires them) ---- */
#define E_FOE 0x108                /* who hurt it last (Payback sets it when one is hit) */
#define E_AMBIENT 0x5d             /* s8: -1 for the city's own people and traffic; 0 for the player and
                                      for vehicles a level placed (parked ones, the tank, the helicopter) */
#define E_SCORE 0x90               /* s32: the player's score, in the record he controls */
#define PB_BONUS (*(volatile s16 *)0x02001df0)              /* the score's bonus multiplier */
/* Payback's "the player hurt entity i" (0x0800020c), which its own weapons call after each hit:
   wanted stars, the kill score (1500 x the bonus multiplier, 2500 for the police), kill counts
   and the mission goals waiting on that entity (a kill target, or one that must not be hurt).
   1: the player did it on foot (we fly as Payback's man). Called once our frame is over. */
#define PB_HURT ((void (*)(int, int))0x0800020d)
static u8 hurt_q[8], hurt_n;       /* (8: a missile's splash can hurt a crowd in one frame) */

static void hurt_send(void)
{
    int n = PB_NENTITY;                                /* (the last index) */
    for (int k = 0; k < hurt_n; k++)
        if (hurt_q[k] <= n)
            PB_HURT(hurt_q[k], 1);
    hurt_n = 0;
}

/* our last shot or missile that hit someone, and when (frame_count): who it knocks down flies
   from it (rag_knock) */
static V3 shot_at;
static u32 shot_when;
static u8 shot_big;

/* dmg off e, record i of the list, as a shot of ours: Payback does the rest (a vehicle at 0
   burns, then blows up; a person at 0 is knocked down), and its kill score and stars come
   through hurt_send. A hit on the city's own people or traffic scores 500 x the bonus at once,
   as every hit of Payback's own gun does (0x0801dae8); a parked or level-placed vehicle scores
   nothing, as there. Once the queue is full (a splash into a crowd and lasers in one frame),
   one not in it yet is spared: hurt without Payback hearing of it, a mission's target could
   die uncounted. 0 then */
static int ent_hurt(u8 *e, int i, int dmg, u8 *me)
{
    if (hurt_n == sizeof hurt_q) {
        int k = 0;
        while (k < hurt_n && hurt_q[k] != i)
            k++;
        if (k == hurt_n)
            return 0;
    } else
        hurt_q[hurt_n++] = i;
    s16 *hp = (s16 *)(e + E_HEALTH);
    *hp = *hp > dmg ? *hp - dmg : 0;
    *(u8 **)(e + E_FOE) = me;
    if (is_person(e) && !*hp)
        e[E_STATE] = ST_DOWN;
    if (me && (s8)e[E_AMBIENT] == -1)
        *(s32 *)(me + E_SCORE) += 500 * PB_BONUS;
    return 1;
}

/* a vehicle's size in its descriptor: half width, ahead of and behind the record, in Payback's
   units (twice ours). Payback's knock and wall sweep use them; the sizes it ships are its
   sprites', about twice the models we draw, and the build (traffic WP1) writes the drawn ones
   there, so the box a shot can hit is the body it sees */
#define D_HALFW 0xe
#define D_AHEAD 0x12
#define D_BEHIND 0x14

/* is p inside e as drawn, with 40 to spare: a box along a vehicle's heading from its descriptor
   sizes, the helicopter's rotor disc (520), 150 each way round a person (a walker crosses 120
   while a bolt flies 2500); from 80 under the record to 300 over it (the tallest body, a bus,
   is 290). Never wider than a tank (152 + 40) nor longer than a bus (520 + 40) each way: the
   sizes Payback ships (a saloon 775 ahead) are its knock's, and until the build writes the drawn
   ones a car would swallow shots far in front of it. person: its class (1) */
#define CITY_REACH 600             /* the most a body reaches from its record (a bus, the rotor) */
static int ent_box(const u8 *e, V3 p, int person)
{
    V3 c = entity_pos(e);
    s32 dx = p.x - c.x, dz = p.z - c.z;
    if (p.y < c.y - 80 || p.y > c.y + 300 || iabs(dx) > CITY_REACH || iabs(dz) > CITY_REACH)
        return 0;
    if (person)
        return iabs(dx) <= 150 && iabs(dz) <= 150;
    if (entity_desc(e) == VEH_HELI)
        return dx * dx + dz * dz <= 520 * 520;
    const u8 *d = desc_of(e);
    s32 hw = 154, ah = 275, bh = 275;                  /* (a saloon, with no descriptor) */
    if (d)
        hw = (*(const s16 *)(d + D_HALFW) >> 1) + 40, ah = (*(const s16 *)(d + D_AHEAD) >> 1) + 40,
        bh = (*(const s16 *)(d + D_BEHIND) >> 1) + 40;
    if (hw > 192) hw = 192;
    if (ah > 560) ah = 560;
    if (bh > 560) bh = 560;
    s32 h = entity_heading(e), fx = fsin(h), fz = fcos(h);
    s32 lf = (dx * fx + dz * fz) >> 14, lr = (dx * fz - dz * fx) >> 14;
    return lr >= -hw && lr <= hw && lf >= -bh && lf <= ah;
}

/* the people and vehicles a shot could meet this tick: those standing in the box lo..hi (where
   the shots fly this tick), widened by CITY_REACH, as bits of their index in the list (near[2]);
   how many. Nothing moves them in our frame, so city_hit looks at those alone (one pass over the
   list a tick, not one each half-step of each shot) */
int city_near(V3 lo, V3 hi, u32 *near)
{
    u8 *me = controlled();
    int n = PB_NENTITY, k = 0;
    near[0] = near[1] = 0;
    if (n > 63) n = 63;
    lo = vsub(lo, v3(CITY_REACH, 300, CITY_REACH)), hi = vadd(hi, v3(CITY_REACH, 80, CITY_REACH));
    for (int i = 0; i <= n; i++) {
        const u8 *e = PB_ENTITY[i];
        if (!valid(e) || e == me || e == hero)
            continue;
        s32 x = *(const s32 *)(e + E_X) >> 1, z = *(const s32 *)(e + E_Y) >> 1;
        if (x < lo.x || x > hi.x || z < lo.z || z > hi.z)
            continue;
        s32 y = ((19904 - *(const u16 *)(e + E_Z)) >> 1) + world.yoff;
        if (y < lo.y || y > hi.y)
            continue;
        int cls = ent_class(e);
        if (cls < 0 || cls > 1 || *(const s16 *)(e + E_HEALTH) <= 0)
            continue;
        near[i >> 5] |= 1u << (i & 31);
        k++;
    }
    return k;
}

/* a shot of ours at p (units), among those city_near found: the person it is in, else the
   nearest vehicle it is in (a person beside a car is hit before the car that would swallow the
   shot), takes dmg; its index in the list + 1 if it hit one, else 0 */
int city_hit(V3 p, int dmg, const u32 *near)
{
    int best = -1, person = 0;
    s32 bd = 0x7fffffff;
    for (int w = 0; w < 2; w++) {
        u32 m = near[w];
        for (int i = w << 5; m; m >>= 1, i++) {
            while (!(m & 0xff))
                m >>= 8, i += 8;
            if (!(m & 1))
                continue;
            u8 *e = PB_ENTITY[i];
            int cls = ent_class(e);
            if (*(s16 *)(e + E_HEALTH) <= 0 || !ent_box(e, p, cls))
                continue;              /* (already down or burning: the shot flies on) */
            s32 dx = p.x - (*(s32 *)(e + E_X) >> 1), dz = p.z - (*(s32 *)(e + E_Y) >> 1);
            s32 d = dx * dx + dz * dz;
            if (cls > person || (cls == person && d < bd))
                best = i, person = cls, bd = d;
        }
    }
    if (best < 0)
        return 0;
    ent_hurt(PB_ENTITY[best], best, dmg, controlled());
    shot_at = p, shot_when = frame_count | 1, shot_big = dmg >= 100;   /* (who it knocks down flies from it) */
    return best + 1;
}

/* a missile's splash at p: dmg x (1 - d / r) off every person and vehicle within r of it (d from
   the record, less the 150 a body reaches), up to r above or below, but not record `skip` (the
   one the missile hit, which took the whole of it) nor one with the city between: a wall, a
   roof or a deck slab on the way from p to its middle (shot_blocked, two steps) */
void city_blast(V3 p, int dmg, s32 r, int skip)
{
    u8 *me = controlled();
    shot_at = p, shot_when = frame_count | 1, shot_big = 1;   /* (with RAGDOLLS on, whoever stands near
                                                                  it is thrown, hit or not: rag_scan) */
    int n = PB_NENTITY;
    if (n > 63) n = 63;
    for (int i = 0; i <= n; i++) {
        u8 *e = PB_ENTITY[i];
        if (i == skip || !valid(e) || e == me || e == hero)
            continue;
        V3 c = entity_pos(e);
        s32 dx = p.x - c.x, dz = p.z - c.z, dy = p.y - c.y;
        if (iabs(dx) >= r || iabs(dz) >= r || iabs(dy) >= r)
            continue;
        int cls = ent_class(e);
        if (cls < 0 || cls > 1 || *(s16 *)(e + E_HEALTH) <= 0)
            continue;
        s32 d = isqrt(dx * dx + dz * dz) - 150;
        if (d < 0)
            d = 0;
        if (d >= r)
            continue;
        V3 m = vadd(c, v3(0, cls ? 114 : 75, 0)), h = v3((p.x + m.x) >> 1, (p.y + m.y) >> 1, (p.z + m.z) >> 1);
        if (!shot_blocked(p, h) && !shot_blocked(h, m))
            ent_hurt(e, i, dmg * (r - d) / r, me);
    }
}

/* Payback's people and vehicles ahead of the Arwing, in one pass over the list: the first one
   the line from `from` along dir (1.14, unit length) meets within len (*ray: how far along,
   len if none; the point of the line nearest its middle, inside ent_box), and auto-aim's
   candidates: of those inside the cone (cos over lim / ONE) within range, the CITY_CANDS the
   line is on most nearly (by the angle off it), then the nearer, a person counting as half as
   far as a vehicle, best first: their indices in the list in cand[], how far along the line
   in at[]; how many. (Whether the nose can see them is the caller's: spacegame.c lock_scan.)
   The drawn middle is aimed at: 75 over a vehicle's record, 114 over a person's. Nothing
   stands higher than 11000 over the street: from higher than range over that, no one is in
   reach. The cheap tests come first: most of the list is behind the nose or off to the side */
int city_scan(V3 from, V3 dir, s32 len, s32 lim, s32 range, s32 *ray, u8 *cand, s32 *at)
{
    u8 *me = controlled(), *man = hero;
    int n = PB_NENTITY, nc = 0;
    s32 sc[CITY_CANDS], tan2 = ((ONE * ONE / lim) * ONE / lim - ONE) >> 4, yo = world.yoff, r = len;   /* (tan2 1.10) */
    if (n > 63) n = 63;
    if (from.y - yo - 11000 > range)
        n = -1;
    for (int i = 0; i <= n; i++) {
        const u8 *e = PB_ENTITY[i];
        if (!valid(e))
            continue;
        s32 dx = (*(const s32 *)(e + E_X) >> 1) - from.x, dz = (*(const s32 *)(e + E_Y) >> 1) - from.z;
        if (iabs(dx) > range || iabs(dz) > range)
            continue;
        s32 dy = ((19904 - *(const u16 *)(e + E_Z)) >> 1) + yo - from.y;
        if (iabs(dy) > range)
            continue;
        s32 t = (dx * dir.x + dy * dir.y + dz * dir.z) >> 14;   /* (all under 20000: no overflow) */
        if (t < 100 - 114 || t > range || e == me || e == man)
            continue;                  /* (behind the nose, even counting the middle's 114) */
        int cls = ent_class(e);
        if (cls < 0 || cls > 1 || *(const s16 *)(e + E_HEALTH) <= 0)
            continue;
        s32 up = cls ? 114 : 75;
        dy += up, t += (up * dir.y) >> 14;
        if (t < 100 || t > range)
            continue;
        s32 p2 = dx * dx + dy * dy + dz * dz - t * t, t2 = (t * t) >> 10;   /* off the line, squared */
        if (t < r && p2 < 1000 * 1000 && ent_box(e, vadd(from, vscale(dir, t)), cls))
            r = t;
        if (p2 > t2 * tan2)
            continue;
        s32 score = 4 * (p2 / t2) + (cls ? t >> 6 : t >> 5);   /* (tan^2 off the line, 1.10, and the distance) */
        if (nc == CITY_CANDS && score >= sc[nc - 1])
            continue;
        int k = nc < CITY_CANDS ? nc++ : nc - 1;
        for (; k > 0 && sc[k - 1] > score; k--)
            sc[k] = sc[k - 1], cand[k] = cand[k - 1], at[k] = at[k - 1];
        sc[k] = score, cand[k] = i, at[k] = t;
    }
    *ray = r;
    return nc;
}

/* record i of the list as a target now (the list changes under a missile): 1 with its drawn
   middle and, if wanted, its velocity (units a tick), 0 once it is gone, down or burning */
int city_target_at(int i, V3 *p, V3 *v)
{
    if (i < 0 || i > PB_NENTITY || i > 63)
        return 0;
    const u8 *e = PB_ENTITY[i];
    if (!valid(e) || e == hero || e == controlled())
        return 0;
    int cls = ent_class(e);
    if (cls < 0 || cls > 1 || *(const s16 *)(e + E_HEALTH) <= 0)
        return 0;
    *p = vadd(entity_pos(e), v3(0, cls ? 114 : 75, 0));
    if (v)
        *v = v3(*(const s16 *)(e + E_VX) >> 2, 0, *(const s16 *)(e + E_VY) >> 2);
    return 1;
}

/* which record stands at index i of the list now, as a byte (0 none): Payback takes a record off
   the list by moving its last one into the hole, so a lock kept as an index can come to name
   someone else, far away */
int city_tag(int i)
{
    if (i < 0 || i > PB_NENTITY || i > 63)
        return 0;
    const u8 *e = PB_ENTITY[i];
    return valid(e) ? ((u32)e >> 3 & 0xff) | 1 : 0;
}

/* the picture is mirrored (see camera_look), so our own vehicles steer with left and right
   swapped to turn the way they look */
static u16 mirror_keys(u16 k)
{
    return (k & ~(KEY_LEFT | KEY_RIGHT)) | (k & KEY_LEFT ? KEY_RIGHT : 0) | (k & KEY_RIGHT ? KEY_LEFT : 0);
}

static s32 heading_of(const M3 *m) { return fatan2(m->f.x, m->f.z); }

/* ---- buttons ---- */

/* In place of Payback's keypad reader's own answer to a press of SELECT (the phone's past
   replayed on the ticker, every tick the press looks new to it, as it does while we hold the
   decoded SELECT off): nothing. A tap gets that replay from sf_keys instead. */
void sf_hook_select(void) {}

/* Called by Payback right after it reads the keypad (the build hooks that call). Holding
   SELECT for half a second calls the Arwing; a short press still reaches Payback, as its
   phone. While we fly, Payback's man sees no buttons but START. */
/* in a car, with SELECT down: down too short a time to tell the radio's chord from a hold of
   SELECT (and R not yet seen with it; 0 when no sound interrupt has seen it yet), or the chord
   made and Payback's keypad tick yet to take it: the D-pad is not the camera's yet (radio_chord:
   within 6 sound interrupts) */
static int chord_wait(void)
{
    return mode == DRIVE && ((radio.keys & 15) <= 6 || radio_chord());
}

void sf_keys(void)
{
    if (STATE[0] != MAGIC || __keep_canary[0] != CANARY)
        return;
    sf_guard[3] = 0;                                   /* a new tick (see sf_guard) */
    key_calls++;
    if (key_calls - frame_calls > 4 || fade_d) {
        sel_down = sel_seen = 0;                       /* paused, a cut scene or a fade: all Payback's */
        return;
    }
    int sel = !(REG_KEYINPUT & KEY_SELECT);
    int pad = ~REG_KEYINPUT & PAD_ALL;
    u32 now = pb_clock();
    int seen = sel_seen;                               /* (seen down as we drew, since the last read) */
    sel_seen = 0;
    if (!sel && !sel_down && seen && !pad)
        sel_since = now, sel_used = 0, sel_down = 1;   /* down and up again between two reads: a tap */
    if (sel && !sel_down) {
        if (!seen)
            sel_since = now;                           /* (else from when the frame first saw it) */
        sel_used = 0;
    }
    /* SELECT and R pressed together in a car: the radio's next song, not the phone, the Arwing,
       a boost or the camera, whatever the D-pad is doing (steering goes on: while that SELECT
       stays down the D-pad is not the camera's) */
    static u8 r_down;
    int r = !(REG_KEYINPUT & KEY_R);
    if (sel && r && (!r_down || !sel_down) && !r_chord && mode == DRIVE && radio_chord())
        radio_skip(), sel_used = 1, r_chord = sel_chord = 1;
    r_chord &= r;
    sel_chord &= sel;
    r_down = r;
    static u8 pad_lock;                                /* the D-pad is the camera's until let go */
    if (!pad || sel_chord)
        pad_lock = 0;
    else if (sel && !chord_wait())
        pad_lock = 1;
    if (sel && pad)
        sel_used = 1;                                  /* SELECT + D-pad: no Arwing, no phone */
    if (sel && !sel_used && now - sel_since >= 8192)
        call_req = 1, sel_used = 1;
    if (!sel && sel_down && !sel_used) {
        sel_replay = 3, cam_home = 1;                  /* a tap: the phone, and the camera comes home */
        TICK_REPLAY();
    }
    sel_down = sel;
    if (mode == FLY || bail || swimming)
        for (int i = 0; i < B_N; i++)
            if (i != B_START)
                PB_BTN[i] = 0;
    PB_BTN[B_SELECT] = PB_BTN[B_SELECT2] = 0;
    if (sel_replay) {
        sel_replay--;
        PB_BTN[B_SELECT] = PB_BTN[B_SELECT2] = 1;
    }
    /* on foot, the D-pad walks too: hold UP to walk on, DOWN to back up; a quick tap still
       picks the next or previous weapon (Payback sees the tap when it is let go) */
    const u8 *who = controlled();
    static u8 held[2], tap[2];
    if (pad_lock || swimming) {
        PB_BTN[B_UP] = PB_BTN[B_DOWN] = PB_BTN[B_LEFT] = PB_BTN[B_RIGHT] = 0;
        held[0] = held[1] = tap[0] = tap[1] = 0;
    } else if (mode == FOOT && who && is_person(who) && !PB_RESPAWN && !bail) {
        for (int k = B_UP; k <= B_DOWN; k++) {
            int dn = PB_BTN[k];
            if (tap[k]) {
                tap[k]--;
                PB_BTN[k] = 1;
                continue;
            }
            if (dn) {
                if (held[k] < 255)
                    held[k]++;
                PB_BTN[k] = 0;
                if (held[k] > PAD_TAP)
                    PB_BTN[k == B_UP ? B_A : B_B] = 1;
            } else {
                if (held[k] && held[k] <= PAD_TAP)
                    tap[k] = 2;
                held[k] = 0;
            }
        }
    }
    if (inject_l) {
        const u8 *me = controlled();
        inject_l = me && is_car(me) ? inject_l - 1 : 0; /* only to get out of a car */
        PB_BTN[B_L] = inject_l > 0;                     /* press, then let go */
    }
    if (mode == DRIVE && car_ent && who == car_ent) {
        if (car_kind != TANK || r_chord)
            PB_BTN[B_R] = 0;                           /* R is our boost and the radio chord's; the tank's is its gun */
        if (PB_BTN[B_L] && !bail)
            bail_press();                              /* the car stops dead, or at speed he bails out */
    }
}

/* ---- the camera ---- */

static V3 cam_focus;                               /* what the camera looks at (the man, the car, the Arwing) */
static void camera_look(V3 pos, V3 fwd, V3 up, s32 dist, s32 height, s32 aim_up, s32 aim_fwd, int free)
{
    if (free) {
        /* the player's orbit and zoom (see cam_yaw): swing the whole rig round the up axis */
        if (cam_yaw)
            fwd = vnorm(vadd(vscale(fwd, fcos(cam_yaw)), vscale(vcross(up, fwd), fsin(cam_yaw))));
        s32 z = cam_zoom < ZOOM_NEAR ? ZOOM_NEAR : cam_zoom;   /* (first person is not a closer chase) */
        dist = dist * z >> 8;
        height = height * z * z >> 16;   /* further out is higher up, nearer is lower */
    }
    V3 want = vadd(vscale(fwd, -dist), vscale(up, height));
    s32 w;
    if (world_water(pos.x, pos.z, &w) && pos.y < w)
        pos.y = w;                                     /* sunk in water: watch the surface */
    cam_focus = pos;
    cam_off = cam_cut ? want : vadd(cam_off, vshr(vsub(want, cam_off), 2));
    if (cam_keep && !cam_cut) {
        /* on foot the swing is round you, at its distance: eased straight toward its new place
           it cut through you on every turn, your back across half the screen for a second */
        s32 yaw = fatan2(cam_off.x, cam_off.z), r = isqrt(cam_off.x * cam_off.x + cam_off.z * cam_off.z);
        yaw += (s16)(fatan2(want.x, want.z) - yaw) >> 2;
        r += (dist - r) >> 3;                          /* (and in to it: out of the Arwing it jumped 400 in a frame) */
        cam_off.x = fsin(yaw) * r >> 14;
        cam_off.z = fcos(yaw) * r >> 14;
    }
    cam_up = cam_cut ? up : vnorm(vadd(cam_up, vshr(vsub(up, cam_up), 2)));
    cam_cut = 0;
    cam.pos = vadd(pos, cam_off);
    /* Payback's streets are narrow: come in closer rather than look out of a wall */
    V3 pivot = vadd(pos, v3(0, 150, 0)), span = vsub(cam.pos, pivot);
    int in = 0, k;
    for (k = 1; k <= 8; k++) {
        V3 q = vadd(pivot, vscale(span, k * 2048));
        if (world_ground(q.x, q.z) > q.y - 40) {
            cam.pos = vadd(pivot, vscale(span, (k - 1) * 2048));
            in = 9 - k;
            break;
        }
    }
    if (k <= 8 && swimming && mode == FOOT) {
        /* a swimmer backed up to a bank: as near, aim as far nearer him, down at the water (a man's
           height over him and on ahead would leave him under the picture) */
        aim_up = aim_up * (k - 1) >> 3;
        aim_fwd = (aim_fwd * (k - 1) >> 3) + 48;
    }
    /* ... and on foot it rises as it comes in, looking down past you: close behind at your
       height, your back filled the middle of the screen and Payback's hearts for seconds */
    static s32 lift;
    s32 lw = cam_keep ? in * 70 : 0, room = 1 << 20, db, dt;
    for (int k = 0; k < 2; k++)                        /* (not up through a deck over you: half the room) */
        if (world_deck(cam.pos.x, cam.pos.z, k, &db, &dt) && pos.y < db && db - 100 - cam.pos.y < room)
            room = db - 100 - cam.pos.y;
    if (room < 0)
        room = 0;
    if (lw > room >> 1)
        lw = room >> 1;
    lift += (lw - lift) >> 2;
    cam.pos.y += lift < room ? lift : room;
    s32 g = world_ground(cam.pos.x, cam.pos.z) + 60;
    if (cam.pos.y < g)
        cam.pos.y = g;
    V3 target = vadd(pos, vadd(vscale(up, aim_up), vscale(fwd, aim_fwd)));
    cam.m.f = vsub(target, cam.pos);
    cam.m.u = cam_up;
    morth(&cam.m);
    /* Payback's world is the mirror image of ours (its y is our z): draw it the way Payback
       shows it, so its walking and the minimap turn the same way as the picture */
    cam.m.r = v3(-cam.m.r.x, -cam.m.r.y, -cam.m.r.z);
}

/* First person: the camera at the eyes, looking where he (or the car) looks, swung round by the
   player's SELECT + LEFT/RIGHT like the chase view. Our own body and car are not drawn then. */
static void camera_eyes(V3 pos, V3 fwd, V3 up, s32 eye_up, s32 eye_fwd, s32 look_down)
{
    if (cam_yaw)
        fwd = vnorm(vadd(vscale(fwd, fcos(cam_yaw)), vscale(vcross(up, fwd), fsin(cam_yaw))));
    cam.pos = vadd(pos, vadd(vscale(up, eye_up), vscale(fwd, eye_fwd)));
    s32 w;
    if (world_water(pos.x, pos.z, &w) && cam.pos.y < w + 30)
        cam.pos.y = w + 30;
    cam_off = vsub(cam.pos, pos);
    cam_focus = pos;
    cam_up = cam_cut ? up : vnorm(vadd(cam_up, vshr(vsub(up, cam_up), 2)));
    cam_cut = 0;
    cam.m.f = vadd(vscale(fwd, 1000), vscale(up, -look_down));
    cam.m.u = cam_up;
    morth(&cam.m);
    cam.m.r = v3(-cam.m.r.x, -cam.m.r.y, -cam.m.r.z);   /* (the mirror image: see camera_look) */
}

/* SELECT + D-pad: the screen is mirrored, so LEFT swings the view the way it looks */
static void camera_move(int ticks)
{
    if (mode == FLY && sg_state == SG_DOCKED)
        return;                                        /* the hangar's camera is fixed */
    if (cam_pad) {
        cam_home = 0;
        if (cam_pad & KEY_LEFT)
            cam_yaw += 400 * ticks;                    /* about 2.7 s a turn */
        if (cam_pad & KEY_RIGHT)
            cam_yaw -= 400 * ticks;
        if (cam_pad & KEY_UP)
            cam_zoom -= 3 * ticks;
        if (cam_pad & KEY_DOWN)
            cam_zoom += 3 * ticks;
        cam_yaw = (s16)cam_yaw;
        cam_zoom = clamp(cam_zoom, ZOOM_IN, ZOOM_OUT);
    } else if (cam_home) {
        for (int t = 0; t < ticks; t++) {
            cam_yaw -= cam_yaw / 12;                   /* back behind you in about half a second */
            if (!fp_view)
                cam_zoom -= (cam_zoom - 256) / 12;     /* (first person stays: SELECT+DOWN steps back) */
        }
        if (iabs(cam_yaw) < 300 && (fp_view || iabs(cam_zoom - 256) < 12))
            cam_yaw = 0, cam_zoom = fp_view ? cam_zoom : 256, cam_home = 0;
    }
}

static int car_tall(void);
static void camera_update(const u8 *me)
{
    V3 level = v3(0, ONE, 0);
    if (bail_camera())
        return;
    cam_keep = mode == FOOT && me && !is_vehicle(me);
    int can_fp = mode == DRIVE || (mode == FOOT && me && !swimming);
    int was_fp = fp_view;
    fp_view = can_fp && (cam_zoom < ZOOM_FP || (fp_view && cam_zoom < ZOOM_FP + 30));
    if (fp_view != was_fp) {
        cam_cut = 1;                                   /* (a cut in, not a swoop through the car) */
        static u8 told;
        if (fp_view && !told)
            told = 1, sg_note("First person. SELECT+DOWN steps back.");   /* (once: the ticker stays quiet) */
    }
    if (fp_view && mode == DRIVE) {
        V3 fwd = car.b.m.f, up = car.b.m.u;
        if (!car.wheels)
            up = level;
        int tall = car_tall();
        camera_eyes(vshr(car.b.pos, FX), fwd, up, tall ? 150 : 70, 40, 20);
    } else if (fp_view) {
        M3 m;
        myaw(&m, entity_heading(me));
        camera_eyes(entity_pos(me), m.f, level, 230, 30, 30);
    } else if (mode == DRIVE) {
        V3 fwd = car.b.m.f, up = car.b.m.u;
        if (!car.wheels) {
            if (vlen(car.b.vel) > 4000)
                fwd = vnorm(v3(car.b.vel.x, car.b.vel.y >> 1, car.b.vel.z));
            up = level;                                /* airborne: keep the horizon level */
        }
        int tall = car_tall();
        if (car.on_loop)
            camera_look(vshr(car.b.pos, FX), fwd, up, 600, 340, 30, 250, 1);
        else    /* (over a van or a bus from higher: at a car's height its box hid the road ahead) */
            camera_look(vshr(car.b.pos, FX), fwd, up, tall ? 880 : 820, tall ? 440 : 300, tall ? 190 : 110, 250, 1);
    } else if (mode == FLY && sg_state == SG_DOCKED) {
        /* in the hangar: the camera sways slowly in front of the Arwing on its pad */
        M3 m;
        myaw(&m, 41768 + fsin(frame_count * 40) * 4000 / ONE);       /* in front, to one side */
        /* (shifted sideways, so the Arwing stands clear of the menu on the left) */
        camera_look(vadd(sg_pad(), vscale(m.r, 300)), m.f, level, 800, 300, 40, 0, 0);
    } else if (mode == FLY) {
        V3 up = ship.b.m.u, fwd = ship.b.m.f;
        if (sg_state == SG_DEAD) {
            up = level;                                /* (a wreck rolling over: the camera does not; */
            if (iabs(cam.m.f.x) + iabs(cam.m.f.z) > ONE / 8)   /* nor round with its tumbling nose, */
                fwd = vnorm(v3(cam.m.f.x, 0, cam.m.f.z));      /* 40-60 degrees a frame: its own heading) */
        } else if ((ship.b.pos.y >> FX) < SPACE_HI)    /* half the bank, like Star Fox; over on its side */
            up = vnorm(vadd(up, v3(0, up.y >= ONE / 2 ? ONE : up.y > 0 ? 2 * up.y : 0, 0)));
                                                       /* and on over a loop, all of it (no flip at the top) */
        /* (docking, lower: 250 over the Arwing it went through the station's ring, the screen
           grey, then orange, for half a second) */
        camera_look(vshr(ship.b.pos, FX), fwd, up, 950, sg_state == SG_DOCKING ? 100 : 250, 110, 250, 1);
    } else if (me) {
        M3 m;
        myaw(&m, entity_heading(me));
        int on_foot = !is_vehicle(me);
        camera_look(entity_pos(me), m.f, level, on_foot ? 560 : 900, on_foot ? 360 : 400,
                    on_foot ? 150 : 110, on_foot ? 200 : 300, 1);
    }
}

/* ---- the Stunt Fox car in Payback's traffic ---- */

static void car_take(u8 *e)
{
    V3 p = entity_pos(e);
    car_reset(&car, v3(p.x, (surface_fine(v3(p.x << FX, p.y << FX, p.z << FX)) >> FX) + 140, p.z), entity_heading(e));
    car_ent = e;
    car_kind = vehicle_kind(e);
    car_boom = car_wet = 0;
    mode = DRIVE;
    ghost = GH_NONE;                               /* (back into the car rolling on empty: it stops) */
}

/* a vehicle as we draw it: a box (or two, the helicopter) on the ground, from its descriptor
   (half width, ahead, behind: build.py writes the drawn sizes there, twice our units) */
#define D_HALFW 0xe
#define D_AHEAD 0x12
#define D_BEHIND 0x14
#define D_MASS 0x20
typedef struct { s32 x, z, fx, fz, hw, hl; } HitBox;  /* middle, forward (ONE), half width and length */
typedef struct { HitBox b[2]; s32 n, reach, mass; } Shape;

static void box_at(HitBox *b, V3 p, s32 fx, s32 fz, s32 mid, s32 hw, s32 hl)
{
    b->x = p.x + (fx * mid >> 14), b->z = p.z + (fz * mid >> 14);
    b->fx = fx, b->fz = fz, b->hw = hw, b->hl = hl;
}

static void shape_of(Shape *c, const u8 *d, V3 p, s32 fx, s32 fz)
{
    s32 w = 114, ah = 235, bh = 235, m = 1000;       /* (a saloon, if we have no descriptor) */
    if (d)
        w = *(const s16 *)(d + D_HALFW) >> 1, ah = *(const s16 *)(d + D_AHEAD) >> 1,
        bh = *(const s16 *)(d + D_BEHIND) >> 1, m = *(const u16 *)(d + D_MASS);
    box_at(&c->b[0], p, fx, fz, (ah - bh) >> 1, w, (ah + bh) >> 1);
    c->n = 1;
    c->reach = (ah > bh ? ah : bh) + w;
    c->mass = (m >> 4) + 1;
}

/* any vehicle record: the helicopter (models.c heli_v) its cabin (180 x 320, z -150..170) and its
   thin tail boom (to z -500, 60 up and over; the rotor is over our roof), the rest by descriptor */
static void shape_rec(Shape *c, const u8 *e, V3 p)
{
    s32 h = entity_heading(e), fx = fsin(h), fz = fcos(h);
    const u8 *d = desc_of(e);
    if (entity_desc(e) != VEH_HELI) {
        shape_of(c, d, p, fx, fz);
        return;
    }
    box_at(&c->b[0], p, fx, fz, 10, 90, 160);
    box_at(&c->b[1], p, fx, fz, -320, 16, 180);
    c->n = 2;
    c->reach = 600;
    c->mass = (*(const u16 *)(d + D_MASS) >> 4) + 1;
}

/* our car's shape, where it is now (c: its middle, units) */
static void shape_ours(Shape *me, V3 c)
{
    s32 fl = isqrt((car.b.m.f.x >> 2) * (car.b.m.f.x >> 2) + (car.b.m.f.z >> 2) * (car.b.m.f.z >> 2)) << 2;
    if (fl < 1024)
        fl = 1024;                                     /* (on its nose: any heading will do) */
    shape_of(me, car_ent ? desc_of(car_ent) : 0, c, car.b.m.f.x * ONE / fl, car.b.m.f.z * ONE / fl);
}

/* how far apart two boxes are along the axis that parts them most (under 0: they overlap, by
   that much at the least along it), and that axis out towards a (n, ONE) */
static s32 box_sep(const HitBox *a, const HitBox *b, s32 *nx, s32 *nz)
{
    s32 dx = a->x - b->x, dz = a->z - b->z, best = -0x7fffffff;
    for (int k = 0; k < 4; k++) {
        const HitBox *o = k < 2 ? a : b;
        s32 ux = k & 1 ? o->fz : o->fx, uz = k & 1 ? -o->fx : o->fz;
        s32 d = (dx * ux + dz * uz) >> 14;
        s32 ra = (a->hw * iabs((a->fz * ux - a->fx * uz) >> 14) + a->hl * iabs((a->fx * ux + a->fz * uz) >> 14)) >> 14;
        s32 rb = (b->hw * iabs((b->fz * ux - b->fx * uz) >> 14) + b->hl * iabs((b->fx * ux + b->fz * uz) >> 14)) >> 14;
        s32 sep = iabs(d) - ra - rb;
        if (sep > best)
            best = sep, *nx = d < 0 ? -ux : ux, *nz = d < 0 ? -uz : uz;
    }
    return best;
}

/* the deepest overlap (least apart) of two shapes' boxes, as box_sep */
static s32 shape_sep(const Shape *p, const Shape *q, s32 *nx, s32 *nz)
{
    s32 best = 0x7fffffff, x, z;
    for (int a = 0; a < p->n; a++)
        for (int k = 0; k < q->n; k++) {
            s32 g = box_sep(&p->b[a], &q->b[k], &x, &z);
            if (g < best)
                best = g, *nx = x, *nz = z;
        }
    return best;
}

/* a change of our car's velocity by a hit (fine a tick): never off backwards faster than a quarter
   of the speed it went in at, nor sideways faster than that (or 12 a tick), nor on ahead by more
   than twice it, so an off-centre hit does not throw it into a roll. Under 24 a tick (stopped, or
   creeping) it counts as 24 along its own heading: a police car at full chase no longer throws a
   stopped car sideways 8 cells */
#define KICK_SLOW (24 << FX >> 4)
static void car_kick(s32 cx, s32 cz)
{
    Body *b = &car.b;
    s32 ix = b->vel.x >> 4, iz = b->vel.z >> 4, in = isqrt(ix * ix + iz * iz);
    cx >>= 4, cz >>= 4;
    if (in < KICK_SLOW) {
        s32 fx = b->m.f.x >> 4, fz = b->m.f.z >> 4, fl = isqrt(fx * fx + fz * fz);
        if (fl < 64)
            fx = 0, fz = fl = 1;                       /* (on its nose: any heading will do) */
        ix = fx * KICK_SLOW / fl, iz = fz * KICK_SLOW / fl, in = KICK_SLOW;
    }
    /* along and across the way we were going (fine >> 4) */
    s32 al = (cx * ix + cz * iz) / in, ac = (cz * ix - cx * iz) / in, cap = in >> 2;
    if (cap < (12 << FX >> 4))
        cap = 12 << FX >> 4;
    ac = clamp(ac, -cap, cap);
    al = clamp(al, -in - (in >> 2), 2 * in);
    b->vel.x += ((al * ix - ac * iz) / in) << 4;
    b->vel.z += ((al * iz + ac * ix) / in) << 4;
}

/* the size of the car we drive (car.c: half width, ahead, behind; 256 = the saloon), from its
   descriptor, which build.py sizes from the model we draw for it (2 to our units) */
void car_scale(u16 s[3])
{
    const u8 *d = car_ent && entity_desc(car_ent) != VEH_HELI ? desc_of(car_ent) : 0;
    s32 w = 228, a = 470, b = 470;
    if (d)
        w = *(const s16 *)(d + D_HALFW), a = *(const s16 *)(d + D_AHEAD), b = *(const s16 *)(d + D_BEHIND);
    s[0] = clamp(w * 256 / 228, 160, 640);             /* (no wheels on top of each other) */
    s[1] = clamp(a * 256 / 470, 160, 640);
    s[2] = clamp(b * 256 / 470, 160, 640);
}

/* Payback's knock pushes two records apart when it sees them meet by the end of its next frame
   (0x080135bc: their circles, moved on by their speeds over the frame's ticks), so with our car
   it pushed the other car a car length before ours got there, and our car stopped or turned short
   of it. Between our car and a vehicle its push and its harm never come (guard.s sf_hook_kick,
   both records, and sf_hook_knock): car_bump meets the two where they touch, with one bounce and
   Payback's harm for it (with the knock on top, both were pushed twice and the parked car left at
   twice our speed, and the harm came when car_bump had already parted them: none). A person's
   knock is Payback's (holding it until the two touch would not hold his reel, which it starts
   at once: he reeled unhurt). 1: none comes. */
int sf_kick_far(const u8 *a, const u8 *b)
{
    const u8 *o = a == car_ent ? b : b == car_ent ? a : 0;
    return o && mode == DRIVE && valid(o) && is_vehicle(o);
}

/* Payback's vehicles are solid: our car against each as the two are drawn (boxes), where they
   are now and at our height (a car on a deck above or below is not met). Payback's knock between
   them never comes (sf_kick_far): this meets them as our car moves: we are moved out of the
   overlap, and if we still close on it the two share a bounce (half) by mass, the other takes
   Payback's harm for it, and our car feels it as a crash (car_crash) */
static void car_bump(void)
{
    V3 c = vshr(car.b.pos, FX);
    s32 cy = c.y - 76;                                 /* (our record's height: our wheels' ground) */
    Shape me, it;
    shape_ours(&me, c);
    int n = PB_NENTITY;                                /* (the last index) */
    if (n > 63) n = 63;
    for (int i = 0; i <= n; i++) {
        u8 *e = PB_ENTITY[i];
        if (!valid(e) || e == car_ent || !is_vehicle(e))
            continue;
        V3 p = entity_pos(e);
        s32 dx = c.x - p.x, dz = c.z - p.z, dy = cy - p.y;
        if (iabs(dx) >= 2048 || iabs(dz) >= 2048 || iabs(dy) > (entity_desc(e) == VEH_HELI ? 150 : 260))
            continue;                                  /* (the helicopter's cabin is 150 tall, as our car) */
        shape_rec(&it, e, p);
        s32 reach = me.reach + it.reach, nx, nz;
        if (iabs(dx) >= reach || iabs(dz) >= reach)
            continue;
        s32 deep = -shape_sep(&me, &it, &nx, &nz);
        if (deep < 0)
            continue;
        if (deep > 1024)
            deep = 1024;                               /* (vscale would overflow) */
        V3 nrm = v3(nx, 0, nz);
        car.b.pos.x += nrm.x * deep >> (14 - FX);
        car.b.pos.z += nrm.z * deep >> (14 - FX);
        V3 tv = v3(*(const s16 *)(e + E_VX) << 6, 0, *(const s16 *)(e + E_VY) << 6);
        s32 vn = vdot(vsub(car.b.vel, tv), nrm);       /* closing: under 0 */
        if (vn < 0) {
            s32 j = vn < -43690 ? -65535 : vn + (vn >> 1), ours = it.mass * 256 / (me.mass + it.mass);
            V3 dv = vscale(nrm, j * ours >> 8);         /* (|j| under 2^16) */
            car_kick(-dv.x, -dv.z);
            s32 g = j * (256 - ours) >> 14;            /* (its record's units: >> 8, >> 6) */
            *(s16 *)(e + E_VX) += nrm.x * g >> 14;
            *(s16 *)(e + E_VY) += nrm.z * g >> 14;
            /* and its harm, as Payback's knock would take it: by the square of its change of
               velocity in its units (3/16384: rear-ending a parked k5 at 85 in a k7 takes 25,
               head-on into one coming at 24, 40; two saloons at 48, 4; at 16, none). Ours is
               car_crash's. Not the helicopter's (Payback never knocks it either) */
            s32 ga = iabs(g) > 1024 ? 1024 : iabs(g), harm = ga * ga * 3 >> 14;
            s16 *hp = (s16 *)(e + E_HEALTH);
            if (harm > 0 && *hp > 0 && entity_desc(e) != VEH_HELI) {
                *hp = *hp > harm ? *hp - harm : 0;
                *(u8 **)(e + E_FOE) = car_ent;         /* (we did it: Payback's score and stars) */
            }
            if (-vn > car.impact)
                car.impact = -vn;
            if (vn <= -(24 << FX))
                shout("CRASH!");
        }
    }
}

/* Payback's map ends two cells in from its edge */
static void car_fence(void)
{
    const s32 lo = (2 * CELL) << FX, hi = ((CITY - 2) * CELL) << FX;
    Body *b = &car.b;
    if (b->pos.x < lo) b->pos.x = lo, b->vel.x = iabs(b->vel.x) >> 1;
    if (b->pos.x > hi) b->pos.x = hi, b->vel.x = -iabs(b->vel.x) >> 1;
    if (b->pos.z < lo) b->pos.z = lo, b->vel.z = iabs(b->vel.z) >> 1;
    if (b->pos.z > hi) b->pos.z = hi, b->vel.z = -iabs(b->vel.z) >> 1;
}

static int air_ticks, loop_top, upside_ticks;
static s32 spin_pitch, spin_roll, spin_yaw;

static void car_stunts(void)
{
    Body *b = &car.b;
    if (car.in_water)
        air_ticks = 0;                                 /* (sinking is no jump) */
    else if (car.wheels == 0) {
        air_ticks++;
        spin_pitch += vdot(b->w, b->m.r);
        spin_roll += vdot(b->w, b->m.f);
        spin_yaw += vdot(b->w, b->m.u);
    } else {
        if (air_ticks > 45 && car.wheels >= 2 && b->m.u.y > 8000) {
            s32 turn = 1544000;                        /* 0.9 of a turn, 1.18 radians */
            if (iabs(spin_pitch) > turn)
                shout(spin_pitch > 0 ? "FRONT FLIP!" : "BACK FLIP!");
            else if (iabs(spin_roll) > turn)
                shout("BARREL ROLL!");
            else if (iabs(spin_yaw) > turn)
                shout("360 SPIN!");
            else if (air_ticks > 100)
                shout("HUGE AIR!");
            else
                shout("BIG AIR!");
        }
        air_ticks = 0;
        spin_pitch = spin_roll = spin_yaw = 0;
    }
    if (car.on_loop >= 2 && car.loop_ang > 26000 && car.loop_ang < 39000)
        loop_top = 1;
    if (loop_top && !car.on_loop && car.wheels >= 3) {
        loop_top = 0;
        if (b->m.u.y > 12000)
            shout("LOOP THE LOOP!");
    }
    /* stuck on the roof or side: back on its wheels */
    if (b->m.u.y < 4000 && vlen(b->vel) < 1000)
        upside_ticks++;
    else
        upside_ticks = 0;
    if (upside_ticks > 100) {
        upside_ticks = 0;
        myaw(&b->m, heading_of(&b->m));
        b->w = v3(0, 0, 0);
        b->vel = v3(0, 0, 0);
        b->pos.y += 160 << FX;
    }
}

/* the car's own crashes: health off its record the way Payback takes it from its own vehicles
   (by the square of the speed into the wall, in Payback's velocity units, but twice that: a
   few crashes at full speed wear it down to its last point, never past it), for the speed it
   lost flat out (not landing a jump) */
static s32 crash_lost;

static void car_crash(s32 speed_before)
{
    Body *b = &car.b;
    s32 vx = b->vel.x >> 4, vz = b->vel.z >> 4;
    s32 lost = speed_before - (s32)(isqrt(vx * vx + vz * vz) << 4);
    if (car.impact > 4096 && lost > car.impact >> 2) {
        s32 v = car.impact >> 6;
        crash_lost += v * v >> 13;
    }
}

/* Payback's knocks on our car's record (sf_knock), which entity_put writes over: our car takes
   them as they are (its change is weighted by mass, equal and opposite to the other's; only a
   person's come, when Payback sees the two meet: a vehicle's never, sf_kick_far), within
   car_kick's limits, and it wears for it as for a crash (car_crash: the square of the change, in
   Payback's units, >> 13) */
static void car_knocked(void)
{
    s32 kx = clamp(sf_knock[0], -1024, 1024), kz = clamp(sf_knock[1], -1024, 1024);
    sf_knock[0] = sf_knock[1] = 0;
    if (!(kx | kz) || mode != DRIVE)
        return;
    car_kick(kx << 6, kz << 6);                        /* (Payback's change, << 6) */
    crash_lost += (kx * kx + kz * kz) >> 13;
}

/* our car is burning or burnt out, or Payback has the player (dead or arrested): it stops
   (a wreck blows up, then the player is reborn) */
static int car_dead(void)
{
    return car_ent && (wrecked(car_ent) || PB_RESPAWN > 0);
}

/* ---- swimming ----
   Payback's man sinks in its water and drowns there (a life lost, and its death screen). Ours
   swims: once he is in (walked or fell in, got out of a car going under, or of the Arwing on
   the water) we move him, his head at the surface, and hold Payback's record there each frame
   (it sinks him 24 a tick from where we put him, nowhere near the depth it drowns him at). The
   D-pad swims, slower than he walks and turning as he does; he climbs out onto a bank no
   higher than himself, or up a ladder, where tools/mkworld.py found them (world.swim). */
#define SWIM_FWD 10                /* units a tick: 0.6 of a cell a second (he walks about 1) */
#define SWIM_FAR 15                /* ... in open water, far from a way out (the arrow shows): a long
                                      swim (map 2's channel, map 6's sea) takes a third less time */
#define SWIM_BACK 6
#define SWIM_TURN 480              /* a turn in about 2.3 s, as walking */
#define SWIM_CLIMB 256             /* the highest bank he climbs out onto (mkworld.py's CLIMB) */
#define SWIM_DROP 512              /* ... the lowest (DROP) */
#define SWIM_ROOM 256              /* room he needs over the water under a deck (SWIM_ROOM) */
#define LADDER_UP 20               /* units a tick up a ladder */
#define SWIM_BODY 192              /* he keeps this far off a bank he does not climb (in front of its
                                      face, which would hide him drawn at it) */
#define E_SINKING 0x125            /* Payback's man is on the bed of its water, going down */
static s32 swim_head;              /* our heading */
static V3 swim_at;                 /* where he is: on the water, or up a ladder */
static u16 swim_t;                 /* ticks in the water (his stroke) */

static int cell_of(s32 x, s32 z) { return clamp(x >> 10, 0, CITY - 1) * CITY + clamp(z >> 10, 0, CITY - 1); }

/* is anything over the water of cell c too low to swim under? */
static int swim_roof(int c, s32 surf)
{
    const s8 *dd[2] = {world.deck + 4 * c, world.deck2 + 4 * c};
    for (int k = 0; k < 2; k++) {
        const s8 *d = dd[k];
        if ((d[0] | d[1] | d[2] | d[3]) && (d[0] + HBIAS) * 64 < surf + SWIM_ROOM && (d[1] + HBIAS) * 64 > surf)
            return 1;
    }
    return 0;
}

/* Payback's record where he is: he sees no buttons (sf_keys), we move him */
static void swim_hold(u8 *me)
{
    man_put(me, swim_at, swim_head);
    *(u16 *)(me + E_Z) = 19904 - 2 * (swim_at.y - world.yoff);
    *(s16 *)(me + E_VZ) = 0;
}

/* is cell (x, z) water he swims on into (or a bank, a wall)? */
static int wet_cell(int x, int z)
{
    return world_cell(x << 10, z << 10)->shape == SHAPE_WATER;
}

/* in the water at p (its surface): swimming from now on (a body's breadth off its banks) */
static void swim_in(u8 *me, V3 p)
{
    int x = p.x >> 10, z = p.z >> 10;
    p.x = clamp(p.x, (x << 10) + (wet_cell(x - 1, z) ? 0 : SWIM_BODY),
                (x << 10) + (wet_cell(x + 1, z) ? 1023 : 1023 - SWIM_BODY));
    p.z = clamp(p.z, (z << 10) + (wet_cell(x, z - 1) ? 0 : SWIM_BODY),
                (z << 10) + (wet_cell(x, z + 1) ? 1023 : 1023 - SWIM_BODY));
    swimming = 1;
    swim_lad = 0;
    swim_at = p;
    swim_head = entity_heading(me);
    swim_t = 0;
    swim_hold(me);
    if (!(told & 16)) {
        told |= 16;
        swim_hint = 240;                               /* 2 s (on screen, not on Payback's ticker) */
        swim_msg = 0;
    }
}

/* out onto the bank at p: Payback's man again */
static void swim_out(u8 *me, V3 p)
{
    swimming = swim_lad = 0;
    swim_at = p;
    swim_hold(me);
    me[E_SINKING] = 0;
}

/* Payback's man has gone into the water. Or it sinks him where we have land: out of a car going
   under by a quay, its door is in the quay, under its ground (Payback's water runs under it).
   Then he comes up in the water nearest him, the car's, never inside the bank. */
static APART void swim_check(u8 *me)
{
    V3 p = entity_pos(me);
    s32 w;
    if (world_water(p.x, p.z, &w)) {
        if (p.y <= w + 16)
            swim_in(me, v3(p.x, w, p.z));
        return;
    }
    if (!me[E_SINKING])
        return;
    int x = p.x >> 10, z = p.z >> 10;
    s32 bd = -1;
    V3 at = p;
    for (int a = x - 2; a <= x + 2; a++)
        for (int b = z - 2; b <= z + 2; b++) {
            if (a < 2 || b < 2 || a >= CITY - 2 || b >= CITY - 2 || !(world.swim[a * CITY + b] & 16))
                continue;
            s32 qx = clamp(p.x, a << 10, (a << 10) + 1023), qz = clamp(p.z, b << 10, (b << 10) + 1023);
            s32 d = (qx - p.x) * (qx - p.x) + (qz - p.z) * (qz - p.z);
            if (bd < 0 || d < bd)
                bd = d, at = v3(qx, world.cell[a * CITY + b].hi, qz);
        }
    if (bd >= 0)                                       /* (none near: Payback's own way) */
        swim_in(me, at);
}

/* a move along x or z (one of dx, dz is 0): on through the water, onto a bank or up a ladder,
   or stopped a body's breadth off it (his front, f, at the bank) */
static void swim_move(u8 *me, s32 dx, s32 dz)
{
    V3 q = v3(swim_at.x + dx, swim_at.y, swim_at.z + dz);
    if (q.x < 2 * CELL || q.z < 2 * CELL || q.x >= (CITY - 2) * CELL || q.z >= (CITY - 2) * CELL)
        return;
    s32 fx = q.x + (dx > 0 ? SWIM_BODY : dx < 0 ? -SWIM_BODY : 0);
    s32 fz = q.z + (dz > 0 ? SWIM_BODY : dz < 0 ? -SWIM_BODY : 0);
    int i = cell_of(swim_at.x, swim_at.z), j = cell_of(fx, fz);
    if (i == j) {
        swim_at = q;
        return;
    }
    const Cell *c = &world.cell[j];
    if (c->shape == SHAPE_WATER) {
        /* (on into it, and down at once where it is lower when he is in it) */
        if (c->hi - swim_at.y <= SWIM_CLIMB && !swim_roof(j, c->hi))
            swim_at = v3(q.x, cell_of(q.x, q.z) == j ? c->hi : swim_at.y, q.z);
        return;
    }
    int e = dx < 0 ? 3 : dx > 0 ? 1 : dz < 0 ? 0 : 2, w = world.swim[i];
    if (w & 32)
        for (int k = 0; k < world.nladder; k++) {
            const Ladder *l = &world.ladder[k];
            if (l->x * CITY + l->z == i && l->edge == e) {
                swim_lad = k + 1;                      /* onto it, facing the bank (swim_tick takes */
                swim_head = (2 - e) * 16384;           /* him in to its foot) */
                return;
            }
        }
    /* onto a bank no higher than he is (where nothing in reach is, any bank): its height on the
       edge where he crosses it, as mkworld.py has it (a ramp up out of the water at its foot; the
       8: a unit in from the edge, as close as a cell's floor gets) */
    s32 ex = (fx & ~1023) + (dx < 0 ? 1023 : 0), ez = (fz & ~1023) + (dz < 0 ? 1023 : 0);
    s32 g = world_ground(dx ? ex : q.x, dz ? ez : q.z);
    /* (water with no table, the map's rim: any bank of that height) */
    if ((w >> e & 1 || !(w & 16)) && g - swim_at.y <= SWIM_CLIMB + 8 && g >= swim_at.y - SWIM_DROP - 8) {
        q = v3(fx + dx * 6, 0, fz + dz * 6);
        q.y = world_ground(q.x, q.z);
        swim_out(me, q);
        return;
    }
    /* a bank he climbs onto along part of the edge only (one sloping along the water, an
       underpass's ramp going down beside it): on along it to the nearest part he can, not
       stopped dead where nothing shows why */
    static u8 sliding;
    if (!(w >> e & 1) || sliding)
        return;
    s32 at = dx ? q.z : q.x, best = at + 4096;
    for (s32 t = (at & ~1023) + 32; t < (at | 1023); t += 64) {
        s32 h = dx ? world_ground(ex, t) : world_ground(t, ez);
        if (h - swim_at.y <= SWIM_CLIMB && h >= swim_at.y - SWIM_DROP && iabs(t - at) < iabs(best - at))
            best = t;
    }
    s32 v = iabs(dx + dz), d = clamp(best - at, -v, v);
    if (best - at < 4096 && d) {
        sliding = 1;
        swim_move(me, dx ? 0 : d, dx ? d : 0);
        sliding = 0;
    }
}

static APART void swim_tick(u8 *me, u16 k)
{
    swim_t++;
    if (swim_lad) {
        /* in to its foot, a hand's breadth off the bank's face, as he goes up (not in one jump) */
        static const s16 lx[4] = {512, 1024 - 72, 512, 72}, lz[4] = {72, 512, 1024 - 72, 512};
        const Ladder *l = &world.ladder[swim_lad - 1];
        s32 tx = (l->x << 10) + lx[l->edge], tz = (l->z << 10) + lz[l->edge];
        swim_at.x += clamp(tx - swim_at.x, -40, 40);
        swim_at.z += clamp(tz - swim_at.z, -40, 40);
        swim_at.y += LADDER_UP;
        if (swim_at.y >= l->hi) {
            static const s8 out[4][2] = {{0, -1}, {1, 0}, {0, 1}, {-1, 0}};
            V3 p = v3(tx + out[l->edge][0] * 160, 0, tz + out[l->edge][1] * 160);
            p.y = world_ground(p.x, p.z);
            swim_out(me, p);
        }
        return;
    }
    if (k & KEY_LEFT)
        swim_head += SWIM_TURN;
    if (k & KEY_RIGHT)
        swim_head -= SWIM_TURN;
    swim_head = (u16)swim_head;
    int v = k & (KEY_UP | KEY_A) ? (swim_far ? SWIM_FAR : SWIM_FWD) : k & (KEY_DOWN | KEY_B) ? -SWIM_BACK : 0;
    if (v) {
        swim_move(me, fsin(swim_head) * v >> 14, 0);
        if (swimming && !swim_lad)
            swim_move(me, 0, fcos(swim_head) * v >> 14);
    }
}

/* ---- the Arwing ---- */

static int was_flying, in_space;

static void board(u8 *me)
{
    V3 p = entity_pos(me);
    V3 d = vsub(vshr(ship.b.pos, FX), p);
    if (!parked || iabs(d.x) > 2500 || iabs(d.z) > 2500 || iabs(d.y) > 600) {
        /* call it in: it lands right beside you */
        M3 m;
        myaw(&m, entity_heading(me));
        V3 at = vadd(p, vscale(m.r, -500));
        s32 g = surface_fine(v3(at.x << FX, at.y << FX, at.z << FX)) >> FX, w = world_ground(at.x, at.z);
        ship_reset(&ship, v3(at.x, g > w ? g : w, at.z), entity_heading(me));     /* (on water: on it) */
    }
    mode = FLY;
    parked = 0;
    was_flying = 0;
    sg_state = SG_FLY;
    cam_cut = 1;                                   /* (swung round from where you stood, it can go through a wing) */
}

/* Called, the Arwing flies in from behind the camera, over your head, and sets down a few steps
   ahead of you facing the way the camera looks: never put down out of nothing, and boarding
   leaves the camera behind its tail (put down beside you out of a car, it had the camera in a
   wing) */
#define ARRIVE 72                                  /* ticks of the fly-in: 1.2 s */
static u8 arrive, boarding;                        /* fly-in ticks left; called: board once it is down */
static V3 arrive_at;                               /* where it sets down (units) */
static s32 arrive_yaw;

/* the ground at q (units), on the level of p: p.y + 200 looks down on it (not up at a roof) */
static s32 level_at(V3 p, V3 q)
{
    return surface_fine(v3(q.x << FX, (p.y + 200) << FX, q.z << FX)) >> FX;
}

/* how far from p along f (unit) the ground stays level with p, in steps of 300 units (12 at most) */
static int clear_run(V3 p, V3 f)
{
    int run = 0;
    while (run < 12) {
        V3 q = vadd(p, vscale(f, 300 * (run + 1)));
        /* (past the map's edge there is no ground, which looked level: Tank Warfare's trenches
           run out there, and the Arwing was set down facing their end wall) */
        if (q.x < 2 * CELL || q.z < 2 * CELL || q.x >= (CITY - 2) * CELL || q.z >= (CITY - 2) * CELL ||
            iabs(level_at(p, q) - p.y) >= 100)
            break;
        run++;
    }
    return run;
}

static void call_ship(const u8 *me)
{
    static const s8 spot[5][2] = {{0, 7}, {6, 5}, {-6, 5}, {0, 12}, {9, 0}};   /* (right, ahead), 100 units */
    V3 p = entity_pos(me);
    M3 m;
    /* it sets down facing the longest clear run (its take-off run: in a dense city the camera
       often looks straight at a wall across the street); the camera's own way wins a tie */
    arrive_yaw = heading_of(&cam.m);
    myaw(&m, arrive_yaw);
    int best = clear_run(p, m.f);
    for (s32 yaw = 0; yaw < 65536 && best < 12; yaw += 16384) {
        M3 t;
        myaw(&t, yaw);
        int run = clear_run(p, t.f);
        if (run > best)
            best = run, arrive_yaw = yaw, m = t;
    }
    arrive_at = vadd(p, vscale(m.f, 700));
    /* the first spot on your own level, clear of the camera, with room for its wings; failing
       that, one with room for them on the level below you (The Big Track's sunk lane, called from
       its ramp: set down across the ramp a wing was in it, a crash on arrival); failing that, on
       your level and flat under it, without the wings (wedged between walls you can still get out) */
    for (int pass = 0; pass < 3; pass++)
        for (int i = 0; i < 10; i++) {                 /* (then the other side) */
            V3 q = vadd(p, vadd(vscale(m.r, spot[i % 5][0] * (i < 5 ? 100 : -100)), vscale(m.f, spot[i % 5][1] * 100)));
            s32 g = level_at(p, q);
            if ((pass == 1 ? g > p.y - 100 || g < p.y - 1500 : iabs(g - p.y) >= 100) ||
                iabs(q.x - cam.pos.x) + iabs(q.z - cam.pos.z) <= 1200)
                continue;
            V3 o = v3(q.x, g, q.z);
            if (pass < 2 ? iabs(level_at(o, vadd(q, vscale(m.r, 400))) - g) >= 100 ||
                           iabs(level_at(o, vadd(q, vscale(m.r, -400))) - g) >= 100
                         : iabs(level_at(o, vadd(q, vscale(m.r, 150))) - g) >= 60 ||
                           iabs(level_at(o, vadd(q, vscale(m.f, 150))) - g) >= 60)
                continue;
            arrive_at = o;
            if (pass == 1)                             /* (down there, its own longest run) */
                for (s32 yaw = 0, b = -1, r; yaw < 65536; yaw += 16384) {
                    M3 t;
                    myaw(&t, yaw);
                    if ((r = clear_run(o, t.f)) > b)
                        b = r, arrive_yaw = yaw;
                }
            pass = 3;
            break;
        }
    arrive = ARRIVE;
    parked = 1;
}

static void arrive_tick(void)
{
    M3 m;
    myaw(&m, arrive_yaw);
    s32 s = --arrive * (ONE / ARRIVE), k = s * s >> 14, h = s * (s32)isqrt(s << 14) >> 14;
    if (!arrive) {
        ship_reset(&ship, arrive_at, arrive_yaw);  /* down on its gear */
        return;
    }
    /* in along the way the camera looks, slowing (s^2), and down from high over the camera's
       head (s^1.5: well clear of it as it passes) */
    V3 p = vadd(arrive_at, v3((m.f.x * -4200 >> 14) * k >> 14, 2600 * h >> 14, (m.f.z * -4200 >> 14) * k >> 14));
    /* and over the camera wherever it is now (you walk out to meet it), till the last moments */
    s32 dx = iabs(p.x - cam.pos.x), dz = iabs(p.z - cam.pos.z), over = cam.pos.y + 1100 - (dx > dz ? dx : dz) - p.y;
    if (over > 0)
        p.y += over * (s < ONE / 4 ? s : ONE / 4) >> 12;
    ship.b.pos = v3(p.x << FX, (p.y + 120) << FX, p.z << FX);
    ship.b.vel = ship.b.w = v3(0, 0, 0);
    s32 dip = 6000 * arrive / ARRIVE;              /* nose down its path, level as it lands */
    ship.b.m.r = m.r;
    ship.b.m.f = vnorm(vadd(vscale(m.f, 15000), v3(0, -dip, 0)));
    ship.b.m.u = vnorm(vadd(vscale(m.u, 15000), vscale(m.f, dip)));
}

static void bail_ship(void);

static void land(u8 *me)
{
    Body *b = &ship.b;
    V3 p = vshr(b->pos, FX);
    s32 g = surface_fine(b->pos) >> FX, w;
    V3 at = vadd(p, vscale(b->m.r, 380));
    if (vlen(b->vel) <= (60 << FX) && world_water(at.x, at.z, &w) && p.y - w < 200
        && world.swim[cell_of(at.x, at.z)] & 16) {
        /* on the water (where it skims along, slowed by B): he gets out into it beside it,
           with a bank in reach (none in a pool on a roof) */
        man_put(me, v3(at.x, w, at.z), heading_of(&b->m));
        swim_in(me, v3(at.x, w, at.z));
        mode = FOOT;
        parked = 1;
        return;
    }
    s32 ga = level_at(v3(p.x, g, p.z), at);
    /* beside it, wherever Payback lets the man stand at that height: the street, a raised
       plaza (Real Park's), a deck or a roof; not the water (he would sink) */
    if (ship.gear < 2 || vlen(b->vel) > (25 << FX) || p.y - g > 160 || iabs(ga - g) > 40 || !stand_at(at.x, at.z, ga)) {
        if (p.y < SPACE_LO)
            bail_ship();                           /* he jumps (whether or not RAGDOLLS is on: his own body only) */
        else
            sg_note("Fly to Fox Station to dock.");
        return;
    }
    swimming = swim_lad = 0;                           /* (called from the water, landed on the street) */
    entity_put(me, at, heading_of(&b->m), v3(0, 0, 0));
    *(u16 *)(me + E_Z) = 19904 - 2 * (ga - world.yoff);   /* (set down at its height, as Payback keeps it) */
    *(s16 *)(me + E_VZ) = 0;
    mode = FOOT;
    parked = 1;
}

static void ship_events(void)
{
    Body *b = &ship.b;
    s32 alt = b->pos.y >> FX;
    if (!ship.gear) {
        if (alt > 600)
            was_flying = 1;
    } else if (was_flying && vlen(b->vel) < (25 << FX) && ship.gear >= 2) {
        was_flying = 0;
        if (ship.gear_kind == SURF_DECK)
            sg_landed(&ship);
        else if (surface_fine(b->pos) > (300 << FX))
            sg_note("ROOFTOP LANDING!");
        else
            sg_note("Nice landing. Hold SELECT to get out.");
    }
    if (alt > SPACE_HI && !in_space) {
        in_space = 1;
        told |= 1 << H_CLIMB;
        sg_note("SPACE! Fox Station is on the radar.");
    }
    if (alt < SPACE_LO)
        in_space = 0;
}

/* ---- drawing ---- */

/* Payback's vehicles, in the order of its descriptor table: the model, the paint and how
   far back the exhaust is. A descriptor's look (D_LOOK) picks its entry; the police cars and
   vans of every city share two. (WP1's drawn sizes in build.py go by the same entries.) */
typedef struct { const Model *md; u8 paint, scale; s16 rear, roof; } VehicleLook;   /* roof: model units up */
static const VehicleLook looks[] = {
    {&mdl_saloon, M_TEAL, 0, -235, 92},      /* Mundaneo */
    {&mdl_saloon, M_BRICK, 224, -235, 92},   /* Pug */
    {&mdl_sport, M_STUNT, 0, -232, 70},      /* Diblo */
    {&mdl_bus, M_ACCENT, 0, -520, 232},      /* bus */
    {&mdl_saloon, M_CONCRETE, 0, -235, 92},  /* Vapour */
    {&mdl_saloon, M_CAR, 224, -235, 92},     /* Pug GTI */
    {&mdl_saloon, M_CREAM, 0, -235, 92},     /* Fjord */
    {&mdl_van, M_SHIP, 0, -245, 152},        /* van */
    {&mdl_limo, M_ROAD, 0, -340, 92},        /* limo */
    {&mdl_saloon, M_SHIP, 0, -235, 92},      /* police car */
    {&mdl_sport, M_CAR, 0, -232, 70},        /* Scooby */
    {&mdl_tank, M_GRASS, 0, -280, 107},      /* tank */
    {&mdl_sport, M_SHIP, 0, -232, 70},       /* Evo */
    {&mdl_saloon, M_ACCENT, 0, -235, 92},    /* taxi */
    {&mdl_van, M_CREAM, 0, -245, 152},       /* ice cream van */
    {&mdl_pickup, M_BRICK, 0, -245, 92},     /* pickup */
    {&mdl_sport, M_GLOW, 0, -232, 70},       /* hot rod */
    {&mdl_heli, M_CAR, 0, 0, 150},           /* helicopter (it stands on its skids, not on wheels) */
    /* the other cities' vehicles */
    {&mdl_saloon, M_CAR, 224, -235, 92},     /* a small blue saloon (desc 18) */
    {&mdl_bus, M_CREAM, 0, -520, 232},       /* coach (19: radius 728, longer than the bus) */
    {&mdl_van, M_SHIP, 0, -245, 152},        /* police van (20, and 47, 48): white, light bar */
    {&mdl_van, M_TEAL, 0, -245, 152},        /* van (21) */
    {&mdl_sport, M_GLOW, 92, -232, 70},      /* a tiny one (22: radius 112, 168 long) */
    {&mdl_tank, M_PLAZA, 0, -280, 107},      /* desert tank (23: armoured, like the tank) */
    {&mdl_pickup, M_CAR, 0, -245, 92},       /* long blue pickup, white load bed (24 to 26) */
    {&mdl_saloon, M_STEEL, 0, -235, 92},     /* saloon (27) */
};
#define POLICE_CAR 9
#define HELI_LOOK 17
#define POLICE_VAN 20

static int vehicle_kind(const u8 *e)
{
    const u8 *d = desc_of(e);
    if (!d)
        return 0;
    u32 k = d[D_LOOK] - LOOK0;
    if (d[D_POLICE])                                   /* (every police vehicle, chasing or not) */
        return k == POLICE_VAN ? POLICE_VAN : POLICE_CAR;
    return k < sizeof looks / sizeof looks[0] ? (int)k : 0;
}

static int car_tall(void)
{
    const Model *md = car_ent ? looks[vehicle_kind(car_ent)].md : 0;
    return md == &mdl_van || md == &mdl_bus;
}

/* the light bar on a police car's roof: red and blue, lit steadily (lights that take turns
   would blink) */
static void police_lights(const Place *pl)
{
    MVert r[4] = {{-60, 106, -36}, {-6, 106, -36}, {-6, 106, -8}, {-60, 106, -8}};
    MVert b[4] = {{6, 106, -36}, {60, 106, -36}, {60, 106, -8}, {6, 106, -8}};
    MVert rf[4] = {{-60, 92, -8}, {-6, 92, -8}, {-6, 106, -8}, {-60, 106, -8}};
    MVert bf[4] = {{6, 92, -8}, {60, 92, -8}, {60, 106, -8}, {6, 106, -8}};
    int cr = COLOR(M_STUNT, 3, pl->fog), cb = COLOR(M_GLASS, 3, pl->fog);   /* (fading out with the car) */
    model_poly(pl, rf, 4, cr);
    model_poly(pl, bf, 4, cb);
    model_poly(pl, r, 4, cr);
    model_poly(pl, b, 4, cb);
}

/* A model in the water, cut at the surface (cut: its height over the model's origin, units):
   only what is over it is drawn, since the water is drawn first and covers nothing. Lit
   flat, by how far each face looks up. near: sorted that much nearer (a man on a ladder,
   whose legs are further off than the bank's face is on average) */
static void draw_wet(const Model *md, const Place *pl, s32 cut, s32 near)
{
    const M3 *m = pl->m;
    s32 a = m->r.y, b = m->u.y, c = m->f.y;            /* the world's up, in the model's frame */
    cut = (cut << 8) / pl->s;
    if (pl->s <= 0 || cut > md->radius)
        return;                                        /* all under */
    for (int i = 0; i < md->nf; i++) {
        const MFace *f = &md->f[i];
        const N3 *n = &md->normal[i];
        V3 nc = v3((n->x * pl->nx.x + n->y * pl->ny.x + n->z * pl->nz.x) >> 14,
                   (n->x * pl->nx.y + n->y * pl->ny.y + n->z * pl->nz.y) >> 14,
                   (n->x * pl->nx.z + n->y * pl->ny.z + n->z * pl->nz.z) >> 14);
        MVert v[8];
        int k = 0, nv = f->n;
        for (int j = 0; j < nv; j++) {
            const MVert *p = &md->v[f->idx[j]], *q = &md->v[f->idx[(j + 1) % nv]];
            s32 hp = (a * p->x + b * p->y + c * p->z) >> 14, hq = (a * q->x + b * q->y + c * q->z) >> 14;
            if (hp >= cut)
                v[k++] = *p;
            if ((hp >= cut) != (hq >= cut)) {
                s32 t = ((cut - hp) << 12) / (hq - hp);
                v[k++] = (MVert){p->x + ((q->x - p->x) * t >> 12), p->y + ((q->y - p->y) * t >> 12),
                                 p->z + ((q->z - p->z) * t >> 12)};
            }
        }
        if (k < 3)
            continue;
        if (!(f->flags & MF_TWO)) {
            V3 o = pl->t;                              /* (a face turned away is not drawn) */
            const MVert *p = &v[0];
            o.x += (pl->ax.x * p->x + pl->ay.x * p->y + pl->az.x * p->z) >> 14;
            o.y += (pl->ax.y * p->x + pl->ay.y * p->y + pl->az.y * p->z) >> 14;
            o.z += (pl->ax.z * p->x + pl->ay.z * p->y + pl->az.z * p->z) >> 14;
            if ((nc.x * (o.x >> 4) + nc.y * (o.y >> 4) + nc.z * (o.z >> 4)) >= 0)
                continue;
        }
        int mat = f->mat == M_CAR ? model_body : f->mat == M_SKY ? model_legs : f->mat == M_SHIP ? model_hull : f->mat;
        int lv = (f->flags & MF_GLOW) ? 3 : 1 + (iabs(a * n->x + b * n->y + c * n->z) > (8000 << 14) ? 2 : 0);
        if (!near) {
            model_poly(pl, v, k, COLOR(mat, lv, pl->fog));
            continue;
        }
        V3 q[8];
        s32 key = 0;
        for (int j = 0; j < k; j++) {
            q[j] = v3(pl->t.x + ((pl->ax.x * v[j].x + pl->ay.x * v[j].y + pl->az.x * v[j].z) >> 14),
                      pl->t.y + ((pl->ax.y * v[j].x + pl->ay.y * v[j].y + pl->az.y * v[j].z) >> 14),
                      pl->t.z + ((pl->ax.z * v[j].x + pl->ay.z * v[j].y + pl->az.z * v[j].z) >> 14));
            key += q[j].z;
        }
        key = key / k - near;
        r_poly(q, k, COLOR(mat, lv, pl->fog), key < 0 ? 0 : key, 0);
    }
}

/* the way out, as the water's cells point to it (world.swim bits 6..7): 1, and a point a few
   cells along it in to, when it is not right there (a long swim, out of sight) */
static int swim_way(V3 *to)
{
    static const s8 st[4][2] = {{0, -1}, {1, 0}, {0, 1}, {-1, 0}};
    int x = swim_at.x >> 10, z = swim_at.z >> 10;
    for (int k = 0; k < 8; k++) {
        int w = world.swim[x * CITY + z];
        if (!(w & 16) || w >> (w >> 6) & 1 || w & 32) {   /* (none in reach, or it is here: past an
                                                             island's beach to the streets) */
            *to = v3((x << 10) + 512, 0, (z << 10) + 512);
            return k >= 4 && w & 16;
        }
        x += st[w >> 6][0], z += st[w >> 6][1];
    }
    *to = v3((x << 10) + 512, 0, (z << 10) + 512);
    return 1;
}

/* The player in the water: his head and shoulders over it, his arms going round in a calm
   breaststroke (about a stroke and a half a second swimming, slower treading water), and a
   ring of ripple round him, steady. Up a ladder, the man himself, as far as he is out. */
static APART void draw_swimmer(void)
{
    M3 m;
    Place pl;
    if (fp_view)
        return;
    myaw(&m, swim_head);
    model_body = M_GLOW;
    model_legs = M_GLASS;
    swim_far = 0;
    if (swim_lad) {
        s32 w = world.ladder[swim_lad - 1].lo;
        if (model_place(&pl, swim_at, &m, 256, 0, 150)) {
            draw_wet(&mdl_hero[0][0], &pl, w - swim_at.y, 96);
            draw_wet(&mdl_hero[0][1], &pl, w - swim_at.y, 96);
        }
    } else if (model_place(&pl, swim_at, &m, 256, 0, 160)) {
        model_draw(&mdl_swim[0], &pl);
        model_draw(&mdl_swim[1], &pl);
        int moving = keys & (KEY_UP | KEY_DOWN | KEY_A | KEY_B | KEY_LEFT | KEY_RIGHT);
        u32 u = swim_t * (moving ? 700 : 300);
        s32 r = (ONE - fcos(u)) >> 1;                  /* 0: the hands out at his sides .. ONE: in front */
        int col = COLOR(M_GLOW, 2, pl.fog);
        for (int sd = -1; sd <= 1; sd += 2) {
            s32 hx = sd * (22 + (50 * (ONE - r) >> 14)), hz = 24 + (66 * r >> 14), sx = sd * 30;
            s32 dx = hx - sx, dz = hz - 22, len = iabs(dx) + iabs(dz) + 1;
            s32 px = -dz * 7 / len, pz = dx * 7 / len;
            MVert arm[4] = {{sx - px, 6, 22 - pz}, {sx + px, 6, 22 + pz}, {hx + px, 5, hz + pz}, {hx - px, 5, hz - pz}};
            model_poly(&pl, arm, 4, col);
        }
        /* the ripple: its 16 corners placed once (a model_poly a piece placed each twice) */
        static const s8 ring[8][2] = {{0, 127}, {90, 90}, {127, 0}, {90, -90}, {0, -127}, {-90, -90}, {-127, 0}, {-90, 90}};
        V3 q[16];
        for (int k = 0; k < 16; k++) {
            s32 r = k & 1 ? 104 : 120, x = ring[k >> 1][0] * r >> 7, z = (ring[k >> 1][1] * r >> 7) + 10;
            q[k] = v3(pl.t.x + ((pl.ax.x * x + pl.ay.x + pl.az.x * z) >> 14), pl.t.y + ((pl.ax.y * x + pl.ay.y + pl.az.y * z) >> 14),
                      pl.t.z + ((pl.ax.z * x + pl.ay.z + pl.az.z * z) >> 14));
        }
        int rc = COLOR(M_CREAM, 2, pl.fog);
        for (int k = 0; k < 16; k += 2) {
            int n = (k + 2) & 15;
            V3 s[4] = {q[k], q[n], q[n + 1], q[k + 1]};
            r_poly(s, 4, rc, -1, 0);
        }
        /* far from a way out: a steady arrow on the water, out past the ripple, pointing to it */
        V3 to;
        swim_far = swim_way(&to);
        if (swim_far) {
            s32 dx = to.x - swim_at.x, dz = to.z - swim_at.z, d = isqrt(dx * dx + dz * dz) + 1, y = swim_at.y + 8;
            dx = dx * 256 / d, dz = dz * 256 / d;
            V3 a[3] = {r_cam(v3(swim_at.x + dx * 2, y, swim_at.z + dz * 2)),
                       r_cam(v3(swim_at.x + dx + dz * 3 / 8, y, swim_at.z + dz - dx * 3 / 8)),
                       r_cam(v3(swim_at.x + dx - dz * 3 / 8, y, swim_at.z + dz + dx * 3 / 8))};
            r_poly(a, 3, COLOR(M_GLOW, 3, pl.fog), -1, 0);
        }
    }
    model_body = M_CAR;
    model_legs = M_ROAD;
}

/* a ladder's bar, x0..x1 by y0..y1 just off the bank's face, at o: sorted a little nearer than
   the face (at the same depth it would be left to the order they were sent in, the bank first) */
static void lad_bar(const Place *pl, s32 x0, s32 x1, s32 y0, s32 y1, V3 o, int c)
{
    V3 q[4];
    s32 key = 0;
    for (int i = 0; i < 4; i++) {
        s32 x = i == 1 || i == 2 ? x1 : x0, y = i >= 2 ? y1 : y0;
        q[i] = v3(o.x + ((pl->ax.x * x + pl->ay.x * y - pl->az.x * 8) >> 14),
                  o.y + ((pl->ax.y * x + pl->ay.y * y - pl->az.y * 8) >> 14),
                  o.z + ((pl->ax.z * x + pl->ay.z * y - pl->az.z * 8) >> 14));
        key += q[i].z;
    }
    key = (key >> 2) - 48;
    r_poly(q, 4, c, key < 0 ? 0 : key, 0);
}

/* the ladders up banks too high to climb out of the water at (world.ladder): two rails and
   rungs, on the bank's face */
static APART void draw_ladders(void)
{
    static const s16 ex[4] = {0, 512, 0, -512}, ez[4] = {-512, 0, 512, 0};
    int cx = cam.pos.x >> 10, cz = cam.pos.z >> 10;
    for (int k = 0; k < world.nladder; k++) {
        const Ladder *l = &world.ladder[k];
        if ((unsigned)(l->x - cx + 9) > 18 || (unsigned)(l->z - cz + 9) > 18)
            continue;                                  /* (cells: most are far off) */
        s32 h = l->hi - l->lo;
        V3 p = v3((l->x << 10) + 512 + ex[l->edge], l->lo + h / 2, (l->z << 10) + 512 + ez[l->edge]);
        V3 d = vsub(p, cam.pos);
        if (iabs(d.x) > 9000 || iabs(d.z) > 9000)
            continue;
        M3 m;
        Place pl;
        myaw(&m, (2 - l->edge) * 16384);               /* facing the bank */
        if (!model_place(&pl, p, &m, 256, 0, h / 2 + 64))
            continue;
        int c = COLOR(M_STEEL, 3, pl.fog);
        lad_bar(&pl, -52, -44, -h / 2, h / 2 + 48, pl.t, c);
        lad_bar(&pl, 44, 52, -h / 2, h / 2 + 48, pl.t, c);
        if (iabs(d.x) + iabs(d.z) > 3500)
            continue;                                  /* (far off, the rails are enough) */
        c = COLOR(M_STEEL, 2, pl.fog);
        for (s32 y = 96 - h / 2; y < h / 2; y += 192)
            lad_bar(&pl, -44, 44, y, y + 10, pl.t, c);
    }
}

/* Payback runs its traffic and people only inside a square of cells round its camera centre (a
   cell or so ahead of its man, who is us or rides under the Arwing): it drops whatever leaves
   the square and adds new ones just inside it, dropped in from a height. Down our long streets
   that edge is in plain view, so we draw only to a cell and a half short of it, by the centre's
   own smooth position, and shrink each to nothing over the cell and a half before that, as the
   square of the room left (it grows from nothing with no jump: eased out, a fast flight took a
   car from too small to draw to 40 % in one frame). Its test
   (0x080126b8) keeps a record while its cell is within half cells of the centre's cell, both
   ways, and its spawner adds them exactly half cells out; a cell number is less than a cell from
   the position, so anything we draw is at most half - 1 cells out by Payback's count: never one it
   is adding or dropping, nor a new car still dropping in. (A cell short is the least that holds;
   the half cell more keeps a car whole when Payback's centre swings round as its man turns.)
   (Not by fog: a car in fog 3 is the sky's pale blue, and on a dark road at fog 0 that stands out
   more than the car did.) */
#define PB_VIEW_X ((const volatile s32 *)0x02001e88)      /* its camera centre, 16.16 cells (per player) */
#define PB_VIEW_Y ((const volatile s32 *)0x02001e98)
#define PB_CAMZ ((const volatile s32 *)0x02001e54)        /* its camera's height: the square grows with it */
#define PB_BOX_SHIFT 11

/* Payback's shots (police bullets, shells): descriptors 41 to 47 of its table, below ours */
#define SHOT_DESC0 0x08354860u
#define E_PITCH 0x10               /* s16, 5760 a turn: a vehicle's nose down the slope (+), up (-) */
#define E_BURN 0x64                /* a burning vehicle's clock: 100 at the kill, -1 a tick, a wreck at 15 */

/* a burning vehicle (state 5): Payback's blast for the first 12 ticks of its burn clock, then a
   steady fire on the roof while it burns. Steady colours: nothing spins, blinks or takes turns. */
static void vehicle_fire(const u8 *e, const Place *pl, V3 p, const M3 *m, int roof, int size)
{
    int t = 100 - *(const s16 *)(e + E_BURN);
    if ((u32)t < 12) {
        if (size < 256)
            return;                                    /* (near Payback's edge: not a blast to pop in) */
        Place bp;
        int sz = t < 4 ? 160 + t * 75 : 460 - (t - 4) * 40;        /* grows, then dies down */
        if (model_place(&bp, vadd(p, mlocal(m, v3(0, roof >> 1, 0))), m, sz, 0, mdl_boom.radius))
            model_draw(&mdl_boom, &bp);
        return;
    }
    int c = COLOR(M_GLOW, 3, pl->fog), y = roof - 10;    /* (one colour: the two cross) */
    MVert a[3] = {{-90, y, 30}, {90, y, -30}, {0, y + 190, 0}};
    MVert b[3] = {{-30, y, -90}, {30, y, 90}, {0, y + 160, 0}};
    model_poly(pl, a, 3, c);
    model_poly(pl, b, 3, c);
}

/* a person's clothes, for good (by their record, so a punch never recolours them) */
static void dress(const u8 *e, u8 *body, u8 *legs)
{
    static const u8 shirts[] = {M_BRICK, M_CAR, M_CREAM, M_TEAL, M_ACCENT, M_SHIP, M_STUNT, M_GRASS};
    if (e == hero) {
        *body = M_GLOW;                                /* the stunt fox: orange jacket, jeans */
        *legs = M_GLASS;
    } else if (desc_of(e)[D_POLICE]) {
        *body = M_SHIP;                                /* an officer: blue */
        *legs = M_ROAD;
    } else {
        u32 kind = ((u32)e - 0x02000000) / 0x168;
        *body = shirts[kind % sizeof shirts];
        *legs = (kind >> 3) & 1 ? M_STEEL : M_ROAD;
    }
}

/* everyone Payback is running: traffic, parked cars, helicopters, people and their shots */
static void draw_entities(const u8 *me)
{
    int n = PB_NENTITY;                                /* (the last index: the man just out of a car is there too) */
    if (n > 63) n = 63;                                /* (the list's last place: its 64 slots end there) */
    s32 vx = PB_VIEW_X[0], vy = PB_VIEW_Y[0];
    s32 end = ((((PB_CAMZ[0] + 1500) * 8 >> PB_BOX_SHIFT) + 3) << 16) + 0x8000;   /* half - 1.5 cells, 16.16 */
    for (int i = 0; i <= n; i++) {
        const u8 *e = PB_ENTITY[i];
        if (!valid(e))
            continue;
        if (((mode == DRIVE || ghost == GH_CAR) && e == car_ent) || (mode == FLY && e == me) || (bail && e == hero))
            continue;
        if (fp_view && mode == FOOT && e == hero)
            continue;                                  /* (his own eyes) */                                  /* we draw that one ourselves */
        s32 cx = iabs((*(const s32 *)(e + E_X) << 5) - vx), cy = iabs((*(const s32 *)(e + E_Y) << 5) - vy);
        s32 room = (end - (cx > cy ? cx : cy)) >> 8;   /* 256 a cell to go */
        if (room < 0)
            continue;
        int size = room >= 384 ? 256 : room * room * 455 >> 18;   /* (grows from nothing with no jump: 256 (room/384)^2) */
        if (size < 16)
            continue;
        V3 p = entity_pos(e);
        if (p.x < 1024 && p.z < 1024)
            continue;                                  /* unused records wait in the corner */
        V3 d = vsub(p, cam.pos);
        if (iabs(d.x) > 20000 || iabs(d.z) > 20000)
            continue;
        M3 m;
        myaw(&m, entity_heading(e));
        Place pl;
        int cls = ent_class(e);
        if (cls < 0 && entity_desc(e) - SHOT_DESC0 < 7 * VEH_SIZE)
            cls = 2;
        if (cls < 0)
            continue;
        if (cls == 2) {
            /* a shot: a short bright streak the way it flies */
            s32 sx = *(const s16 *)(e + E_VX), sz = *(const s16 *)(e + E_VY);
            if (sx || sz)
                myaw(&m, fatan2(sx, sz));
            if (model_place(&pl, vadd(p, v3(0, 70, 0)), &m, size, 0, 130)) {
                int c = COLOR(M_ACCENT, 3, pl.fog);
                MVert h[4] = {{-10, 0, 40}, {10, 0, 40}, {10, 0, -120}, {-10, 0, -120}};
                MVert v[4] = {{0, -10, 40}, {0, 10, 40}, {0, 10, -120}, {0, -10, -120}};
                model_poly(&pl, h, 4, c);
                model_poly(&pl, v, 4, c);
            }
            continue;
        }
        if (cls > 2) {
            /* a phone, crate or pickup Payback put in the street */
            if (model_place(&pl, p, &m, size >> 1, 0, mdl_crate.radius))
                model_draw(&mdl_crate, &pl);
            continue;
        }
        if (!cls) {
            int k = vehicle_kind(e);
            const VehicleLook *lk = &looks[k];
            u8 st = e[E_STATE];
            int dead = wrecked(e);
            if (k == HELI_LOOK) {
                if (st == 6 || st == 7) {
                    /* a wreck: down on one skid */
                    V3 r = m.r, u = m.u;
                    s32 sn = fsin(4000), cs = fcos(4000);
                    m.r = v3((r.x * cs + u.x * sn) >> 14, (r.y * cs + u.y * sn) >> 14, (r.z * cs + u.z * sn) >> 14);
                    m.u = v3((u.x * cs - r.x * sn) >> 14, (u.y * cs - r.y * sn) >> 14, (u.z * cs - r.z * sn) >> 14);
                }
            } else {
                /* on a ramp, along its slope (Payback's +0x10; the bank, +0xe, is a degree or two
                   and left out); the body rides 58 above its wheels */
                s32 a = *(const s16 *)(e + E_PITCH);
                a = a > 2880 ? a - 5760 : a < -2880 ? a + 5760 : a;
                if (a) {
                    a = -a * 11651 >> 10;              /* nose up: -, 5760 -> 65536 a turn */
                    s32 sn = fsin(a), cs = fcos(a);
                    V3 f = m.f, u = m.u;
                    m.f = v3((f.x * cs + u.x * sn) >> 14, (f.y * cs + u.y * sn) >> 14, (f.z * cs + u.z * sn) >> 14);
                    m.u = v3((u.x * cs - f.x * sn) >> 14, (u.y * cs - f.y * sn) >> 14, (u.z * cs - f.z * sn) >> 14);
                }
                p = vadd(p, vscale(m.u, 58 * size >> 8));
            }
            if (!model_place(&pl, p, &m, (lk->scale ? lk->scale : 256) * size >> 8, 0, lk->md->radius))
                continue;
            model_body = dead ? M_ROAD : lk->paint;
            s32 w;
            if (world_water(p.x, p.z, &w) && p.y - 58 < w) {
                draw_wet(lk->md, &pl, w - p.y, 0);        /* going under */
                continue;
            }
            if (pl.t.z > 2800 && lk->md != &mdl_tank && k != HELI_LOOK) {
                Model far = *lk->md;                   /* far away: no wheels (the last 24 points, 4 faces) */
                far.nv -= 24;
                far.nf -= 4;
                model_draw(&far, &pl);
            } else {
                model_draw(lk->md, &pl);
            }
            if ((k == POLICE_CAR || k == POLICE_VAN) && pl.t.z < 9000 && !dead) {
                Place lp = pl;                         /* (the bar sits on a saloon's roof: up to the van's) */
                s32 up = lk->roof - 92;
                lp.t = vadd(pl.t, v3(pl.ay.x * up >> 14, pl.ay.y * up >> 14, pl.ay.z * up >> 14));
                police_lights(&lp);
            }
            if (st == 5 && dead)                       /* (burning: 5 with no health; with some, no driver) */
                vehicle_fire(e, &pl, p, &m, lk->roof, size);
            continue;
        }
        /* a person: dressed for good, walking when they move, the arm out while they punch or
           shoot, lying down once knocked down (or flying: that body draws them, rag_draw) */
        if (rag_on && rag_of(e))
            continue;
        u8 st = e[E_STATE];
        int down = st == ST_DOWN;
        if (down) {
            V3 f = m.f;
            m.f = v3(-m.u.x, -m.u.y, -m.u.z);
            m.u = f;
            p.y += 20;
        }
        if (e == hero && swimming) {
            draw_swimmer();
            continue;
        }
        if (!model_place(&pl, p, &m, size, 0, 140))
            continue;
        s32 wl;
        int wet = world_water(p.x, p.z, &wl) && p.y < wl;   /* going down in Payback's water */
        if (wet && p.y + 240 < wl)
            continue;
        dress(e, &model_body, &model_legs);
        u32 a = (entity_desc(e) - PED_DESC0) / VEH_SIZE;   /* Payback's animation for them */
        const Model *md = &mdl_ped;
        if (pl.t.z < 1800 || e == hero) {
            const s32 *w = (const s32 *)e;
            int moving = w[E_X / 4] != w[E_PREV1 / 4] || w[E_Y / 4] != w[E_PREV1 / 4 + 1];
            int pose = a >= ANIM_ATTACK0 && a <= ANIM_ATTACK1 && !down ? 3
                     : down || !moving ? 0 : 1 + (((iabs(w[E_X / 4]) + iabs(w[E_Y / 4])) >> 9) & 1);
            static const Model *const crowd[4] = {&mdl_stand, &mdl_stride_a, &mdl_stride_b, &mdl_punch};
            if (e == hero) {
                if (wet)
                    draw_wet(&mdl_hero[pose][0], &pl, wl - p.y, 0);
                else
                    model_draw(&mdl_hero[pose][0], &pl);
                md = &mdl_hero[pose][1];
            } else {
                md = crowd[pose];
            }
        }
        if (st == ST_HIT)
            model_body = M_STUNT;                      /* just hit: red while they stagger (no flashing) */
        if (wet)
            draw_wet(md, &pl, wl - p.y, 0);
        else
            model_draw(md, &pl);
    }
    model_body = M_CAR;
    model_legs = M_ROAD;
}

/* ---- people sent flying (src/ragdoll.c) ----
   The moment Payback knocks someone down (or our shots do), a body in their clothes is thrown
   the way the blow went: by a car at its speed, feet first; by a blast up and away from it; by
   a punch or a shot a little. It tumbles, bounces and settles, and is drawn in place of
   Payback's lying figure while that lies there; if they get up it goes. Payback's records are
   only read: who died, the score and the stars are all Payback's as before. */
static u8 rag_st[64];                              /* each entity's state when we last looked */
static u16 rag_who[64];                            /* ... and which record that was (address / 8) */
static u32 rag_seed = 0x6d2b79f5;
#define ST_GONE 6                  /* a person: dead (lies there until Payback uses the record again) */
static int felled(u8 st) { return st == ST_HIT || st == ST_DOWN || st == ST_GONE; }

static s32 rag_rand(s32 lo, s32 hi)
{
    rag_seed = rag_seed * 1664525 + 1013904223;
    return lo + (s32)((rag_seed >> 8) % (u32)(hi - lo + 1));
}

/* (fine units a tick) a car coming at p fast, near enough for Payback to have knocked p (its
   knock leads by up to a car length and a half), or 0 */
static int rag_car_near(V3 p, V3 *vel)
{
    if (rag_car) {
        V3 c = vshr(rag_car->pos, FX), v = rag_car->vel;
        s32 dx = p.x - c.x, dz = p.z - c.z;
        s32 l = vlen(v), ahead = l > 6 << FX ? (dx * (v.x >> 4) + dz * (v.z >> 4)) / (l >> 4) : 0;
        if (iabs(dx) < 1200 && iabs(dz) < 1200 && ahead > 0)
            return *vel = v, ahead > 380 ? 2 : 1;      /* (2: still a car's length or more short of them) */
    }
    int n = PB_NENTITY;                                /* (the last index) */
    if (n > 63) n = 63;
    for (int i = 0; i <= n; i++) {
        const u8 *e = PB_ENTITY[i];
        if (!valid(e) || !is_car(e) || e == car_ent)
            continue;
        V3 c = entity_pos(e), v = v3(*(const s16 *)(e + E_VX) << 6, 0, *(const s16 *)(e + E_VY) << 6);
        s32 dx = p.x - c.x, dz = p.z - c.z;
        if (iabs(dx) < 900 && iabs(dz) < 900 && iabs(v.x) + iabs(v.z) > 6 << FX && (dx * (v.x >> 4) + dz * (v.z >> 4)) > 0)
            return *vel = v, 1;
    }
    return 0;
}

/* e has just gone down (or been hit): thrown as what did it says */
static void rag_knock(u8 *e, V3 blast, int big)
{
    V3 p = entity_pos(e), v, spin;
    s32 up;
    int k = 0;
    if (blast.y != -1) {                               /* a blast (or a shot): up and away from it */
        V3 d = v3(p.x - blast.x, 0, p.z - blast.z);
        s32 l = vlen(d);
        if (l < 24)
            d = v3(rag_rand(-99, 99), 0, rag_rand(-99, 99)), l = vlen(d) | 1;
        s32 sp = big ? clamp(40 - l / 24, 14, 40) : 9;   /* (units a tick) */
        v = v3(d.x * sp / l << FX, 0, d.z * sp / l << FX);
        up = (big ? 12 + sp / 3 : 8) << FX;            /* (out more than up: two or three storeys, in sight
                                                          of the Arwing's camera, not a speck above it) */
        spin = v3(rag_rand(-1, 1) * 900, rag_rand(-1, 1) * 400, rag_rand(-1, 1) * 900);
    } else if ((k = rag_car_near(p, &v)) == 2) {        /* Payback knocks them down while our car is still up to a
                                                          cell short of them (its reach runs ahead at speed): they
                                                          stagger the way it comes, and fly when it gets there
                                                          (ragdoll.c: a car knocks a body on), in front of it, not
                                                          a speck a cell ahead of a chase camera */
        v = vshr(v, 4);
        up = 3 << FX;
    } else if (k) {                                    /* run over: on at most of its speed (the car slows as it
                                                          hits), up a little (a storey or two: a chase camera sees
                                                          it fly on ahead, not go up out of the picture) */
        s32 sp = vlen(v), sd = rag_rand(0, 1) ? 1 : -1;
        v = vadd(vscale(v, 11469), v3(-sd * (v.z >> 2), 0, sd * (v.x >> 2)));   /* (and off to a side: seen across) */
        up = (6 << FX) + sp / 6;
    } else {
        const u8 *h = hero;                            /* a punch: away from the one who threw it */
        V3 d = h && h != e ? vsub(p, entity_pos(h)) : v3(0, 0, 0);
        if (iabs(d.x) + iabs(d.z) < 400 && (d.x | d.z)) {
            s32 l = vlen(d) | 1;
            v = v3(d.x * 9 / l << FX, 0, d.z * 9 / l << FX);
        } else {                                       /* else the way Payback shoves them */
            v = v3(*(const s16 *)(e + E_VX) << 6, 0, *(const s16 *)(e + E_VY) << 6);
        }
        up = 7 << FX;
    }
    if (blast.y == -1)                                 /* tumbling the way it goes: feet first */
        spin = v3(-v.z * 10 >> 8, rag_rand(-150, 150), v.x * 10 >> 8);
    v.y = up;
    u8 body, legs;
    dress(e, &body, &legs);
    int s = rag_throw(p, entity_heading(e), v, spin, body, legs, e == hero, e);
    if (s >= 0 && k == 2)
        rags[s].due = 1;                               /* (lying there till then: ragdoll.c) */
}

/* once a frame: who went down, and the bodies that stand for someone who got up go */
static void rag_scan(int ticks)
{
    static const V3 none = {0, -1, 0};
    rag_car = (mode == DRIVE && !car_boom) || ghost == GH_CAR ? &car.b : 0;
    int n = PB_NENTITY;                                /* (the last index) */
    if (n > 63) n = 63;
    static u32 blast_seen;
    int blast = rag_on && shot_big && shot_when != blast_seen && frame_count - shot_when < 12;
    if (blast)
        blast_seen = shot_when;                        /* a missile: everyone near it flies, not only the one
                                                          Payback is told it hurt (city_hit hurts one); the
                                                          rest get up where they come down */
    if (rag_on) {
        for (int i = 0; i <= n; i++) {
            u8 *e = PB_ENTITY[i];
            if (!valid(e) || ((mode == FLY || bail) && e == hero))
                continue;
            if (blast && e != hero && is_person(e) && !felled(e[E_STATE]) && !rag_of(e)) {
                V3 d = vsub(entity_pos(e), shot_at);
                s32 ax = iabs(d.x), az = iabs(d.z);
                if ((ax > az ? ax + (az * 3 >> 3) : az + (ax * 3 >> 3)) < 640 && iabs(d.y) < 300)
                    rag_knock(e, shot_at, 1);          /* (within about 600: the fireball and a little more) */
            }
            u8 st = e[E_STATE], was = rag_st[i];
            u16 who = (u32)e >> 3;
            if (who != rag_who[i])
                was = st;                              /* (someone else in that place now) */
            rag_st[i] = st, rag_who[i] = who;
            if ((st == ST_HIT || st == ST_DOWN) && !felled(was) && is_person(e) && !rag_of(e)) {
                int ours = shot_when && frame_count - shot_when < 12;
                V3 d = vsub(entity_pos(e), shot_at);
                rag_knock(e, ours && iabs(d.x) + iabs(d.z) < 700 ? shot_at : none, shot_big);
            }
        }
    }
    for (int k = 0; k < RAG_N; k++) {
        Rag *r = &rags[k];
        if (!r->state || r->own)
            continue;                                  /* (the player's own: bail_frame) */
        u8 *e = (u8 *)r->rec;
        if (e) {
            int i = 0;
            while (i <= n && PB_ENTITY[i] != e)
                i++;
            V3 p = i <= n ? entity_pos(e) : v3(0, 0, 0), b = rag_pelvis(r);
            if (r->state >= RAG_RISE) {                /* getting up where the body lay, as them */
                if (i > n || !is_person(e))
                    r->state = RAG_FREE, r->rec = 0;
                else if (man_put(e, b, entity_heading(e)), r->state == RAG_UP && r->age)
                    r->state = RAG_FREE, r->rec = 0;   /* standing: that is them now, where it stood */
            } else if (i > n || !is_person(e) || iabs(p.x - r->kx) + iabs(p.z - r->kz) > 600) {
                r->rec = 0;                            /* gone, or Payback has used the record again */
            } else if (r->state == RAG_REST && (!r->held || !felled(e[E_STATE]))) {
                /* come to rest: Payback's record of them to the body (once: held marks it; they lie,
                   or get up, there rather than where they were hit, cells away), if Payback can stand
                   them there */
                s32 fl = rag_floor(b.x, b.z, b.y), w;
                if (!r->held && iabs(fl - p.y) < 80 && street_at(b.x, b.z) && !world_water(b.x, b.z, &w))
                    man_put(e, b, entity_heading(e)), p = b;
                r->held = 1;
                r->kx = p.x, r->kz = p.z;
                if (!felled(e[E_STATE])) {             /* up again: the body gets up the way it lies, then is
                                                          them, facing that way (kx is its yaw from now) */
                    s32 yaw = rag_yaw(r);
                    rag_rise(r, yaw);
                    man_put(e, b, yaw);
                }
            } else {
                r->kx = p.x, r->kz = p.z;              /* (Payback shoves the one it knocks a little; it may get
                                                          up while the body still flies: hidden till it lands) */
            }
        }
        V3 d = vsub(rag_pelvis(r), cam.pos);
        if (!r->rec && r->state == RAG_REST && (r->age > 1800 || iabs(d.x) + iabs(d.z) > 14000))
            r->state = RAG_FREE;                       /* lain long enough, or left far behind */
    }
    rag_tick(ticks);
}

/* ---- bailing out ----
   L in the car at speed, or SELECT held in the air, and he jumps: thrown clear as a body of his
   own (src/ragdoll.c) with the vehicle's speed, he tumbles and bounces, and gets up where it
   settles. Meanwhile Payback's record of him is held under the body wherever Payback can stand
   him, sees no buttons but START, and nothing hurts him (sf_guard[0], as under the Arwing): a
   fall from a height costs health only with that option on (bail_land). The empty car rolls on
   under our physics and never into him, and stops as Payback's car with no driver; the empty
   Arwing flies on, noses down and crashes, and SELECT calls the next one as ever. */
static u8 bail_req;                /* L in the car at speed (sf_keys), for choose_mode */
static u8 bail_in;                 /* frames Payback has kept him in the car since (it takes a second) */
static u8 bail_out;                /* Payback has let him out (till then its record of the car stands where he
                                      pressed L: it lets nobody out of a car on the move) */
static u8 bail_dead;               /* Payback is bringing him back (a fatal fall): the body lies till then */
static u16 ghost_t;                /* ticks the vehicle has gone on empty */
static s16 bail_hurt;              /* fall damage not yet taken (he may not be out of the car yet) */
static s32 bail_yaw;               /* the way he went: he gets up facing it, the camera looks along it */
static u8 bail_near;               /* ticks he has been down (to 20): the camera comes in to where the one on
                                      foot will be as he gets up, so standing is no cut */
#define BAIL_MIN 5                 /* units a tick: slower than this L is Payback's own way out */
#define FALL_SAFE 18               /* units a tick: coming down slower costs nothing (a drop of 320 units) */
#define FALL_DEAD 46               /* ... and this fast (a fall of 2700, a three-storey roof) it kills; between,
                                      by the energy, so a fall of 1000 costs 29, of 2000 72 */

/* L in our car (sf_keys): Payback lets him out at any speed and its own physics would roll the
   empty car on into him, so its record's speeds go to 0 either way; at speed he bails out */
static void bail_press(void)
{
    *(s16 *)(car_ent + E_VX) = *(s16 *)(car_ent + E_VY) = 0;
    *(s16 *)(car_ent + E_SPEED) = *(s16 *)(car_ent + E_SPEED + 2) = 0;
    if (vlen(v3(car.b.vel.x, 0, car.b.vel.z)) > BAIL_MIN << FX && !car.in_water && !car_dead())
        bail_req = 1;
    else
        car.b.vel.x = car.b.vel.z = 0, car.b.w = v3(0, 0, 0);   /* out of a car that stands */
}

static void bail_start(int k, s32 yaw)
{
    rags[k].own = 1;
    bail = k + 1;
    bail_in = bail_out = bail_dead = 0;
    bail_hurt = 0;
    bail_yaw = yaw;
    bail_near = 0;
    mode = FOOT;
}

static void bail_car(void)
{
    Body *b = &car.b;
    V3 p = vshr(b->pos, FX), r = b->m.r;
    s32 g = world_ground(p.x, p.z);
    /* out of the side the car swings away from as it turns, else the side with room */
    int side = iabs(b->w.y) > 60 ? (b->w.y > 0 ? -1 : 1) : 1;
    V3 q = vadd(p, vscale(r, side * 320));
    s32 w;
    if (world_ground(q.x, q.z) > g + 24 || world_water(q.x, q.z, &w))
        side = -side;
    V3 feet = vadd(v3(p.x, p.y - 90 > g ? p.y - 90 : g, p.z), vscale(r, side * 110));
    V3 v = vadd(vscale(b->vel, 14336), vadd(vscale(r, side * (8 << FX)), v3(0, 13 << FX, 0)));   /* (up two body heights:
                                                                                              it hops three times) */
    V3 spin = vadd(vscale(b->m.f, side * -420), v3(0, rag_rand(-120, 120), 0));
    s32 yaw = heading_of(&b->m);
    int k = rag_throw(feet, yaw + side * 16384, v, spin, M_GLOW, M_GLASS, 1, 0);
    if (k < 0) {                                   /* (nowhere to be thrown: out of a car that stands) */
        b->vel.x = b->vel.z = 0, b->w = v3(0, 0, 0);
        return;
    }
    bail_start(k, yaw);
    ghost = GH_CAR, ghost_t = 0;
}

static void bail_ship(void)
{
    Body *b = &ship.b;
    V3 p = vshr(b->pos, FX);
    s32 g = surface_fine(b->pos) >> FX;
    int side = rag_rand(0, 1) ? 1 : -1;            /* out of one side, up and clear of it as it flies on */
    V3 feet = vadd(v3(p.x, p.y - 110 > g ? p.y - 110 : g, p.z), vscale(b->m.r, side * 70));
    V3 v = vadd(vscale(b->vel, 13107), vadd(vscale(b->m.r, side * (6 << FX)), v3(0, 4 << FX, 0)));
    s32 yaw = heading_of(&b->m);
    int k = rag_throw(feet, yaw, v, vscale(b->m.r, side * 520), M_GLOW, M_GLASS, 1, 0);
    if (k < 0)
        return;
    bail_start(k, yaw);
    parked = 1;                                    /* (it is drawn while it flies on) */
    if (ship.gear < 2 || vlen(b->vel) > (25 << FX))
        ghost = GH_SHIP, ghost_t = 0;              /* (landed, it waits where it is) */
}

/* how hard he came down, as fall damage (FALL DAMAGE on): Payback's own health, so a fatal fall
   is one of its deaths (at 0 it kills him as wear does) and lives, respawn and score are its */
static void bail_land(Rag *r)
{
    s32 v = r->land;
    r->land = 0;
    if (rag_fall && v > FALL_SAFE) {
        s32 d = (v * v - FALL_SAFE * FALL_SAFE) * 100 / (FALL_DEAD * FALL_DEAD - FALL_SAFE * FALL_SAFE);
        bail_hurt += d > 100 ? 100 : d;
    }
    if (bail_hurt && hero) {
        s16 *hp = (s16 *)(hero + E_HEALTH);
        *hp = *hp > bail_hurt ? *hp - bail_hurt : 0;
        bail_hurt = 0;
    }
}

/* Payback's man at the height the body lies at (its record's height is nobody's but ours to set:
   entity_put leaves it, and Payback keeps a man where he is put, on a roof or a bridge deck as on
   the street) */
static void man_height(u8 *e, s32 y)
{
    s32 z = 19904 - 2 * (y - world.yoff);
    *(u16 *)(e + E_Z) = z < 0 ? 0 : z > 0xffff ? 0xffff : z;
}

static u8 fall_calm;              /* frames fall_scan waits after he gets up (Payback settles him on its floor) */
static s32 shore_x, shore_z;       /* where he climbs out of the water, or shore_x 0: not looked for yet / none */

static void bail_stop(void)
{
    Rag *r = &rags[bail - 1];
    if (r->own)
        r->own = 0, r->state = RAG_FREE;
    bail = 0;
    fall_calm = 60;
}

/* the nearest place by p (units) Payback can stand him at street level out of the water, within
   six cells (a body that comes down in the water floats there and climbs out: Payback's man is
   never put in the water, where he would drown); 0 for none */
static int shore_find(V3 p)
{
    s32 cx = p.x >> 10, cz = p.z >> 10, best = 0x7fffffff;
    for (int rr = 1; rr <= 6 && best == 0x7fffffff; rr++)
        for (int i = -rr; i <= rr; i++)
            for (int j = -rr; j <= rr; j++) {
                if (iabs(i) != rr && iabs(j) != rr)
                    continue;                      /* (the ring alone) */
                s32 x0 = (cx + i) << 10, z0 = (cz + j) << 10, w;
                s32 x = clamp(p.x, x0 + 160, x0 + 864), z = clamp(p.z, z0 + 160, z0 + 864);
                if (world_water(x, z, &w) || !street_at(x, z))
                    continue;
                s32 d = iabs(x - p.x) + iabs(z - p.z);
                if (d < best)
                    best = d, shore_x = x, shore_z = z;
            }
    return best != 0x7fffffff;
}

/* once a frame, after the bodies have moved */
static void bail_frame(u8 *me, int ticks)
{
    if (fall_calm)
        fall_calm--;
    if (!bail)
        return;
    Rag *r = &rags[bail - 1];
    if (!r->own || !r->state) {
        bail = 0;
        return;
    }
    if (PB_RESPAWN > 0 || bail_dead) {             /* Payback is bringing him back: the body lies till then */
        bail_dead = 1;                             /* (an ordinary death: no banner, see build.py's MERGE_NO_POPUPS) */
        if (!PB_RESPAWN && me)
            bail_stop();
        return;
    }
    if (!bail_out) {                               /* Payback has not let him out yet */
        if (me && is_person(me))
            bail_out = 1, shore_x = 0;
        else if (++bail_in > 90 && car_ent && is_car(car_ent) && car_ent[E_STATE] < 6) {
            bail_stop();                           /* (it will not: back in the car, wherever it has rolled) */
            car_take(car_ent);
            return;
        }
    }
    V3 p = rag_pelvis(r);
    s32 w, fl = rag_floor(p.x, p.z, p.y);
    int wet = world_water(p.x, p.z, &w) && fl < w + 100;   /* (over the water, not a bridge over it) */
    bail_land(r);
    if (!hero)
        return;                                    /* (out, but not yet in Payback's list) */
    if (wet && r->state <= RAG_REST && (shore_x || shore_find(p))) {
        /* in the water: Payback's man waits on the bank (in the water it would drown him), and the
           body, once it floats, drifts there and gets up on it */
        man_put(hero, v3(shore_x, 0, shore_z), bail_yaw);
        if (r->state == RAG_REST) {
            s32 dx = shore_x - p.x, dz = shore_z - p.z, d = iabs(dx) + iabs(dz), v = 5 + d / 96;   /* (at most
                                                      two seconds from six cells out) */
            v = v * ticks < d ? v * ticks : d;
            r->o[0] += dx * v / (d | 1), r->o[2] += dz * v / (d | 1);
            s32 dy = (s16)(fatan2(dx, dz) - bail_yaw), most = 120 * ticks;   /* (turning to the bank in a
                                                      second or two: the camera swings round it, not through it) */
            bail_yaw = (bail_yaw + clamp(dy, -most, most)) & 0xffff;
        }
        return;
    }
    if (!wet)
        man_put(hero, p, bail_yaw);                /* under the body (the minimap and the police see him there;
                                                      a roof, a bridge or a ramp: Payback stands him on its floor
                                                      there, as it does on foot) */
    if (r->state == RAG_FLY && r->age > 480)
        r->state = RAG_REST;                       /* (a superball: enough) */
    if (r->state == RAG_REST) {
        if (wet) {                                 /* (afloat, nowhere near a bank: Payback's man in the water, its) */
            man_put(hero, p, bail_yaw);
            bail_stop();
            return;
        }
        man_put(hero, p, bail_yaw);
        if (*(s16 *)(hero + E_HEALTH) > 0 || r->age > 1200)
            rag_rise(r, bail_yaw);                 /* (none left: he lies there till Payback's death of him, a
                                                      few frames on, not up and then down dead) */
    }
    if (r->state >= RAG_REST && !wet && bail_near < 20)
        bail_near = bail_near + ticks < 20 ? bail_near + ticks : 20;
    if (r->state >= RAG_REST && !wet)              /* down: at the floor the body lies on, so a roof or a deck is
                                                      where he gets up, not the street under it (and not the
                                                      pelvis' height, a body's height up, that Payback dropped
                                                      him from as a fall) */
        man_height(hero, fl);
    if (r->state == RAG_UP && r->age)
        bail_stop();                               /* standing (seen so a frame first, not a pop up from a
                                                      crouch): he is Payback's man again */
}

/* On foot Payback drops him off a roof, a ledge or a bridge at a steady fast rate and sets him
   down unhurt. Seen falling (down more than a ramp's slope takes in a frame), he goes as a body
   of his own instead, as out of a car: it tumbles down, bounces, and he gets up where it comes
   to rest (bail_frame), with FALL DAMAGE if that is on. Payback's own fall goes on under it. */
static s32 fall_y;
static u8 fall_seen;
static void fall_scan(u8 *me)
{
    if (mode != FOOT || bail || fall_calm || !(rag_on | rag_fall) || !me || !is_person(me) || PB_RESPAWN > 0 || me[E_STATE] != 2) {
        fall_seen = 0;
        return;
    }
    V3 p = entity_pos(me);
    s32 y0 = fall_y;
    int seen = fall_seen;
    fall_y = p.y, fall_seen = 1;
    if (!seen || y0 - p.y < 64 || p.y < rag_floor(p.x, p.z, p.y) + 256)
        return;                                    /* (down a ramp, a stair or a kerb Payback steps him in
                                                      jumps of up to 80 units, on our floor; off the side of a
                                                      ramp or a low wall it drops him 180 a frame: a fall of
                                                      a storey or more is one) */
    V3 v = v3(*(const s16 *)(me + E_VX) << 6, -(2 << FX), *(const s16 *)(me + E_VY) << 6);
    s32 yaw = entity_heading(me);
    int k = rag_throw(v3(p.x, y0, p.z), yaw, v, v3(0, rag_rand(-100, 100), 0), M_GLOW, M_GLASS, 1, 0);
    if (k >= 0)
        bail_start(k, yaw);
}

static int bail_camera(void)
{
    if (!bail)
        return 0;
    M3 m;
    myaw(&m, bail_yaw);
    /* back and up from where his feet would be (thrown, a little further than on foot, to see him
       fly); down, it comes in to the camera on foot as he gets up */
    int n = bail_near;
    V3 p = rag_pelvis(&rags[bail - 1]);
    p.y -= 100;
    if (n)
        p.y += (rag_floor(p.x, p.z, p.y + 100) - p.y) * n / 20;
    camera_look(p, m.f, v3(0, ONE, 0), 620 - 3 * n, 480 - 6 * n, 190 - 2 * n, 160 + 2 * n, 1);
    return 1;
}

/* the empty car, a tick: it coasts, crashes and glances off traffic, and off him */
static void ghost_car(void)
{
    Body *b = &car.b;
    s32 vx = b->vel.x >> 4, vz = b->vel.z >> 4, was = isqrt(vx * vx + vz * vz) << 4;
    car_update(&car, car.speed < (6 << FX) ? KEY_B : 0);   /* (rolls on, then its brakes go on) */
    b->vel.x -= b->vel.x >> 5, b->vel.z -= b->vel.z >> 5;  /* (the engine off: from full speed it rolls to a
                                                              stop in about four seconds) */
    car_fence();
    car_bump();
    car_crash(was);
    V3 c = vshr(b->pos, FX), m = bail ? rag_pelvis(&rags[bail - 1]) : hero ? entity_pos(hero) : v3(0, -9999, 0);
    s32 dx = c.x - m.x, dz = c.z - m.z;
    if (ghost_t > 30 && iabs(dx) < 320 && iabs(dz) < 320 && iabs(c.y - m.y) < 300) {   /* (once he is clear of it) */
        s32 d = isqrt(dx * dx + dz * dz);
        if (d < 320) {
            V3 n = d ? v3(dx * ONE / d, 0, dz * ONE / d) : b->m.f;
            b->pos = vadd(b->pos, vscale(n, (320 - d) << FX));
            s32 vn = vdot(b->vel, n);
            if (vn < 0)
                b->vel = vsub(b->vel, vscale(n, vn + (vn >> 1)));
        }
    }
    vx = b->vel.x >> 4, vz = b->vel.z >> 4;
    if (++ghost_t > 1200 || (ghost_t > 60 && car.wheels >= 3 && vx * vx + vz * vz < 24 * 24))   /* (1.5 units a tick) */
        ghost = GH_NONE;                           /* at rest: Payback's car, with nobody in it */
}

/* the empty Arwing, a tick: on along its path, falling, the nose down it and rolling slowly,
   till it hits something */
static void ghost_ship(void)
{
    Body *b = &ship.b;
    b->vel.y -= G_ACC;
    b->vel = vsub(b->vel, vshr(b->vel, 8));
    b->pos = vadd(b->pos, b->vel);
    if (iabs(b->vel.x) + iabs(b->vel.y) + iabs(b->vel.z) > 512) {
        V3 d = vnorm(vshr(b->vel, 2));
        b->m.f = vnorm(vadd(b->m.f, vshr(vsub(d, b->m.f), 4)));
        morth(&b->m);
        mrotate(&b->m, vscale(b->m.f, 260));
        morth(&b->m);
    }
    const s32 lo = (2 * CELL) << FX, hi = ((CITY - 2) * CELL) << FX;
    s32 g = surface_fine(b->pos), w;
    if (world_water(b->pos.x >> FX, b->pos.z >> FX, &w) && g < w << FX)
        g = w << FX;                               /* (down on the water, not through it to the bottom) */
    if (b->pos.y < g + (50 << FX) || ++ghost_t > 900 || b->pos.x < lo || b->pos.x > hi || b->pos.z < lo || b->pos.z > hi) {
        V3 p = vshr(b->pos, FX);
        if (p.y < (g >> FX) + 40)
            p.y = (g >> FX) + 40;
        sg_crash(p);                               /* its fire, pieces and smoke, and nothing lost */
        ghost = GH_NONE;
        parked = 0;                                /* gone: the next call flies a new one in */
    }
}

/* the car we drive looks like the Payback vehicle it is */
static void draw_car(void)
{
    Place pl;
    V3 p = vshr(car.b.pos, FX);
    const VehicleLook *lk = &looks[car_kind];
    if (!model_place(&pl, p, &car.b.m, lk->scale ? lk->scale : 256, 0, lk->md->radius))
        return;
    int dead = car_ent && wrecked(car_ent);           /* (an arrest stops it too, but it does not burn) */
    model_body = dead ? M_ROAD : lk->paint;
    s32 w;
    if (car.in_water && world_water(p.x, p.z, &w)) {
        draw_wet(lk->md, &pl, w - p.y, 0);
        model_body = M_CAR;
        return;
    }
    if (!fp_view)
        model_draw(lk->md, &pl);
    model_body = M_CAR;
    if ((dead || (car_ent && car_ent[E_STATE] == 5 && mode == DRIVE)) && car_boom < 24) {
        /* on fire (get out!), then the blast (once: it grows and dies away, nothing blinks) */
        int t = car_boom, s = !t ? 140 : t < 8 ? 140 + t * 40 : 460 - (t - 8) * 28;
        M3 m;
        Place fp;
        myaw(&m, t * 3000);
        if (model_place(&fp, vadd(p, v3(0, 60, 0)), &m, s, 0, mdl_boom.radius))
            model_draw(&mdl_boom, &fp);
    }
    if (dead)
        return;
    if (car_kind == POLICE_CAR)
        police_lights(&pl);
    if (car.boosting) {
        int z = lk->rear;                              /* (steady: a flame that comes and goes blinks) */
        MVert fl[3] = {{-50, -10, z}, {50, -10, z}, {0, 0, z - 210}};
        model_poly(&pl, fl, 3, COLOR(M_GLOW, 3, 0));
    }
}

static void draw_ship(void)
{
    Place pl;
    V3 p = vshr(ship.b.pos, FX);
    V3 d = vsub(p, cam.pos);
    if (iabs(d.x) > 40000 || iabs(d.y) > 40000 || iabs(d.z) > 40000)
        return;
    if (!sg_ship_visible() || !model_place(&pl, p, &ship.b.m, 256, 0, mdl_arwing.radius))
        return;
    sg_paint();
    model_draw(&mdl_arwing, &pl);
    model_hull = M_SHIP;
    model_body = M_CAR;
    if ((mode == FLY && !ship.gear && sg_state != SG_DEAD) || arrive) {
        int len = ship.boosting ? 380 : 200;
        MVert fl[3] = {{-30, 6, -90}, {30, 6, -90}, {0, 26, -90 - len}};      /* (steady, no flicker) */
        model_poly(&pl, fl, 3, COLOR(M_GLOW, 3, 0));
    }
}

/* ---- colours ----
   Inside Payback the screen keeps Payback's own palette, always: its tiles need it, our flat
   colours are matched to it (tools/mkpal.py) and the sky is drawn in its blues (space.c). We
   never write a colour, so nothing is ever shown in the wrong colours, and Payback's fades
   (pause, scene changes) work as they always did, except that none of them goes toward white
   any more: those were bright full-screen flashes. The one that hid the zoom into a new level
   under white now goes as far toward black instead, since that zoom, uncovered, jumps a few
   frames at a time (14 flashes a second by flashcheck's measure, starting Los Francos). */

#define PB_PALETTE ((const u16 *)0x086367a8)              /* red and blue swapped */
#define PB_PALETTE_NIGHT ((const u16 *)0x08636ba8)        /* Corona City's, when ... */
#define PB_NIGHT (*(volatile u8 *)0x02002c4c)               /* ... this is 1 (read by 0x0803d77c) */
typedef void (*FadeBy)(int);
#define PB_FADE_ADD ((FadeBy)0x080777ed)                    /* + level / 8 to every channel */
#define PB_FADE_MUL ((FadeBy)0x080779bd)                    /* * (level >> 16) / 256 */
#define PB_FADE_MUL2 ((FadeBy)0x08077f45)                   /* the same, another copy */

/* is Payback's palette on screen as it is (not faded)? */
static int palette_plain(void)
{
    static const u8 probe[] = {3, 104, 197};
    const u16 *pal = PB_NIGHT == 1 ? PB_PALETTE_NIGHT : PB_PALETTE;
    for (unsigned i = 0; i < sizeof probe; i++) {
        u16 c = pal[probe[i]];
        if (PAL_BG[probe[i]] != ((c >> 10 & 31) | (c & 0x3e0) | (c & 31) << 10))
            return 0;
    }
    return 1;
}

/* Payback calls these in place of its palette fades (the build redirects every call) */
void sf_fade(int level)
{
    PB_FADE(level > 256 ? 256 : level);
    if (STATE[0] != MAGIC || __keep_canary[0] != CANARY)
        return;
    fade_d = (level - 256) >> 3;   /* (not 0: paused, or a scene is changing) */
}

/* Corona City's lightning is this fade with a level that decays from about 340 (toward white:
   0x02001df2, called from 0x08017b78): a glow of two steps a channel at most instead, which no
   measure of a flash counts, dying away as Payback's level does. */
#define LIGHTNING 16
void sf_fade_add(int level)
{
    PB_FADE_ADD(level > LIGHTNING ? LIGHTNING : level);
}

/* The zoom into a new level (0x0803c75a) fades toward white with it: toward black instead,
   as said above. */
void sf_fade_zoom(int level)
{
    if (level > 0)
        PB_FADE_MUL((256 - (level > 256 ? 256 : level)) << 16);
    else
        PB_FADE_ADD(level);
}

void sf_fade_mul(int level)
{
    PB_FADE_MUL(level > 256 << 16 ? 256 << 16 : level);
}

void sf_fade_mul2(int level)
{
    PB_FADE_MUL2(level > 256 << 16 ? 256 << 16 : level);
}

/* Payback's physics for one entity (gravity, then the map's walls and floors), which its entity
   update calls for everyone (the build redirects that call here). It costs about 10k cycles a
   vehicle, and parked cars and settled wrecks never move: Freedom City always has four parked,
   and every car blown up stays as a wreck. The physics reads only the record and the map (and
   dt), so once two calls in a row on the same record have left it as it was, with a result of 0
   (no bump), it is at rest: until anything in it changes the call is skipped. It runs anyway
   about once a second. Our guarded records (sf_guard) always get the real call: what it does
   to them depends on the guard (sf_hook_wall), which comes and goes. */
typedef void (*Phys)(u8 *, u8 *);
#define PB_PHYS ((Phys)0x080174ed)
#define ST_PARKED 4
#define ST_WRECK 6                 /* 6 and 7 */
#define MEMO_N 8
#define MEMO_OK 0x80
static u32 memo_hk[MEMO_N];        /* the record's hash, its low byte replaced by the record's key */
static u8 memo_t[MEMO_N];          /* the clock at the last real call (7 bits), | MEMO_OK */

u32 rec_hash(const u8 *e, u32 h);  /* rechash.s */
static u32 phys_key(const u8 *e) { return rec_hash(e, (u32)e ^ (u32)PB_GRID) & ~0xff; }

void sf_phys(u8 *out, u8 *e)
{
    u32 st = e[E_STATE];
    if ((st != ST_PARKED && st - ST_WRECK > 1) || !is_vehicle(e) || e == sf_guard[0] || e == sf_guard[1]) {
        PB_PHYS(out, e);
        return;
    }
    u32 key = (u32)e >> 3 & 0xff;  /* (records are 45 * 8 bytes apart: no two share a key) */
    u32 now = PB_LEVEL_CLOCK, i, old = 0;
    for (i = 0; i < MEMO_N && (memo_hk[i] & 0xff) != key; i++)
        if (((now - memo_t[i]) & 0x7f) > ((now - memo_t[old]) & 0x7f))
            old = i;
    if (i == MEMO_N) {
        if (((now - memo_t[old]) & 0x7f) < 64) {             /* all in use */
            PB_PHYS(out, e);
            return;
        }
        i = old;
        memo_hk[i] = key, memo_t[i] = now & 0x7f;            /* (nothing known yet) */
    }
    u32 h = phys_key(e) | key, t = memo_t[i];
    if ((t & MEMO_OK) && memo_hk[i] == h && ((now - t) & 0x7f) < 32) {
        *(u16 *)out = 0;           /* (Payback reads only these two bytes of it) */
        return;
    }
    PB_PHYS(out, e);
    int rest = memo_hk[i] == h && *(u16 *)out == 0 && (phys_key(e) | key) == h;
    memo_t[i] = (now & 0x7f) | (rest ? MEMO_OK : 0);
    memo_hk[i] = h;
}

/* ---- the frame ---- */

/* who moves the player this frame: Payback, our car or the Arwing */
static void choose_mode(u8 *me)
{
    if (bail_req) {
        bail_req = 0;
        if (mode == DRIVE)
            bail_car();
    }
    if (bail)
        call_req = 0;                                  /* (a body calls nothing) */
    if (!me || (bail && me == car_ent))
        return;                                        /* (on his way out: bail_frame) */
    if (mode == FLY) {
        if (is_vehicle(me))
            mode = FOOT, parked = 1;                   /* a mission put the player somewhere */
        else if (call_req && !sg_select(&ship))
            land(me);
    } else if (is_car(me)) {
        boarding = 0;
        if (mode != DRIVE || car_ent != me)
            car_take(me);
        swimming = 0;
        if (call_req)
            want_ship = 60;                            /* out of the car, then the Arwing comes */
        if (car_wet > 20 && !want_ship) {
            /* in the water: he gets out (Payback lets him, see build.py) and swims while it sinks */
            car.b.vel.x = car.b.vel.z = 0;
            *(s16 *)(me + E_SPEED) = *(s16 *)(me + E_SPEED + 2) = 0;
            if (!inject_l && car_wet & 8)              /* (it counts ticks, 4 or so a frame: a */
                inject_l = 4;                          /* multiple of 8 may never be seen here) */
        }
        if (want_ship) {
            car.b.vel = car.b.w = v3(0, 0, 0);         /* Payback lets nobody out at speed */
            *(s16 *)(me + E_SPEED) = *(s16 *)(me + E_SPEED + 2) = 0;
            if (!inject_l && !(want_ship & 7))
                inject_l = 4;                          /* press L for Payback */
            want_ship--;
        }
    } else {
        mode = FOOT;
        inject_l = 0;
        if (!is_vehicle(me) && (call_req || want_ship))
            boarding = 1;
        want_ship = 0;
        if (boarding && !is_vehicle(me) && !arrive && !bail && ghost != GH_SHIP) {
            V3 d = vsub(vshr(ship.b.pos, FX), entity_pos(me));
            if (parked && iabs(d.x) <= 2500 && iabs(d.z) <= 2500 && iabs(d.y) <= 600)
                board(me), boarding = 0;            /* it is here (or has just set down) */
            else
                call_ship(me);
        }
    }
    call_req = 0;
}

/* the hint for what you are doing now, if it has not been said (see news_send) */
static int hint_pick(const u8 *me)
{
    if (mode != last_mode)
        last_mode = mode, mode_since = frame_count;
    if (mode == FLY)
        flew_at = frame_count | 1;
    u32 calm = frame_count - mode_since;       /* in this mode so long */
    int h = -1;
    if (mode == FOOT && me && !is_vehicle(me) && calm > 900 && (!flew_at || frame_count - flew_at > 3600))
        h = H_FOOT;                            /* on foot a while, and not just out of the Arwing */
    else if (mode == DRIVE && car_ent && vehicle_kind(car_ent) != TANK)
        h = H_CAR;                             /* (Tank Warfare's tank is no stunt car) */
    else if (mode == FLY && sg_state == SG_FLY) {
        s32 alt = ship.b.pos.y >> FX;
        h = alt > SPACE_HI ? H_SPACE : alt > SPACE_LO ? -1 : !(told & 1 << H_ARWING) || ship.gear || calm < 1200 ? H_ARWING : H_CLIMB;
    }
    if ((h < 0 || told & 1 << h) && mode != FLY && calm > 1800 && told & 1 << H_FOOT)
        h = H_CAMERA;
    return h >= 0 && !(told & 1 << h) ? h : -1;
}

/* the lane through a cell of Payback's grid, by its direction: 1 -y, 2 +x, 4 +y, 8 -x (0 none) */
static inline int lane_at(const u32 *g, s32 x, s32 z)
{
    if ((u32)x >= CITY || (u32)z >= CITY)
        return 0;
    const u8 *c = (const u8 *)g[x * CITY + z];
    return (u32)c - 0x02000000 >= 0x08000000 ? 0 : c[3] & 0x0f;
}

/* man_follow's test of a cell: on the map, no lane through it, street (street_at's test, inline:
   it runs on up to 81 cells), and no lane running into it or out of it from the cells beside:
   traffic goes on through a lane-free cell at a lane's end, under a bridge or across a junction
   (Little Chicago: a car waited 19 samples of 30 for him in the cell under a bridge) */
static inline int free_street(const u32 *g, s32 x, s32 z, u32 top)
{
    if ((u32)x >= CITY || (u32)z >= CITY)
        return 0;
    const u8 *c = (const u8 *)g[x * CITY + z];
    if ((u32)c - 0x02000000 >= 0x08000000 || c[3] & 0x0f)
        return 0;
    for (int k = 0; k < 3; k++, c += 20)
        if (c[8] && (*(const u16 *)(c + 4) > top || *(const u16 *)(c + 6) > top
                     || (c[10] | (c[11] & 3) << 8) == PB_TILE_WATER))
            return 0;
    return !(lane_at(g, x, z - 1) & 5 || lane_at(g, x, z + 1) & 5 || lane_at(g, x - 1, z) & 10 ||
             lane_at(g, x + 1, z) & 10);
}

/* Payback's man rides along under the Arwing (not drawn), so its traffic, police and minimap
   follow us. Flying (32 units a tick or more, a tick being a vblank: B held is 39, cruise 82,
   boost 135; Payback's cars run at a median of 30) he is set right under it, as before, if that
   is street: he outruns most cars behind him, and moving him from pavement to pavement made him
   (and Payback's centre with him) jump up to 6 cells, so things popped in at the cut-off. Once
   under it he stays there down to 24 a tick (no hopping between the two near 32). Slower, each
   frame he is set in the middle of the street cell
   nearest the Arwing's ground
   point where no lane runs or ends (a pavement or a square: free_street), looking in its own
   cell, then ring by ring out to 4 cells, stopping at the first ring with one: Payback's traffic
   stops for anyone ahead in
   its lane, and would queue behind nothing. (Its lane is wider than a cell: a car stops for a man
   0.62 of a cell from its line, not 0.8; the middle of a pavement cell is a whole cell from the
   next lane's.) With none in the first ring round, a cell of that kind he already stands on will
   do, 2 cells away at most (4 while the Arwing hovers, under 4 a tick: it then costs 10 cells a
   frame, not up to 81). (Kept further while moving he lags, then jumps: Payback's centre catches
   up by half the gap a frame, things pop in at the cut-off, and its square shrinks while he
   stands still.)
   With no such street within 4 he is set right under the Arwing, lane or not
   (if that is street); over roofs or water he waits where he was. Rings 3 and 4 are looked in
   only with street under the Arwing (where he would otherwise stand on the lane): over roofs
   the search stops at 2 cells, 25 cells at most, not 81 every frame.
   Near a goal Payback reaches by its man standing at it (kinds 1, 2, 4, 7, 50 and 55 within half
   a cell of it, 0x0807b8d4; 15, a destination area of two, 0x0807b114), he stands right under
   the Arwing as before, lane or not: missions put those on road nodes, and from a pavement he
   would never be on them. A ringing phone (1, 7) counts only inside Payback's own reach (half a
   cell, and a little): phones stand beside roads, and a rampage always has one ringing. (Not every 4th frame by frame_count: that goes up by the ticks of each frame,
   so its low bits can stay put for long.) */
static void man_follow(u8 *me)
{
    const u32 *g = PB_GRID;
    if ((u32)g - 0x02000000 >= 0x40000)
        return;
    V3 p = vshr(ship.b.pos, FX), at = p;
    s32 v = iabs(ship.b.vel.x) + iabs(ship.b.vel.z);
    s32 ux = (*(const s32 *)(me + E_X) >> 1) - p.x, uz = (*(const s32 *)(me + E_Y) >> 1) - p.z;
    if (v >= (32 << FX) || (v >= (24 << FX) && iabs(ux) < CELL / 2 && iabs(uz) < CELL / 2)) {
        /* (flying: right under it; once there, down to 24 a tick, so he does not hop back and forth) */
        if (street_at(p.x, p.z))
            man_put(me, p, heading_of(&ship.b.m));
        return;
    }
    int n = PB_NGOALS;
    if (n < 0 || n > 64)
        n = 0;
    for (int i = 0; i < n; i++) {
        const s32 *q = PB_GOALS + 9 * i;
        s32 k = q[1];
        s32 gx = iabs((q[2] >> 1) - p.x), gz = iabs((q[3] >> 1) - p.z);
        if (((k == 2 || k == 4 || k == 15 || k == 50 || k == 55) && gx < 5 * CELL / 2 && gz < 5 * CELL / 2) ||
            ((k == 1 || k == 7) && gx < CELL / 2 + 128 && gz < CELL / 2 + 128)) {
            if (street_at(p.x, p.z))
                man_put(me, p, heading_of(&ship.b.m));
            return;
        }
    }
    u32 top = PB_STREET + 16 - (world.yoff >> 3);       /* (this map's street level: see world.h) */
    s32 cx = p.x >> 10, cz = p.z >> 10, best = 0x7fffffff;
    s32 mx = *(const s32 *)(me + E_X) >> 11, mz = *(const s32 *)(me + E_Y) >> 11;   /* (his cell) */
    s32 keep = v < (4 << FX) ? 4 : 2;                                                 /* (hovering: 4) */
    for (s32 r = 0; r <= 4 && best == 0x7fffffff; r++) {
        if (r == 3 && !street_at(p.x, p.z))
            return;                                      /* (rings 3 and 4 only over street) */
        if (r == 2 && iabs(mx - cx) <= keep && iabs(mz - cz) <= keep && free_street(g, mx, mz, top)) {
            at = v3(mx * CELL + CELL / 2, 0, mz * CELL + CELL / 2);
            best = 0;
            break;
        }
        for (s32 x = cx - r; x <= cx + r; x++)
            for (s32 z = cz - r; z <= cz + r; z += x == cx - r || x == cx + r ? 1 : 2 * r) {
                V3 q = v3(x * CELL + CELL / 2, 0, z * CELL + CELL / 2);   /* (its middle: see above) */
                s32 d = (q.x - p.x) * (q.x - p.x) + (q.z - p.z) * (q.z - p.z);
                if (d < best && free_street(g, x, z, top))
                    best = d, at = q;
            }
    }
    if (best != 0x7fffffff || street_at(p.x, p.z))
        man_put(me, at, heading_of(&ship.b.m));
}

static void step(u8 *me, int ticks)
{
    car_knocked();
    hits |= keys & ~prev_keys;                         /* (a frame can pass with no tick in it) */
    int dead = mode == DRIVE && car_dead();
    if (mode != DRIVE && me && is_person(me) && !swimming && !bail)
        swim_check(me);                                /* (under the Arwing too: Payback's own move of him;
                                                          a body bailing out floats to the bank itself) */
    for (int t = 0; t < ticks; t++) {
        if (mode == DRIVE) {
            s32 vx = car.b.vel.x >> 4, vz = car.b.vel.z >> 4, was = isqrt(vx * vx + vz * vz) << 4;
            if (dead) {
                car_update(&car, car.speed > (2 << FX) ? KEY_B : 0);   /* no driver: it rolls to a stop */
                car.b.vel.x -= car.b.vel.x >> 3, car.b.vel.z -= car.b.vel.z >> 3;
            } else
                car_update(&car, mirror_keys(keys) & ~KEY_L);          /* L is Payback's: get out */
            car_fence();
            car_bump();
            car_stunts();
            car_crash(was);
            if (car_boom || (car_ent && (car_ent[E_STATE] == 6 || car_ent[E_STATE] == 7)))
                car_boom += car_boom < 255;
            car_wet = car.in_water ? car_wet + (car_wet < 255) : 0;
        } else if (mode == FOOT && swimming) {
            swim_tick(me, keys);
        } else if (mode == FLY) {
            sg_tick(&ship, mirror_keys(keys), t ? 0 : hits);
            if (sg_state == SG_FLY)
                ship_events();
        }
        if (ghost == GH_CAR && mode != DRIVE)
            ghost_car();
        else if (ghost == GH_SHIP)
            ghost_ship();
        if (mode != FLY)
            sg_fx_tick();
        if (arrive)
            arrive_tick();
        space_tick();
        hits = 0;
    }
    /* (our car's record only while it is the player's, or rolls on empty: after a wreck Payback
       gives it to someone new) */
    int empty = ghost == GH_CAR && mode != DRIVE && car_ent && (!bail || bail_out);
    if ((mode == DRIVE && !car_boom && me == car_ent) || empty) {
        entity_put(car_ent, vshr(car.b.pos, FX), heading_of(&car.b.m), empty ? v3(0, 0, 0) : car.b.vel);
        if (empty)                                 /* (no speed: Payback's own physics leaves it to ours) */
            *(s16 *)(car_ent + E_SPEED) = *(s16 *)(car_ent + E_SPEED + 2) = 0;
        /* and its height, ours: Payback's own lifts it a tick at a time, and a hop over a ramp's
           top leaves it in the air for good at our tick rate (wall tests at the wrong height) */
        if (!car.in_water) {
            s32 y = car.wheels ? surface_fine(car.b.pos) >> FX : (car.b.pos.y >> FX) - 76, w;
            if (world_water(car.b.pos.x >> FX, car.b.pos.z >> FX, &w) && y < w)
                y = w;                                 /* (over the water, at its bed: Payback drowns it there) */
            *(u16 *)(car_ent + E_Z) = 19904 - 2 * (y - world.yoff);
            *(s16 *)(car_ent + E_VZ) = 0;
        }
        s16 *hp = (s16 *)(car_ent + E_HEALTH);
        if (crash_lost && *hp > 0)
            *hp = *hp > crash_lost ? *hp - crash_lost : 1;   /* our crashes wear it down, never wreck
                                                                 it (empty, it would blow up by him;
                                                                 driven, the hearts are the man's) */
    } else if (mode == FLY && me) {
        V3 p = vshr(ship.b.pos, FX);
        if (swimming && street_at(p.x, p.z))
            swim_out(me, v3(p.x, world_ground(p.x, p.z), p.z));   /* (called from the water, over the street) */
        man_follow(me);                                /* (last: where he waits under us) */
    }
    if (swimming && me)
        swim_hold(me);                                 /* (afloat while we fly, or Payback sinks him) */
    crash_lost = 0;
}

/* Payback has loaded a level (or started a replay), on this map or another, while our memory
   lived on: the map's world, and whatever belonged to the last level goes (the car's record, the
   Arwing parked there, the space game's pirates, shots and job under way). The player's
   progress (credits, missiles, upgrades, paint, medals, jobs done) stays. */
static void level_enter(int map)
{
    world_select(map_now = map);
    mode = FOOT;
    parked = 0;
    car_ent = hero = 0;
    memset(&car, 0, sizeof car);
    memset(&ship, 0, sizeof ship);
    want_ship = inject_l = call_req = arrive = boarding = cam_cut = 0;   /* (and no fly-in under way) */
    sel_down = sel_replay = sel_seen = 0;
    was_flying = in_space = 0;
    air_ticks = loop_top = upside_ticks = 0;
    car_boom = hurt_n = car_wet = 0;
    swimming = swim_lad = 0;
    sf_guard[0] = sf_guard[1] = sf_guard[2] = sf_guard[3] = 0;
    rag_clear();
    memset(rag_who, 0, sizeof rag_who);
    bail = bail_req = ghost = fall_seen = 0;
    cam_yaw = 0, cam_zoom = 256, cam_home = 0;
    tick_acc = 0;
    sg_level_enter();
    opt_level_enter();
    if (chain_to) {                /* the campaign's next map: where you are in it */
        char t[] = "RAMPAGE: MAP 00 OF 11";
        int n = chain_to;
        chain_to = 0;
        t[13] = '0' + n / 10, t[14] = '0' + n % 10;
        if (n < 10)
            t[13] = t[14], t[14] = ' ';
        sg_note(t);
    }
}

/* The progress is checked once a frame against a copy at the top of EWRAM, past everything
   Payback writes in play (even its replay recorder, since the build caps it: see build.py):
   whatever changed it between our frames was not us, so it is put back. A copy that is still
   good also brings the progress back if we ever have to start over (start()). */
#define MIRROR (STATE + 2)         /* 4 words (sg_save), then their check */

static u32 mirror_sum(const volatile u32 *w)
{
    u32 s = MAGIC;
    for (int i = 0; i < 4; i++)
        s = (s ^ w[i]) * 0x01000193 + i;
    return s;
}

static int mirror_load(void)
{
    u32 w[4];
    for (int i = 0; i < 4; i++)
        w[i] = MIRROR[i];
    if (mirror_sum(w) != MIRROR[4])
        return 0;
    sg_load(w);
    return 1;
}

static void progress_check(void)
{
    u32 w[4];
    sg_save(w);
    if (mirror_sum(w) != MIRROR[4])
        mirror_load();
}

static void progress_keep(void)
{
    u32 w[4];
    sg_sane();
    sg_save(w);
    for (int i = 0; i < 4; i++)
        MIRROR[i] = w[i];
    MIRROR[4] = mirror_sum(w);
}

/* After every level Payback asks its game menu (0x08037fe4) what to play next, as map * 2 + sub
   (the bl at 0x080249be, which build.py points here). When a rampage ends with its target
   reached, we answer instead: a rampage on the next map, at once. So one rampage runs through
   all eleven maps, the cities and then every multiplayer map, as a campaign. */
#define PB_GAME_MENU ((int (*)(int))0x08037fe5)
#define PB_LEVEL_END (*(volatile s16 *)0x02001e08)    /* 3: the level's target was reached */
#define PB_MAP (*(volatile s16 *)0x02001d40)          /* the map rampage plays, 0..10 */
#define PB_RAMPAGE (*(volatile u8 *)0x02001d39)
#define PB_WAS_RAMPAGE (*(volatile u8 *)0x02001d3a)   /* Payback sets it as a rampage ends */
#define MAPS 11

int sf_menu(int arg)
{
    int m = PB_MAP;
    if (PB_WAS_RAMPAGE && PB_LEVEL_END == 3 && m >= 0 && m < MAPS - 1) {
        PB_MAP = ++m;
        PB_RAMPAGE = 1;
        PB_WAS_RAMPAGE = 0;
        chain_to = m + 1;
        fill32((void *)0x06000000, 0, 0x14000);       /* both bitmap pages: the old map must not show */
        return m * 2;                                 /* while the next one loads (its first frames flip) */
    }
    return PB_GAME_MENU(arg);
}

/* Payback picks a mission's place (where a phone job's car waits, where it is to go) at random
   among a map's floor cells (0x0803cf54: a random x and y, 1..126 each, from its rand at 0x0807801c,
   then the nearest node of its roads, a search of some 80 ms). Our phones on The Killing Zone run
   its jobs there, and its arena, 34 cells square, stands in 15228 cells of a filler floor that
   passes its test: the car waited outside the walls, where no one gets. So its two random draws
   come through here, and on a map most of whose cells are the corner's column they are drawn
   from the box the other cells fit in (no other map has such a plain: nothing changes there). */
typedef int (*Rand)(int);
#define PB_RAND ((Rand)0x0807801d)                    /* 0..n-1: the next byte of its table, scaled */
#define PICK_X 0x0803cf6e                             /* the chooser's return addresses: x, then y */
#define PICK_Y 0x0803cf78
static u32 filler_corner, filler_clock;
static u8 filler_box[4] = {0, CITY - 1, 0, CITY - 1}; /* x0, x1, z0, z1 of the cells that are not filler */
static void filler_find(void)
{
    const u32 *g = PB_GRID;
    u32 c = g[0];
    int n = 0, x0 = CITY, x1 = -1, z0 = CITY, z1 = -1;
    for (int x = 0; x < CITY; x++)
        for (int z = 0; z < CITY; z++) {
            if (g[x * CITY + z] == c) { n++; continue; }
            if (x < x0) x0 = x;
            if (x > x1) x1 = x;
            if (z < z0) z0 = z;
            if (z > z1) z1 = z;
        }
    if (n <= CITY * CITY / 2) { x0 = z0 = 0; x1 = z1 = CITY - 1; }
    filler_box[0] = x0; filler_box[1] = x1; filler_box[2] = z0; filler_box[3] = z1;
    filler_corner = c;
    filler_clock = PB_LEVEL_CLOCK | 1;                /* (a new level starts the clock again) */
}
__attribute__((noinline)) int sf_pick_rand(int n)
{
    u32 from = (u32)__builtin_return_address(0) & ~1u;
    if (PB_GRID[0] != filler_corner || PB_LEVEL_CLOCK < filler_clock)
        filler_find();
    if (from != PICK_X && from != PICK_Y)
        return PB_RAND(n);
    int lo = filler_box[from == PICK_X ? 0 : 2], hi = filler_box[from == PICK_X ? 1 : 3];
    if (lo == 0 && hi == CITY - 1)
        return PB_RAND(n);
    return lo - 1 + PB_RAND(hi - lo + 1);              /* (the chooser adds 1) */
}

/* Payback reads the keypad once a game frame, 3 to 7 video frames apart: a quick SELECT tap can
   come and go in between, so the frame looks too, as it draws. A hold that starts while
   Payback reads no keys (the first second of a level) counts from the first look that saw it. */
static void sel_look(void)
{
    if (REG_KEYINPUT & KEY_SELECT)
        return;
    if (!sel_seen && !sel_down)
        sel_since = pb_clock();
    sel_seen = 1;
}

/* Called by sf_frame (keyhook.s) in place of Payback's world renderer, with that renderer's
   split-screen view: 0 when Payback is to draw this frame itself (on a map we have no world
   for), else we drew it. Payback's renderer then runs from sf_frame with Payback's own stack:
   it runs deep, and with this function's frame under it, it wrote over Payback's IWRAM data
   at 0x030072xx (a crash on the first punch, measured on Los Francos in v11). */
extern s32 view_alt, view_floor;
extern u8 view_floored;
static u8 ring_high;
int sf_draw(int view)
{
    /* (no EWRAM wait-state write here: it gained about 3% in mGBA but left Pizza Boy A on a black
       screen from the first frame of every level, v12 to v12.2) */
    int ours = STATE[0] == MAGIC && __keep_canary[0] == CANARY;
    int map = view != 0 ? -1 : which_map(ours ? map_now : -1);
    if (map < 0) {
        STATE[0] = 0;                                  /* Payback's renderer reuses our memory */
        hot_restore(1);
        return 0;
    }
    hot_install();
    if (!ours)
        start(map);
    else if (map != map_now || PB_LEVEL_CLOCK < level_clock)
        level_enter(map);
    level_clock = PB_LEVEL_CLOCK;
    progress_check();
    /* (Payback rebuilds its table at each level.) The water drifts a texel every quarter of a
       second, 32 one way then 32 back, a slow swell: the tile moves as a whole, so nothing in it
       blinks, and it never jumps (the image does not repeat every 32) */
    u32 drift = (frame_count >> 4) & 63;
    ((const u8 **)PB_TEXTAB)[TEX_WATER] = PB_WATER + (drift < 32 ? drift : 63 - drift);
    /* Payback's pause menu (or a replay): it draws the world, but none of its game ticks has read
       the keys since our last frame. Nothing of ours moves or takes a key then, and our HUD keeps
       off its menu. */
    int paused = key_calls == frame_calls;
    frame_calls = key_calls;
    prev_keys = keys;
    keys = ~REG_KEYINPUT & 0x3ff;
    if (!(keys & PAD_ALL) || sel_chord)
        cam_lock = 0;
    else if ((keys & KEY_SELECT) && !chord_wait())
        cam_lock = 1;
    cam_pad = cam_lock ? keys & PAD_ALL : 0;
    keys &= ~cam_pad;                                  /* the camera's, not the car's or the Arwing's */
    if (r_chord || (mode == DRIVE && (keys & KEY_SELECT) && (keys & KEY_R) && radio_chord()))
        keys &= ~KEY_R;                                /* (the chord's R is the radio's) */
    if (mode == DRIVE && car_kind == TANK)
        keys &= ~KEY_R;                                /* (a tank's R is Payback's: it fires, no boost jet) */
    u32 now = pb_clock();
    tick_acc += (now - last_clock) * 60;
    last_clock = now;
    int ticks = tick_acc >> 14;
    tick_acc &= 0x3fff;
    if (ticks > 8) ticks = 8;
    if (fade_d || paused)
        ticks = 0;                                     /* Payback's pause menu is up */
    frame_count += ticks;

    /* while Payback kills (or arrests) the player and brings him back, its index may point at
       anyone, a car nearby or nothing: we take no orders from it then */
    u8 *me = PB_RESPAWN > 0 ? 0 : controlled();
    if (me)
        hero = is_person(me) ? me : 0;
    if (!me || me != hero)
        swimming = 0;
    goals_scan(me);
    opt_frame(me, ticks);
    if (!paused) {
        choose_mode(me);
        step(me, ticks);
        rag_scan(ticks);
        fall_scan(me);
        bail_frame(me, ticks);
        hint_now = hint_pick(me);
    }
    camera_move(ticks);
    camera_update(me ? me : hero && is_person(hero) ? hero : 0);

    s32 alt = cam.pos.y;
    r_pmap = pb_pmap;
    tex_on = 1;                    /* Payback's tiles (they fade out with height, see tex.c) */
    r_nofog = alt > 16000;         /* (our fog colours are the sky's; in space there is none) */
    r_begin();
    tex_frame();
    sky_draw(alt);
    int hangar = mode == FLY && sg_state == SG_DOCKED;   /* inside: the city far below is out of sight */
    /* your own car or Arwing first: with the pool full (a high look-down over a dense district,
       in Freedom City's second story level, where Payback's cell copies take 3 KB of it) what
       comes later is left out, never you */
    if (mode == DRIVE)
        draw_car();
    if (mode == FLY || parked)
        draw_ship();
    /* (the view's ground: under you on foot, driving or parked; in flight, round the camera) */
    view_floored = mode != FLY || ship.gear;
    if (view_floored)
        view_floor = world_ground(cam_focus.x, cam_focus.z);
    if (!hangar)
        world_draw(), props_draw(), rings_draw();
    sel_look();
    space_draw();
    if (!hangar)
        draw_entities(me), draw_ladders(), rag_draw();   /* (the ladders after him: he is on top where they tie) */
    sg_draw(&ship);
    /* the phone's pointer down in the city, by the view's eased height over it (see world_draw:
       by the ground straight under the camera it blinked over every roof) */
    if (view_alt > 6400) ring_high = 1;
    else if (view_alt < 5600) ring_high = 0;
    if (!hangar && !ring_high && !paused)
        ring_pointer(me);
    else
        point_x = 0, pointed = paused ? pointed : 0;
    sel_look();
    r_flush_bg();
    sel_look();
    stars_draw(alt);
    r_flush_fg();
    r_end();
    sel_look();
    int done = PB_LEVEL_END == 3;                      /* (Payback's red level-complete lines are where ours go) */
    if (point_x && !done)
        d_text(point_x, 69, "PHONE", point_c);
    if (paused || done)
        ;                                              /* (off Payback's menu) */
    else if (mode == FLY)
        sg_hud(&ship);
    else
        sg_banner();
    if (!(mode == FLY && sg_state == SG_DOCKED))
        opt_hud(paused || done);                       /* (it gives Payback's sprites back first) */
    radio_hud(mode == DRIVE && !paused && !done, ticks, PB_BTN[B_START]);
    if (swimming && swim_far && !swim_hint && !(told & 32) && mode == FOOT) {
        told |= 32;                                    /* (once: the arrow says it from then on) */
        swim_hint = 360;
        swim_msg = 1;
    }
    if (swim_hint && !paused && !done) {
        /* (on the left under Payback's weapon, clear of its hearts and its minimap) */
        static const char *const t[2][3] = {{"Swim to a low bank", "or a ladder to climb out.", ""},
                                            {"Follow the arrow out,", "or hold SELECT for", "your Arwing."}};
        if (swimming && mode == FOOT)                  /* (gone for good once out, or flying) */
            for (int k = 0; k < 3; k++)
                d_text(8, 44 + 10 * k, t[swim_msg][k], COLOR(M_GLOW, 3, 0));
        swim_hint = swim_hint > ticks ? swim_hint - ticks : 0;
    }
    if (fade_d && palette_plain())
        fade_d = 0;                /* Payback has put its colours back */
    sf_guard[0] = mode == FLY || bail || ghost == GH_CAR ? hero : 0;   /* (a body, or by his car rolling on) */
    sf_guard[1] = mode == DRIVE || ghost == GH_CAR ? car_ent : 0;
    sf_guard[2] = mode == FOOT ? hero : 0;            /* (the hooks look at [0] first) */
    if (mode == FLY && sf_guard[0] && *(s16 *)(hero + E_HEALTH) < 100)
        *(s16 *)(hero + E_HEALTH) = 100;              /* (and nothing slower wears him down) */
    progress_keep();
    off_arrow_line(hero);                              /* (Payback's arrow code runs next) */
    off_arrow_line(controlled());
    hot_restore(0);
    news_send();
    hurt_send();
    props_send();                  /* (props.c: the crates our bolts hit) */
    return 1;
}
