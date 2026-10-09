#ifndef PALETTE_H
#define PALETTE_H
#include "gba.h"

enum {
    M_SKY, M_ROAD, M_KERB, M_GRASS, M_PLAZA, M_CONCRETE, M_GLASS, M_BRICK, M_TEAL, M_CREAM,
    M_STEEL, M_CAR, M_ACCENT, M_SHIP, M_GLOW, M_STUNT
};

/* colours as 5-bit r, g, b; written to palette_out (the BG palette unless changed) */
void palette_set(const u8 *zenith, const u8 *horizon, const u8 *fog);
extern u16 *palette_out;

#endif
