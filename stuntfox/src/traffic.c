/* Models for Payback's own vehicles and people, drawn by the MERGE build. Vehicles share the
   car's origin: the centre of the body, with the road 58 units below. People stand on their
   origin. Faces in M_CAR take the paint job (model_body), people's legs (M_SKY) take
   model_legs (model.h). */
#include "model.h"
#include "palette.h"
#include "traffic.h"

#define F3(m, fl, a, b, c) {3, m, fl, {a, b, c}}
#define F4(m, fl, a, b, c, d) {4, m, fl, {a, b, c, d}}
#define F5(m, fl, a, b, c, d, e) {5, m, fl, {a, b, c, d, e}}
#define F6(m, fl, a, b, c, d, e, f) {6, m, fl, {a, b, c, d, e, f}}

#define G (-58)                    /* the road */

/* a wheel: a six-sided disc on the side of the car, radius 40 */
#define HEX(x, z) {x, G + 80, z}, {x, G + 60, (z) + 35}, {x, G + 20, (z) + 35}, \
                  {x, G, z}, {x, G + 20, (z) - 35}, {x, G + 60, (z) - 35}
#define WHEELS(x, zf, zr) HEX(-(x), zf), HEX(x, zf), HEX(-(x), zr), HEX(x, zr)
#define WHEEL_F(b) F6(M_ROAD, MF_TWO, b, b + 1, b + 2, b + 3, b + 4, b + 5)
#define WHEEL_FACES(b) WHEEL_F(b), WHEEL_F(b + 6), WHEEL_F(b + 12), WHEEL_F(b + 18)

/* A saloon: body, bonnet and boot, a glass cabin with a roof. L: half length, cf/cb: where
   the cabin meets the body, rf/rb: its roof, w: half width. */
#define SALOON_V(L, cf, cb, rf, rb, w)                                                          \
    {-(w), G + 22, L}, {w, G + 22, L}, {w, G + 22, -(L)}, {-(w), G + 22, -(L)},                 \
    {-(w), G + 82, (L) - 10}, {w, G + 82, (L) - 10}, {w, G + 86, 5 - (L)}, {-(w), G + 86, 5 - (L)}, \
    {-(w), G + 82, cf}, {w, G + 82, cf}, {w, G + 84, cb}, {-(w), G + 84, cb},                 \
    {20 - (w), G + 150, rf}, {(w) - 20, G + 150, rf}, {(w) - 20, G + 150, rb}, {20 - (w), G + 150, rb}
static const MFace saloon_f[] = {
    F4(M_CAR, 0, 0, 1, 5, 4), F4(M_CAR, 0, 2, 3, 7, 6), F6(M_CAR, 0, 3, 0, 4, 8, 11, 7),
    F6(M_CAR, 0, 1, 2, 6, 10, 9, 5), F4(M_CAR, 0, 4, 5, 9, 8), F4(M_CAR, 0, 11, 10, 6, 7),
    F4(M_GLASS, 0, 8, 9, 13, 12), F4(M_GLASS, 0, 10, 11, 15, 14), F4(M_GLASS, 0, 11, 8, 12, 15),
    F4(M_GLASS, 0, 9, 10, 14, 13), F4(M_CAR, 0, 12, 13, 14, 15),
    WHEEL_FACES(16),
};
static const MVert saloon_v[] = {SALOON_V(235, 70, -120, 30, -95, 112), WHEELS(114, 150, -150)};
static const MVert limo_v[] = {SALOON_V(340, 120, -230, 80, -205, 112), WHEELS(114, 250, -250)};
static const MVert pickup_v[] = {SALOON_V(245, 150, -20, 110, 0, 118), WHEELS(120, 160, -160)};

/* the Blue Falcon wedge (sports cars), with wheels */
static const MVert sport_v[] = {
    {-115, -38, 235}, {115, -38, 235}, {125, -38, -225}, {-125, -38, -225},
    {-105, 12, 140}, {105, 12, 140}, {118, 32, -225}, {-118, 32, -225},
    {-26, -38, 238}, {26, -38, 238}, {-24, 12, 140}, {24, 12, 140},
    {-55, 16, 95}, {55, 16, 95}, {0, 64, -40}, {-62, 28, -150}, {62, 28, -150},
    {100, 32, -165}, {100, 98, -245}, {100, 32, -235},
    {-100, 32, -165}, {-100, 98, -245}, {-100, 32, -235},
    WHEELS(127, 160, -150),
};
static const MFace sport_f[] = {
    F4(M_CAR, 0, 0, 8, 10, 4), F4(M_ACCENT, 0, 8, 9, 11, 10), F4(M_CAR, 0, 9, 1, 5, 11),
    F4(M_CAR, 0, 4, 5, 6, 7), F4(M_CAR, 0, 0, 4, 7, 3), F4(M_CAR, 0, 1, 2, 6, 5),
    F4(M_STEEL, 0, 3, 2, 6, 7),
    F3(M_GLASS, 0, 12, 13, 14), F3(M_GLASS, 0, 13, 16, 14), F3(M_CAR, 0, 16, 15, 14), F3(M_GLASS, 0, 15, 12, 14),
    F3(M_ACCENT, MF_TWO, 17, 18, 19), F3(M_ACCENT, MF_TWO, 20, 21, 22),
    WHEEL_FACES(23),
};

