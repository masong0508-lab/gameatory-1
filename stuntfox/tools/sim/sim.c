/* Host-side physics test: runs the car or the Arwing with scripted controls and prints a
   trace. Build and run with tools/sim/run.sh after a normal build (needs build/gen). */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "car.h"
#include "ship.h"
#include "world.h"
#include "gba.h"

/* Host-only storage. The SFW4 grids alone exceed the old 256 KiB buffer; all
   supported worlds fit in 1 MiB. Oversized/truncated files fail before world_init
   can follow their offsets. This buffer is never linked into the cartridge. */
u32 world_data[1 << 18];
u32 frame_count;

static void invalid(const char *path, const char *why)
{
    fprintf(stderr, "%s: invalid world (%s)\n", path, why);
    exit(1);
}

static void validate(const char *path, size_t n)
{
    const u32 *h = world_data;
    if (n < 26 * sizeof(u32) || memcmp(h, "SFW4", 4))
        invalid(path, "missing SFW4 header");
    /* Byte sizes in header-offset order (src/world.c, tools/mkworld.py).
       Widen before multiplying, so corrupt counts cannot wrap a bounds check. */
    const u64 sizes[] = {
        (u64)h[1] * sizeof(Box), (u64)h[2] * sizeof(Lot), (u64)h[3] * sizeof(Ramp),
        (u64)h[4] * sizeof(Loop), 16 * 16 * 4, (u64)h[5] * sizeof(u16),
        CITY * CITY * sizeof(Cell), 16 * 16 * 4, (u64)h[6] * sizeof(Line),
        (u64)h[7] * sizeof(Tree), CITY * CITY * 2, (u64)h[1] * 32,
        CITY * CITY * 4, CITY * CITY * 3, CITY * CITY * 4, CITY * CITY * 2,
        CITY * CITY + 4,
    };
    for (unsigned i = 0; i < sizeof sizes / sizeof sizes[0]; i++) {
        u64 start = h[9 + i], end = i == 16 ? n : h[10 + i];
        if (start < 26 * sizeof(u32) || (start & 3) || end < start || end > n || sizes[i] > end - start)
            invalid(path, "truncated or invalid section");
    }
    const u8 *swim = (const u8 *)h + h[25];
    unsigned ladders = swim[CITY * CITY] | (unsigned)swim[CITY * CITY + 1] << 8;
    if ((u64)h[25] + CITY * CITY + 4 + (u64)ladders * sizeof(Ladder) > n)
        invalid(path, "truncated ladder table");
    const u16 *sectors = (const u16 *)((const u8 *)h + h[13]);
    for (int i = 0; i < 16 * 16; i++)
        if ((u32)sectors[2 * i] + sectors[2 * i + 1] > h[5])
            invalid(path, "sector outside item table");
    const u16 *items = (const u16 *)((const u8 *)h + h[14]);
    const u32 counts[] = {h[1], h[2], h[3], h[4], h[6], h[7]};
    for (u32 i = 0; i < h[5]; i++)
        if ((items[i] >> 13) >= 6 || (items[i] & 0x1fff) >= counts[items[i] >> 13])
            invalid(path, "item outside geometry table");
}

static void load(const char *path)
{
    FILE *f = fopen(path, "rb");
    if (!f) { perror(path); exit(1); }
    size_t n = fread(world_data, 1, sizeof world_data, f);
    int extra = fgetc(f);
    if (ferror(f)) { perror(path); fclose(f); exit(1); }
    fclose(f);
    if (extra != EOF)
        invalid(path, "larger than the host's 1 MiB limit");
    validate(path, n);
    world_init();
    fprintf(stderr, "world: %zu bytes, %d loops, highest collision surface %d\n", n, world.nloop, world.top);
}

static double kmh(s32 v) { return v / 256.0 * 60 / 128 * 3.6; }

int main(int argc, char **argv)
{
    load(argc > 1 ? argv[1] : "build/gen/world.bin");
    const char *test = argc > 2 ? argv[2] : "loop";
    if (test[0] == 's') {
        Ship s;
        ship_reset(&s, v3(48 * 1024, 0, 39 * 1024), 16384);
        for (int t = 0; t < 1200; t++) {
            u16 k = KEY_A;
            if (t >= 300 && t < 320) k |= KEY_DOWN;
            ship_update(&s, k);
            if (t % 20 == 0)
                printf("t%4d pos %6d %6d %6d v %6.1f kmh gear %d imp %5d f %6d %6d %6d u %6d %6d %6d\n", t,
                       s.b.pos.x >> 8, s.b.pos.y >> 8, s.b.pos.z >> 8, kmh(vlen(s.b.vel)), s.gear, s.impact,
                       s.b.m.f.x, s.b.m.f.y, s.b.m.f.z, s.b.m.u.x, s.b.m.u.y, s.b.m.u.z);
        }
        return 0;
    }
    Car c;
    int boost_at = argc > 3 ? atoi(argv[3]) : 0;
    car_reset(&c, v3(43 * 1024, 140, 37376), 16384);
    for (int t = 0; t < 900; t++) {
        u16 k = KEY_A;
        if (boost_at && t >= boost_at) k |= KEY_R;
        if (test[0] == 't' && t > 120) k |= KEY_RIGHT;
        car_update(&c, k);
        if (t % 10 == 0)
            printf("t%4d pos %6d %6d %6d %6.1f kmh wheels %d loop %d ang %5u up %6d %6d %6d imp %d\n", t,
                   c.b.pos.x >> 8, c.b.pos.y >> 8, c.b.pos.z >> 8, kmh(c.speed), c.wheels, c.on_loop,
                   c.loop_ang, c.b.m.u.x, c.b.m.u.y, c.b.m.u.z, c.impact);
    }
    return 0;
}
