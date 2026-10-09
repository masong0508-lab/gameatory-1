/* Payback's vehicles and people as Stunt Fox models (MERGE build). */
#ifndef TRAFFIC_H
#define TRAFFIC_H
#include "model.h"

extern Model mdl_saloon, mdl_limo, mdl_pickup, mdl_sport, mdl_van, mdl_bus, mdl_tank;
extern Model mdl_stand, mdl_stride_a, mdl_stride_b, mdl_punch;
extern Model mdl_hero[4][2];       /* the player (legs, body): standing, two strides, a punch */
void traffic_init(void);

#endif
