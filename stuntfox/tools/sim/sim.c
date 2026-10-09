/* Host-side physics test: runs the car or the Arwing with scripted controls and prints a
   trace. Build and run with tools/sim/run.sh after a normal build (needs build/gen). */
#include <stdio.h>
#include <stdlib.h>
#include "car.h"
#include "ship.h"
#include "world.h"
#include "gba.h"

u32 world_data[65536];
u32 frame_count;

static void load(const char *path)
{
    FILE *f = fopen(path, "rb");
    if (!f || !fread(world_data, 1, sizeof world_data, f)) { perror(path); exit(1); }
    fclose(f);
}

static double kmh(s32 v) { return v / 256.0 * 60 / 128 * 3.6; }

int main(int argc, char **argv)
{
    load(argc > 1 ? argv[1] : "build/gen/world.bin");
    const char *test = argc > 2 ? argv[2] : "loop";
    world_init();
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
