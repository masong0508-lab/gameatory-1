/* Model data. Units match the physics: the car is about 4 m long, the Arwing about 6 m, a
   person about 1.8 m tall. */
#include "model.h"
#include "palette.h"
#include "physics.h"

#define F3(m, fl, a, b, c) {3, m, fl, {a, b, c}}
#define F4(m, fl, a, b, c, d) {4, m, fl, {a, b, c, d}}
#define F6(m, fl, a, b, c, d, e, f) {6, m, fl, {a, b, c, d, e, f}}
#define N(a) (sizeof a / sizeof a[0])

/* The car: a low Blue Falcon style wedge with a canopy, fins and a jet. */
static const MVert car_v[] = {
    {-115, -38, 235}, {115, -38, 235}, {125, -38, -225}, {-125, -38, -225},
    {-105, 12, 140}, {105, 12, 140}, {118, 32, -225}, {-118, 32, -225},
    {-26, -38, 238}, {26, -38, 238}, {-24, 12, 140}, {24, 12, 140},
    {-55, 16, 95}, {55, 16, 95}, {0, 64, -40}, {-62, 28, -150}, {62, 28, -150},
    {100, 32, -165}, {100, 98, -245}, {100, 32, -235},
    {-100, 32, -165}, {-100, 98, -245}, {-100, 32, -235},
    {-70, -22, -229}, {70, -22, -229}, {70, 20, -229}, {-70, 20, -229},
};
static const MFace car_f[] = {
    F4(M_CAR, 0, 0, 8, 10, 4), F4(M_ACCENT, 0, 8, 9, 11, 10), F4(M_CAR, 0, 9, 1, 5, 11),
    F4(M_CAR, 0, 4, 5, 6, 7), F4(M_CAR, 0, 0, 4, 7, 3), F4(M_CAR, 0, 1, 2, 6, 5),
    F4(M_STEEL, 0, 3, 2, 6, 7), F4(M_GLOW, MF_GLOW, 23, 24, 25, 26), F4(M_STEEL, 0, 0, 1, 2, 3),
    F3(M_GLASS, 0, 12, 13, 14), F3(M_GLASS, 0, 13, 16, 14), F3(M_CAR, 0, 16, 15, 14), F3(M_GLASS, 0, 15, 12, 14),
    F3(M_ACCENT, MF_TWO, 17, 18, 19), F3(M_ACCENT, MF_TWO, 20, 21, 22),
};

/* The Arwing. */
static const MVert arwing_v[] = {
    {0, 0, 400}, {-75, 10, -60}, {75, 10, -60}, {0, 70, -80}, {0, -50, -60},
    {0, 34, 170}, {-28, 44, 40}, {28, 44, 40}, {0, 82, -20},
    {60, 0, 30}, {60, 0, -150}, {330, -30, -170}, {320, -30, -80},
    {-60, 0, 30}, {-60, 0, -150}, {-330, -30, -170}, {-320, -30, -80},
    {325, -30, -20}, {325, 125, -250}, {325, -30, -270}, {325, -85, -200},
    {-325, -30, -20}, {-325, 125, -250}, {-325, -30, -270}, {-325, -85, -200},
    {-42, 4, -82}, {42, 4, -82}, {0, 48, -94},
};
static const MFace arwing_f[] = {
    F3(M_SHIP, 0, 0, 1, 3), F3(M_SHIP, 0, 0, 3, 2), F3(M_STEEL, 0, 0, 4, 1), F3(M_STEEL, 0, 0, 2, 4),
    F3(M_STEEL, 0, 1, 2, 3), F3(M_STEEL, 0, 1, 4, 2), F3(M_GLOW, MF_GLOW, 25, 26, 27),
    F3(M_GLASS, 0, 5, 6, 8), F3(M_GLASS, 0, 5, 8, 7),
    F4(M_SHIP, MF_TWO, 9, 10, 11, 12), F4(M_SHIP, MF_TWO, 13, 14, 15, 16),
    F4(M_CAR, MF_TWO, 17, 18, 19, 20), F4(M_CAR, MF_TWO, 21, 22, 23, 24),
};

