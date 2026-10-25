/* The shapes of the city's bigger pirates (sgx.c): a turret, a winged gunship, a long hull and the mothership.
   Plain ROM data. Their face normals are worked out by model_init on the host (tools/sgnorm.py writes
   sgnorm.inc: tests/s2/sgmodels.py holds the file to it), so nothing about them takes RAM. */
#ifndef SGMODELS_H
#define SGMODELS_H
#include "model.h"
#include "palette.h"

#define F3(m, fl, a, b, c) {3, m, fl, {a, b, c}}
#define F4(m, fl, a, b, c, d) {4, m, fl, {a, b, c, d}}

/* a gun turret on a roof: a truncated pyramid with a lit top (8 points) */
static const MVert turret_v[] = {
    {-230, 0, -230}, {230, 0, -230}, {230, 0, 230}, {-230, 0, 230},
    {-130, 170, -130}, {130, 170, -130}, {130, 170, 130}, {-130, 170, 130},
};
static const MFace turret_f[] = {
    F4(M_STEEL, 0, 0, 1, 5, 4), F4(M_ROAD, 0, 1, 2, 6, 5), F4(M_STEEL, 0, 2, 3, 7, 6), F4(M_ROAD, 0, 3, 0, 4, 7),
    F4(M_GLOW, MF_GLOW, 4, 5, 6, 7),
};

/* a gunship: a dark dart, swept wings, a fin, engines lit at the stern; M_CAR is the trim (model_body) */
static const MVert wing_v[] = {
    {0, 0, 900}, {-190, 80, -240}, {190, 80, -240}, {0, -150, -300}, {0, 200, -180},
    {-150, 20, 160}, {-190, 20, -300}, {-1000, -90, -760},
    {150, 20, 160}, {190, 20, -300}, {1000, -90, -760},
    {0, 200, -180}, {0, 520, -620}, {0, 80, -520},
    {-170, -40, -246}, {-30, -40, -246}, {-30, 100, -246}, {-170, 100, -246},
    {30, -40, -246}, {170, -40, -246}, {170, 100, -246}, {30, 100, -246},
};
static const MFace wing_f[] = {
    F3(M_ROAD, 0, 0, 1, 4), F3(M_ROAD, 0, 0, 4, 2), F3(M_STEEL, 0, 0, 2, 3), F3(M_STEEL, 0, 0, 3, 1),
    F3(M_ROAD, 0, 1, 4, 2),
    F3(M_ROAD, MF_TWO, 5, 6, 7), F3(M_CAR, MF_TWO, 8, 9, 10),
    F3(M_CAR, MF_TWO, 11, 12, 13),
    F4(M_GLOW, MF_GLOW, 14, 15, 16, 17), F4(M_GLOW, MF_GLOW, 18, 19, 20, 21),
};

/* a long hull (frigate, barge): a nose cone, a slab with a bridge tower and two lit engines */
static const MVert hull_v[] = {
    {0, 40, 2700},
    {-520, -260, 1200}, {520, -260, 1200}, {520, 340, 1200}, {-520, 340, 1200},
    {-640, -300, -2200}, {640, -300, -2200}, {640, 400, -2200}, {-640, 400, -2200},
    {-210, 340, -1500}, {210, 340, -1500}, {210, 340, -800}, {-210, 340, -800},
    {-150, 760, -1400}, {150, 760, -1400}, {150, 760, -900}, {-150, 760, -900},
    {-480, -160, -2204}, {-120, -160, -2204}, {-120, 240, -2204}, {-480, 240, -2204},
    {120, -160, -2204}, {480, -160, -2204}, {480, 240, -2204}, {120, 240, -2204},
};
static const MFace hull_f[] = {
    F3(M_STEEL, 0, 0, 1, 2), F3(M_ROAD, 0, 0, 2, 3), F3(M_STEEL, 0, 0, 3, 4), F3(M_ROAD, 0, 0, 4, 1),
    F4(M_STEEL, 0, 1, 2, 6, 5), F4(M_ROAD, 0, 4, 3, 7, 8), F4(M_CAR, 0, 1, 5, 8, 4), F4(M_CAR, 0, 2, 3, 7, 6),
    F4(M_STEEL, 0, 5, 6, 7, 8),
    F4(M_STEEL, 0, 9, 10, 14, 13), F4(M_ROAD, 0, 10, 11, 15, 14), F4(M_STEEL, 0, 11, 12, 16, 15),
    F4(M_ROAD, 0, 12, 9, 13, 16), F4(M_STUNT, 0, 13, 14, 15, 16),
    F4(M_GLOW, MF_GLOW, 17, 18, 19, 20), F4(M_GLOW, MF_GLOW, 21, 22, 23, 24),
};

