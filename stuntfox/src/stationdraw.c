/* Fox Station's rooms on the screen (stage 2, S; station.h): a two-colour clear, then each room's parts as models seen from inside
   (no yaw in any camera: the D-pad means the same on every screen), the crew and the walker, and the names over the doors and the
   places. Flat shades only, no Payback tiles, no fog (merge.c sets that up before st_draw); the 2D over it is station.c's st_hud. */
#include "stage2.h"
#include "station.h"
#include "render.h"
#include "palette.h"
#include "draw2d.h"
#include "traffic.h"

#define PSCALE 384                 /* people are drawn 1.5 times their city size: the rooms are wide and the screen is small */

static void part_draw(const StRoom *rm, const StPart *pt, const M3 *m)
{
    Model md;
    md.v = (const MVert *)(st_blob + pt->off_v);
    md.f = (const MFace *)(st_blob + pt->off_f);
    md.nv = pt->nv;
    md.nf = pt->nf;
    md.radius = 9000;
    md.normal = (N3 *)(st_blob + pt->off_n);
    Place pl;
    (void)rm;
    if (model_place(&pl, v3(0, 0, 0), m, 256, 0, md.radius))
        model_draw(&md, &pl);
}

static void person(const Model *a, const Model *b, V3 at, u16 yaw, int body, int legs)
{
    M3 m;
    Place pl;
    myaw(&m, yaw);
    model_body = body;
    model_legs = legs;
    if (model_place(&pl, at, &m, PSCALE, 0, 150)) {
        model_draw(a, &pl);
        if (b)
            model_draw(b, &pl);
    }
}

void st_draw_room(void)
{
    const StRoom *rm = st_room(stw.room);
    d_fill(0, 0, 240, 80, COLOR(rm->ceilc, 0, 0));
    d_fill(0, 80, 240, 80, COLOR(rm->floorc, 1, 0));
    cam.pos = v3(stw.bx, stw.by, stw.bz);
    cam.m.f = v3(0, stw.bty - stw.by, stw.btz - stw.bz);
    cam.m.u = v3(0, ONE, 0);
    morth(&cam.m);                                       /* (not mirrored: the rooms are ours, and left is left) */
    M3 id;
    myaw(&id, 0);
    const StPart *pt = (const StPart *)(st_blob + rm->off_parts);
    for (int i = 0; i < rm->nparts; i++)
        part_draw(rm, &pt[i], &id);
    const StCrew *c = st_crews(rm);
    for (int i = 0; i < rm->ncrew; i++) {
        static const Model *const pose[3] = {&mdl_stand, &mdl_stride_a, &mdl_stride_b};
        person(pose[c[i].model % 3], 0, v3(c[i].x, 0, c[i].z), c[i].yaw, c[i].body, c[i].legs);
    }
    int p = stw.moving ? 1 + (stw.phase >> 3 & 1) : 0;
    person(&mdl_hero[p][0], &mdl_hero[p][1], v3(stw.x, 0, stw.z), stw.yaw, M_GLOW, M_GLASS);   /* (the stunt fox: orange jacket, jeans) */
    model_body = M_CAR;
    model_legs = M_ROAD;
}

static void tag(V3 w, const char *s, int color)
{
    V3 c = r_cam(w);
    if (c.z < 300 || !s[0])
        return;
    int x = 120 + fdiv(FOCAL * c.x, c.z), y = 80 - fdiv(FOCAL * c.y, c.z), n = 0;
    while (s[n])
        n++;
    if (x < 8 || x > 232)                              /* (a name whose door is off the edge is left out, not piled on its neighbour) */
        return;
    x -= n * TEXT_W / 2;
    x = x > 238 - n * TEXT_W ? 238 - n * TEXT_W : x < 2 ? 2 : x;   /* (keep the whole name on screen) */
    d_text(x, y - 4, s, color);
}

void st_draw_labels(void)
{
    const StRoom *rm = st_room(stw.room);
    const StUse *u = st_uses(rm);
    int near = stw.near >> 5 == U_TERM ? (stw.near & 31) - 1 : -1;
    for (int i = 0; i < rm->nuse; i++)
        if (u[i].ly >= 300)
            tag(v3(u[i].x, u[i].ly, u[i].z), st_text(u[i].label), i == near ? COLOR(M_ACCENT, 3, 0) : COLOR(M_CREAM, 3, 0));
    const StCrew *c = st_crews(rm);
    for (int i = 0; i < rm->ncrew; i++)
        tag(v3(c[i].x, 450, c[i].z), st_crew_name[c[i].crew & 7], stw.near >> 5 == U_TALK && (stw.near & 31) == i + 1 ? COLOR(M_ACCENT, 3, 0) : COLOR(M_STEEL, 3, 0));
}
