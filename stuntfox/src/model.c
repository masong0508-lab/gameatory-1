/* Drawing polygon models: transform, back-face cull, flat light from the sun. */
#include "model.h"
#include "render.h"
#include "palette.h"

static const V3 sun = {6553, 13107, 7372};     /* roughly (0.4, 0.8, 0.45) */
u8 model_body = M_CAR;                          /* material drawn for M_CAR faces (paint job) */

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
        if (((n.x * fx + n.y * fy + n.z * fz) >> 4) < 0)      /* make it point outward */
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
    return 1;
}

static inline V3 xf(const Place *pl, const MVert *v)
{
    return v3(pl->t.x + ((pl->ax.x * v->x + pl->ay.x * v->y + pl->az.x * v->z) >> 14),
              pl->t.y + ((pl->ax.y * v->x + pl->ay.y * v->y + pl->az.y * v->z) >> 14),
              pl->t.z + ((pl->ax.z * v->x + pl->ay.z * v->y + pl->az.z * v->z) >> 14));
}

void model_draw(const Model *md, const Place *pl)
{
    V3 cv[64];
    for (int i = 0; i < md->nv; i++)
        cv[i] = xf(pl, &md->v[i]);
    for (int i = 0; i < md->nf; i++) {
        const MFace *f = &md->f[i];
        V3 n = v3(md->normal[i].x, md->normal[i].y, md->normal[i].z);
        int two = f->flags & MF_TWO;
        if (!two) {
            /* camera-space normal (unscaled direction is enough for the sign) */
            V3 nc = v3((pl->nx.x * n.x + pl->ny.x * n.y + pl->nz.x * n.z) >> 14,
                       (pl->nx.y * n.x + pl->ny.y * n.y + pl->nz.y * n.z) >> 14,
                       (pl->nx.z * n.x + pl->ny.z * n.y + pl->nz.z * n.z) >> 14);
            V3 p = cv[f->idx[0]];
            while (nc.x > 4096 || nc.x < -4096 || nc.y > 4096 || nc.y < -4096 || nc.z > 4096 || nc.z < -4096)
                nc = vshr(nc, 1);
            while (p.x > 60000 || p.x < -60000 || p.y > 60000 || p.y < -60000 || p.z > 60000 || p.z < -60000)
                p = vshr(p, 1);
            if (nc.x * p.x + nc.y * p.y + nc.z * p.z >= 0)
                continue;
        }
        int color, mat = f->mat == M_CAR ? model_body : f->mat;
        if (f->flags & MF_GLOW)
            color = COLOR(mat, 3, 0);
        else {
            s32 l = vdot(mlocal(pl->m, n), sun);
            if (two && l < 0) l = -l;
            int lv = (l + 16384) >> 13;
            color = COLOR(mat, lv > 3 ? 3 : lv, pl->fog);
        }
        V3 q[6];
        for (int k = 0; k < f->n; k++)
            q[k] = cv[f->idx[k]];
        r_poly(q, f->n, color, -1, 0);
    }
}

void model_poly(const Place *pl, const MVert *v, int n, int color)
{
    V3 q[8];
    for (int k = 0; k < n; k++)
        q[k] = xf(pl, &v[k]);
    r_poly(q, n, color, -1, 0);
}