/* The station's hub: a flat deck you can land on, with a pad, lit windows and a mast, and the
   docking bay's mouth in its front (+z) face. */
#define HX HUB_HX
#define HY HUB_HY
#define HZ HUB_HZ
#define BX BAY_HX
#define B0 BAY_Y0
#define B1 BAY_Y1
#define BZ BAY_Z0
static const MVert hub_v[] = {
    {-HX, -HY, -HZ}, {HX, -HY, -HZ}, {HX, -HY, HZ}, {-HX, -HY, HZ},
    {-HX, HY, -HZ}, {HX, HY, -HZ}, {HX, HY, HZ}, {-HX, HY, HZ},
    {-800, HY + 4, -800}, {800, HY + 4, -800}, {800, HY + 4, 800}, {-800, HY + 4, 800},
    {-HX - 4, -120, -1300}, {-HX - 4, -120, 1300}, {-HX - 4, 120, 1300}, {-HX - 4, 120, -1300},
    {HX + 4, -120, -1300}, {HX + 4, -120, 1300}, {HX + 4, 120, 1300}, {HX + 4, 120, -1300},
    {-1300, -120, -HZ - 4}, {1300, -120, -HZ - 4}, {1300, 120, -HZ - 4}, {-1300, 120, -HZ - 4},
    {-BX, B0, HZ}, {BX, B0, HZ}, {BX, B1, HZ}, {-BX, B1, HZ},
    {1200, HY, 1200}, {1450, HY, 1200}, {1325, HY, 1450}, {1325, HY + 1600, 1325},
};
static const MFace hub_f[] = {
    F4(M_STEEL, 0, 0, 1, 2, 3), F4(M_CONCRETE, 0, 4, 5, 6, 7), F4(M_SHIP, 0, 0, 3, 7, 4),
    F4(M_SHIP, 0, 1, 2, 6, 5), F4(M_SHIP, 0, 0, 1, 5, 4),
    F4(M_SHIP, 0, 7, 6, 26, 27), F4(M_STEEL, 0, 3, 2, 25, 24), F4(M_SHIP, 0, 3, 24, 27, 7),
    F4(M_SHIP, 0, 2, 6, 26, 25),                                                  /* the front, round the mouth */
    F4(M_ACCENT, 0, 8, 9, 10, 11), F4(M_GLOW, MF_GLOW, 12, 13, 14, 15), F4(M_GLOW, MF_GLOW, 16, 17, 18, 19),
    F4(M_GLOW, MF_GLOW, 20, 21, 22, 23),
    F3(M_STUNT, MF_TWO, 28, 29, 31), F3(M_STUNT, MF_TWO, 29, 30, 31), F3(M_STUNT, MF_TWO, 30, 28, 31),
};

/* The docking bay inside the hub: a hangar you fly into through the mouth, with a landing pad,
   strip lights, a lit sign at the back and lights round the mouth. */
