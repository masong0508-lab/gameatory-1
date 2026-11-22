/* Real campaign.c, synthetic chapter/Payback/graphics interfaces. The fixture
 * has a two-part story city, a final city, and a reserved future chapter.
 * The save codec is real, over an in-memory block device; no game data or
 * physical save device is needed. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../../src/campaign.c"

PbMock pbm;
S2Frame s2f;
u8 cpm_rampage, cpm_was_rampage;
s16 cpm_sub, cpm_map, cpm_trophies[6];
static int docks, rooms, armed, paid, checks, has_station = 1, text_count;
static int device_mode;
static u8 native_eeprom[8192];
static SgProgress ship_progress;
static char drawn[24][64];
static const Chapter chapters[] = {
    {.map = 0, .flags = CH_STORY, .nact = 2, .split = 1, .mis0 = 0, .nmis = 2, .next = 1},
    {.map = 10, .flags = CH_FINAL, .nact = 2, .split = 2, .mis0 = 2, .nmis = 2, .next = 0xffff},
    {.map = 11, .flags = CH_RESERVED, .next = 0xffff},
};
static const MisDef missions[] = {
    {.kind = MK_ACT, .act = 1}, {.kind = MK_ACT, .act = 2},
    {.kind = MK_ACT, .act = 1}, {.kind = MK_ACT, .act = 2, .pay = 1000},
};
int ms_nchap(void) { return 3; }
const Chapter *ms_chap(int c) { return c >= 0 && c < 3 ? &chapters[c] : 0; }
const MisDef *ms_def(int m) { return m >= 0 && m < 4 ? &missions[m] : 0; }
const char *ms_text(int id) { (void)id; return "CITY"; }
void ms_arm(int m) { armed = m; }
void sg_get_progress(void *p) { memcpy(p, &ship_progress, sizeof ship_progress); }
void sg_set_progress(const void *p) { memcpy(&ship_progress, p, sizeof ship_progress); }
void sg_give(int n) { paid += n; ship_progress.credits += n; }
int sg_credits(void) { return ship_progress.credits; }
void sg_unlock_paint(int n) { ship_progress.paints |= 1 << n; }
void s2_progress_keep(void) {}
void s2_dock_start(void) { docks++; s2f.mode = FLY; s2f.docked = 1; }
int st_enter(void) { if (has_station) rooms++; return has_station; }
int st_active(void) { return rooms != 0; }
void st_chal_done(int c, int o) {}
void pl_drop_begin(int map, int x, int y) {}
void pl_drop_end(void) {}
void hl_clear(void) {}
void hl_card(const char *text, int ticks) {}
void hl_text(const char *text) {}
void hl_stat(int kind, int a, int b) {}
int sv_mode(void) { return device_mode; }
int sv_prove(void) { return 0; }
static int device_read(int blk, u8 *data)
{
    if (blk < 0 || blk >= (int)sizeof native_eeprom / SV_BLK) return -1;
    memcpy(data, native_eeprom + blk * SV_BLK, SV_BLK); return 0;
}
static int device_write(int blk, const u8 *data)
{
    if (blk < 0 || blk >= (int)sizeof native_eeprom / SV_BLK) return -1;
    memcpy(native_eeprom + blk * SV_BLK, data, SV_BLK); return 0;
}
const SvDev sv_eeprom = {device_read, device_write};

void d_text(int x, int y, const char *text, int color)
{
    if (x < 0 || y < 0 || x + (int)strlen(text) * TEXT_W > 240 || y + 8 > 160) {
        fprintf(stderr, "text outside screen: %s\n", text);
        exit(1);
    }
    if (text_count < 24)
        snprintf(drawn[text_count++], 64, "%s", text);
}
void d_fill(int x, int y, int w, int h, int color) {}
void d_rect(int x, int y, int w, int h, int color) {}
void d_hline(int x0, int x1, int y, int color) {}
char *d_num(char *p, int n) { return p + sprintf(p, "%d", n); }
char *d_cat(char *p, const char *s) { while (*s) *p++ = *s++; *p = 0; return p; }

#define CHECK(expr) do { checks++; if (!(expr)) { fprintf(stderr, "line %d: %s\n", __LINE__, #expr); return 1; } } while (0)
static int seen(const char *text)
{
    for (int i = 0; i < text_count; i++) if (!strcmp(text, drawn[i])) return 1;
    return 0;
}
static void fixture(int final_city)
{
    memset(&C, 0, sizeof C); C.chap = C.tgt = -1;
    memset(&sw, 0, sizeof sw); memset(&spick, 0, sizeof spick);
    memset(&cp_prog, 0, sizeof cp_prog); memset(&pbm, 0, sizeof pbm);
    memset(&s2f, 0, sizeof s2f); memset(&ship_progress, 0, sizeof ship_progress);
    memset(cpm_trophies, 0, sizeof cpm_trophies);
    docks = rooms = paid = 0; armed = -1; has_station = 1;
    device_mode = SV_4K;
    cp_prog.flags = CPF_ON; cp_prog.chap_unlocked = final_city ? 1 : 0;
    cp_prog.acts[0] = final_city ? 3 : 0; cp_prog.acts[1] = final_city ? 1 : 0;
    cp_prog.medals[0] = 0x41; cp_prog.spare[CP_SPARE_EVA] = 5;
    ship_progress.credits = 1234; ship_progress.engine = 2;
    cpm_rampage = final_city; cpm_sub = 0; cpm_map = final_city ? 10 : 0;
    s2f.map = cpm_map; s2f.mode = FLY;
    pbm.ngoals = 1; pbm.goals[PBG_A] = 5000; pbm.mult = 1;
    cp_level_enter(s2f.map); cp_tick();
}
static void age(void) { s2f.ticks += 60; pbm.clock += 30; cp_tick(); }
static void card(void) { text_count = 0; cp_hud(); }

static int store_native(const Prog *p)
{
    SvW writer;
    SvPick empty = {0};
    memset(native_eeprom, 0xff, sizeof native_eeprom);
    sv_begin(&writer, (const u8 *)p, sizeof *p, &empty);
    while (writer.busy)
        if (sv_step(&sv_eeprom, &writer, (const u8 *)p, sizeof *p) < 0) return 0;
    return 1;
}

static void cold_load(void)
{
    memset(&C, 0, sizeof C); C.chap = C.tgt = -1;
    memset(&sw, 0, sizeof sw); memset(&spick, 0, sizeof spick);
    memset(&cp_prog, 0, sizeof cp_prog); memset(&ship_progress, 0, sizeof ship_progress);
    memset(&s2f, 0, sizeof s2f); memset(&pbm, 0, sizeof pbm);
    ship_progress.credits = 300; ship_progress.missiles = 4;
    cpm_rampage = cpm_sub = cpm_map = rooms = 0;
    s2f.mode = FLY; s2f.docked = 1;
    pbm.ngoals = 1; pbm.goals[PBG_A] = 5000; pbm.mult = 1;
    device_mode = SV_64K;
    cp_level_enter(0); cp_tick();
}

int main(void)
{
    fixture(1);
    CHECK(armed == 3 && cp_ending() == CP_END_NONE);
    cp_set(CP_FLAG_FINALE, 1);          /* the final mission's SET, before FINISH */
    CHECK(cp_ace() && !cp_postgame() && !cp_ending());
    cp_ev(EV_MIS_DONE, 3, 20);
    CHECK(cp_prog.acts[1] == 3 && cp_postgame() && cp_ending() == CP_END_RETURN);
    CHECK(cp_prog.chap_unlocked == 1 && paid == 0 && ship_progress.credits == 1234);
    CHECK(cp_prog.medals[0] == 0x41 && cp_prog.spare[CP_SPARE_EVA] == 5 && ship_progress.engine == 2);
    CHECK(!cp_travel(0) && !cp_travel(2));
    s2f.paused = 1; age(); CHECK(!docks && cp_ending() == CP_END_RETURN);
    s2f.paused = 0; pbm.respawn = 1; age(); CHECK(!docks);
    pbm.respawn = 0; s2f.mode = FOOT; age(); CHECK(!docks);
    s2f.mode = FLY; s2f.walk = 2; age(); CHECK(!docks);
    s2f.walk = 0; age(); CHECK(docks == 1 && cp_ending() == CP_END_COMPLETE);
    CHECK(pbm.level_end == 0 && pbm.goals[PBG_A] == HOLD_A);
    card(); CHECK(seen("CAMPAIGN COMPLETE"));
    u32 signature = cp_sig();
    cp_dock_keys(KEY_A, KEY_A, 1); CHECK(cp_ending() == CP_END_COMPLETE);
    age(); cp_dock_keys(0, KEY_A, 1); CHECK(cp_ending() == CP_END_COMPLETE);
    cp_dock_keys(KEY_A, KEY_A, 1); CHECK(cp_ending() == CP_END_ACE && cp_sig() != signature);
    card(); CHECK(seen("ACE MODE UNLOCKED"));
    cp_dock_keys(KEY_A, KEY_A, 1); CHECK(cp_ending() == CP_END_ACE);
    age(); cp_dock_keys(KEY_B, KEY_B, 1); CHECK(cp_ending() == CP_END_COMPLETE);
    age(); s2f.paused = 1; cp_dock_keys(KEY_A, KEY_A, 1); CHECK(cp_ending() == CP_END_COMPLETE);
    s2f.paused = 0; cp_dock_keys(KEY_A, KEY_A, 1); CHECK(cp_ending() == CP_END_ACE);
    age(); cp_dock_keys(KEY_A, KEY_A, 1); CHECK(cp_ending() == CP_END_STATION);
    card(); CHECK(seen("WELCOME HOME, FOX") && seen("TRY SPACE WALKS ON THE NAV BOARD."));
    age(); CHECK(cp_dock_keys(KEY_A, KEY_A, 1) == 1 && rooms == 1 && !cp_ending());
    for (int i = 0; i < 20; i++) age();
    CHECK(docks == 1 && !pbm.level_end && cp_postgame());
    cp_ev(EV_MIS_DONE, 3, 20); age();
    CHECK(!cp_ending() && docks == 1 && !pbm.level_end && paid == 0);
    CHECK(cp_travel(0) == 1); age(); CHECK(pbm.level_end == 3 && cp_menu(0) == 0);

    /* A completed story city must allow immediate departure, rather than
       waiting forever for the held score goal to finish. Reload is quiet. */
    pbm.level_end = 0; cpm_rampage = 0; cpm_sub = 0; s2f.map = 0;
    cp_level_enter(0); cp_tick();
    CHECK(cp_postgame() && !cp_ending() && cp_prog.acts[0] == 3);
    CHECK(cp_travel(1) == 1); age(); CHECK(pbm.level_end == 3 && cp_menu(0) == 20);
    pbm.level_end = 0; cpm_rampage = 1; s2f.map = 10;
    cp_level_enter(10); cp_tick();
    CHECK(cp_postgame() && !cp_ending());
    CHECK(cp_prog.spare[CP_SPARE_EVA] == 5 && cp_prog.medals[0] == 0x41);
    cp_dbg(16, 4); CHECK(!cp_active() && !cp_postgame() && !cp_ending());
    CHECK(pbm.goals[PBG_A] != HOLD_A && cp_flag(CP_FLAG_FINALE));

    /* Ordinary chapter and story-sublevel completion retain their old path. */
    fixture(0); cp_ev(EV_MIS_DONE, 0, 10); age(); age();
    CHECK(!cp_ending() && !cp_postgame() && cp_prog.chap_unlocked == 0);
    pbm.level_end = 3; CHECK(cp_menu(0) == 1);
    pbm.level_end = 0; cpm_sub = 1; cp_level_enter(0);
    cp_ev(EV_MIS_DONE, 1, 10);
    CHECK(cp_prog.chap_unlocked == 1 && !cp_ending() && !cp_ace());

    /* No station package/data: dismissing the ending leaves the working hangar. */
    fixture(1); cp_ev(EV_MIS_DONE, 3, 10); age(); has_station = 0;
    for (int i = 0; i < 3; i++) { age(); cp_dock_keys(KEY_A, KEY_A, 1); }
    CHECK(!cp_ending() && !rooms && s2f.docked && cp_postgame());
    cp_dbg(16, 2); CHECK(cp_active() && !cp_ace() && !cp_postgame() && !cp_ending());
    CHECK(cp_prog.acts[1] == 0 && ship_progress.credits == 1234);

    /* A stopped native campaign must keep its equipment across a cold boot.
       Free play stays separate until CONTINUE explicitly restores that image. */
    fixture(0); cp_prog.acts[0] = 1;
    ship_progress.rack = 1; ship_progress.missiles = 6; ship_progress.paint = 1;
    ship_progress.spare[0] = 'S'; ship_progress.spare[1] = 1;
    for (int i = 2; i < 16; i++) ship_progress.spare[i] = 0x40 + i;
    cp_dbg(16, 4);
    Prog stopped = cp_prog;
    SgProgress equipment = ship_progress;
    CHECK(!(stopped.flags & CPF_ON) && prog_ok(&stopped) && store_native(&stopped));
    cold_load();
    CHECK(!cp_active() && prog_ok(&cp_prog) && C.resume_sg);
    CHECK(ship_progress.credits == 300 && !ship_progress.rack && ship_progress.missiles == 4);
    CHECK(cp_prog.acts[0] == 1 && cp_prog.spare[CP_SPARE_EVA] == 5);
    cp_open(); cp_dock_keys(KEY_A, KEY_A, 1);
    CHECK(cp_active() && !C.resume_sg && !memcmp(&ship_progress, &equipment, sizeof equipment));
    CHECK(!memcmp(cp_prog.sg, &equipment, sizeof equipment) && prog_ok(&cp_prog));
    CHECK(cp_prog.acts[0] == 1 && cp_prog.medals[0] == 0x41 && cp_prog.spare[CP_SPARE_EVA] == 5);

    /* A stop and continue in the same running game retains purchases made in
       free play; it must not reapply an older stopped inventory. */
    cp_dbg(16, 4); sg_give(77); ship_progress.shield = 2;
    equipment = ship_progress;
    cp_open(); cp_dock_keys(KEY_A, KEY_A, 1);
    CHECK(cp_active() && !memcmp(&ship_progress, &equipment, sizeof equipment));
    CHECK(!C.resume_sg && !memcmp(cp_prog.sg, &equipment, sizeof equipment));

    /* START OVER is still a new campaign with current live ownership. An
       active native image, in contrast, restores immediately on loading. */
    CHECK(store_native(&stopped)); cold_load();
    cp_dbg(16, 2);
    CHECK(cp_active() && !C.resume_sg && cp_prog.acts[0] == 0);
    CHECK(ship_progress.credits == 300 && !ship_progress.rack && ship_progress.missiles == 4);
    stopped.flags |= CPF_ON; prog_seal(&stopped);
    CHECK(store_native(&stopped)); cold_load();
    CHECK(cp_active() && !C.resume_sg && cp_prog.acts[0] == 1);
    CHECK(!memcmp(&ship_progress, stopped.sg, sizeof ship_progress));
    printf("%d campaign ending checks passed\n", checks);
    return 0;
}
