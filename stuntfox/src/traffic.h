/* Payback's vehicles and people as Stunt Fox models (MERGE build). */
#ifndef TRAFFIC_H
#define TRAFFIC_H
#include "model.h"

extern MODEL_ROM Model mdl_saloon, mdl_limo, mdl_pickup, mdl_sport, mdl_van, mdl_bus, mdl_tank;
/* a vehicle's extras (wheels, lamps, a taxi's sign, a police car's stripes), drawn first and only when it is near */
extern MODEL_ROM Model mdl_saloon_x, mdl_taxi_x, mdl_police_x, mdl_limo_x, mdl_pickup_x, mdl_sport_x, mdl_van_x, mdl_bus_x;
extern MODEL_ROM Model mdl_stand, mdl_stride_a, mdl_stride_b, mdl_punch;
extern MODEL_ROM Model mdl_hero[4][3];       /* the player (legs, body and head, arms): standing, two strides, a punch */
extern MODEL_ROM Model mdl_swim[2];          /* ... swimming: his back, his head */
void traffic_init(void);

#endif