#define PZ BAY_PAD_Z
static const MVert bay_v[] = {
    {-BX, B0, BZ}, {BX, B0, BZ}, {BX, B0, HZ}, {-BX, B0, HZ},
    {-BX, B1, BZ}, {BX, B1, BZ}, {BX, B1, HZ}, {-BX, B1, HZ},
    {-430, B0 + 3, PZ - 430}, {430, B0 + 3, PZ - 430}, {430, B0 + 3, PZ + 430}, {-430, B0 + 3, PZ + 430},
    {-300, B0 + 6, PZ - 300}, {300, B0 + 6, PZ - 300}, {300, B0 + 6, PZ + 300}, {-300, B0 + 6, PZ + 300},
    {-BX + 4, -20, BZ + 250}, {-BX + 4, -20, HZ - 120}, {-BX + 4, 30, HZ - 120}, {-BX + 4, 30, BZ + 250},
    {BX - 4, -20, BZ + 250}, {BX - 4, -20, HZ - 120}, {BX - 4, 30, HZ - 120}, {BX - 4, 30, BZ + 250},
    {-180, B1 - 4, -500}, {180, B1 - 4, -500}, {180, B1 - 4, -100}, {-180, B1 - 4, -100},
    {-180, B1 - 4, 500}, {180, B1 - 4, 500}, {180, B1 - 4, 900}, {-180, B1 - 4, 900},
    {-420, -230, BZ + 4}, {420, -230, BZ + 4}, {420, 30, BZ + 4}, {-420, 30, BZ + 4},
    {-BX, B1, HZ + 4}, {BX, B1, HZ + 4}, {BX, B1 + 50, HZ + 4}, {-BX, B1 + 50, HZ + 4},
    {-BX, B0 - 50, HZ + 4}, {BX, B0 - 50, HZ + 4}, {BX, B0, HZ + 4}, {-BX, B0, HZ + 4},
};
#define IN (MF_IN | MF_BACK)
static const MFace bay_f[] = {
    F4(M_CONCRETE, IN, 0, 1, 2, 3), F4(M_ROAD, IN, 4, 5, 6, 7), F4(M_STEEL, IN, 0, 3, 7, 4),
    F4(M_STEEL, IN, 1, 2, 6, 5), F4(M_SHIP, IN, 0, 1, 5, 4),
    F4(M_ACCENT, IN, 8, 9, 10, 11), F4(M_ROAD, IN, 12, 13, 14, 15),
    F4(M_GLOW, IN | MF_GLOW, 16, 17, 18, 19), F4(M_GLOW, IN | MF_GLOW, 20, 21, 22, 23),
    F4(M_CREAM, IN | MF_GLOW, 24, 25, 26, 27), F4(M_CREAM, IN | MF_GLOW, 28, 29, 30, 31),
    F4(M_STUNT, IN | MF_GLOW, 32, 33, 34, 35),
    F4(M_GLOW, MF_GLOW, 36, 37, 38, 39), F4(M_GLOW, MF_GLOW, 40, 41, 42, 43),
};

/* The ring around the hub, built at start-up: 8 sides, and 4 spokes. */
#define RING_N 8
#define RING_Y 400
static MVert ring_v[RING_N * 4 + 16] EWRAM_BSS;
static MFace ring_f[RING_N * 4 + 4] EWRAM_BSS;

/* An asteroid: a lumpy octahedron, radius 256. */
static const MVert rock_v[] = {
    {0, 256, 30}, {0, -230, -20}, {250, 10, 40}, {-260, -20, 10}, {30, 20, 250}, {-10, 40, -240},
    {150, 160, 150}, {-150, -140, -160},
};
static const MFace rock_f[] = {
    F3(M_STEEL, 0, 0, 2, 6), F3(M_CONCRETE, 0, 6, 2, 4), F3(M_STEEL, 0, 0, 6, 4), F3(M_BRICK, 0, 0, 5, 2),
    F3(M_STEEL, 0, 0, 3, 5), F3(M_CONCRETE, 0, 0, 4, 3), F3(M_STEEL, 0, 1, 2, 5), F3(M_BRICK, 0, 1, 7, 3),
    F3(M_CONCRETE, 0, 1, 5, 7), F3(M_STEEL, 0, 7, 5, 3), F3(M_BRICK, 0, 1, 4, 2), F3(M_STEEL, 0, 1, 3, 4),
};

