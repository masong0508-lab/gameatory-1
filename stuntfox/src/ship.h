/* The Arwing: flies with arcade aerodynamics, lands on its gear anywhere flat (rooftops, the
   space station deck) and keeps flying above the sky into space. */
#ifndef SHIP_H
#define SHIP_H
#include "physics.h"

typedef struct {
    Body b;
    int gear;                  /* gear legs touching */
    u8 gear_kind;              /* surface under the gear (SURF_*) */
    s32 comp[3];
    s32 impact;
    int boosting;
    int rolling;               /* barrel roll ticks left */
    s32 roll_dir;
} Ship;

extern const V3 ship_gear[3];
#define SHIP_SUSP 90

void ship_reset(Ship *s, V3 pos_units, s32 heading);   /* parked on the ground at pos */
void ship_update(Ship *s, u16 keys);

#endif
