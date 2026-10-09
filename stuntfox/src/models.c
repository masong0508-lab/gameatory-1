/* Model data. Units match the physics: the car is about 4 m long, the Arwing about 6 m. */
#include "model.h"
#include "palette.h"
#include "physics.h"

#define F3(m, fl, a, b, c) {3, m, fl, {a, b, c}}
#define F4(m, fl, a, b, c, d) {4, m, fl, {a, b, c, d}}

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

/* The station's hub: a flat deck you can land on, with a pad, lit windows and a mast. */
#define HX HUB_HX
#define HY HUB_HY
#define HZ HUB_HZ
static const MVert hub_v[] = {
    {-HX, -HY, -HZ}, {HX, -HY, -HZ}, {HX, -HY, HZ}, {-HX, -HY, HZ},
    {-HX, HY, -HZ}, {HX, HY, -HZ}, {HX, HY, HZ}, {-HX, HY, HZ},
    {-800, HY + 4, -800}, {800, HY + 4, -800}, {800, HY + 4, 800}, {-800, HY + 4, 800},
    {-HX - 4, -120, -1300}, {-HX - 4, -120, 1300}, {-HX - 4, 120, 1300}, {-HX - 4, 120, -1300},
    {HX + 4, -120, -1300}, {HX + 4, -120, 1300}, {HX + 4, 120, 1300}, {HX + 4, 120, -1300},
    {-1300, -120, HZ + 4}, {1300, -120, HZ + 4}, {1300, 120, HZ + 4}, {-1300, 120, HZ + 4},
    {-1300, -120, -HZ - 4}, {1300, -120, -HZ - 4}, {1300, 120, -HZ - 4}, {-1300, 120, -HZ - 4},
    {1200, HY, 1200}, {1450, HY, 1200}, {1325, HY, 1450}, {1325, HY + 1600, 1325},
};
static const MFace hub_f[] = {
    F4(M_STEEL, 0, 0, 1, 2, 3), F4(M_CONCRETE, 0, 4, 5, 6, 7), F4(M_SHIP, 0, 0, 3, 7, 4),
    F4(M_SHIP, 0, 1, 2, 6, 5), F4(M_SHIP, 0, 3, 2, 6, 7), F4(M_SHIP, 0, 0, 1, 5, 4),
    F4(M_ACCENT, 0, 8, 9, 10, 11), F4(M_GLOW, MF_GLOW, 12, 13, 14, 15), F4(M_GLOW, MF_GLOW, 16, 17, 18, 19),
    F4(M_GLOW, MF_GLOW, 20, 21, 22, 23), F4(M_GLOW, MF_GLOW, 24, 25, 26, 27),
    F3(M_STUNT, MF_TWO, 28, 29, 31), F3(M_STUNT, MF_TWO, 29, 30, 31), F3(M_STUNT, MF_TWO, 30, 28, 31),
};

/* The ring around the hub, built at start-up: 8 sides, and 4 spokes. */
#define RING_N 8
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

static V3 nbuf[160] EWRAM_BSS;
Model mdl_car, mdl_arwing, mdl_hub, mdl_ring, mdl_rock;

static void setup(Model *md, const MVert *v, int nv, const MFace *f, int nf, int radius, V3 **nb)
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
        s32 ro = 6600, ri = 5900, h = 260;
        ring_v[i] = (MVert){(s16)((ro * s) >> 14), (s16)h, (s16)((ro * c) >> 14)};
        ring_v[RING_N + i] = (MVert){(s16)((ro * s) >> 14), (s16)-h, (s16)((ro * c) >> 14)};
        ring_v[2 * RING_N + i] = (MVert){(s16)((ri * s) >> 14), (s16)h, (s16)((ri * c) >> 14)};
        ring_v[3 * RING_N + i] = (MVert){(s16)((ri * s) >> 14), (s16)-h, (s16)((ri * c) >> 14)};
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
        ring_v[nv] = (MVert){(s16)(x0 + px), 0, (s16)(z0 + pz)};
        ring_v[nv + 1] = (MVert){(s16)(x1 + px), 0, (s16)(z1 + pz)};
        ring_v[nv + 2] = (MVert){(s16)(x1 - px), 0, (s16)(z1 - pz)};
        ring_v[nv + 3] = (MVert){(s16)(x0 - px), 0, (s16)(z0 - pz)};
        ring_f[nf++] = (MFace)F4(M_STEEL, MF_TWO, nv, nv + 1, nv + 2, nv + 3);
        nv += 4;
    }
    V3 *nb = nbuf;
    setup(&mdl_car, car_v, sizeof car_v / sizeof car_v[0], car_f, sizeof car_f / sizeof car_f[0], 300, &nb);
    setup(&mdl_arwing, arwing_v, sizeof arwing_v / sizeof arwing_v[0], arwing_f, sizeof arwing_f / sizeof arwing_f[0], 450, &nb);
    setup(&mdl_hub, hub_v, sizeof hub_v / sizeof hub_v[0], hub_f, sizeof hub_f / sizeof hub_f[0], 2400, &nb);
    setup(&mdl_ring, ring_v, nv, ring_f, nf, 6700, &nb);
    setup(&mdl_rock, rock_v, sizeof rock_v / sizeof rock_v[0], rock_f, sizeof rock_f / sizeof rock_f[0], 270, &nb);
}
