/* Stunt Fox: drive the stunt arena, take the Arwing parked beside you, fly over Payback's
   city and keep climbing into space. */
#include "gba.h"
#include "fx.h"
#include "render.h"
#include "world.h"
#include "palette.h"
#include "physics.h"
#include "car.h"
#include "ship.h"
#include "model.h"
#include "hud.h"
#include "space.h"

u32 frame_count;
u32 prof[8];
int game_fps;

enum { V_CAR, V_SHIP };

static Car car;
static Ship ship;
static int vehicle, car_settle;
static u16 keys, prev;

static const V3 car_spawn = {43 * 1024, 140, 37376};
static const V3 ship_spawn = {46 * 1024, 0, 38 * 1024 + 512};

/* ---- messages and score ---- */

static char msg[20], hint[32];
static int msg_t, msg_pal, hint_t;
static int score;

static void copy(char *d, const char *s, int n)
{
    while (*s && --n > 0)
        *d++ = *s++;
    *d = 0;
}

static void say(const char *s, int pal, int t)
{
    copy(msg, s, sizeof msg);
    msg_pal = pal;
    msg_t = t;
}

static void tip(const char *s, int t)
{
    copy(hint, s, sizeof hint);
    hint_t = t;
}

/* ---- sound: an engine note on square channel 2, bursts of noise on channel 4 ---- */

#define REG_SND(o) (*(volatile u16 *)(0x04000060 + (o)))

static void sound_init(void)
{
    REG_SOUNDCNT_X = 0x80;
    REG_SND(0x20) = 0xaa77;                 /* SOUNDCNT_L: channels 2 and 4, both sides */
    REG_SND(0x22) = 0x0002;                 /* SOUNDCNT_H: full PSG volume */
    REG_SND(0x08) = 0x0080 | (7 << 12);     /* channel 2: 50% duty, volume 7 */
    REG_SND(0x0c) = 0x8000 | 1000;
}

static void engine_note(int hz)
{
    if (hz < 64) hz = 64;
    REG_SND(0x0c) = 2048 - 131072 / hz;
}

static void noise(int vol, int len)
{
    REG_SND(0x18) = (vol << 12) | (len << 8) | 0x0000 | 0x00;   /* envelope: fade out */
    REG_SND(0x1c) = 0x8000 | 0x0052;
}

/* ---- camera ---- */

static V3 cam_off, cam_up = {0, ONE, 0};

static void camera_follow(V3 pos, const M3 *m, V3 vel, int grounded, int is_ship)
{
    V3 fwd = m->f, up = m->u;
    if (!is_ship && !grounded) {
        /* airborne car: look along the flight path, keep the horizon level */
        if (vlen(vel) > 4000)
            fwd = vnorm(v3(vel.x, vel.y >> 1, vel.z));
        up = v3(0, ONE, 0);
    }
    if (is_ship && pos.y < SPACE_HI)
        up = vnorm(vadd(up, v3(0, ONE, 0)));     /* half the bank, like Star Fox */
    s32 dist = is_ship ? 950 : 820, height = is_ship ? 250 : 300;
    if (!is_ship && car.on_loop)
        dist = 600, height = 340;                /* stay inside the loop's curve */
    V3 want = vadd(vscale(fwd, -dist), vscale(up, height));
    cam_off = vadd(cam_off, vshr(vsub(want, cam_off), 2));
    cam_up = vnorm(vadd(cam_up, vshr(vsub(up, cam_up), 2)));
    cam.pos = vadd(pos, cam_off);
    s32 g = world_ground(cam.pos.x, cam.pos.z) + 60;
    if (cam.pos.y < g)
        cam.pos.y = g;
    V3 target = vadd(pos, vadd(vscale(up, !is_ship && car.on_loop ? 30 : 110), vscale(fwd, 250)));
    cam.m.f = vsub(target, cam.pos);
    cam.m.u = cam_up;
    morth(&cam.m);
}

/* ---- stunts ---- */

static int air_ticks, loop_top, upside_ticks, was_flying, in_space, at_station;
static s32 spin_pitch, spin_roll, spin_yaw;

static s32 iabs(s32 v) { return v < 0 ? -v : v; }

