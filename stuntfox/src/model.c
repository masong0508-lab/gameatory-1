/* Drawing polygon models: transform, back-face cull, flat light from the sun. */
#include "model.h"
#include "render.h"
#include "palette.h"

static const V3 sun = {6553, 13107, 7372};     /* roughly (0.4, 0.8, 0.45) */
u8 model_body = M_CAR;                          /* material drawn for M_CAR faces (paint job) */
u8 model_legs = M_ROAD;                         /* ... and for M_SKY faces */
u8 model_hull = M_SHIP;                         /* ... and for M_SHIP faces */

void model_init(Model *md)
{
    /* the solid part's centre (thin two-sided parts left out): normals point away from it */
    s32 cx = 0, cy = 0, cz = 0, cn = 0;
    for (int i = 0; i < md->nf; i++)
        if (!(md->f[i].flags & MF_TWO))
            for (int k = 0; k < md->f[i].n; k++, cn++)
                cx += md->v[md->f[i].idx[k]].x, cy += md->v[md->f[i].idx[k]].y, cz += md->v[md->f[i].idx[k]].z;
    if (cn)
        cx /= cn, cy /= cn, cz /= cn;
    for (int i = 0; i < md->nf; i++) {
        const MFace *f = &md->f[i];
        const MVert *a = &md->v[f->idx[0]], *b = &md->v[f->idx[1]], *c = &md->v[f->idx[2]];
        V3 e1 = v3(b->x - a->x, b->y - a->y, b->z - a->z), e2 = v3(c->x - a->x, c->y - a->y, c->z - a->z);
        while (e1.x > 2000 || e1.x < -2000 || e1.y > 2000 || e1.y < -2000 || e1.z > 2000 || e1.z < -2000)
            e1 = vshr(e1, 1);
        while (e2.x > 2000 || e2.x < -2000 || e2.y > 2000 || e2.y < -2000 || e2.z > 2000 || e2.z < -2000)
            e2 = vshr(e2, 1);
        V3 n = vnorm(v3(e1.y * e2.z - e1.z * e2.y, e1.z * e2.x - e1.x * e2.z, e1.x * e2.y - e1.y * e2.x));
        s32 fx = 0, fy = 0, fz = 0;
        for (int k = 0; k < f->n; k++)
            fx += md->v[f->idx[k]].x, fy += md->v[f->idx[k]].y, fz += md->v[f->idx[k]].z;
        fx = fx / f->n - cx, fy = fy / f->n - cy, fz = fz / f->n - cz;
        if ((((n.x * fx + n.y * fy + n.z * fz) >> 4) < 0) != !!(f->flags & MF_IN))   /* outward (or in) */
            n = v3(-n.x, -n.y, -n.z);
        md->normal[i] = (N3){(s16)n.x, (s16)n.y, (s16)n.z};
    }
}

int model_place(Place *pl, V3 pos, const M3 *m, s32 scale, int shift, s32 radius)
{
    V3 t = shift ? r_cam_far(pos, shift) : r_cam(pos);
    s32 rad = (radius * scale >> 8) >> shift;
    if (t.z < -rad || FOCAL * t.x - 121 * t.z > rad * 182 || -FOCAL * t.x - 121 * t.z > rad * 182 ||
        FOCAL * t.y - 81 * t.z > rad * 158 || -FOCAL * t.y - 81 * t.z > rad * 158)
        return 0;
    s32 s = scale >> shift;
    pl->t = t;
    pl->m = m;
    pl->nx = v3(vdot(cam.m.r, m->r), vdot(cam.m.u, m->r), vdot(cam.m.f, m->r));
    pl->ny = v3(vdot(cam.m.r, m->u), vdot(cam.m.u, m->u), vdot(cam.m.f, m->u));
    pl->nz = v3(vdot(cam.m.r, m->f), vdot(cam.m.u, m->f), vdot(cam.m.f, m->f));
    pl->ax = vscale(pl->nx, s << 6);
    pl->ay = vscale(pl->ny, s << 6);
    pl->az = vscale(pl->nz, s << 6);
    pl->fog = fog_of(t.z << shift);
    pl->s = s;
    return 1;
}

