/* Loop geometry, shared by drawing and physics.

   A loop starts at its entry point on the road, heading along dir. Its track is a helix:
   a vertical circle of radius r whose centre line also moves sideways by the track width w
   over one turn, so the exit runs beside the entry instead of into it. */
#include "loops.h"

void loop_frame(const Loop *lp, V3 *fwd, V3 *side)
{
    static const s8 fx[4] = {0, 1, 0, -1}, fz[4] = {1, 0, -1, 0};
    int d = lp->dir & 3;
    *fwd = v3(fx[d] * ONE, 0, fz[d] * ONE);
    *side = v3(fz[d] * ONE, 0, -fx[d] * ONE);      /* right-hand side: cross(up, fwd) */
}

void loop_at(const Loop *lp, s32 ang, s32 lat, V3 *out)
{
    V3 f, s;
    loop_frame(lp, &f, &s);
    s32 r = lp->r;
    s32 along = (r * fsin(ang)) >> 14;
    s32 up = r - ((r * fcos(ang)) >> 14);
    s32 sideways = lat + ((lp->w * (ang >> 2)) >> 14);   /* w per full turn (65536) */
    out->x = lp->x + ((f.x * along + s.x * sideways) >> 14);
    out->y = up;
    out->z = lp->z + ((f.z * along + s.z * sideways) >> 14);
}

void loop_point(const Loop *lp, int i, s32 lat, V3 *out)
{
    loop_at(lp, i * (65536 / LOOP_SEG), lat, out);
}