/* A person: legs and body in their clothes' colour (M_CAR, painted per person) and a head. */
static const MVert ped_v[] = {
    {-34, 0, -20}, {34, 0, -20}, {34, 0, 20}, {-34, 0, 20},
    {-34, 180, -20}, {34, 180, -20}, {34, 180, 20}, {-34, 180, 20},
    {-18, 180, -18}, {18, 180, -18}, {18, 180, 18}, {-18, 180, 18},
    {-18, 228, -18}, {18, 228, -18}, {18, 228, 18}, {-18, 228, 18},
};
static const MFace ped_f[] = {
    F4(M_CAR, 0, 0, 1, 5, 4), F4(M_CAR, 0, 1, 2, 6, 5), F4(M_CAR, 0, 2, 3, 7, 6), F4(M_CAR, 0, 3, 0, 4, 7),
    F4(M_CAR, 0, 4, 5, 6, 7),
    F4(M_CREAM, 0, 8, 9, 13, 12), F4(M_CREAM, 0, 9, 10, 14, 13), F4(M_CREAM, 0, 10, 11, 15, 14),
    F4(M_CREAM, 0, 11, 8, 12, 15), F4(M_ROAD, 0, 12, 13, 14, 15),
};

/* A helicopter: cabin, tail boom and a two-blade rotor. */
static const MVert heli_v[] = {
    {-90, 0, -150}, {90, 0, -150}, {90, 0, 170}, {-90, 0, 170},
    {-90, 150, -120}, {90, 150, -120}, {90, 150, 110}, {-90, 150, 110},
    {0, 110, -140}, {0, 120, -480}, {0, 60, -140}, {0, 230, -500},
    {-30, 170, -30}, {30, 170, -30}, {30, 170, 30}, {-30, 170, 30},
    {-20, 172, -520}, {20, 172, -520}, {20, 172, 520}, {-20, 172, 520},
    {-520, 174, -20}, {520, 174, -20}, {520, 174, 20}, {-520, 174, 20},
    {-60, 90, 172}, {60, 90, 172}, {60, 140, 112}, {-60, 140, 112},
};
static const MFace heli_f[] = {
    F4(M_CAR, 0, 0, 1, 5, 4), F4(M_CAR, 0, 1, 2, 6, 5), F4(M_CAR, 0, 3, 0, 4, 7), F4(M_CAR, 0, 4, 5, 6, 7),
    F4(M_STEEL, 0, 0, 3, 2, 1), F4(M_CAR, 0, 2, 3, 7, 6), F4(M_GLASS, MF_TWO, 24, 25, 26, 27),
    F3(M_CAR, MF_TWO, 8, 9, 10), F3(M_CAR, MF_TWO, 8, 11, 9),
    F4(M_STEEL, MF_TWO, 12, 13, 14, 15), F4(M_ROAD, MF_TWO, 16, 17, 18, 19), F4(M_ROAD, MF_TWO, 20, 21, 22, 23),
};

/* A pirate raider: a dark dart with forward-swept blades and red fins. */
static const MVert raider_v[] = {
    {0, 0, 330}, {-70, 30, -170}, {70, 30, -170}, {0, -50, -170}, {0, 75, -120},
    {-50, 0, 40}, {-60, 0, -130}, {-400, -30, -260}, {50, 0, 40}, {60, 0, -130}, {400, -30, -260},
    {-400, -30, -260}, {-390, 90, -310}, {-380, -30, -170}, {400, -30, -260}, {390, 90, -310}, {380, -30, -170},
};
static const MFace raider_f[] = {
    F3(M_BRICK, 0, 0, 1, 4), F3(M_BRICK, 0, 0, 4, 2), F3(M_ROAD, 0, 0, 2, 3), F3(M_ROAD, 0, 0, 3, 1),
    F3(M_BRICK, 0, 1, 4, 2), F3(M_GLOW, MF_GLOW, 1, 2, 3),
    F3(M_ROAD, MF_TWO, 5, 6, 7), F3(M_ROAD, MF_TWO, 8, 9, 10),
    F3(M_STUNT, MF_TWO, 11, 12, 13), F3(M_STUNT, MF_TWO, 14, 15, 16),
};

