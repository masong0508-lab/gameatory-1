/* What a mission puts in the 3D scene (ms_draw3d, stage2.h): the start beacon, the objective's beacon, the next
   ring (and a mark for the one after), the pickups and the par ghost. Everything is steady in colour and
   in light: shapes turn slowly, nothing pulses or blinks. At most about 10k cycles a frame: a beacon is one
   panel turned to face the camera (the cost is the fill, and a second panel doubled it), a ring is four
   panels, a pickup is a coin, and nothing draws beyond 40 cells. */
#include "stage2.h"
#include "mission.h"
#include "model.h"
#include "render.h"
#include "palette.h"
#include "draw2d.h"

#define FAR_BEACON 40960           /* 40 cells */
#define FAR_PICK 26000
#define GHOST_NEAR 3000
#define NPICK 4

static inline s32 ab(s32 v) { return v < 0 ? -v : v; }

static V3 wpos(const MsPlace *p)
{
    s32 ox, oy;
    pb_window_origin(&ox, &oy);
    return v3((p->x8 + ox) * 128, p->h, (p->y8 + oy) * 128);
}

/* a point on screen, 0 if behind or off it */
static int project(V3 w, int *sx, int *sy)
{
    V3 d = vsub(w, cam.pos);
    while (ab(d.x) > 30000 || ab(d.y) > 30000 || ab(d.z) > 30000)
        d = vshr(d, 1);
    s32 z = vdot(cam.m.f, d);
    if (z < 64)
        return 0;
    *sx = 120 + FOCAL * vdot(cam.m.r, d) / z;
    *sy = 80 - FOCAL * vdot(cam.m.u, d) / z;
    return *sx > 6 && *sx < 234 && *sy > 6 && *sy < 154;
}

/* a mark where w is, over the scene (the nearest bucket): a diamond of the colour in a dark rim, two panels of the 2D
   kind (no clipping or transform: a few hundred cycles; four corner marks by pixels took 2.4k) */
static void mark(V3 w, int c)
{
    int x, y;
    if (!project(w, &x, &y))
        return;
    s32 cx = x * 16, cy = y * 16;
    s32 lit[8] = {cx, cy - 64, cx + 64, cy, cx, cy + 64, cx - 64, cy};
    s32 rim[8] = {cx, cy - 96, cx + 96, cy, cx, cy + 96, cx - 96, cy};
    r_poly2d(lit, 4, c, 0, 0);                      /* (the later one is drawn first in a bucket) */
    r_poly2d(rim, 4, COLOR(M_ROAD, 0, 0), 0, 0);
}

/* a shaft from a to b (camera space), w wide, wholly past one side of the view: the beacon's ball is as wide
   as it is tall and takes in most of the view, so model_place would let every one through */
static int shaft_out(V3 a, V3 b, s32 w)
{
    s32 x = w * FRX, y = w * FRY;
    return (a.z < -w && b.z < -w) || (FOCAL * a.x - 121 * a.z > x && FOCAL * b.x - 121 * b.z > x) ||
           (-FOCAL * a.x - 121 * a.z > x && -FOCAL * b.x - 121 * b.z > x) ||
           (FOCAL * a.y - 81 * a.z > y && FOCAL * b.y - 81 * b.z > y) ||
           (-FOCAL * a.y - 81 * a.z > y && -FOCAL * b.y - 81 * b.z > y);
}

static const MVert beacon_v[4] = {{-70, 0, 0}, {70, 0, 0}, {70, 6000, 0}, {-70, 6000, 0}};

static void beacon(const MsPlace *pl_, int mat)
{
    M3 m;
    Place pl;
    V3 p = wpos(pl_), d = vsub(p, cam.pos);
    s32 far = ab(d.x) > ab(d.z) ? ab(d.x) : ab(d.z);
    if (far > FAR_BEACON)
        return;
    s32 s = 384 + (far > 18000 ? 18000 : far) / 16, h = 6000 * s >> 8;     /* (wider far off: it must show from afar) */
    V3 a = r_cam(p);
    if (shaft_out(a, vadd(a, v3(cam.m.r.y * h >> 14, cam.m.u.y * h >> 14, cam.m.f.y * h >> 14)), 80 * s >> 8))
        return;
    /* half as wide up close (to 1 by 24 cells): a long panel is mostly fill, and fill is what it costs */
    s32 k = ONE / 2 + (far > 12000 ? (far > 24000 ? 12000 : far - 12000) * (ONE / 2) / 12000 : 0);
    myaw(&m, fatan2(-d.x, -d.z));                   /* (its face toward the camera) */
    m.r = vscale(m.r, k);
    if (model_place(&pl, p, &m, s, 0, 6000))
        model_poly(&pl, beacon_v, 4, COLOR(mat, 3, 0));
}

