/* Stage 2's core (MERGE build): the frame state, the events, the hook dispatch, the debug mailbox, the
   count of Payback's own "Mission complete!" banners, and a weak stub for every other package's entry
   point, so each package builds and runs alone (stage2.h lists them). A strong definition in another
   file wins at link time. With every stub in place the game plays as it did without stage 2. */
#include "stage2.h"
#include "render.h"
#include "physics.h"
#include "world.h"

#define WEAK __attribute__((weak))

S2Frame s2f;
u16 s2_phones;
S2Dbg s2_dbg;
static u8 ev_count[EV_N];          /* (saturating) what the harness reads through the mailbox */
static u16 hook_count[HK_N];
static u8 last_mode, in_room;
static s16 resp_was;

/* ---- the stubs: empty, or the answer that means "no such package" ---- */
WEAK void ms_tick(void) {}
WEAK void ms_ev(int ev, int a, int b) { (void)ev; (void)a; (void)b; }
WEAK void ms_draw3d(void) {}
WEAK void ms_level_enter(int map) { (void)map; }
WEAK int ms_dbg(int cmd, int arg) { (void)cmd; (void)arg; return -1; }
WEAK void hl_draw(void) {}
WEAK int s2_hud_owned(void) { return 0; }
WEAK void cp_tick(void) {}
WEAK void cp_ev(int ev, int a, int b) { (void)ev; (void)a; (void)b; }
WEAK void cp_level_enter(int map) { (void)map; }
WEAK int cp_menu(int arg) { (void)arg; return -1; }
WEAK u32 cp_keys(void) { return 0; }
WEAK int cp_dbg(int cmd, int arg) { (void)cmd; (void)arg; return -1; }
WEAK int cp_act_running(void) { return 0; }
WEAK void cp_hud(void) {}
WEAK int cp_dock_keys(u16 hit, u16 keys, int main_ok) { (void)hit; (void)keys; (void)main_ok; return 0; }
WEAK u32 cp_sig(void) { return 0; }
WEAK void pl_drop_begin(int map, int hx2, int hy2) { (void)map; (void)hx2; (void)hy2; }
WEAK void pl_drop_end(void) {}
WEAK int pl_drop_active(void) { return 0; }
WEAK int st_view(void) { return 0; }
WEAK void st_draw(void) {}
WEAK void st_hud(void) {}
WEAK void st_ev(int ev, int a, int b) { (void)ev; (void)a; (void)b; }
WEAK int st_dbg(int cmd, int arg) { (void)cmd; (void)arg; return -1; }
WEAK int st_active(void) { return 0; }
WEAK int sg_dbg(int cmd, int arg) { (void)cmd; (void)arg; return -1; }
WEAK int sg_job_active(void) { return 0; }
WEAK int sg_foe_spawn(int kind, V3 p, V3 home, int hp, int tag) { (void)kind; (void)p; (void)home; (void)hp; (void)tag; return -1; }
WEAK int sg_foe_alive(int tag) { (void)tag; return 0; }
WEAK void sg_foe_clear(int tag) { (void)tag; }
WEAK void sg_foe_hold(int tag, int on) { (void)tag; (void)on; }
WEAK int sg_boss_spawn(int boss, V3 p, int tag) { (void)boss; (void)p; (void)tag; return -1; }
WEAK int sg_boss_alive(int tag) { (void)tag; return 0; }
WEAK int bigmap_enter(int arg) { (void)arg; return 0; }

/* ---- events ---- */
void s2_ev(int ev, int a, int b)
{
    if (!s2_ready())                   /* (Payback's crate_break calls in too, on maps and in menus that are not ours) */
        return;
    if ((unsigned)ev < EV_N && ev_count[ev] < 255)
        ev_count[ev]++;
    ms_ev(ev, a, b);
    cp_ev(ev, a, b);
    st_ev(ev, a, b);
}

