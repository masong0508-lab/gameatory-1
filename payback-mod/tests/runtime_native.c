/* Direct behavioral tests for the real runtime C, using mapped GBA addresses.
 * The fixture contains synthetic columns/entities only, never copyrighted ROM data.
 */
#define _GNU_SOURCE
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>

static void test_queue(char *, int);
#define TICK_QUEUE test_queue
#include "../asm/editor.c"

const u32 cols[85] = {
    0x8800000,
    0x880003c,
    0x8800078,
    0x88000b4,
    0x88000f0,
    0x880012c,
    0x8800168,
    0x88001a4,
    0x88001e0,
    0x880021c,
    0x8800258,
    0x8800294,
    0x88002d0,
    0x880030c,
    0x8800348,
    0x8800384,
    0x88003c0,
    0x88003fc,
    0x8800438,
    0x8800474,
    0x88004b0,
    0x88004ec,
    0x8800528,
    0x8800564,
    0x88005a0,
    0x88005dc,
    0x8800618,
    0x8800654,
    0x8800690,
    0x88006cc,
    0x8800708,
    0x8800744,
    0x8800780,
    0x88007bc,
    0x88007f8,
    0x8800834,
    0x8800870,
    0x88008ac,
    0x88008e8,
    0x8800924,
    0x8800960,
    0x880099c,
    0x88009d8,
    0x8800a14,
    0x8800a50,
    0x8800a8c,
    0x8800ac8,
    0x8800b04,
    0x8800b40,
    0x8800b7c,
    0x8800bb8,
    0x8800bf4,
    0x8800c30,
    0x8800c6c,
    0x8800ca8,
    0x8800ce4,
    0x8800d20,
    0x8800d5c,
    0x8800d98,
    0x8800dd4,
    0x8800e10,
    0x8800e4c,
    0x8800e88,
    0x8800ec4,
    0x8800f00,
    0x8800f3c,
    0x8800f78,
    0x8800fb4,
    0x8800ff0,
    0x880102c,
    0x8801068,
    0x88010a4,
    0x88010e0,
    0x880111c,
    0x8801158,
    0x8801194,
    0x88011d0,
    0x880120c,
    0x8801248,
    0x8801284,
    0x88012c0,
    0x88012fc,
    0x8801338,
    0x8801374,
    0x88013b0
};
const u32 *const maps[3] = {
    (const u32 *)0x08a00000, (const u32 *)0x08a10000, (const u32 *)0x08a20000
};
static char message[500];
static int messages;
static u8 *const car = (u8 *)0x02009394;