/* a ring is a square frame of four panels: the renderer takes ~1.5k to queue a panel, and the eight of an octagon were
   15k a frame. Its hole (+-500) has the gate's circle (700) at its corners. */
static const MVert ring_v[8] = {{-630, -630, 0}, {630, -630, 0}, {630, 630, 0}, {-630, 630, 0},
                                {-500, -500, 0}, {500, -500, 0}, {500, 500, 0}, {-500, 500, 0}};

/* world axis k (0 x, 1 y, 2 z), turned round if neg, in camera space (its model_place without the parts a flat frame
   has no use for: the third axis, the lighting, the fog) */
static V3 caxis(int k, int neg)
{
    V3 a = k == 0 ? v3(cam.m.r.x, cam.m.u.x, cam.m.f.x) : k == 1 ? v3(cam.m.r.y, cam.m.u.y, cam.m.f.y) : v3(cam.m.r.z, cam.m.u.z, cam.m.f.z);
    return neg ? v3(-a.x, -a.y, -a.z) : a;
}

/* a ring, facing along x, along z (Payback's y) or up */
static void ring(const MsPlace *pp, int mat)
{
    V3 p = wpos(pp), d = vsub(p, cam.pos);
    if (ab(d.x) > FAR_BEACON || ab(d.z) > FAR_BEACON || ab(d.y) > FAR_BEACON)
        return;
    int far = ab(d.x) > 28000 || ab(d.y) > 28000 || ab(d.z) > 28000 ? 2 : 0;
    s32 s = ((pp->r8 ? pp->r8 * 128 : 1536) * 187 >> 9) >> far;      /* (the model's 700 is the radius: 256 / 700) */
    s32 rad = 710 * s >> 8;
    V3 t = far ? r_cam_far(p, far) : r_cam(p);
    if (t.z < -rad || FOCAL * t.x - 121 * t.z > rad * FRX || -FOCAL * t.x - 121 * t.z > rad * FRX ||
        FOCAL * t.y - 81 * t.z > rad * FRY || -FOCAL * t.y - 81 * t.z > rad * FRY)
        return;
    V3 ax = vscale(pp->kind == PK_RING_X ? caxis(2, 1) : caxis(0, 0), s << 6);
    V3 ay = vscale(pp->kind == PK_RING_H ? caxis(2, 0) : caxis(1, 0), s << 6);
    V3 c[8];
    for (int i = 0; i < 8; i++) {                   /* (model.c's XF) */
        c[i].x = t.x + ((ax.x * ring_v[i].x + ay.x * ring_v[i].y) >> 14);
        c[i].y = t.y + ((ax.y * ring_v[i].x + ay.y * ring_v[i].y) >> 14);
        c[i].z = t.z + ((ax.z * ring_v[i].x + ay.z * ring_v[i].y) >> 14);
    }
    int col = COLOR(mat, 3, 0), key = t.z < 0 ? 0 : t.z;
    for (int i = 0; i < 4; i++) {
        int j = (i + 1) & 3;
        V3 q[4] = {c[i], c[j], c[4 + j], c[4 + i]};
        r_poly(q, 4, col, key, 0);
    }
}

/* the pickups not yet taken, the nearest NPICK within reach, as coins that turn */
static void pickups(const MisObj *o, u32 taken)
{
    M3 m;
    Place pl;
    int best[NPICK], nb = 0;
    s32 bd[NPICK];
    int n = o->n < 32 ? o->n : 32;
    for (int i = 0; i < n; i++) {
        if (taken >> i & 1)
            continue;
        const MsPlace *p = ms_place(o->place + i);
        if (!p)
            continue;
        V3 w = wpos(p);
        s32 dx = ab(w.x - cam.pos.x), dz = ab(w.z - cam.pos.z);
        if (dx > FAR_PICK || dz > FAR_PICK)
            continue;
        s32 dd = dx + dz;
        int k = nb;
        if (nb == NPICK) {                          /* (full: it must beat the farthest kept) */
            if (bd[NPICK - 1] <= dd)
                continue;
            k = NPICK - 1;
        } else
            nb++;
        for (; k > 0 && bd[k - 1] > dd; k--)
            bd[k] = bd[k - 1], best[k] = best[k - 1];
        bd[k] = dd, best[k] = i;
    }
    myaw(&m, frame_count * 300);                    /* (slowly: a third of a turn a second) */
    for (int k = 0; k < nb; k++) {
        V3 p = wpos(ms_place(o->place + best[k]));
        p.y += 140;
        if (model_place(&pl, p, &m, 300, 0, mdl_medal.radius))
            model_draw(&mdl_medal, &pl);
    }
}

/* where the par ghost is, clock seconds after the race began: along the checkpoints at the pace that
   finishes the laps in the mission's par; its heading */
