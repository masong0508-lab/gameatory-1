
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

/* The vehicles (a body and its extras: wheels, lamps, signs, drawn only near and first: merge.c's looks) and the player
   (three parts, four poses) are drawn by tools/mkcars.py, which writes cars.h; read its notes before changing a point. */
#include "cars.h"

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
/* a punch (or a shot): the right arm straight out in front, the feet apart */
static const MVert punch_v[] = {
    BOX(-26, -4, 0, 100, 25, 0, 13), BOX(4, 26, 0, 100, -25, 0, 13), BOX(-34, 34, 98, 180, 0, 0, 18),
    BOX(-16, 16, 184, 226, 0, 0, 16),
    {-38, 175, -8}, {-38, 175, 8}, {-38, 115, 30}, {-38, 115, 14},
    {38, 168, 0}, {38, 182, 0}, {30, 182, 115}, {30, 168, 115},
};

#define N(a) (sizeof a / sizeof a[0])
/* The player: a better-made person (cars.h): shoes and trousers (model_legs) with knees, a jacket from belt to shoulders in
   rings, a head with eyes, a fringe and hair, then the arms in three parts (sleeves model_body, hands skin). Three models
   (model_draw takes at most 56 points), each pose with its own normals: the limbs lean, so a model's centre is no help to
   find which way a face looks and every one of his faces carries its winding (MF_WIND). */
