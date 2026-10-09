#ifndef LOOPS_H
#define LOOPS_H
#include "world.h"

#define LOOP_SEG 24
void loop_frame(const Loop *lp, V3 *fwd, V3 *side);
/* point on the track centre line at angle ang (0 at the entry, 65536 for a full turn),
   shifted sideways by lat */
void loop_at(const Loop *lp, s32 ang, s32 lat, V3 *out);
void loop_point(const Loop *lp, int i, s32 lat, V3 *out);
#endif
