/* Rigid bodies and the surfaces they touch.

   Positions and velocities are in world units << 8 ("fine" units, per tick at 60 ticks a
   second); accelerations in fine units per tick squared. Angular velocity is a world-frame
   vector in 1.18 radians per tick. Mass is 1: forces are accelerations. */
#ifndef PHYSICS_H
#define PHYSICS_H
#include "fx.h"

#define FX 8
#define G_ACC 128                  /* gravity at street level, about 1.4 g */
#define SPACE_LO 12000             /* gravity and air start fading here (units of altitude) */
#define SPACE_HI 24000             /* ... and are gone here: space */

typedef struct {
    V3 pos, vel;
    M3 m;
    V3 w;
    s32 inv_i[3];                  /* 2^24 / moment of inertia (units^2), local x, y, z */
    V3 acc;                        /* force accumulator */
    V3 alpha;                      /* local angular acceleration accumulator, 1.18 */
} Body;

/* f (fine/tick^2) applied at offset r (units, world frame) from the centre of mass */
void body_force(Body *b, V3 r, V3 f);
/* impulse j (fine/tick) at offset r: changes velocity and spin at once */
void body_impulse(Body *b, V3 r, V3 j);
V3 body_point_vel(const Body *b, V3 r);
/* effective mass (256 = 1) of the body at offset r along unit normal n */
s32 body_eff_mass(const Body *b, V3 r, V3 n);
void body_integrate(Body *b);
/* resolve contact of the body point at offset r (units) against solid geometry: returns 1
   on contact and the impact speed (fine/tick) in *impact */
int body_collide(Body *b, V3 r, s32 bounce, s32 friction, s32 *impact);

/* 0 at street level .. 16384 in space */
s32 space_factor(s32 y_units);

enum { SURF_NONE, SURF_GROUND, SURF_LOOP, SURF_DECK, SURF_ROCK };

typedef struct {
    s32 dist;                      /* fine units */
    V3 n;                          /* surface normal, 1.14 */
    u8 kind;
    u8 idx;                        /* loop: which one */
    u16 ang;                       /* loop: angle around the loop where we touched */
} Hit;

/* Cast from p (fine) along -up up to max (fine) and return the nearest surface hit. */
int ray_surface(V3 p, V3 up, s32 max, Hit *h);
/* If p (fine) is inside solid geometry: depth (fine) and the way out. */
int penetrate(V3 p, Hit *h);
s32 ground_fine(s32 x, s32 z);

/* the space station and asteroids, positioned by space.c */
typedef struct { V3 c; s32 r; } Rock;
extern V3 station_pos;             /* units: centre of the hub */
extern Rock rocks[];
extern int nrocks;
#define HUB_HX 1600
#define HUB_HY 500
#define HUB_HZ 1600
/* the docking bay: a hangar inside the hub, open at its front (+z) face */
#define BAY_HX 800
#define BAY_Y0 (-420)
#define BAY_Y1 140
#define BAY_Z0 (-900)                 /* its back wall */
#define BAY_PAD_Z 250                 /* the landing pad's centre */

#endif
