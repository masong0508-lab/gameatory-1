/* Polygon models: the car, the Arwing, the space station and asteroids. */
#ifndef MODEL_H
#define MODEL_H
#include "fx.h"

typedef struct { s16 x, y, z; } N3;              /* a unit vector, 1.14 */
typedef struct { s16 x, y, z; } MVert;
typedef struct { u8 n, mat, flags, idx[6]; } MFace;
enum { MF_TWO = 1, MF_GLOW = 2 };              /* two-sided (thin fins and wings), self-lit */

typedef struct {
    const MVert *v;
    const MFace *f;
    u8 nv, nf;
    s16 radius;
    N3 *normal;                                 /* per face, local, filled by model_init */
} Model;

/* camera-space placement of a model for one frame */
typedef struct {
    V3 t;                                       /* origin in camera space */
    V3 ax, ay, az;                              /* model axes in camera space, 1.14, scaled */
    V3 nx, ny, nz;                              /* the same, unscaled (for normals) */
    const M3 *m;
    int fog;
} Place;

void model_init(Model *md);
/* scale: 256 = 1. far: positions further than about 30000 units away need shift 2 or 3. */
int model_place(Place *pl, V3 pos, const M3 *m, s32 scale, int shift, s32 radius);
void model_draw(const Model *md, const Place *pl);
/* one extra polygon in a placed model's frame (local units); two-sided */
void model_poly(const Place *pl, const MVert *v, int n, int color);

extern Model mdl_car, mdl_arwing, mdl_hub, mdl_ring, mdl_rock, mdl_ped, mdl_heli;
extern u8 model_body;                           /* paint for M_CAR faces, M_CAR by default */
extern u8 model_legs;                           /* paint for M_SKY faces (people's legs) */
void models_init(void);

#endif
