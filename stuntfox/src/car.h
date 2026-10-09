/* The car: a rigid body on four sprung wheels with tyre grip, a boost jet and air control. */
#ifndef CAR_H
#define CAR_H
#include "physics.h"

typedef struct {
    Body b;
    s32 steer;                 /* -16384 (left) .. 16384 (right), smoothed */
    s32 comp[4];               /* suspension compression, fine units (for drawing) */
    u8 touch[4];               /* surface under each wheel (SURF_*) */
    int wheels;                /* wheels touching anything */
    int on_loop;               /* wheels touching a loop */
    u16 loop_ang;              /* last angle around the loop under a wheel */
    u8 loop_idx;
    s32 boost;                 /* boost fuel, 0 .. 4096 */
    int boosting;
    s32 impact;                /* hardest body impact this tick (fine/tick) */
    s32 speed;                 /* forward speed, fine/tick (signed) */
} Car;

extern const V3 car_wheel[4];  /* wheel mounts, local units */
#define CAR_SUSP 72            /* suspension length, units */
#define CAR_WHEEL_R 36

void car_reset(Car *c, V3 pos_units, s32 heading);
void car_update(Car *c, u16 keys);

#endif