/* a model point in camera space (a macro, like DOT: ARM code in IWRAM cannot inline Thumb
   functions) */
#define XF(o, pl, v) ((o).x = (pl)->t.x + (((pl)->ax.x * (v)->x + (pl)->ay.x * (v)->y + (pl)->az.x * (v)->z) >> 14), \
                      (o).y = (pl)->t.y + (((pl)->ax.y * (v)->x + (pl)->ay.y * (v)->y + (pl)->az.y * (v)->z) >> 14), \
                      (o).z = (pl)->t.z + (((pl)->ax.z * (v)->x + (pl)->ay.z * (v)->y + (pl)->az.z * (v)->z) >> 14))
#define DOT(a, b) (((a).x * (b).x + (a).y * (b).y + (a).z * (b).z) >> 14)

HOT6 void model_draw(const Model *md, const Place *pl)
{
    /* (a model has at most 56 points, as the player's body: this frame is on the deepest call
       chain, under r_poly and clip, and the stack ends just above IWRAM that Payback needs) */
    V3 cv[56];
    if (md->nv > 56)
        return;
    u32 got[2] = {0, 0};                        /* which points are in cv: only those of faces in view */
    /* the camera and the sun in the model's own frame: a face is turned away when its normal
       points away from the camera, and lit by its normal . the sun, both without turning it.
       (the camera is d units from the model along -t: in model units, shrunk by 2^k to keep the
       products in 32 bits) */
    const V3 t = pl->t;
    s32 cx = -(((pl->nx.x * t.x) >> 14) + ((pl->nx.y * t.y) >> 14) + ((pl->nx.z * t.z) >> 14));
    s32 cy = -(((pl->ny.x * t.x) >> 14) + ((pl->ny.y * t.y) >> 14) + ((pl->ny.z * t.z) >> 14));
    s32 cz = -(((pl->nz.x * t.x) >> 14) + ((pl->nz.y * t.y) >> 14) + ((pl->nz.z * t.z) >> 14));
    if (pl->s != 256 && pl->s > 0)
        cx = cx * 256 / pl->s, cy = cy * 256 / pl->s, cz = cz * 256 / pl->s;
    int k = 0;
    while (cx > 16383 || cx < -16383 || cy > 16383 || cy < -16383 || cz > 16383 || cz < -16383)
        cx >>= 1, cy >>= 1, cz >>= 1, k++;
    const M3 *m = pl->m;
    s32 lx = DOT(m->r, sun), ly = DOT(m->u, sun), lz = DOT(m->f, sun);
    const MFace *f = md->f;
    const N3 *nn = md->normal;
    for (int i = 0; i < md->nf; i++, f++, nn++) {
        s32 nx = nn->x, ny = nn->y, nz = nn->z;
        int two = f->flags & MF_TWO;
        if (!two) {
            const MVert *a = &md->v[f->idx[0]];
            if (nx * ((a->x >> k) - cx) + ny * ((a->y >> k) - cy) + nz * ((a->z >> k) - cz) >= 0)
                continue;
        }
        int color, mat = f->mat == M_CAR ? model_body : f->mat == M_SKY ? model_legs : f->mat == M_SHIP ? model_hull : f->mat;
        if (f->flags & MF_GLOW)
            color = COLOR(mat, 3, 0);
        else {
            s32 l = (nx * lx + ny * ly + nz * lz) >> 14;
            if (two && l < 0) l = -l;
            int lv = (l + 16384) >> 13;
            color = COLOR(mat, lv > 3 ? 3 : lv, pl->fog);
        }
        V3 q[6];
        for (int j = 0; j < f->n; j++) {
            int v = f->idx[j];
            u32 b = 1u << (v & 31);
            if (!(got[v >> 5] & b)) {
                got[v >> 5] |= b;
                XF(cv[v], pl, &md->v[v]);
            }
            q[j] = cv[v];
        }
        r_poly(q, f->n, color, f->flags & MF_BACK ? -2 : -1, 0);
    }
}

void model_poly(const Place *pl, const MVert *v, int n, int color)
{
    V3 q[8];
    for (int k = 0; k < n; k++)
        XF(q[k], pl, &v[k]);
    r_poly(q, n, color, -1, 0);
}