/* ---- the debug mailbox: F's own commands (the packages' are in their files) ---- */
static int core_dbg(int cmd, int arg)
{
    switch (cmd) {
    case DBG_F_EVENTS:
        return (unsigned)arg < EV_N ? ev_count[arg] : -1;
    case DBG_F_HOOK:
        return (unsigned)arg < HK_N ? hook_count[arg] : -1;
    case DBG_F_RAISE:
        s2_ev(arg, 0, 0);
        return 0;
    case DBG_F_PUT: {
        s32 x = (arg >> 7) * CELL + CELL / 2, z = (arg & 127) * CELL + CELL / 2;
        return s2_put_player(v3(x, world_ground(x, z), z), 0, s2f.mode);
    }
    case DBG_F_RESET:
        for (int i = 0; i < EV_N; i++)
            ev_count[i] = 0;
        for (int i = 0; i < HK_N; i++)
            hook_count[i] = 0;
        return 0;
    }
    return -1;
}

/* ---- the hooks ----
   merge.c has put the player's position, speed, heading, mode, docked, paused, airborne, space game
   state, vehicle and record in s2f; the rest is Payback's */
void s2_tick(void)
{
    hook_count[HK_TICK]++;
    s2f.ticks = frame_count;
    s2f.clock = PB_CLOCK;
    s2f.sub = PB_RAMPAGE ? 0 : PB_SUB;
    s2f.story = !PB_RAMPAGE;
    if (s2_dbg.magic == S2_DBG_MAGIC) {
        int c = s2_dbg.cmd, a = s2_dbg.arg;
        s2_dbg.ret = c < 16 ? ms_dbg(c, a) : c < 32 ? cp_dbg(c, a) : c < 48 ? st_dbg(c, a) : c < 64 ? sg_dbg(c, a) : core_dbg(c, a);
        s2_dbg.seq++;
        s2_dbg.magic = 0;
    }
    if (s2f.mode != last_mode) {
        int old = last_mode;
        last_mode = s2f.mode;
        s2_ev(EV_MODE, s2f.mode, old);
    }
    s16 r = PB_RESPAWN;                    /* the countdown starts at a death or an arrest */
    if (r > 0 && resp_was <= 0)
        s2_ev(EV_DEATH, 0, 0);
    resp_was = r;
    ms_tick();
    cp_tick();
}

void s2_draw3d(void)
{
    hook_count[HK_DRAW3D]++;
    ms_draw3d();
}

void s2_hud(void)
{
    hook_count[HK_HUD]++;
    if (in_room)
        st_hud();
    else
        hl_draw();
    cp_hud();
}

void s2_level_enter(int map)
{
    hook_count[HK_LEVEL]++;
    in_room = 0;
    ms_level_enter(map);               /* (the mission engine first: the campaign arms acts through it) */
    cp_level_enter(map);
}

int s2_menu(int arg)
{
    if (!s2_ready())
        return -1;
    hook_count[HK_MENU]++;
    return cp_menu(arg);
}

void s2_keys(void)
{
    hook_count[HK_KEYS]++;
    u32 m = cp_keys() & ((1u << B_N) - 1);              /* (PB_BTN is B_N bytes: a stray high bit would write past it) */
    for (int i = 0; m; i++, m >>= 1)
        if (m & 1)
            PB_BTN[i] = 1;
}

int s2_room_view(void)
{
    int v = st_view();
    in_room = v == 1;
    if (v)
        hook_count[HK_ROOM]++;
    return v;
}

void s2_room_draw(void)
{
    st_draw();
}

/* In place of Payback's banner by number (build: every bl to 0x0807a684 in its code; one argument, the
   line's number): 0x7e6 is "Mission complete!", shown when a phone mission is done (it raises the
   multiplier too). Counted only while our memory is set up: before that, and on a map we do not draw,
   the keep belongs to Payback. Then Payback's own call, with the same argument. */
__attribute__((section(".text.sf_hook_s2_banner")))
void s2_banner_veneer(int idx)
{
    if (s2_ready()) {
        hook_count[HK_BANNER]++;
        if (idx == PB_BANNER_COMPLETE)
            s2_phones++;
    }
    pb_banner_idx(idx);
}
