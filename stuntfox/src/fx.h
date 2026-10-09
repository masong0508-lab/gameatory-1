/* Fixed-point maths: vectors in world units, rotations as basis vectors in 1.14 (16384 = 1). */
#ifndef FX_H
#define FX_H
#include "gba.h"

#define ONE 16384
#define ANG_TURN 65536                     /* angles are u16, 65536 per turn */

typedef struct { s32 x, y, z; } V3;
typedef struct { V3 r, u, f; } M3;          /* right, up, forward: columns of local -> world */

extern const s16 sin_table[4096];

static inline s32 fsin(s32 a) { return sin_table[(a >> 4) & 4095]; }
static inline s32 fcos(s32 a) { return sin_table[((a >> 4) + 1024) & 4095]; }

static inline V3 v3(s32 x, s32 y, s32 z) { V3 v = {x, y, z}; return v; }
static inline V3 vadd(V3 a, V3 b) { return v3(a.x + b.x, a.y + b.y, a.z + b.z); }
static inline V3 vsub(V3 a, V3 b) { return v3(a.x - b.x, a.y - b.y, a.z - b.z); }
static inline V3 vscale(V3 a, s32 k) { return v3((a.x * k) >> 14, (a.y * k) >> 14, (a.z * k) >> 14); }
static inline V3 vshr(V3 a, int s) { return v3(a.x >> s, a.y >> s, a.z >> s); }
static inline s32 vdot(V3 a, V3 b) { return (a.x * b.x + a.y * b.y + a.z * b.z) >> 14; }
static inline V3 vcross(V3 a, V3 b)
{
    return v3((a.y * b.z - a.z * b.y) >> 14, (a.z * b.x - a.x * b.z) >> 14, (a.x * b.y - a.y * b.x) >> 14);
}
/* local (in units) -> world offset */
static inline V3 mlocal(const M3 *m, V3 l)
{
    return v3((m->r.x * l.x + m->u.x * l.y + m->f.x * l.z) >> 14,
              (m->r.y * l.x + m->u.y * l.y + m->f.y * l.z) >> 14,
              (m->r.z * l.x + m->u.z * l.y + m->f.z * l.z) >> 14);
}
/* world offset -> local */
static inline V3 mworld(const M3 *m, V3 w) { return v3(vdot(m->r, w), vdot(m->u, w), vdot(m->f, w)); }

u32 isqrt(u32 v);
s32 vlen(V3 v);                             /* for |components| < 46000 */
V3 vnorm(V3 v);                             /* to length ONE */
void morth(M3 *m);                          /* re-orthonormalise, keeping forward */
void mrotate(M3 *m, V3 w);                  /* small rotation by vector w (1.14 radians), world frame */
void myaw(M3 *m, s32 a);                    /* identity rotated by heading a around world up */
u16 fatan2(s32 y, s32 x);                   /* angle of (x, y), 65536 per turn */
s32 fdiv(s32 a, s32 b);                     /* a / b through the BIOS */

#endif