static int ghost_at(const MisObj *o, const MisDef *d, V3 *out, s32 *head)
{
    int n = o->n > 16 ? 16 : o->n, laps = o->b > 0 ? o->b : 1;
    if (n < 2 || !d->par)
        return 0;
    s32 len[17], lap = 0;
    int legs = laps > 1 ? n : n - 1;
    for (int i = 0; i < legs; i++) {
        V3 a = wpos(ms_place(o->place + i)), b = wpos(ms_place(o->place + (i + 1) % n));
        s32 dx = ab(a.x - b.x), dz = ab(a.z - b.z), dy = ab(a.y - b.y);
        len[i] = (dx > dz ? dx + (dz >> 1) : dz + (dx >> 1)) + dy;
        lap += len[i];
    }
    if (!lap)
        return 0;
    s32 total = laps > 1 ? lap * laps : lap;
    s32 el = s2f.clock - ms_run.t_step, pace = d->par * 30;
    if (el < 0) el = 0;
    s32 s = total * ((el < pace ? el : pace) * 256 / pace) >> 8;       /* (s32 only: no 64-bit divide on this CPU) */
    if (laps > 1)
        s %= lap;
    for (int i = 0; i < legs; i++) {
        if (s <= len[i] || i == legs - 1) {
            V3 a = wpos(ms_place(o->place + i)), b = wpos(ms_place(o->place + (i + 1) % n));
            s32 k = len[i] ? s * 128 / len[i] : 0;
            if (k > 128) k = 128;
            *out = v3(a.x + ((b.x - a.x) * k >> 7), a.y + ((b.y - a.y) * k >> 7), a.z + ((b.z - a.z) * k >> 7));
            *head = fatan2(b.x - a.x, b.z - a.z);
            return 1;
        }
        s -= len[i];
    }
    return 0;
}

static void ghost(const MisObj *o, const MisDef *d)
{
    V3 g;
    s32 head;
    M3 m;
    Place pl;
    if (!ghost_at(o, d, &g, &head))
        return;
    V3 dd = vsub(g, cam.pos);
    s32 dist = ab(dd.x) + ab(dd.y) + ab(dd.z);
    const Model *md = o->mode == 3 ? &mdl_arwing : &mdl_car;
    if (dist < GHOST_NEAR + 3000 && ab(dd.x) < GHOST_NEAR && ab(dd.z) < GHOST_NEAR && ab(dd.y) < GHOST_NEAR) {
        myaw(&m, head);
        u8 body = model_body, hull = model_hull;
        model_body = M_TEAL, model_hull = M_TEAL;      /* (a teal ghost: not the player's own paint) */
        if (model_place(&pl, g, &m, 256, 0, md->radius))
            model_draw(md, &pl);
        model_body = body, model_hull = hull;
        return;
    }
    mark(g, COLOR(M_TEAL, 3, 0));
}

void ms_draw3d(void)
{
    MisRun *r = &ms_run;
    if (r->state == MS_IDLE || r->state == MS_DONE || r->state == MS_FAIL)
        return;
    const MisDef *d = ms_def(r->mis);
    if (!d)
        return;
    if (r->state == MS_ARMED) {
        const MsPlace *p = ms_place(r->ckpt ? ms_obj(d->obj0 + r->ckpt - 1)->place : d->start);
        if (p && d->kind != MK_MEDAL && !(r->flags & RF_QUIET)) {
            if (p->kind >= PK_RING_X && p->kind <= PK_RING_H)
                ring(p, M_ACCENT);
            else
                beacon(p, M_ACCENT);
        }
        model_body = M_CAR;
        return;
    }
    if (r->state != MS_RUN)
        return;
    const MisObj *o = ms_obj(r->obj);
    if (!o || (o->flags & MO_HIDDEN)) {
        model_body = M_CAR;
        return;
    }
    switch (o->op) {
    case OP_RINGS:
        if (r->count < o->n) {
            ring(ms_place(o->place + r->count), M_ACCENT);
            if (r->count + 1 < o->n)
                mark(wpos(ms_place(o->place + r->count + 1)), COLOR(M_ACCENT, 3, 0));
        }
        break;
    case OP_COLLECT: case OP_CRATES:
        pickups(o, r->v[1]);
        if (o->op == OP_CRATES && r->carry && ms_place(o->b))
            beacon(ms_place(o->b), M_TEAL);
        break;
    case OP_RACE:
        ghost(o, d);
        /* (and on) */
    case OP_GOTO: case OP_LAND: case OP_DEFEND: case OP_CHECK: case OP_DELIVER: case OP_ESCORT: {
        int t = ms_target();
        const MsPlace *p = t >= 0 ? ms_place(t) : 0;
        if (p) {
            if (p->kind >= PK_RING_X && p->kind <= PK_RING_H)
                ring(p, M_TEAL);
            else
                beacon(p, M_TEAL);
        }
        break;
    }
    }
    model_body = M_CAR;
}
