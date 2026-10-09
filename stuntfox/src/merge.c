/* Stunt Fox inside Payback (the MERGE build, see build.py --merge).

   Like SkyCraft running Minecraft's player inside Skyrim's world, the two games share one
   cartridge and each does what it is good at. Payback keeps running everything it owns:
   Freedom City's traffic and people, the police, missions, the phone ticker, the minimap,
   music and sound. Its world renderer is gone: where Payback used to draw its 3D view it now
   calls sf_frame(), and Stunt Fox draws the city and everyone in it from a chase camera with
   its own faster renderer.

   The player's car is a Stunt Fox car (springs, loops, ramps, boost) that Payback sees as its
   own: we write its position back into Payback's record, so traffic, police and missions keep
   working around it. Hold SELECT anywhere and the Arwing lands next to you; Payback's man rides
   along under it so the city, the minimap and the police follow you into the sky.

   Payback's code is never copied: the build patches the player's own ROM and reads Freedom
   City's layout from it. */
#include "gba.h"
#include "fx.h"
#include "render.h"
#include "world.h"
#include "palette.h"
#include "physics.h"
#include "car.h"
#include "ship.h"
#include "traffic.h"
#include "model.h"
#include "space.h"

/* ---- Payback (Europe), see payback-mod/docs/payback-notes.md ---- */

#define PB_GRID (*(const u32 *volatile *)0x03000d60)       /* level cells: column pointers */
#define PB_ENTITY ((u8 *const volatile *)0x03000c60)        /* the entity list */
#define PB_NENTITY (*(volatile s16 *)0x0300000c)
#define PB_CONTROLLED (*(volatile s16 *)0x02001db8)         /* the entity the player is or drives */
typedef void (*DrawWorld)(int, int, int, int, int, int, int, int);
#define PB_DRAW_WORLD ((DrawWorld)0x0800adad)               /* Payback's own world renderer */
#define PB_IWRAM_IMAGE ((const u8 *)0x087d9ab8)             /* the ROM copy of Payback's IWRAM code */
typedef void (*Fade)(int);
#define PB_FADE ((Fade)0x0806c82d)                          /* palette brightness, 256 = normal */

/* entity record */
#define E_X 4                      /* s32, 2048 per cell */
#define E_Y 8
#define E_Z 0xc                    /* low 16 bits: 19904 at street level, 16 per height step */
#define E_HEAD 0x12                /* s16, 5760 per turn, 0 = +y */
#define E_HEAD32 0x10              /* the same heading in 16.16 */
#define E_DESC 0x1c                /* descriptor: vehicles are 0x3c-byte records */
#define E_VX 0x40                  /* s16 velocity, units per 1/30 s */
#define E_VY 0x42
#define E_SPEED 0xba               /* s16 speeds */
#define E_PREV1 0xe4               /* earlier positions (x, y) */
#define E_PREV2 0xf0
#define VEH_FIRST 0x08354af4
#define VEH_HELI 0x08354ef0
#define VEH_SIZE 0x3c

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

/* a few words at the top of EWRAM that Payback leaves alone (the old patch mod kept its flags
   here); Payback clears them when it loads a level, which makes us start over too */
#define STATE ((volatile u32 *)0x0203ffd0)
#define MAGIC 0x53465831           /* "SFX1": our memory is set up */

/* cells and their column pointers for Freedom City, written by build.py */
extern const u32 merge_sig[32][2];

/* linker symbols, merge.ld */
extern u8 __hot_start[], __hot_end[], __hot_lma[];
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
    u16 ime = REG_IME;
    REG_IME = 0;
    REG_DMA3CNT = 0;
    REG_DMA3SAD = (u32)s;
    REG_DMA3DAD = (u32)d;
    REG_DMA3CNT = (bytes >> 2) | 0x84000000;
    REG_IME = ime;
}

/* Our hottest code borrows the IWRAM that Payback's world renderer runs from, only for the
   length of our frame; Payback's own code is put back from its ROM image afterwards. */
static void hot_install(void)
{
    if (*(u32 *)__hot_start != *(const u32 *)__hot_lma)
        copy32(__hot_start, __hot_lma, __hot_end - __hot_start);
}

