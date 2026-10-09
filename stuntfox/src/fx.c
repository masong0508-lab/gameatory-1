#include "fx.h"

u32 isqrt(u32 v)
{
    u32 r = 0, b = 1u << 30;
    while (b > v) b >>= 2;
    while (b) {
        if (v >= r + b) { v -= r + b; r = (r >> 1) + b; }
        else r >>= 1;
        b >>= 2;
    }
    return r;
}

static s32 iabs(s32 v) { return v < 0 ? -v : v; }

s32 vlen(V3 v)
{
    int s = 0;
    s32 m = iabs(v.x) | iabs(v.y) | iabs(v.z);
    while (m >= 16384) m >>= 1, s++;
    v = vshr(v, s);
    return (s32)isqrt((u32)(v.x * v.x + v.y * v.y + v.z * v.z)) << s;
}

s32 fdiv(s32 a, s32 b)
{
    return b ? a / b : 0;
}

V3 vnorm(V3 v)
{
    int s = 0;
    s32 m = iabs(v.x) | iabs(v.y) | iabs(v.z);
    if (!m) return v3(0, ONE, 0);
    while (m >= 16384) m >>= 1, s++;
    while (m < 4096) m <<= 1, s--;
    v = s >= 0 ? vshr(v, s) : v3(v.x << -s, v.y << -s, v.z << -s);
    s32 l = (s32)isqrt((u32)(v.x * v.x + v.y * v.y + v.z * v.z));
    return v3(v.x * ONE / l, v.y * ONE / l, v.z * ONE / l);
}

void morth(M3 *m)
{
    m->f = vnorm(m->f);
    m->r = vnorm(vcross(m->u, m->f));
    m->u = vcross(m->f, m->r);
}

void mrotate(M3 *m, V3 w)
{
    m->r = vadd(m->r, vcross(w, m->r));
    m->u = vadd(m->u, vcross(w, m->u));
    m->f = vadd(m->f, vcross(w, m->f));
    morth(m);
}

void myaw(M3 *m, s32 a)
{
    s32 s = fsin(a), c = fcos(a);
    m->f = v3(s, 0, c);                  /* heading 0 looks along +z, 16384 along +x */
    m->u = v3(0, ONE, 0);
    m->r = v3(c, 0, -s);
}

u16 fatan2(s32 y, s32 x)
{
    /* octant reduction + polynomial on |y|/|x| <= 1 */
    if (!x && !y) return 0;
    s32 ax = iabs(x), ay = iabs(y);
    int swap = ay > ax;
    s32 n = swap ? ax : ay, d = swap ? ay : ax;
    while (d > 32767) d >>= 1, n >>= 1;
    s32 t = n * 16384 / (d ? d : 1);                   /* tan, 1.14, 0..1 */
    s32 a = (8192 * t + ((2847 * ((t * (16384 - t)) >> 14)))) >> 14;   /* atan, 8192 = 45 degrees */
    if (swap) a = 16384 - a;
    if (x < 0) a = 32768 - a;
    if (y < 0) a = -a;
    return (u16)a;
}