static void award(const char *what, int pts, int pal)
{
    char b[20], *p = b;
    copy(b, what, sizeof b);
    say(b, pal, 90);
    score += pts;
    p = hud_num(hint, pts);
    (void)p;
    char t[32] = "+";
    copy(t + 1, hint, sizeof t - 1);
    tip(t, 90);
}

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
            s32 turn = 1544000;                    /* 0.9 of a turn, 1.18 radians */
            if (iabs(spin_pitch) > turn)
                award(spin_pitch > 0 ? "FRONT FLIP!" : "BACK FLIP!", 1500, HUD_YELLOW);
            else if (iabs(spin_roll) > turn)
                award("BARREL ROLL!", 1500, HUD_YELLOW);
            else if (iabs(spin_yaw) > turn)
                award("360 SPIN!", 1000, HUD_YELLOW);
            else if (air_ticks > 100)
                award("HUGE AIR!", 800, HUD_CYAN);
            else
                award("BIG AIR!", 300, HUD_CYAN);
        }
        air_ticks = 0;
        spin_pitch = spin_roll = spin_yaw = 0;
    }
    if (car.on_loop >= 2 && car.loop_ang > 26000 && car.loop_ang < 39000)
        loop_top = 1;
    if (loop_top && !car.on_loop && car.wheels >= 3) {
        loop_top = 0;
        if (b->m.u.y > 12000)
            award("LOOP!", 1000, HUD_GREEN);
    }
    /* stuck on the roof or side: put it back on its wheels */
    if (b->m.u.y < 4000 && vlen(b->vel) < 1000)
        upside_ticks++;
    else
        upside_ticks = 0;
    if (upside_ticks > 100) {
        upside_ticks = 0;
        s32 h = fatan2(b->m.f.x, b->m.f.z);
        myaw(&b->m, h);
        b->w = v3(0, 0, 0);
        b->vel = v3(0, 0, 0);
        b->pos.y += 160 << FX;
        tip("BACK ON YOUR WHEELS", 60);
    }
    if (car.impact > 2500) {
        noise(12, 3);
        if (car.impact > 5000)
            say("CRASH!", HUD_RED, 40);
    }
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
            award("DOCKED AT STATION!", 5000, HUD_GREEN);
        else if (ground_fine(b->pos.x, b->pos.z) > (300 << FX))
            award("ROOFTOP LANDING!", 2000, HUD_GREEN);
        else
            award("NICE LANDING", 500, HUD_CYAN);
    }
    if (alt > SPACE_HI && !in_space) {
        in_space = 1;
        say("SPACE!", HUD_CYAN, 120);
        tip("THE STATION IS NEAR", 150);
    }
    if (alt < SPACE_LO)
        in_space = 0;
    V3 d = vsub(v3(b->pos.x >> FX, alt, b->pos.z >> FX), station_pos);
    int near = iabs(d.x) < 9000 && iabs(d.y) < 5000 && iabs(d.z) < 9000;
    if (near && !at_station)
        tip("LAND ON THE YELLOW PAD", 150);
    at_station = near;
    if (ship.impact > 3000) {
        noise(12, 3);
        if (ship.impact > 6000)
            say("OUCH!", HUD_RED, 40);
    }
    /* double-tap L or R: barrel roll */
    static int lt, rt;
    u16 hit = keys & ~prev;
    if (!ship.gear) {
        if (hit & KEY_L) { if (lt) { ship.rolling = 24; ship.roll_dir = 70000; say("BARREL ROLL!", HUD_YELLOW, 40); } lt = 15; }
        if (hit & KEY_R) { if (rt) { ship.rolling = 24; ship.roll_dir = -70000; say("BARREL ROLL!", HUD_YELLOW, 40); } rt = 15; }
    }
    if (lt) lt--;
    if (rt) rt--;
}

/* ---- switching vehicles ---- */

static void to_ship(void)
{
    V3 d = vsub(ship.b.pos, car.b.pos);
    if (iabs(d.x >> FX) > 8000 || iabs(d.z >> FX) > 8000 || iabs(d.y >> FX) > 3000) {
        /* call the Arwing in: it lands right next to you */
        s32 h = fatan2(car.b.m.f.x, car.b.m.f.z);
        V3 p = vadd(v3(car.b.pos.x >> FX, 0, car.b.pos.z >> FX), vscale(car.b.m.r, -700));
        ship_reset(&ship, v3(p.x, ground_fine(p.x << FX, p.z << FX) >> FX, p.z), h);
        if (car.wheels == 0) {
            ship.b.pos = car.b.pos;
            ship.b.vel = car.b.vel;
        }
        tip("ARWING CALLED IN", 60);
    }
    vehicle = V_SHIP;
    car_settle = car.wheels ? 0 : 240;
    was_flying = 0;
    say("ARWING", HUD_CYAN, 50);
    tip("A THRUST  DOWN: PULL UP", 150);
}