/* a van: a tall box with a sloping windscreen */
static const MVert van_v[] = {
    {-118, G + 22, 245}, {118, G + 22, 245}, {118, G + 22, -245}, {-118, G + 22, -245},
    {-118, G + 110, 245}, {118, G + 110, 245}, {118, G + 215, -245}, {-118, G + 215, -245},
    {-118, G + 205, 190}, {118, G + 205, 190},
    WHEELS(120, 160, -160),
};
static const MFace van_f[] = {
    F4(M_CAR, 0, 0, 1, 5, 4), F4(M_GLASS, 0, 4, 5, 9, 8), F4(M_CAR, 0, 8, 9, 6, 7),
    F4(M_CAR, 0, 3, 2, 6, 7), F5(M_CAR, 0, 3, 0, 4, 8, 7), F5(M_CAR, 0, 1, 2, 6, 9, 5),
    WHEEL_FACES(10),
};

/* a bus: long and tall, with a band of windows */
#define BUS_X 130
#define BUS_Z 520
#define BUS_SIDE(x) {x, G + 22, BUS_Z}, {x, G + 170, BUS_Z}, {x, G + 250, BUS_Z}, {x, G + 290, BUS_Z}, \
                    {x, G + 22, -BUS_Z}, {x, G + 170, -BUS_Z}, {x, G + 250, -BUS_Z}, {x, G + 290, -BUS_Z}
static const MVert bus_v[] = {BUS_SIDE(-BUS_X), BUS_SIDE(BUS_X), WHEELS(132, 380, -380)};
static const MFace bus_f[] = {
    F4(M_CAR, 0, 0, 4, 5, 1), F4(M_GLASS, 0, 1, 5, 6, 2), F4(M_CAR, 0, 2, 6, 7, 3),
    F4(M_CAR, 0, 8, 12, 13, 9), F4(M_GLASS, 0, 9, 13, 14, 10), F4(M_CAR, 0, 10, 14, 15, 11),
    F4(M_CAR, 0, 0, 8, 9, 1), F4(M_GLASS, 0, 1, 9, 11, 3), F4(M_CAR, 0, 4, 12, 15, 7),
    F4(M_CAR, 0, 3, 11, 15, 7),
    WHEEL_FACES(16),
};

/* a tank: hull, tracks, turret and gun */
static const MVert tank_v[] = {
    {-150, G + 30, 280}, {150, G + 30, 280}, {150, G + 30, -280}, {-150, G + 30, -280},
    {-150, G + 105, 200}, {150, G + 105, 200}, {150, G + 105, -280}, {-150, G + 105, -280},
    {-85, G + 105, 80}, {85, G + 105, 80}, {85, G + 105, -90}, {-85, G + 105, -90},
    {-70, G + 165, 60}, {70, G + 165, 60}, {70, G + 165, -90}, {-70, G + 165, -90},
    {-152, G, 290}, {-152, G, -290}, {-152, G + 75, -300}, {-152, G + 75, 300},
    {152, G, 290}, {152, G, -290}, {152, G + 75, -300}, {152, G + 75, 300},
    {-12, G + 138, 70}, {12, G + 138, 70}, {12, G + 138, 450}, {-12, G + 138, 450},
    {0, G + 126, 70}, {0, G + 150, 70}, {0, G + 150, 450}, {0, G + 126, 450},
};
static const MFace tank_f[] = {
    F4(M_CAR, 0, 0, 1, 5, 4), F4(M_CAR, 0, 3, 2, 6, 7), F4(M_CAR, 0, 3, 0, 4, 7),
    F4(M_CAR, 0, 1, 2, 6, 5), F4(M_CAR, 0, 4, 5, 6, 7),
    F4(M_ROAD, MF_TWO, 16, 17, 18, 19), F4(M_ROAD, MF_TWO, 20, 21, 22, 23),
    F4(M_CAR, 0, 8, 9, 13, 12), F4(M_CAR, 0, 10, 11, 15, 14), F4(M_CAR, 0, 11, 8, 12, 15),
    F4(M_CAR, 0, 9, 10, 14, 13), F4(M_CAR, 0, 12, 13, 14, 15),
    F4(M_STEEL, MF_TWO, 24, 25, 26, 27), F4(M_STEEL, MF_TWO, 28, 29, 30, 31),
};

