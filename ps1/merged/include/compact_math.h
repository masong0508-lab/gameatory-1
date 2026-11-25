/* PS1-native compact tables; bit-exact reconstruction, generated privately. */
#ifndef SF_COMPACT_MATH_H
#define SF_COMPACT_MATH_H
#include "gba.h"
extern const s16 sfcm_sin_q[1025];
extern const u16 sfcm_rtab_lo[2048];
extern const u8 sfcm_rtab_hi[1024];
extern const u32 sfcm_erecip_hi[257];
extern const u16 sfcm_erecip_lo[2304];
/* Keep one copy of the quadrant decoding code, even under module LTO. */
s32 sfcm_sin(u32 angle);
static inline u32 sfcm_rtab(u32 i){
    u32 hi=(sfcm_rtab_hi[i>>1]>>(4*(i&1)))&15u;
    return ((hi+8u)<<16)|sfcm_rtab_lo[i];
}
static inline u32 sfcm_erecip(u32 i){
    return i<=256u ? sfcm_erecip_hi[i] : sfcm_erecip_lo[i-257u];
}
#endif