/* The pirate carrier: a long armoured wedge with a bridge tower and two engines. */
static const MVert carrier_v[] = {
    {0, 0, 1700}, {0, 460, -500}, {-880, 0, -500}, {880, 0, -500}, {0, -320, -500},
    {-620, 260, -1400}, {620, 260, -1400}, {720, -220, -1400}, {-720, -220, -1400},
    {-130, 400, -800}, {130, 400, -800}, {0, 760, -1050},
    {-560, -120, -1404}, {-180, -120, -1404}, {-180, 120, -1404}, {-560, 120, -1404},
    {180, -120, -1404}, {560, -120, -1404}, {560, 120, -1404}, {180, 120, -1404},
};
static const MFace carrier_f[] = {
    F3(M_ROAD, 0, 0, 1, 2), F3(M_ROAD, 0, 0, 3, 1), F3(M_BRICK, 0, 0, 2, 4), F3(M_BRICK, 0, 0, 4, 3),
    F3(M_ROAD, 0, 1, 6, 5), F3(M_BRICK, 0, 1, 5, 2), F3(M_ROAD, 0, 2, 5, 8), F3(M_STEEL, 0, 2, 8, 4),
    F3(M_STEEL, 0, 4, 8, 7), F3(M_STEEL, 0, 4, 7, 3), F3(M_ROAD, 0, 3, 7, 6), F3(M_BRICK, 0, 3, 6, 1),
    F4(M_STEEL, 0, 5, 6, 7, 8),
    F3(M_STUNT, MF_TWO, 9, 10, 11), F3(M_GLOW, MF_TWO | MF_GLOW, 9, 11, 10),
    F4(M_GLOW, MF_GLOW, 12, 13, 14, 15), F4(M_GLOW, MF_GLOW, 16, 17, 18, 19),
};

/* a cargo pod: a striped canister */
static const MVert pod_v[] = {{0, 150, 0}, {0, -150, 0}, {120, 0, 0}, {-120, 0, 0}, {0, 0, 120}, {0, 0, -120}};
static const MFace pod_f[] = {
    F3(M_ACCENT, 0, 0, 2, 4), F3(M_STEEL, 0, 0, 4, 3), F3(M_ACCENT, 0, 0, 3, 5), F3(M_STEEL, 0, 0, 5, 2),
    F3(M_STEEL, 0, 1, 4, 2), F3(M_ACCENT, 0, 1, 3, 4), F3(M_STEEL, 0, 1, 5, 3), F3(M_ACCENT, 0, 1, 2, 5),
};

/* a fox medal: a gold coin, spinning */
#define HEXR(r, z) {0, r, z}, {(r) * 87 / 100, (r) / 2, z}, {(r) * 87 / 100, -(r) / 2, z}, \
                   {0, -(r), z}, {-(r) * 87 / 100, -(r) / 2, z}, {-(r) * 87 / 100, (r) / 2, z}
static const MVert medal_v[] = {HEXR(200, 0), HEXR(120, 14), HEXR(120, -14)};
static const MFace medal_f[] = {
    F6(M_ACCENT, MF_TWO | MF_GLOW, 0, 1, 2, 3, 4, 5), F6(M_GLOW, MF_TWO | MF_GLOW, 6, 7, 8, 9, 10, 11),
    F6(M_GLOW, MF_TWO | MF_GLOW, 12, 13, 14, 15, 16, 17),
};

/* a crate */
static const MVert crate_v[] = {
    {-110, 0, -110}, {110, 0, -110}, {110, 0, 110}, {-110, 0, 110},
    {-110, 220, -110}, {110, 220, -110}, {110, 220, 110}, {-110, 220, 110},
};
static const MFace crate_f[] = {
    F4(M_BRICK, 0, 4, 5, 6, 7), F4(M_CREAM, 0, 0, 1, 5, 4), F4(M_BRICK, 0, 1, 2, 6, 5),
    F4(M_CREAM, 0, 2, 3, 7, 6), F4(M_BRICK, 0, 3, 0, 4, 7),
};