enum {
    HN_LO0 = 0, HN_LO1 = HN_LO0 + N(hero_lo_f0), HN_LO2 = HN_LO1 + N(hero_lo_f1), HN_LO3 = HN_LO2 + N(hero_lo_f2),
    HN_MID = HN_LO3 + N(hero_lo_f3), HN_ARM0 = HN_MID + N(hero_mid_f), HN_ARM1 = HN_ARM0 + N(hero_arm_f0),
    HN_ARM2 = HN_ARM1 + N(hero_arm_f1), HN_ARM3 = HN_ARM2 + N(hero_arm_f2), HN_END = HN_ARM3 + N(hero_arm_f3)
};
#define HERO(i) {{hero_lo_v##i, hero_lo_f##i, N(hero_lo_v##i), N(hero_lo_f##i), 130, hero_n + HN_LO##i},                  \
                 {hero_mid_v, hero_mid_f, N(hero_mid_v), N(hero_mid_f), 150, hero_n + HN_MID},                           \
                 {hero_arm_v##i, hero_arm_f##i, N(hero_arm_v##i), N(hero_arm_f##i), 150, hero_n + HN_ARM##i}}
#ifndef NORMALS_HOST
/* RAM is short: the normals were worked out at build time (tools/mkconst.py) */
extern const N3 gen_hero_n[HN_END], gen_tnbuf[];
#include "constlen.h"
_Static_assert(HN_END == GEN_HERO_N, "the player's normals: traffic.c and tools/mkconst.py differ");
#define hero_n ((N3 *)gen_hero_n)
#define tnbuf ((N3 *)gen_tnbuf)
#define model_init(md)
#else
static N3 hero_n[HN_END] EWRAM_BSS;
static N3 tnbuf[600] EWRAM_BSS;
#endif
#define TOP(m, b) F4(m, 0, b + 4, b + 5, b + 6, b + 7)
/* The player swimming, as much of him as is over the water (at 0): the top of his back, then
   his head and hair (two models, so each box's faces turn the right way); merge.c draws his
   arms and the ripple round him */
static const MVert swim_back_v[] = {BOX(-32, 32, 0, 8, -6, -6, 34)};
static const MVert swim_head_v[] = {BOX(-15, 15, 0, 38, 36, 36, 15), BOX(-17, 17, 24, 46, 32, 32, 17)};
static const MFace swim_back_f[] = {SIDES(M_CAR, 0), TOP(M_CAR, 0)};
static const MFace swim_head_f[] = {SIDES(M_CREAM, 0), SIDES(M_ROAD, 8), TOP(M_ROAD, 8)};

#ifdef NORMALS_HOST
Model mdl_hero[4][3];
Model mdl_swim[2];

Model mdl_saloon, mdl_limo, mdl_pickup, mdl_sport, mdl_van, mdl_bus, mdl_tank;
Model mdl_saloon_x, mdl_taxi_x, mdl_police_x, mdl_limo_x, mdl_pickup_x, mdl_sport_x, mdl_van_x, mdl_bus_x;
Model mdl_stand, mdl_stride_a, mdl_stride_b, mdl_punch;

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
#define SET(m, v, f, r) setup(&m, v, N(v), f, N(f), r, &nb)
    SET(mdl_saloon, saloon_b_v, saloon_b_f, 290);
    SET(mdl_limo, limo_b_v, limo_b_f, 390);
    SET(mdl_pickup, pickup_b_v, pickup_b_f, 300);
    SET(mdl_sport, sport_b_v, sport_b_f, 300);
    SET(mdl_van, van_b_v, van_b_f, 340);
    SET(mdl_bus, bus_b_v, bus_b_f, 600);
    SET(mdl_tank, tank_b_v, tank_b_f, 520);
    SET(mdl_stand, stand_v, person_f, 140);
    SET(mdl_stride_a, stride_a_v, person_f, 140);
    SET(mdl_stride_b, stride_b_v, person_f, 140);
    SET(mdl_punch, punch_v, person_f, 150);
    SET(mdl_swim[0], swim_back_v, swim_back_f, 60);
    SET(mdl_swim[1], swim_head_v, swim_head_f, 70);
    SET(mdl_saloon_x, saloon_x_v, saloon_x_f, 290);
    SET(mdl_taxi_x, taxi_x_v, taxi_x_f, 290);
    SET(mdl_police_x, police_x_v, police_x_f, 290);
    SET(mdl_limo_x, limo_x_v, limo_x_f, 390);
    SET(mdl_pickup_x, pickup_x_v, pickup_x_f, 300);
    SET(mdl_sport_x, sport_x_v, sport_x_f, 300);
    SET(mdl_van_x, van_x_v, van_x_f, 340);
    SET(mdl_bus_x, bus_x_v, bus_x_f, 600);
#define HSET(i)                                                                                                       \
    do {                                                                                                              \
        N3 *lo = hero_n + HN_LO##i, *mid = hero_n + HN_MID, *arm = hero_n + HN_ARM##i;                                \
        setup(&mdl_hero[i][0], hero_lo_v##i, N(hero_lo_v##i), hero_lo_f##i, N(hero_lo_f##i), 130, &lo);               \
        setup(&mdl_hero[i][1], hero_mid_v, N(hero_mid_v), hero_mid_f, N(hero_mid_f), 150, &mid);                      \
        setup(&mdl_hero[i][2], hero_arm_v##i, N(hero_arm_v##i), hero_arm_f##i, N(hero_arm_f##i), 150, &arm);          \
    } while (0)
    HSET(0);
    HSET(1);
    HSET(2);
    HSET(3);
}
#else
/* the models are ROM const too: each one's normals are the next N(faces) of gen_tnbuf, in this order (tests/s2/models.py
   compares them with what start-up built in RAM) */
enum {
    O_SALOON, O_LIMO = O_SALOON + N(saloon_b_f), O_PICKUP = O_LIMO + N(limo_b_f), O_SPORT = O_PICKUP + N(pickup_b_f),
    O_VAN = O_SPORT + N(sport_b_f), O_BUS = O_VAN + N(van_b_f), O_TANK = O_BUS + N(bus_b_f), O_STAND = O_TANK + N(tank_b_f),
    O_STRIDE_A = O_STAND + N(person_f), O_STRIDE_B = O_STRIDE_A + N(person_f), O_PUNCH = O_STRIDE_B + N(person_f),
    O_SWIM = O_PUNCH + N(person_f), O_SALOON_X = O_SWIM + N(swim_back_f) + N(swim_head_f), O_TAXI_X = O_SALOON_X + N(saloon_x_f),
    O_POLICE_X = O_TAXI_X + N(taxi_x_f), O_LIMO_X = O_POLICE_X + N(police_x_f), O_PICKUP_X = O_LIMO_X + N(limo_x_f),
    O_SPORT_X = O_PICKUP_X + N(pickup_x_f), O_VAN_X = O_SPORT_X + N(sport_x_f), O_BUS_X = O_VAN_X + N(van_x_f),
    O_END = O_BUS_X + N(bus_x_f)
};
_Static_assert(O_END == GEN_TNBUF_N, "traffic.c's list and tools/mkconst.py's differ in length");
#define MODEL(m, v, f, r, o) const Model m = {v, f, N(v), N(f), r, tnbuf + (o)}
MODEL(mdl_saloon, saloon_b_v, saloon_b_f, 290, O_SALOON);
MODEL(mdl_limo, limo_b_v, limo_b_f, 390, O_LIMO);
MODEL(mdl_pickup, pickup_b_v, pickup_b_f, 300, O_PICKUP);
MODEL(mdl_sport, sport_b_v, sport_b_f, 300, O_SPORT);
MODEL(mdl_van, van_b_v, van_b_f, 340, O_VAN);
MODEL(mdl_bus, bus_b_v, bus_b_f, 600, O_BUS);
MODEL(mdl_tank, tank_b_v, tank_b_f, 520, O_TANK);
MODEL(mdl_stand, stand_v, person_f, 140, O_STAND);
MODEL(mdl_stride_a, stride_a_v, person_f, 140, O_STRIDE_A);
MODEL(mdl_stride_b, stride_b_v, person_f, 140, O_STRIDE_B);
MODEL(mdl_punch, punch_v, person_f, 150, O_PUNCH);
MODEL(mdl_saloon_x, saloon_x_v, saloon_x_f, 290, O_SALOON_X);
MODEL(mdl_taxi_x, taxi_x_v, taxi_x_f, 290, O_TAXI_X);
MODEL(mdl_police_x, police_x_v, police_x_f, 290, O_POLICE_X);
MODEL(mdl_limo_x, limo_x_v, limo_x_f, 390, O_LIMO_X);
MODEL(mdl_pickup_x, pickup_x_v, pickup_x_f, 300, O_PICKUP_X);
MODEL(mdl_sport_x, sport_x_v, sport_x_f, 300, O_SPORT_X);
MODEL(mdl_van_x, van_x_v, van_x_f, 340, O_VAN_X);
MODEL(mdl_bus_x, bus_x_v, bus_x_f, 600, O_BUS_X);
const Model mdl_swim[2] = {
    {swim_back_v, swim_back_f, N(swim_back_v), N(swim_back_f), 60, tnbuf + O_SWIM},
    {swim_head_v, swim_head_f, N(swim_head_v), N(swim_head_f), 70, tnbuf + O_SWIM + N(swim_back_f)},
};
const Model mdl_hero[4][3] = {HERO(0), HERO(1), HERO(2), HERO(3)};
void traffic_init(void) {}
#endif
