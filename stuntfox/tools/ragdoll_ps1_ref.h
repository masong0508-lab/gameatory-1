/* Ragdoll solver for the PS1 port: the reference that runs on the PC (tools/ragdoll_ps1_ref.c), and the API
   the port calls. Integer only (no float, no libm), so the PC and the console give the same bits; the
   console's version is this file recompiled with the GTE doing the dot products (design/ragdoll_ps1.md).
   Nothing here goes into the GBA ROM. Units: Q12.20 metres (RP_ONE = 1 m), seconds, kilograms. */
#ifndef RAGDOLL_PS1_REF_H
#define RAGDOLL_PS1_REF_H
#include <stdint.h>

typedef int32_t fx;
#define RP_FB 20
#define RP_ONE (1 << RP_FB)
typedef struct { fx x, y, z; } rp_v3;

#define RP_P 18                    /* particles: the joints */
#define RP_BONES 17                /* capsules: the bodies of the doll */
#define RP_EVENTS 16

enum { RP_PELVIS, RP_SPINE, RP_CHEST, RP_HEAD, RP_SHL, RP_SHR, RP_ELL, RP_ELR, RP_HDL, RP_HDR,
       RP_HPL, RP_HPR, RP_KNL, RP_KNR, RP_ANL, RP_ANR, RP_TOL, RP_TOR };

/* the world, as the game already has it (cells with heights and ramp shapes, bridge decks, solid boxes
   and railings): three queries, all in metres. The solver never owns world data. */
typedef struct rp_world {
    void *user;
    /* the support surface under (x, z) as seen from a point at height y: the highest floor not more than
       `step` above it (a deck the point is over, else the ground, else the water's surface). h = its
       height, n = its normal (unit, Q20), mat = its material (rp_surface index). 0 if there is none. */
    int (*floor)(void *u, fx x, fx z, fx y, fx *h, rp_v3 *n, int *mat);
    /* a ball of radius r at p inside something solid (a building, a railing, a deck's side): the way out
       (unit normal) and how far (depth > 0). 0 if clear. */
    int (*solid)(void *u, rp_v3 p, fx r, rp_v3 *n, fx *depth);
    /* the ball's swept path a->b: the first solid it touches (t in Q20 of the path, normal there). 0 if clear.
       This is what stops a fast body going through a thin wall or deck between two substeps. */
    int (*sweep)(void *u, rp_v3 a, rp_v3 b, fx r, fx *t, rp_v3 *n);
} rp_world;

/* surfaces: friction and the share of a landing kept (both Q20 fractions) */
typedef struct { fx mu, e; } rp_surface;
enum { RP_ROAD, RP_GRASS, RP_SAND, RP_WATER, RP_ROOF, RP_NSURF };
extern rp_surface rp_surfaces[RP_NSURF];

typedef struct { rp_v3 pos, vel; fx half_x, half_y, half_z; fx m[9]; fx mass; } rp_car;   /* an oriented box; m: local->world rows */

enum { RP_EV_FLOOR, RP_EV_WALL, RP_EV_CAR, RP_EV_SELF };
typedef struct { uint8_t kind, part, mat; fx strength; } rp_event;   /* strength: the speed change (m/s) of the hit */

typedef struct {
    rp_v3 pos[RP_P], vel[RP_P];
    uint8_t state;                 /* RP_FREE, RP_LIVE, RP_ASLEEP */
    uint8_t nsub;                  /* substeps the last frame used */
    uint16_t quiet;                /* frames hardly moving */
    fx brace;                      /* 0 limp .. RP_ONE: how hard the motors hold the target pose */
    uint8_t pose;                  /* RP_POSE_* the motors aim at */
    uint8_t contacts;              /* particles touching something last frame */
    /* what the last frame cost the doll and the car (the game turns these into health, sound, shake) */
    int32_t hurt;                  /* the frame's impacts over 3 m/s, joules (half m v^2 of each joint's speed change): fall damage, flinch, sound */
    int32_t hurt_car;              /* the part of it that came from the car (the car's own damage) */
    int nev; rp_event ev[RP_EVENTS];
    uint32_t steps;                /* substeps run, in all */
} rp_doll;
enum { RP_FREE, RP_LIVE, RP_ASLEEP };
enum { RP_POSE_NONE, RP_POSE_BRACE, RP_POSE_STAND, RP_POSE_FETAL, RP_NPOSE };

/* a standing doll at feet, facing yaw (65536 a turn), with velocity v (m/s) and spin w about its middle (rad/s) */
void rp_spawn(rp_doll *d, rp_v3 feet, int yaw, rp_v3 v, rp_v3 w);
/* one 60 Hz frame. car may be 0. Fixed, deterministic: the same inputs give the same bits. */
void rp_step(rp_doll *d, const rp_world *w, const rp_car *car);
void rp_wake(rp_doll *d);
void rp_impulse(rp_doll *d, int part, rp_v3 dv);        /* a hit (a bullet, a blast): speed added to one joint */
void rp_motor(rp_doll *d, int pose, fx brace);          /* the motors: brace for a landing, get up */
rp_v3 rp_bone_a(const rp_doll *d, int bone);            /* a capsule's ends, for drawing and skinning */
rp_v3 rp_bone_b(const rp_doll *d, int bone);
fx rp_bone_r(int bone);
void rp_frame(const rp_doll *d, int bone, fx m[9]);     /* the bone's frame (rows: right, up, along), for skinned meshes */
uint32_t rp_hash(const rp_doll *d);                     /* for the determinism tests */
int64_t rp_energy(const rp_doll *d);                    /* kinetic + potential, J, Q20 (64 bits: 2000 J is over 2^31) */
int rp_bones_of_doll(void);

/* a ready world for tests and tools: a height field of 16 m cells and boxes (rp_boxworld_*). */
#define RP_BW_CELLS 32
#define RP_BW_BOXES 32
typedef struct { rp_v3 lo, hi; } rp_box;
typedef struct {
    fx h[RP_BW_CELLS][RP_BW_CELLS];       /* height at the cell's corners (metres) */
    uint8_t mat[RP_BW_CELLS][RP_BW_CELLS];
    rp_box box[RP_BW_BOXES];
    int nbox;
    fx cell;                              /* cell size, m */
    rp_world w;
} rp_boxworld;
void rp_boxworld_init(rp_boxworld *b, fx cell);
void rp_boxworld_add(rp_boxworld *b, rp_v3 lo, rp_v3 hi);

#endif