/* a race gate: an eight-sided ring facing along z, in the paint of model_body */
static MVert gate_v[16] EWRAM_BSS;
static MFace gate_f[8] EWRAM_BSS;

/* a beacon: a tall shaft of light over a rooftop (two crossed panels) */
static const MVert beacon_v[] = {
    {-70, 0, 0}, {70, 0, 0}, {70, 6000, 0}, {-70, 6000, 0}, {0, 0, -70}, {0, 0, 70}, {0, 6000, 70}, {0, 6000, -70},
};
static const MFace beacon_f[] = {F4(M_CAR, MF_TWO | MF_GLOW, 0, 1, 2, 3), F4(M_CAR, MF_TWO | MF_GLOW, 4, 5, 6, 7)};

/* an explosion's fireball (an octahedron of fire, scaled as it grows) */
static const MVert boom_v[] = {{0, 256, 0}, {0, -256, 0}, {256, 0, 0}, {-256, 0, 0}, {0, 0, 256}, {0, 0, -256}};
static const MFace boom_f[] = {
    F3(M_GLOW, MF_GLOW, 0, 2, 4), F3(M_ACCENT, MF_GLOW, 0, 4, 3), F3(M_GLOW, MF_GLOW, 0, 3, 5),
    F3(M_ACCENT, MF_GLOW, 0, 5, 2), F3(M_ACCENT, MF_GLOW, 1, 4, 2), F3(M_GLOW, MF_GLOW, 1, 3, 4),
    F3(M_ACCENT, MF_GLOW, 1, 5, 3), F3(M_GLOW, MF_GLOW, 1, 2, 5),
};

static N3 nbuf[200] EWRAM_BSS;
Model mdl_car, mdl_arwing, mdl_hub, mdl_ring, mdl_rock, mdl_ped, mdl_heli;
Model mdl_bay, mdl_raider, mdl_carrier, mdl_pod, mdl_medal, mdl_crate, mdl_gate, mdl_beacon, mdl_boom;

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

