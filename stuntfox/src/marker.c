/* The marker for a ringing phone, a mission's start, a checkpoint or a courier's roof: a ring on the ground (or roof),
   a gem turning a cell over it, and a thin shaft that fades out (it used to be a panel six cells tall, which read as a
   beam to the sky). Steady in colour and light, never a flash. Thumb, in ROM. The ring and gem are one model of 10
   faces (4 of the gem's 8 are turned away), the shaft two thin polygons: about the cost of the two panels it replaces. */
#include "model.h"
#include "render.h"
#include "palette.h"

#define MARK_FAR 36000                   /* the farthest it is drawn (r_cam reaches 40000) */
#define SHAFT_H 2000                     /* the shaft's top, up close */

static inline s32 ab(s32 v) { return v < 0 ? -v : v; }

void marker_draw(V3 p, int mat)
{
    V3 d = vsub(p, cam.pos);
    s32 far = ab(d.x) > ab(d.z) ? ab(d.x) : ab(d.z);
    if (far > MARK_FAR || ab(d.y) > MARK_FAR)
        return;
    /* bigger from afar so it shows (2.5 times by 15 cells, and the shaft a little taller: 1.75 times) */
    s32 s = 256 + (far > 15000 ? 15000 : far) / 40, hs = s + 256 >> 1;
    s32 rad = (SHAFT_H + 300) * hs >> 8;           /* (the whole marker is inside this ball) */
    V3 t = r_cam(p);
    if (t.z < -rad || FOCAL * t.x - 121 * t.z > rad * FRX || -FOCAL * t.x - 121 * t.z > rad * FRX ||
        FOCAL * t.y - 81 * t.z > rad * FRY || -FOCAL * t.y - 81 * t.z > rad * FRY)
        return;
    M3 m;
    Place pl;
    u8 body = model_body;
    model_body = mat;
    myaw(&m, frame_count * 96);                    /* (turns once in about 11 s) */
    if (model_place(&pl, p, &m, s, 0, mdl_beacon.radius)) {
        pl.fog = 0;                      /* (no fog on it: steady in colour at any distance, so it shows from afar) */
        model_draw(&mdl_beacon, &pl);
    }
    /* the shaft: two screen-facing segments, the upper fainter (a step further into the fog colour), narrowing to a
       point; drawn from behind the gem (a key a little farther than its) */
    V3 up = v3(cam.m.r.y, cam.m.u.y, cam.m.f.y);
    static const u16 seg[3][2] = {{0, 56}, {800, 34}, {SHAFT_H, 0}};
    for (int i = 0; i < 2; i++) {
        V3 a = vadd(t, vscale(up, seg[i][0] * hs >> 8)), b = vadd(t, vscale(up, seg[i + 1][0] * hs >> 8));
        s32 wa = seg[i][1] * s >> 8, wb = seg[i + 1][1] * s >> 8;
        V3 q[4] = {v3(a.x - wa, a.y, a.z), v3(a.x + wa, a.y, a.z), v3(b.x + wb, b.y, b.z), v3(b.x - wb, b.y, b.z)};
        r_poly(q, wb ? 4 : 3, COLOR(mat, 3, i * 2), (t.z < 0 ? 0 : t.z) + 120, 0);
    }
    model_body = body;
}