/* A person: legs (model_legs), body and arms (model_body), head and hair. s: how far each
   foot is ahead of the hips, a: how far each hand swings. */
#define BOX(x0, x1, y0, y1, zb0, zt0, d) \
    {x0, y0, (zb0) - (d)}, {x1, y0, (zb0) - (d)}, {x1, y0, (zb0) + (d)}, {x0, y0, (zb0) + (d)}, \
    {x0, y1, (zt0) - (d)}, {x1, y1, (zt0) - (d)}, {x1, y1, (zt0) + (d)}, {x0, y1, (zt0) + (d)}
#define PERSON_V(s, a)                                                                          \
    BOX(-26, -4, 0, 100, s, 0, 13), BOX(4, 26, 0, 100, -(s), 0, 13), BOX(-34, 34, 98, 180, 0, 0, 18), \
    BOX(-16, 16, 184, 226, 0, 0, 16),                                                           \
    {-38, 175, -8}, {-38, 175, 8}, {-38, 105, 8 - (a)}, {-38, 105, -8 - (a)},                   \
    {38, 175, -8}, {38, 175, 8}, {38, 105, 8 + (a)}, {38, 105, -8 + (a)}
#define SIDES(m, b) F4(m, 0, b, b + 1, b + 5, b + 4), F4(m, 0, b + 1, b + 2, b + 6, b + 5), \
                    F4(m, 0, b + 2, b + 3, b + 7, b + 6), F4(m, 0, b + 3, b, b + 4, b + 7)
static const MFace person_f[] = {
    SIDES(M_SKY, 0), SIDES(M_SKY, 8), SIDES(M_CAR, 16), F4(M_CAR, 0, 20, 21, 22, 23),
    SIDES(M_CREAM, 24), F4(M_ROAD, 0, 28, 29, 30, 31),
    F4(M_CAR, MF_TWO, 32, 33, 34, 35), F4(M_CAR, MF_TWO, 36, 37, 38, 39),
};
static const MVert stand_v[] = {PERSON_V(0, 0)};
static const MVert stride_a_v[] = {PERSON_V(40, 30)};
static const MVert stride_b_v[] = {PERSON_V(-40, -30)};

Model mdl_saloon, mdl_limo, mdl_pickup, mdl_sport, mdl_van, mdl_bus, mdl_tank;
Model mdl_stand, mdl_stride_a, mdl_stride_b;

static N3 tnbuf[200] EWRAM_BSS;

#define N(a) (sizeof a / sizeof a[0])
static void setup(Model *md, const MVert *v, int nv, const MFace *f, int nf, int radius, N3 **nb)
{
    md->v = v;
    md->nv = nv;
    md->f = f;
    md->nf = nf;
    md->radius = radius;
    md->normal = *nb;
    *nb += nf;
    model_init(md);
}

void traffic_init(void)
{
    N3 *nb = tnbuf;
    setup(&mdl_saloon, saloon_v, N(saloon_v), saloon_f, N(saloon_f), 290, &nb);
    setup(&mdl_limo, limo_v, N(limo_v), saloon_f, N(saloon_f), 390, &nb);
    setup(&mdl_pickup, pickup_v, N(pickup_v), saloon_f, N(saloon_f), 300, &nb);
    setup(&mdl_sport, sport_v, N(sport_v), sport_f, N(sport_f), 300, &nb);
    setup(&mdl_van, van_v, N(van_v), van_f, N(van_f), 340, &nb);
    setup(&mdl_bus, bus_v, N(bus_v), bus_f, N(bus_f), 600, &nb);
    setup(&mdl_tank, tank_v, N(tank_v), tank_f, N(tank_f), 520, &nb);
    setup(&mdl_stand, stand_v, N(stand_v), person_f, N(person_f), 140, &nb);
    setup(&mdl_stride_a, stride_a_v, N(stride_a_v), person_f, N(person_f), 140, &nb);
    setup(&mdl_stride_b, stride_b_v, N(stride_b_v), person_f, N(person_f), 140, &nb);
}