static void to_car(void)
{
    V3 d = vsub(car.b.pos, ship.b.pos);
    s32 h = fatan2(ship.b.m.f.x, ship.b.m.f.z);
    if (!ship.gear) {
        /* jump out of the Arwing: the car drops from the sky */
        car.b.pos = vsub(ship.b.pos, v3(0, 300 << FX, 0));
        car.b.vel = ship.b.vel;
        car.b.w = v3(0, 0, 0);
        myaw(&car.b.m, h);
        say("BOMBS AWAY!", HUD_YELLOW, 60);
    } else if (iabs(d.x >> FX) > 3000 || iabs(d.z >> FX) > 3000 || iabs(d.y >> FX) > 3000) {
        V3 p = vadd(v3(ship.b.pos.x >> FX, 0, ship.b.pos.z >> FX), vscale(ship.b.m.r, 700));
        car_reset(&car, v3(p.x, (ground_fine(p.x << FX, p.z << FX) >> FX) + 140, p.z), h);
    }
    vehicle = V_CAR;
    car_settle = 0;
    say("CAR", HUD_CYAN, 50);
}

static void respawn(void)
{
    if (vehicle == V_CAR) {
        int b = car.boost;
        car_reset(&car, car_spawn, 16384);
        car.boost = b;
    } else {
        ship_reset(&ship, ship_spawn, 16384);
    }
    cam_off = v3(0, 400, -800);
    say("READY", HUD_WHITE, 40);
}

/* ---- drawing the vehicles ---- */

