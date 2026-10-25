/* Strong definitions of stage-2 entry points, for a test build (S2_EXTRA_SRC=tests/s2/override/s2dummy.c): the
   linker must take these in place of s2core.c's weak stubs, and the hooks must run them (tests/s2/override.py).
   Everything counts what it is given; answers are the call's own numbers, so the harness can tell who answered. */
#include "stage2.h"
#include "pbapi.h"
#include "draw2d.h"
#include "render.h"

u32 dummy_ms_tick, dummy_draw3d, dummy_hl, dummy_cp_tick, dummy_keys, dummy_menu, dummy_level_n, dummy_cp_level_n, dummy_level_map;
u32 dummy_ms_ev[EV_N], dummy_cp_ev[EV_N], dummy_st_ev[EV_N];
s32 dummy_ev_a[EV_N], dummy_ev_b[EV_N];     /* the last arguments cp_ev was given, by event */
u32 dummy_keys_mask;                       /* the buttons cp_keys holds (bit i = PB_BTN[i]) */
u32 dummy_menu_set, dummy_menu_val;        /* cp_menu answers dummy_menu_val once dummy_menu_set is 1 */

void ms_tick(void) { dummy_ms_tick++; }
void ms_ev(int ev, int a, int b) { (void)a; (void)b; dummy_ms_ev[ev & 15]++; }
void ms_draw3d(void) { dummy_draw3d++; }
void ms_level_enter(int map) { dummy_level_n++; dummy_level_map = map; }
int ms_dbg(int cmd, int arg) { return 1000 + cmd * 16 + arg; }
void hl_draw(void) { dummy_hl++; }
void cp_tick(void) { dummy_cp_tick++; }
void cp_ev(int ev, int a, int b) { dummy_cp_ev[ev & 15]++; dummy_ev_a[ev & 15] = a; dummy_ev_b[ev & 15] = b; }
void cp_level_enter(int map) { (void)map; dummy_cp_level_n++; }
int cp_menu(int arg) { (void)arg; dummy_menu++; return dummy_menu_set ? (int)dummy_menu_val : -1; }
u32 cp_keys(void) { dummy_keys++; return dummy_keys_mask; }
int cp_dbg(int cmd, int arg) { return 2000 + cmd * 16 + arg; }
void st_ev(int ev, int a, int b) { (void)a; (void)b; dummy_st_ev[ev & 15]++; }
int st_dbg(int cmd, int arg) { return 3000 + cmd * 16 + arg; }
int sg_dbg(int cmd, int arg) { return 4000 + cmd * 16 + arg; }

/* the station's room view: dummy_room_mode is what st_view answers (0 the usual frame, 1 a room, 2 the last picture again) */
u32 dummy_room_mode, dummy_room_draws, dummy_room_huds;
int st_view(void) { return dummy_room_mode; }
void st_draw(void) { dummy_room_draws++; d_fill(0, 0, 10, 10, COLOR(1, 3, 0)); }
void st_hud(void) { dummy_room_huds++; d_text(80, 70, "ROOM TEST", COLOR(3, 3, 0)); }