static void hot_restore(void)
{
    const u8 *orig = PB_IWRAM_IMAGE + ((u32)__hot_start - 0x03000000);
    if (*(u32 *)__hot_start != *(const u32 *)orig)
        copy32(__hot_start, orig, __hot_end - __hot_start);
}

static int in_freedom_city(void)
{
    const u32 *g = PB_GRID;
    if ((u32)g < 0x02000000 || (u32)g >= 0x0203c000)
        return 0;
    int ok = 0;
    for (int i = 0; i < 32; i++)
        ok += g[merge_sig[i][0]] == merge_sig[i][1];
    return ok >= 28;
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
static u16 pal_cache[256] __attribute__((aligned(4)));   /* DMA copies words */
static int mode, parked;           /* parked: the Arwing waits where we left it */
static Car car;
static Ship ship;
static u8 *car_ent;                /* Payback's record of the car we drive */
static int car_kind;               /* which of Payback's vehicles it is */
static int vehicle_kind(const u8 *e);
static u16 keys, prev_keys;
static u8 want_ship, told;

/* SELECT, as sf_keys sees it */
static u32 key_calls, frame_calls, sel_since;
static u8 sel_down, sel_used, sel_replay, inject_l, call_req;

static char news[100];
static s32 fade_d;                 /* added to each colour channel, from Payback's fade */
static u8 news_ready;

static void start(void)
{
    copy32(__data_start, __data_lma, __data_end - __data_start);
    for (u32 *p = (u32 *)__bss_start; p < (u32 *)__bss_end; p++)
        *p = 0;
    r_init();
    world_init();
    models_init();
    traffic_init();
    space_init();
    palette_out = pal_cache;
    cam_off = v3(0, 400, -800);
    cam_up = v3(0, ONE, 0);
    last_clock = pb_clock();
    __keep_canary[0] = CANARY;
    STATE[0] = MAGIC;
}

static s32 iabs(s32 v) { return v < 0 ? -v : v; }
static s32 clamp(s32 v, s32 lo, s32 hi) { return v < lo ? lo : v > hi ? hi : v; }

/* one line for Payback's ticker; sent once our frame is over */
static void say(const char *s)
{
    int n = 0;
    while (s[n] && n < (int)sizeof news - 1)
        news[n] = s[n], n++;
    news[n] = 0;
    news_ready = 1;
}

static void news_send(void)
{
    if (!news_ready)
        return;
    news_ready = 0;
    int i = TICK_IDX;
    if (i < 0 || i > 9)
        i = 0;
    char *dst = TICK_SLOTS + i * 500;
    for (int n = 0; n < (int)sizeof news; n++)
        if (!(dst[n] = news[n]))
            break;
    TICK_QUEUE(dst, 2);
    TICK_IDX = i >= 9 ? 0 : i + 1;
}

/* ---- Payback's entities ---- */

static int valid(const u8 *e) { return (u32)e >= 0x02000000 && (u32)e < 0x02040000; }

static V3 entity_pos(const u8 *e)
{
    s32 x = *(const s32 *)(e + E_X), y = *(const s32 *)(e + E_Y);
    s32 z = *(const u16 *)(e + E_Z);
    return v3(x >> 1, (19904 - z) >> 1, y >> 1);
}

static s32 entity_heading(const u8 *e)
{
    return (*(const s16 *)(e + E_HEAD) * 11651) >> 10;      /* 5760 -> 65536 per turn */
}

/* move Payback's record to where we are (units, our heading, fine/tick) */
static void entity_put(u8 *e, V3 p, s32 heading, V3 vel)
{
    s32 *w = (s32 *)e;
    w[E_PREV1 / 4] = w[E_PREV2 / 4] = w[E_X / 4];
    w[E_PREV1 / 4 + 1] = w[E_PREV2 / 4 + 1] = w[E_Y / 4];
    w[E_X / 4] = clamp(p.x, 2 * CELL, (CITY - 2) * CELL) * 2;
    w[E_Y / 4] = clamp(p.z, 2 * CELL, (CITY - 2) * CELL) * 2;
    w[E_HEAD32 / 4] = (heading & 0xffff) * 5760;
    *(s16 *)(e + E_VX) = vel.x >> 6;
    *(s16 *)(e + E_VY) = vel.z >> 6;
}

static u32 entity_desc(const u8 *e) { return *(const u32 *)(e + E_DESC); }

static int is_vehicle(const u8 *e)
{
    u32 d = entity_desc(e);
    return d >= VEH_FIRST && d <= VEH_HELI;
}

static int is_car(const u8 *e) { return is_vehicle(e) && entity_desc(e) != VEH_HELI; }

static u8 *controlled(void)
{
    int i = PB_CONTROLLED, n = PB_NENTITY;
    if (i < 0 || i >= n)
        return 0;
    u8 *e = PB_ENTITY[i];
    return valid(e) ? e : 0;
}

static s32 heading_of(const M3 *m) { return fatan2(m->f.x, m->f.z); }

/* ---- buttons ---- */

/* Called by Payback right after it reads the keypad (the build hooks that call). Holding
   SELECT for half a second calls the Arwing; a short press still reaches Payback, as its
   phone. While we fly, Payback's man sees no buttons but START. */
void sf_keys(void)
{
    if (STATE[0] != MAGIC || __keep_canary[0] != CANARY)
        return;
    key_calls++;
    if (key_calls - frame_calls > 4 || fade_d) {
        sel_down = 0;                                  /* paused, a cut scene or a fade: all Payback's */
        return;
    }
    int sel = !(REG_KEYINPUT & KEY_SELECT);
    u32 now = pb_clock();
    if (sel && !sel_down)
        sel_since = now, sel_used = 0;
    if (sel && !sel_used && now - sel_since >= 8192)
        call_req = 1, sel_used = 1;
    if (!sel && sel_down && !sel_used)
        sel_replay = 3;
    sel_down = sel;
    if (mode == FLY)
        for (int i = 0; i < B_N; i++)
            if (i != B_START)
                PB_BTN[i] = 0;
    PB_BTN[B_SELECT] = PB_BTN[B_SELECT2] = 0;
    if (sel_replay) {
        sel_replay--;
        PB_BTN[B_SELECT] = PB_BTN[B_SELECT2] = 1;
    }
    if (inject_l) {
        const u8 *me = controlled();
        inject_l = me && is_car(me) ? inject_l - 1 : 0; /* only to get out of a car */
        PB_BTN[B_L] = inject_l > 0;                     /* press, then let go */
    }
}

/* ---- the camera ---- */

static void camera_look(V3 pos, V3 fwd, V3 up, s32 dist, s32 height, s32 aim_up, s32 aim_fwd)
{
    V3 want = vadd(vscale(fwd, -dist), vscale(up, height));
    cam_off = vadd(cam_off, vshr(vsub(want, cam_off), 2));
    cam_up = vnorm(vadd(cam_up, vshr(vsub(up, cam_up), 2)));
    cam.pos = vadd(pos, cam_off);
    /* Payback's streets are narrow: come in closer rather than look out of a wall */
    V3 pivot = vadd(pos, v3(0, 150, 0)), span = vsub(cam.pos, pivot);
    for (int k = 1; k <= 8; k++) {
        V3 q = vadd(pivot, vscale(span, k * 2048));
        if (world_ground(q.x, q.z) > q.y - 40) {
            cam.pos = vadd(pivot, vscale(span, (k - 1) * 2048));
            break;
        }
    }
    s32 g = world_ground(cam.pos.x, cam.pos.z) + 60;
    if (cam.pos.y < g)
        cam.pos.y = g;
    V3 target = vadd(pos, vadd(vscale(up, aim_up), vscale(fwd, aim_fwd)));
    cam.m.f = vsub(target, cam.pos);
    cam.m.u = cam_up;
    morth(&cam.m);
}

static void camera_update(const u8 *me)
{
    V3 level = v3(0, ONE, 0);
    if (mode == DRIVE) {
        V3 fwd = car.b.m.f, up = car.b.m.u;
        if (!car.wheels) {
            if (vlen(car.b.vel) > 4000)
                fwd = vnorm(v3(car.b.vel.x, car.b.vel.y >> 1, car.b.vel.z));
            up = level;                                /* airborne: keep the horizon level */
        }
        if (car.on_loop)
            camera_look(vshr(car.b.pos, FX), fwd, up, 600, 340, 30, 250);
        else
            camera_look(vshr(car.b.pos, FX), fwd, up, 820, 300, 110, 250);
    } else if (mode == FLY) {
        V3 up = ship.b.m.u;
        if ((ship.b.pos.y >> FX) < SPACE_HI)
            up = vnorm(vadd(up, level));               /* half the bank, like Star Fox */
        camera_look(vshr(ship.b.pos, FX), ship.b.m.f, up, 950, 250, 110, 250);
    } else if (me) {
        M3 m;
        myaw(&m, entity_heading(me));
        int on_foot = !is_vehicle(me);
        camera_look(entity_pos(me), m.f, level, on_foot ? 560 : 900, on_foot ? 360 : 400,
                    on_foot ? 150 : 110, on_foot ? 200 : 300);
    }
}

/* ---- the Stunt Fox car in Payback's traffic ---- */

static void car_take(u8 *e)
{
    V3 p = entity_pos(e);
    car_reset(&car, v3(p.x, (ground_fine(p.x << FX, p.z << FX) >> FX) + 140, p.z), entity_heading(e));
    car_ent = e;
    car_kind = vehicle_kind(e);
    mode = DRIVE;
    if (!(told & 1)) {
        told |= 1;
        say("Stunt car! A gas, B brake, R boost. Hold SELECT for the Arwing.");
    }
}

/* Payback's cars are solid: push ours off them */
static void car_bump(void)
{
    V3 c = vshr(car.b.pos, FX);
    if (c.y - world_ground(c.x, c.z) > 260)
        return;                                        /* flying over the traffic */
    int n = PB_NENTITY;
    if (n > 64) n = 64;
    for (int i = 0; i < n; i++) {
        const u8 *e = PB_ENTITY[i];
        if (!valid(e) || e == car_ent || !is_car(e))
            continue;
        V3 p = entity_pos(e);
        s32 dx = c.x - p.x, dz = c.z - p.z;
        if (iabs(dx) >= 300 || iabs(dz) >= 300)
            continue;
        s32 d = isqrt(dx * dx + dz * dz);
        if (d >= 300)
            continue;
        V3 nrm = d ? v3(dx * ONE / d, 0, dz * ONE / d) : car.b.m.r;
        car.b.pos = vadd(car.b.pos, vscale(nrm, (300 - d) << FX));
        s32 vn = vdot(car.b.vel, nrm);
        if (vn < 0) {
            car.b.vel = vsub(car.b.vel, vscale(nrm, vn + (vn >> 1)));
            if (vn < -2500)
                say("Crash!");
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
    if (car.wheels == 0) {
        air_ticks++;
        spin_pitch += vdot(b->w, b->m.r);
        spin_roll += vdot(b->w, b->m.f);
        spin_yaw += vdot(b->w, b->m.u);
    } else {
        if (air_ticks > 45 && car.wheels >= 2 && b->m.u.y > 8000) {
            s32 turn = 1544000;                        /* 0.9 of a turn, 1.18 radians */
            if (iabs(spin_pitch) > turn)
                say(spin_pitch > 0 ? "FRONT FLIP!" : "BACK FLIP!");
            else if (iabs(spin_roll) > turn)
                say("BARREL ROLL!");
            else if (iabs(spin_yaw) > turn)
                say("360 SPIN!");
            else if (air_ticks > 100)
                say("HUGE AIR!");
            else
                say("BIG AIR!");
        }
        air_ticks = 0;
        spin_pitch = spin_roll = spin_yaw = 0;
    }
    if (car.on_loop >= 2 && car.loop_ang > 26000 && car.loop_ang < 39000)
        loop_top = 1;
    if (loop_top && !car.on_loop && car.wheels >= 3) {
        loop_top = 0;
        if (b->m.u.y > 12000)
            say("LOOP THE LOOP!");
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
        ship_reset(&ship, v3(at.x, ground_fine(at.x << FX, at.z << FX) >> FX, at.z), entity_heading(me));
    }
    mode = FLY;
    parked = 0;
    was_flying = 0;
    say(told & 2 ? "Arwing!" : "Arwing! A thrust, B brake, DOWN pull up, L R bank. Hold SELECT on the street to get out.");
    told |= 2;
}

static void land(u8 *me)
{
    Body *b = &ship.b;
    V3 p = vshr(b->pos, FX);
    s32 g = ground_fine(b->pos.x, b->pos.z) >> FX;
    if (ship.gear < 2 || vlen(b->vel) > (25 << FX) || p.y - g > 160 || g > 40) {
        say("Land on the street to get out.");
        return;
    }
    V3 at = vadd(p, vscale(b->m.r, 380));
    entity_put(me, at, heading_of(&b->m), v3(0, 0, 0));
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
            say("DOCKED AT THE SPACE STATION!");
        else if (ground_fine(b->pos.x, b->pos.z) > (300 << FX))
            say("ROOFTOP LANDING!");
        else
            say("Nice landing. Hold SELECT to get out.");
    }
    if (alt > SPACE_HI && !in_space) {
        in_space = 1;
        say("SPACE! The station is near.");
    }
    if (alt < SPACE_LO)
        in_space = 0;
}

/* ---- drawing ---- */

/* Payback's vehicles, in the order of its descriptor table: the model, the paint and how
   far back the exhaust is */
typedef struct { const Model *md; u8 paint, scale; s16 rear; } VehicleLook;
static const VehicleLook looks[] = {
    {&mdl_saloon, M_TEAL, 0, -235},       /* Mundaneo */
    {&mdl_saloon, M_BRICK, 224, -235},    /* Pug */
    {&mdl_sport, M_STUNT, 0, -232},       /* Diblo */
    {&mdl_bus, M_ACCENT, 0, -520},        /* bus */
    {&mdl_saloon, M_CONCRETE, 0, -235},   /* Vapour */
    {&mdl_saloon, M_CAR, 224, -235},      /* Pug GTI */
    {&mdl_saloon, M_CREAM, 0, -235},      /* Fjord */
    {&mdl_van, M_SHIP, 0, -245},          /* van */
    {&mdl_limo, M_ROAD, 0, -340},         /* limo */
    {&mdl_saloon, M_SHIP, 0, -235},       /* police car */
    {&mdl_sport, M_CAR, 0, -232},         /* Scooby */
    {&mdl_tank, M_GRASS, 0, -280},        /* tank */
    {&mdl_sport, M_SHIP, 0, -232},        /* Evo */
    {&mdl_saloon, M_ACCENT, 0, -235},     /* taxi */
    {&mdl_van, M_CREAM, 0, -245},         /* ice cream van */
    {&mdl_pickup, M_BRICK, 0, -245},      /* pickup */
    {&mdl_sport, M_GLOW, 0, -232},        /* hot rod */
};
#define POLICE_CAR 9

static int vehicle_kind(const u8 *e)
{
    u32 k = (entity_desc(e) - VEH_FIRST) / VEH_SIZE;
    return k < sizeof looks / sizeof looks[0] ? (int)k : 0;
}

/* red and blue lights on a police car's roof, taking turns */
static void police_lights(const Place *pl)
{
    int red = frame_count & 8, f = pl->fog;
    MVert r[4] = {{-60, 106, -36}, {-6, 106, -36}, {-6, 106, -8}, {-60, 106, -8}};
    MVert b[4] = {{6, 106, -36}, {60, 106, -36}, {60, 106, -8}, {6, 106, -8}};
    MVert rf[4] = {{-60, 92, -8}, {-6, 92, -8}, {-6, 106, -8}, {-60, 106, -8}};
    MVert bf[4] = {{6, 92, -8}, {60, 92, -8}, {60, 106, -8}, {6, 106, -8}};
    int cr = red ? COLOR(M_STUNT, 3, 0) : COLOR(M_STUNT, 0, f);
    int cb = red ? COLOR(M_GLASS, 0, f) : COLOR(M_GLASS, 3, 0);
    model_poly(pl, rf, 4, cr);
    model_poly(pl, bf, 4, cb);
    model_poly(pl, r, 4, cr);
    model_poly(pl, b, 4, cb);
}

/* everyone Payback is running: traffic, parked cars, helicopters and people */
static void draw_entities(const u8 *me)
{
    static const u8 shirts[] = {M_BRICK, M_CAR, M_CREAM, M_TEAL, M_ACCENT, M_SHIP, M_STUNT, M_GRASS};
    int n = PB_NENTITY;
    if (n > 64) n = 64;
    for (int i = 0; i < n; i++) {
        const u8 *e = PB_ENTITY[i];
        if (!valid(e))
            continue;
        if ((mode == DRIVE && e == car_ent) || (mode == FLY && e == me))
            continue;                                  /* we draw that one ourselves */
        V3 p = entity_pos(e);
        if (p.x < 1024 && p.z < 1024)
            continue;                                  /* unused records wait in the corner */
        V3 d = vsub(p, cam.pos);
        if (iabs(d.x) > 20000 || iabs(d.z) > 20000)
            continue;
        M3 m;
        myaw(&m, entity_heading(e));
        Place pl;
        if (is_vehicle(e)) {
            if (entity_desc(e) == VEH_HELI) {
                model_body = M_CAR;
                if (model_place(&pl, p, &m, 256, 0, mdl_heli.radius))
                    model_draw(&mdl_heli, &pl);
                continue;
            }
            int k = vehicle_kind(e);
            const VehicleLook *lk = &looks[k];
            p.y += 58;                                 /* the body rides above its wheels */
            if (!model_place(&pl, p, &m, lk->scale ? lk->scale : 256, 0, lk->md->radius))
                continue;
            model_body = lk->paint;
            model_draw(lk->md, &pl);
            if (k == POLICE_CAR && pl.t.z < 9000)
                police_lights(&pl);
            continue;
        }
        /* a person: dressed by kind (Payback's descriptor), walking when they move */
        if (!model_place(&pl, p, &m, 256, 0, 140))
            continue;
        u32 kind = entity_desc(e) >> 3;
        model_body = shirts[kind % sizeof shirts];
        model_legs = (kind >> 3) & 1 ? M_STEEL : M_ROAD;
        const Model *md = &mdl_ped;
        if (pl.t.z < 2600) {
            const s32 *w = (const s32 *)e;
            int moving = w[E_X / 4] != w[E_PREV1 / 4] || w[E_Y / 4] != w[E_PREV1 / 4 + 1];
            md = !moving ? &mdl_stand : ((iabs(w[E_X / 4]) + iabs(w[E_Y / 4])) >> 7) & 1 ? &mdl_stride_a : &mdl_stride_b;
        }
        model_draw(md, &pl);
    }
    model_body = M_CAR;
    model_legs = M_ROAD;
}

/* the car we drive looks like the Payback vehicle it is */
static void draw_car(void)
{
    Place pl;
    V3 p = vshr(car.b.pos, FX);
    const VehicleLook *lk = &looks[car_kind];
    if (!model_place(&pl, p, &car.b.m, lk->scale ? lk->scale : 256, 0, lk->md->radius))
        return;
    model_body = lk->paint;
    model_draw(lk->md, &pl);
    model_body = M_CAR;
    if (car_kind == POLICE_CAR)
        police_lights(&pl);
    if (car.boosting && (frame_count & 2)) {
        int z = lk->rear;
        MVert fl[3] = {{-50, -10, z}, {50, -10, z}, {0, 0, z - 190 - (int)(frame_count & 4) * 20}};
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
    if (!model_place(&pl, p, &ship.b.m, 256, 0, mdl_arwing.radius))
        return;
    model_draw(&mdl_arwing, &pl);
    if (mode == FLY && !ship.gear) {
        int len = ship.boosting ? 380 : 200;
        MVert fl[3] = {{-30, 6, -90}, {30, 6, -90}, {0, 26, -90 - len - (int)(frame_count & 2) * 30}};
        model_poly(&pl, fl, 3, COLOR(M_GLOW, 3, 0));
    }
}

/* The BG palette is ours (Payback's HUD uses the sprite palettes), shown as bright as
   Payback's fades want it: darker while paused, black between scenes. */

static u16 faded(u16 c)
{
    if (!fade_d)
        return c;
    s32 r = (c & 31) + fade_d, g = (c >> 5 & 31) + fade_d, b = (c >> 10 & 31) + fade_d;
    return clamp(r, 0, 31) | clamp(g, 0, 31) << 5 | clamp(b, 0, 31) << 10;
}

static void palette_show(void)
{
    u16 buf[256] __attribute__((aligned(4)));
    for (int i = 0; i < 256; i++)
        buf[i] = faded(pal_cache[i]);
    copy32((void *)PAL_BG, buf, 512);
}

/* put ours back whenever Payback wrote its own (without a fade: then it is at full brightness) */
static void palette_keep(void)
{
    if (PAL_BG[3] != faded(pal_cache[3]) || PAL_BG[COLOR(M_GRASS, 2, 0)] != faded(pal_cache[COLOR(M_GRASS, 2, 0)]) ||
        PAL_BG[COLOR(M_BRICK, 1, 1)] != faded(pal_cache[COLOR(M_BRICK, 1, 1)])) {
        fade_d = 0;
        palette_commit();
        palette_show();
    } else if (palette_commit()) {
        palette_show();
    }
}

/* Payback calls this in place of its palette fade (the build redirects every call): its
   fade works from its own colours in ROM, so ours are faded the same way after it. */
void sf_fade(int level)
{
    PB_FADE(level);
    if (STATE[0] != MAGIC || __keep_canary[0] != CANARY)
        return;
    fade_d = (level - 256) >> 3;
    palette_show();
}

/* ---- the frame ---- */

/* who moves the player this frame: Payback, our car or the Arwing */
static void choose_mode(u8 *me)
{
    if (!me)
        return;
    if (mode == FLY) {
        if (is_vehicle(me))
            mode = FOOT, parked = 1;                   /* a mission put the player somewhere */
        else if (call_req)
            land(me);
    } else if (is_car(me)) {
        if (mode != DRIVE || car_ent != me)
            car_take(me);
        if (call_req)
            want_ship = 60;                            /* out of the car, then the Arwing comes */
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
            board(me);
        want_ship = 0;
    }
    call_req = 0;
}

static void step(u8 *me, int ticks)
{
    for (int t = 0; t < ticks; t++) {
        if (mode == DRIVE) {
            car_update(&car, keys & ~KEY_L);          /* L is Payback's: get out */
            car_fence();
            car_bump();
            car_stunts();
        } else if (mode == FLY) {
            ship_update(&ship, keys);
            ship_events();
        }
        space_tick();
    }
    if (mode == DRIVE)
        entity_put(car_ent, vshr(car.b.pos, FX), heading_of(&car.b.m), car.b.vel);
    else if (mode == FLY && me)
        entity_put(me, vshr(ship.b.pos, FX), heading_of(&ship.b.m), v3(0, 0, 0));
}

/* Called by Payback in place of its world renderer, with that renderer's arguments (the last
   one is the split-screen view). */
void sf_frame(int a0, int a1, int a2, int a3, int s0, int s1, int s2, int view)
{
    if (view != 0 || !in_freedom_city()) {
        STATE[0] = 0;                                  /* Payback's renderer reuses our memory */
        hot_restore();
        PB_DRAW_WORLD(a0, a1, a2, a3, s0, s1, s2, view);
        return;
    }
    hot_install();
    if (STATE[0] != MAGIC || __keep_canary[0] != CANARY)
        start();
    frame_calls = key_calls;
    prev_keys = keys;
    keys = ~REG_KEYINPUT & 0x3ff;
    u32 now = pb_clock();
    tick_acc += (now - last_clock) * 60;
    last_clock = now;
    int ticks = tick_acc >> 14;
    tick_acc &= 0x3fff;
    if (ticks > 8) ticks = 8;
    if (fade_d)
        ticks = 0;                                     /* Payback's pause menu is up */
    frame_count += ticks;

    u8 *me = controlled();
    choose_mode(me);
    step(me, ticks);
    if (!(told & 4) && frame_count > 240) {
        told |= 4;
        say("Hold SELECT to call your Arwing.");
    }
    camera_update(me);

    s32 alt = cam.pos.y;
    r_begin();
    sky_draw(alt);
    world_draw();
    space_draw();
    draw_entities(me);
    if (mode == DRIVE)
        draw_car();
    if (mode == FLY || parked)
        draw_ship();
    r_flush_bg();
    stars_draw(alt);
    r_flush_fg();
    palette_keep();
    hot_restore();
    news_send();
}