static void test_queue(char *text, int kind)
{
    assert(kind == 2);
    strcpy(message, text);
    ++messages;
}
static void map_memory(unsigned long address, unsigned long length)
{
    if (mmap((void *)address, length, PROT_READ | PROT_WRITE,
             MAP_PRIVATE | MAP_ANONYMOUS | MAP_FIXED_NOREPLACE, -1, 0) == MAP_FAILED) {
        perror("Cannot map synthetic GBA memory");
        exit(77);
    }
}
static void keys(u16 value) { KEYS = (u16)(~value & 0x3ff); }
static void fill_grid(const u32 *src) { memcpy(GRID, src, 128 * 128 * 4); }
static void setup(void)
{
    memset((void *)0x02000000, 0, 0x40000);
    memset((void *)0x03000000, 0, 0x10000);
    memset((void *)0x04000000, 0, 0x1000);
    for (int k = 0; k < 85; ++k) {
        u16 *p = (u16 *)(uptr)cols[k];
        p[2] = p[3] = 0x100;
    }
    for (int k = 0; k < 16384; ++k) {
        ((u32 *)(uptr)SPACE_MAP)[k] = cols[2];
        ((u32 *)(uptr)CITY_MAP)[k] = cols[0];
        ((u32 *)(uptr)NEO_MAP)[k] = cols[1];
    }
    GRID_PTR = 0x0202c720;
    fill_grid(CITY_MAP);
    ((u32 *)ENTS)[0] = (u32)(uptr)car;
    ENTITY_LAST = 0;
    CONTROLLED = 0;
    *(int *)(car + 4) = 50 * 2048 + 300;
    *(int *)(car + 8) = 50 * 2048 + 700;
    *(s16 *)(car + 0xc) = 19904;
    *(u16 *)(car + 0xe) = 0x7a6b;
    *(u32 *)(car + 0x1c) = CAR_DESC_FIRST;
    keys(0);
    message[0] = 0;
    messages = 0;
    sync_state(car);
}
static void active_loop(int phase, int speed)
{
    LOOP_ON = 1;
    LOOP_D = 1;
    LOOP_X = *(int *)(car + 4);
    LOOP_Y = *(int *)(car + 8);
    LOOP_L = 0;
    LOOP_V = speed * 16;
    LOOP_P = phase;
}
static void entity_bounds(void)
{
    assert(controlled_entity() == car); /* sole entity is index zero, not an empty list */
    ENTITY_LAST = CONTROLLED = 31;
    ((u32 *)ENTS)[31] = (u32)(uptr)car;
    assert(controlled_entity() == car);
    CONTROLLED = 32;
    assert(!controlled_entity());
    CONTROLLED = 0;
    ENTITY_LAST = 32;
    assert(!controlled_entity());
    ENTITY_LAST = -1;
    assert(!controlled_entity());
    ENTITY_LAST = 0;
    ((u32 *)ENTS)[0] = STATE_START - 0x168 + 4;
    assert(!controlled_entity());
    ((u32 *)ENTS)[0] = (u32)(uptr)car + 1;
    assert(!controlled_entity());
}
static void world_and_column_bounds(void)
{
    assert(world_ready());
    GRID_PTR = 0x02030000; /* grid would overlap mod state */
    assert(!world_ready());
    GRID_PTR = 0x0202c721;
    assert(!world_ready());
    assert(top(0) == 0x100);
    assert(top(0x08000001) == 0x100);
    assert(top(0x08fffff0) == 0x100);
    assert(top(STATE_START - 4) == 0x100);
    u16 *ramcol = (u16 *)0x02015000;
    ramcol[2] = 0x120;
    ramcol[3] = 0x160;
    assert(top((u32)(uptr)ramcol) == 0x160);
}
static void cursor_and_map_swap(void)
{
    const int i = 52 * 128 + 50;
    cursor_on(52, 50);
    assert(GRID[i] == CURSOR);
    assert(CUR_I == (u32)i + 1);
    load_map(NEO_MAP);
    assert(CUR_I == 0);
    cursor_off();
    assert(GRID[i] == NEO_MAP[i]);
    CUR_I = 0xffffffff;
    cursor_off();
    assert(CUR_I == 0); /* no unchecked out-of-grid read */
    GRID[i] = 0;
    cursor_on(52, 50);
    assert(GRID[i] == 0); /* corrupt columns do not become apparently valid cursors */
    cursor_off();
    GRID[i] = 0x02015000;
    put(52, 50, cols[5]);
    assert(GRID[i] == 0x02015000); /* preserve game-created dynamic columns */
}
static void reload_state(void)
{
    FREE_ROAM = 1;
    sync_state(car);
    maps_update(car);
    assert(IN_NEO && !IN_SPACE && GRID[0] == NEO_MAP[0]);
    LOOP_ON = 1;
    NITRO_T = 12;
    cursor_on(52, 50);
    fill_grid(CITY_MAP); /* same address, same mode, scratch deliberately NOT cleared */
    sync_state(car);
    assert(!IN_NEO && !IN_SPACE && !LOOP_ON && !NITRO_T && !CUR_I);
    maps_update(car);
    assert(IN_NEO && GRID[0] == NEO_MAP[0]);
    FREE_ROAM = 0;
    fill_grid(CITY_MAP);
    sync_state(car);
    maps_update(car);
    assert(!IN_NEO && !IN_SPACE && GRID[0] == CITY_MAP[0]);
    FREE_ROAM = 1;
    sync_state(car);
    maps_update(car);
    GRID[0] = 0x02015000; /* a dynamic corner must not cause a repeated reset/swap */
    sync_state(car);
    assert(IN_NEO && GRID[0] == 0x02015000);
}
static void landed_arwing_exit(void)
{
    u8 buttons[8] = {0};
    FREE_ROAM = 1;
    *(u32 *)(car + 0x1c) = ARWING_DESC;
    editor(buttons);
    assert(IN_SPACE && IN_NEO && GRID[0] == SPACE_MAP[0]);
    /* Real reproduction: after landing, player occupies the inclusive last index. */
    ENTITY_LAST = CONTROLLED = 4;
    ((u32 *)ENTS)[4] = (u32)(uptr)car;
    *(u32 *)(car + 0x1c) = 0x08355670;
    editor(buttons);
    assert(!IN_SPACE && IN_NEO && GRID[0] == NEO_MAP[0]);
}
static void loop_entry_and_z(void)
{
    for (int d = 0; d < 4; ++d) {
        setup();
        *(s16 *)(car + 0x12) = d * 1440;
        ((s16 *)(car + 0x40))[0] = d == 1 ? 300 : d == 3 ? -300 : 0;
        ((s16 *)(car + 0x40))[1] = d == 0 ? 300 : d == 2 ? -300 : 0;
        int x0 = *(int *)(car + 4), y0 = *(int *)(car + 8);
        GRID[(x0 >> 11) * 128 + (y0 >> 11)] = LOOP_PAD;
        stunts(car, 0);
        assert(LOOP_ON == 1);
        if (d & 1) assert(*(int *)(car + 8) == y0);
        else assert(*(int *)(car + 4) == x0);
        assert(*(u16 *)(car + 0xe) == 0x7a6b);
    }
    setup();
    active_loop(1024, 300);
    stunts(car, 0);
    assert(*(u16 *)(car + 0xe) == 0x7a6b);
    CHEAT_MOON = 1;
    LOOP_ON = 0;
    cheats(car, 0, 0);
    assert(*(u16 *)(car + 0xe) == 0x7a6b);
}
static void build_controls_and_braking(void)
{
    active_loop(0, 300);
    stunts(car, KSEL | KA | KB | KLEFT);
    int speed = LOOP_V, phase = LOOP_P, lane = LOOP_L;
    int x = *(int *)(car + 4), y = *(int *)(car + 8);
    setup();
    active_loop(0, 300);
    stunts(car, 0);
    assert(LOOP_V == speed && LOOP_P == phase && LOOP_L == lane);
    assert(*(int *)(car + 4) == x && *(int *)(car + 8) == y);
    setup();
    active_loop(0, 5);
    stunts(car, KB);
    assert(LOOP_V == 0 && LOOP_P == 0); /* braking cannot generate reverse acceleration */
}
static void continuous_loop_exit(void)
{
    active_loop(FULL - 2, 4);
    stunts(car, 0);
    assert(LOOP_ON == 1 && LOOP_P == FULL - 1);
    int before = *(int *)(car + 4);
    LOOP_V = 4 * 16;
    stunts(car, 0);
    assert(LOOP_ON == 0xff && ROLL == 0);
    int delta = *(int *)(car + 4) - before;
    assert(delta >= 0 && delta <= 32); /* includes the 16-unit sine quantization; formerly snapped over 128 */
    assert(*(s16 *)(car + 0xc) == 19904);
    assert(*(u16 *)(car + 0xe) == 0x7a6b);
    assert(messages == 1 && !strcmp(message, "Loop clear!"));
    stunts(car, 0);
    assert(messages == 1);
}
static void entity_switch_and_invalid_world(void)
{
    active_loop(500, 300);
    NITRO_T = 12;
    ROLL = 500;
    cursor_on(52, 50);
    sync_state((u8 *)0x02009664);
    assert(!LOOP_ON && !NITRO_T && !ROLL && !CUR_I);
    u8 buttons[8];
    memset(buttons, 1, sizeof(buttons));
    GRID_PTR = 0;
    keys(KSEL | KA);
    editor(buttons);
    for (int i = 0; i < 8; ++i) assert(buttons[i] == 1);
}
static void stadium_retry_controls(void)
{
    FREE_ROAM = 1;
    sync_state(car);
    maps_update(car);
    active_loop(1000, 300);
    ROLL = 1000;
    NITRO_T = 12;
    *(s16 *)(car + 0x40) = 189;
    *(s16 *)(car + 0x42) = -40;
    *(s16 *)(car + 0x44) = -20;
    *(s16 *)(car + 0xba) = 189; /* engine reconstructs velocity from this even after XYZ is zeroed */
    PREV = KSEL;
    keys(KSEL | KSTART);
    u8 buttons[8];
    memset(buttons, 1, sizeof(buttons));
    editor(buttons);
    assert(*(int *)(car + 4) == 42 * 2048);
    assert(*(int *)(car + 8) == 37 * 2048 + 1024);
    assert(*(s16 *)(car + 0x12) == 1440);
    assert(*(s16 *)(car + 0xc) == 19904 && *(u16 *)(car + 0xe) == 0x7a6b);
    assert(!LOOP_ON && !NITRO_T && !ROLL && !CUR_I);
    assert(*(s16 *)(car + 0x40) == 0 && *(s16 *)(car + 0x42) == 0 &&
           *(s16 *)(car + 0x44) == 0 && *(s16 *)(car + 0xba) == 0);
    for (int i = 0; i < 8; ++i) assert(!buttons[i]);
    assert(messages == 1 && strstr(message, "Stadium retry."));
    *(int *)(car + 4) = 43 * 2048;
    editor(buttons);
    assert(*(int *)(car + 4) == 43 * 2048 && messages == 1); /* hold is not repeated */
    *(s16 *)(car + 0x40) = -144;
    *(s16 *)(car + 0xba) = -144; /* reverse travel must stop as well */
    PREV = KSEL;
    editor(buttons);
    assert(*(int *)(car + 4) == 42 * 2048 && *(int *)(car + 8) == 37 * 2048 + 1024);
    assert(*(s16 *)(car + 0x40) == 0 && *(s16 *)(car + 0xba) == 0 && messages == 2);
    FREE_ROAM = 0;
    assert(!stadium_retry(car));
    FREE_ROAM = 1;
    IN_SPACE = 1;
    assert(!stadium_retry(car));
    IN_SPACE = 0;
    *(u32 *)(car + 0x1c) = ARWING_DESC;
    assert(!stadium_retry(car));
    *(u32 *)(car + 0x1c) = 0x08355670;
    assert(!stadium_retry(car));
}
static void signed_headings(void)
{
    const int angles[] = {-5760, -4320, -2880, -1440, -720, -721, 0, 1440, 2880, 4320, 5760};
    const int expected[] = {0, 1, 2, 3, 0, 3, 0, 1, 2, 3, 0};
    for (unsigned i = 0; i < sizeof(angles) / sizeof(angles[0]); ++i) {
        *(s16 *)(car + 0x12) = angles[i];
        assert(heading4(car) == expected[i]);
    }
}

int main(int argc, char **argv)
{
    map_memory(0x02000000, 0x40000);
    map_memory(0x03000000, 0x10000);
    map_memory(0x04000000, 0x1000);
    map_memory(0x08000000, 0x1000000);
    setup();
    assert(argc == 2);
#define RUN(name) if (!strcmp(argv[1], #name)) { name(); puts(#name ": PASS"); return 0; }
    RUN(entity_bounds)
    RUN(world_and_column_bounds)
    RUN(cursor_and_map_swap)
    RUN(reload_state)
    RUN(landed_arwing_exit)
    RUN(loop_entry_and_z)
    RUN(build_controls_and_braking)
    RUN(continuous_loop_exit)
    RUN(entity_switch_and_invalid_world)
    RUN(stadium_retry_controls)
    RUN(signed_headings)
    fprintf(stderr, "Unknown test: %s\n", argv[1]);
    return 1;
}