static void draw_car(void)
{
    Place pl;
    V3 p = vshr(car.b.pos, FX);
    if (!model_place(&pl, p, &car.b.m, 256, 0, mdl_car.radius))
        return;
    model_draw(&mdl_car, &pl);
    for (int i = 0; i < 4; i++) {
        /* wheels ride on the suspension */
        s32 y = car_wheel[i].y - (CAR_SUSP - (car.comp[i] >> FX)) + CAR_WHEEL_R;
        s32 x = car_wheel[i].x < 0 ? -131 : 131, z = car_wheel[i].z, r = CAR_WHEEL_R;
        MVert w[6] = {{x, y + r, z}, {x, y + r / 2, z + r}, {x, y - r / 2, z + r},
                      {x, y - r, z}, {x, y - r / 2, z - r}, {x, y + r / 2, z - r}};
        model_poly(&pl, w, 6, COLOR(M_ROAD, 0, pl.fog));
    }
    if (car.boosting && (frame_count & 2)) {
        MVert fl[3] = {{-50, -10, -232}, {50, -10, -232}, {0, 0, -420 - (int)(frame_count & 4) * 20}};
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
    if (vehicle == V_SHIP && !ship.gear) {
        int len = ship.boosting ? 380 : 200;
        MVert fl[3] = {{-30, 6, -90}, {30, 6, -90}, {0, 26, -90 - len - (int)(frame_count & 2) * 30}};
        model_poly(&pl, fl, 3, COLOR(M_GLOW, 3, 0));
    }
}

/* ---- HUD ---- */

static void draw_hud(int fps)
{
    char b[32], *p;
    hud_begin();
    Body *body = vehicle == V_CAR ? &car.b : &ship.b;
    s32 v = vehicle == V_CAR ? iabs(car.speed) : vlen(body->vel);
    p = hud_num(b, (v * 27) >> 12);                 /* fine/tick -> km/h */
    copy(p, " KM/H", 8);
    hud_text(8, 148, b, HUD_WHITE);
    hud_text(8, 4, vehicle == V_CAR ? "CAR" : "ARWING", HUD_CYAN);
    (void)fps;
    if (vehicle == V_CAR) {
        p = b;
        copy(p, "BOOST ", 8);
        p = hud_num(p + 6, car.boost * 100 / 4096);
        copy(p, "%", 2);
        hud_text(152, 148, b, car.boost > 600 ? HUD_YELLOW : HUD_RED);
    } else {
        copy(b, "ALT ", 6);
        p = hud_num(b + 4, (body->pos.y >> FX) / 128);
        copy(p, "M", 2);
        hud_text(160, 148, b, HUD_WHITE);
    }
    p = hud_num(b, score);
    hud_text(232 - 8 * (int)(p - b), 4, b, HUD_YELLOW);
    if (msg_t > 0) {
        int n = 0;
        while (msg[n]) n++;
        hud_big(120 - n * 7, 48, msg, msg_pal);
    }
    if (hint_t > 0) {
        int n = 0;
        while (hint[n]) n++;
        hud_text(120 - n * 4, 72, hint, HUD_WHITE);
    }
    if (keys & KEY_SELECT && keys & KEY_START) {
        p = hud_num(b, fps);
        copy(p, " FPS", 5);
        hud_text(8, 16, b, HUD_GREEN);
    }
    hud_end();
}

int main(void)
{
    REG_WAITCNT = 0x4317;
    REG_IE = 1;
    REG_DISPSTAT = 8;
    REG_IME = 1;
    cycles_init();
    r_init();
    world_init();
    models_init();
    space_init();
    hud_init();
    sound_init();
    car_reset(&car, car_spawn, 16384);
    ship_reset(&ship, ship_spawn, 16384);
    cam_off = v3(0, 400, -800);
    say("STUNT FOX", HUD_YELLOW, 150);
    tip("ARWING PARKED AHEAD, LEFT", 240);

    u32 last = frame_count, fps_t = frame_count;
    int frames = 0, fps = 0, intro = 0;
    for (;;) {
        prev = keys;
        keys = ~REG_KEYINPUT & 0x3ff;
        u16 hit = keys & ~prev;
        if (hit & KEY_SELECT && !(keys & KEY_START)) {
            if (vehicle == V_CAR) to_ship();
            else to_car();
        }
        if (hit & KEY_START && !(keys & KEY_SELECT))
            respawn();

        int ticks = frame_count - last;
        last = frame_count;
        if (ticks > 4) ticks = 4;
        u32 tp = cycles();
        for (int t = 0; t < ticks; t++) {
            if (vehicle == V_CAR) {
                car_update(&car, keys);
                car_stunts();
            } else {
                ship_update(&ship, keys);
                ship_events();
                if (car_settle) {
                    car_settle--;
                    car_update(&car, 0);
                }
            }
            space_tick();
            if (msg_t) msg_t--;
            if (hint_t) hint_t--;
        }
        prof[5] += cycles() - tp;
        prof[6] += ticks;
        if (++intro == 200 && vehicle == V_CAR)
            tip("SELECT: FLY THE ARWING", 240);

        Body *b = vehicle == V_CAR ? &car.b : &ship.b;
        V3 pos = vshr(b->pos, FX);
        camera_follow(pos, &b->m, b->vel, vehicle == V_CAR ? car.wheels > 0 : ship.gear > 0, vehicle == V_SHIP);
        if (vehicle == V_CAR)
            engine_note(70 + ((iabs(car.speed) >> FX) * 3 >> 1) + (car.boosting ? 40 : 0));
        else
            engine_note(110 + (vlen(ship.b.vel) >> FX) + (ship.boosting ? 60 : 0));
        if (vehicle == V_CAR && car.boosting && !(frame_count & 7))
            noise(5, 1);

        s32 alt = cam.pos.y;
        u32 t0 = cycles();
        r_begin();
        sky_draw(alt);
        world_draw();
        u32 t1 = cycles();
        space_draw();
        draw_car();
        draw_ship();
        u32 t2 = cycles();
        r_flush_bg();
        stars_draw(alt);
        r_flush_fg();
        u32 t3 = cycles();
        prof[0] += t1 - t0; prof[1] += t2 - t1; prof[2] += t3 - t2; prof[3]++; prof[4] += r_polys;
        draw_hud(fps);
        r_flip();
        hud_commit();
        palette_commit();
        frames++;
        if (frame_count - fps_t >= 60) {
            fps = game_fps = frames;
            frames = 0;
            fps_t = frame_count;
        }
    }
}