/* the mothership: a hexagonal saucer with a glowing core on top */
#define DISC_V(r, y) {0, y, r}, {(r) * 87 / 100, y, (r) / 2}, {(r) * 87 / 100, y, -(r) / 2}, \
                     {0, y, -(r)}, {-(r) * 87 / 100, y, -(r) / 2}, {-(r) * 87 / 100, y, (r) / 2}
static const MVert disc_v[] = {
    DISC_V(3000, 0), DISC_V(1900, 520), DISC_V(1300, -420), {0, 1100, 0}, {0, -760, 0},
};
static const MFace disc_f[] = {
    F4(M_STEEL, 0, 0, 1, 7, 6), F4(M_ROAD, 0, 1, 2, 8, 7), F4(M_STEEL, 0, 2, 3, 9, 8),
    F4(M_ROAD, 0, 3, 4, 10, 9), F4(M_STEEL, 0, 4, 5, 11, 10), F4(M_ROAD, 0, 5, 0, 6, 11),
    F3(M_GLOW, MF_GLOW, 6, 7, 18), F3(M_ACCENT, MF_GLOW, 7, 8, 18), F3(M_GLOW, MF_GLOW, 8, 9, 18),
    F3(M_ACCENT, MF_GLOW, 9, 10, 18), F3(M_GLOW, MF_GLOW, 10, 11, 18), F3(M_ACCENT, MF_GLOW, 11, 6, 18),
    F4(M_CAR, 0, 0, 12, 13, 1), F4(M_STEEL, 0, 1, 13, 14, 2), F4(M_CAR, 0, 2, 14, 15, 3),
    F4(M_STEEL, 0, 3, 15, 16, 4), F4(M_CAR, 0, 4, 16, 17, 5), F4(M_STEEL, 0, 5, 17, 12, 0),
    F3(M_ROAD, 0, 12, 13, 19), F3(M_ROAD, 0, 13, 14, 19), F3(M_ROAD, 0, 14, 15, 19),
    F3(M_ROAD, 0, 15, 16, 19), F3(M_ROAD, 0, 16, 17, 19), F3(M_ROAD, 0, 17, 12, 19),
};

/* the same three from afar (a boss from more than twice its size away, an ace from a few thousand units): about half the faces, the
   same outlines, since what a frame can draw is a handful of polygons */
static const MVert wing_lo_v[] = {
    {0, 0, 900}, {-1000, -90, -760}, {1000, -90, -760}, {0, 0, -300},
    {0, 200, -180}, {0, 520, -620}, {0, 80, -520},
    {-170, -40, -300}, {170, -40, -300}, {170, 100, -300}, {-170, 100, -300},
};
static const MFace wing_lo_f[] = {
    F3(M_ROAD, MF_TWO, 0, 1, 3), F3(M_ROAD, MF_TWO, 0, 3, 2), F3(M_CAR, MF_TWO, 4, 5, 6),
    F4(M_GLOW, MF_GLOW, 7, 8, 9, 10),
};

static const MVert hull_lo_v[] = {
    {0, 40, 2700},
    {-520, -260, 1200}, {520, -260, 1200}, {520, 340, 1200}, {-520, 340, 1200},
    {-640, -300, -2200}, {640, -300, -2200}, {640, 400, -2200}, {-640, 400, -2200},
};
static const MFace hull_lo_f[] = {
    F3(M_STEEL, 0, 0, 1, 2), F3(M_ROAD, 0, 0, 2, 3), F3(M_STEEL, 0, 0, 3, 4), F3(M_ROAD, 0, 0, 4, 1),
    F4(M_STEEL, 0, 1, 2, 6, 5), F4(M_ROAD, 0, 4, 3, 7, 8), F4(M_CAR, 0, 1, 5, 8, 4), F4(M_CAR, 0, 2, 3, 7, 6),
    F4(M_GLOW, MF_GLOW, 5, 6, 7, 8),
};

static const MVert disc_lo_v[] = {
    {0, 0, 3000}, {2610, 0, 1500}, {2610, 0, -1500}, {0, 0, -3000}, {-2610, 0, -1500}, {-2610, 0, 1500}, {0, 1100, 0}, {0, -760, 0},
};
static const MFace disc_lo_f[] = {
    F3(M_GLOW, MF_GLOW, 0, 1, 6), F3(M_ACCENT, MF_GLOW, 1, 2, 6), F3(M_GLOW, MF_GLOW, 2, 3, 6),
    F3(M_ACCENT, MF_GLOW, 3, 4, 6), F3(M_GLOW, MF_GLOW, 4, 5, 6), F3(M_ACCENT, MF_GLOW, 5, 0, 6),
    F3(M_STEEL, 0, 1, 0, 7), F3(M_ROAD, 0, 2, 1, 7), F3(M_STEEL, 0, 3, 2, 7),
    F3(M_ROAD, 0, 4, 3, 7), F3(M_STEEL, 0, 5, 4, 7), F3(M_ROAD, 0, 0, 5, 7),
};

#endif
