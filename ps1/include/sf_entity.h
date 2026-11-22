#ifndef PS1_SF_ENTITY_H
#define PS1_SF_ENTITY_H

/* Shared runtime/renderer ABI. The surrounding runtime defines s32/u16/u8.
 * Coordinates use 1024 units per cell. kind: 0 vehicle, 1 person.
 * spare is the guest entity index; look is descriptor+0x38 minus 0x1a;
 * pol is the police flag. A person's look of 0xfe selects the player outfit.
 */
typedef struct { s32 x, y, z; u16 yaw; u8 kind, spare, look, pol; } SfEnt;
_Static_assert(sizeof(SfEnt) == 20, "SfEnt size must match across modules");
_Static_assert(__builtin_offsetof(SfEnt, look) == 16, "SfEnt look offset");
_Static_assert(__builtin_offsetof(SfEnt, pol) == 17, "SfEnt police offset");

#endif