void models_init(void)
{
    for (int i = 0; i < RING_N; i++) {
        s32 a = i * 65536 / RING_N + 4096, c = fcos(a), s = fsin(a);
        s32 ro = 6600, ri = 5900, h = RING_Y + 260, l = RING_Y - 260;   /* (above the bay's mouth) */
        ring_v[i] = (MVert){(s16)((ro * s) >> 14), (s16)h, (s16)((ro * c) >> 14)};
        ring_v[RING_N + i] = (MVert){(s16)((ro * s) >> 14), (s16)l, (s16)((ro * c) >> 14)};
        ring_v[2 * RING_N + i] = (MVert){(s16)((ri * s) >> 14), (s16)h, (s16)((ri * c) >> 14)};
        ring_v[3 * RING_N + i] = (MVert){(s16)((ri * s) >> 14), (s16)l, (s16)((ri * c) >> 14)};
    }
    int nf = 0;
    for (int i = 0; i < RING_N; i++) {
        int j = (i + 1) % RING_N;
        ring_f[nf++] = (MFace)F4(M_SHIP, 0, i, j, RING_N + j, RING_N + i);                         /* outside */
        ring_f[nf++] = (MFace)F4(M_GLOW, MF_GLOW | MF_TWO, 2 * RING_N + i, 2 * RING_N + j, 3 * RING_N + j,
                                 3 * RING_N + i);                                                   /* windows */
        ring_f[nf++] = (MFace)F4(i & 1 ? M_STUNT : M_STEEL, 0, i, j, 2 * RING_N + j, 2 * RING_N + i);
        ring_f[nf++] = (MFace)F4(M_STEEL, 0, RING_N + i, RING_N + j, 3 * RING_N + j, 3 * RING_N + i);
    }
    int nv = 4 * RING_N;
    for (int k = 0; k < 4; k++) {                                                                  /* spokes */
        s32 a = k * 16384, c = fcos(a), s = fsin(a), px = (c * 120) >> 14, pz = (-s * 120) >> 14;
        s32 x0 = (s * 1600) >> 14, z0 = (c * 1600) >> 14, x1 = (s * 5900) >> 14, z1 = (c * 5900) >> 14;
        ring_v[nv] = (MVert){(s16)(x0 + px), RING_Y, (s16)(z0 + pz)};
        ring_v[nv + 1] = (MVert){(s16)(x1 + px), RING_Y, (s16)(z1 + pz)};
        ring_v[nv + 2] = (MVert){(s16)(x1 - px), RING_Y, (s16)(z1 - pz)};
        ring_v[nv + 3] = (MVert){(s16)(x0 - px), RING_Y, (s16)(z0 - pz)};
        ring_f[nf++] = (MFace)F4(M_STEEL, MF_TWO, nv, nv + 1, nv + 2, nv + 3);
        nv += 4;
    }
    N3 *nb = nbuf;
    setup(&mdl_car, car_v, sizeof car_v / sizeof car_v[0], car_f, sizeof car_f / sizeof car_f[0], 300, &nb);
    setup(&mdl_arwing, arwing_v, sizeof arwing_v / sizeof arwing_v[0], arwing_f, sizeof arwing_f / sizeof arwing_f[0], 450, &nb);
    setup(&mdl_hub, hub_v, sizeof hub_v / sizeof hub_v[0], hub_f, sizeof hub_f / sizeof hub_f[0], 2400, &nb);
    setup(&mdl_ring, ring_v, nv, ring_f, nf, 6700, &nb);
    setup(&mdl_rock, rock_v, sizeof rock_v / sizeof rock_v[0], rock_f, sizeof rock_f / sizeof rock_f[0], 270, &nb);
    setup(&mdl_ped, ped_v, sizeof ped_v / sizeof ped_v[0], ped_f, sizeof ped_f / sizeof ped_f[0], 130, &nb);
    setup(&mdl_heli, heli_v, sizeof heli_v / sizeof heli_v[0], heli_f, sizeof heli_f / sizeof heli_f[0], 560, &nb);
    for (int i = 0; i < 8; i++) {
        s32 a = i * 8192, c = fcos(a), s = fsin(a);
        gate_v[i] = (MVert){(s16)((700 * s) >> 14), (s16)((700 * c) >> 14), 0};
        gate_v[8 + i] = (MVert){(s16)((560 * s) >> 14), (s16)((560 * c) >> 14), 0};
        int j = (i + 1) & 7;
        gate_f[i] = (MFace)F4(M_CAR, MF_TWO | MF_GLOW, i, j, 8 + j, 8 + i);
    }
    setup(&mdl_bay, bay_v, N(bay_v), bay_f, N(bay_f), 2000, &nb);
    setup(&mdl_raider, raider_v, N(raider_v), raider_f, N(raider_f), 420, &nb);
    setup(&mdl_carrier, carrier_v, N(carrier_v), carrier_f, N(carrier_f), 1800, &nb);
    setup(&mdl_pod, pod_v, N(pod_v), pod_f, N(pod_f), 160, &nb);
    setup(&mdl_medal, medal_v, N(medal_v), medal_f, N(medal_f), 210, &nb);
    setup(&mdl_crate, crate_v, N(crate_v), crate_f, N(crate_f), 170, &nb);
    setup(&mdl_gate, gate_v, 16, gate_f, 8, 710, &nb);
    setup(&mdl_beacon, beacon_v, N(beacon_v), beacon_f, N(beacon_f), 6000, &nb);
    setup(&mdl_boom, boom_v, N(boom_v), boom_f, N(boom_f), 260, &nb);
}
