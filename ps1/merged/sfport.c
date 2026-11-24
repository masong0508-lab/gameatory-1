/* Milestone B (PS1): C for the Stunt Fox functions that the GBA build has in ARM assembly and that native C calls in its inner loops
   (stuntfox/src/fill.s, rechash.s, texrun.s), instruction for instruction the same results.  Compiled with the Stunt Fox module
   (natbuild.py), so its memory accesses take the guest memory model too (irmem.py).  The assembly hooks Payback calls (keyhook.s,
   guard.s, cart32.s, radiodec.s) are not here: they run in the interpreter from the ROM and call the native C they call on the GBA. */
#include "gba.h"

/* fill.s: rows scanlines from row between the 16.16 edges xl, xr (stepping sl, sr a row); a pixel is set when its centre lies between */
void fill_trap(u8 *row, int rows, s32 xl, s32 sl, s32 xr, s32 sr, u32 color4)
{
    u8 c = (u8)color4;
    for (; rows > 0; rows--) {
        s32 a = (xl + 0x7fff) >> 16, e = (xr + 0x7fff) >> 16;
        for (s32 x = a; x < e; x++)
            row[x] = c;
        row += 240;
        xl += sl;
        xr += sr;
    }
}

/* rechash.s: a hash of one of Payback's entity records (0x168 bytes) bar the words at +0x14 and +0x64 */
u32 rec_hash(const u8 *e, u32 h)
{
    const u32 *w = (const u32 *)e;
    for (int i = 0; i < 0x168 / 4; i++) {
        if (i == 5 || i == 25)
            continue;
        h ^= w[i];
        h = h >> 13 | h << 19;
        h *= 0x9e3779b1u;
    }
    return h;
}

/* texrun.s: a texture position is packed in one word (bits 31..27 the tile's column, 26..16 its fraction, 15..11 the row, 10..0 its
   fraction); every texel covers 2 x 2 pixels */
#define TEXEL(uv) (((uv) >> 6 & 0x3e0) | (uv) >> 27)
void tex_hrun(u8 *dst, int n, u32 uv, u32 duv, const u8 *tile, int row2)
{
    for (; n > 0; n--) {
        u32 v = tile[TEXEL(uv)];
        uv += duv;
        v |= v << 8;
        *(u16 *)(dst + row2) = v;
        *(u16 *)dst = v;
        dst += 2;
    }
}
void tex_hrun4(u32 *dst, int n, u32 uv, u32 duv, const u8 *tile, int row2)
{
    for (; n > 0; n--) {
        u32 v = tile[TEXEL(uv)];
        uv += duv;
        v |= v << 8;
        v |= v << 16;
        *(u32 *)((u8 *)dst + row2) = v;
        *dst++ = v;
    }
}
void tex_vrun(u8 *dst, int n, u32 uv, u32 duv, const u8 *tile, const u8 *lut, int row2)
{
    for (; n > 0; n--) {
        u32 v = tile[TEXEL(uv)];
        uv += duv;
        if (lut)
            v = lut[v];
        v |= v << 8;
        *(u16 *)(dst + row2) = v;
        *(u16 *)dst = v;
        dst += 480;
    }
}
void tex_mrun1(u8 *dst, int n, u32 uv, u32 duv, const u8 *mip, int row2)
{
    for (; n > 0; n--) {
        u32 v = mip[(uv >> 8 & 0xf0) | uv >> 28];
        uv += duv;
        v |= v << 8;
        *(u16 *)(dst + row2) = v;
        *(u16 *)dst = v;
        dst += 2;
    }
}
void tex_vrun4(u8 *dst, int n, u32 uv, u32 duv, const u8 *tile, const u8 *lut)
{
    for (; n > 0; n--) {
        u32 v = tile[TEXEL(uv)];
        uv += duv;
        if (lut)
            v = lut[v];
        v |= v << 8;
        *(u16 *)(dst + 240) = v;
        *(u16 *)(dst + 480) = v;
        *(u16 *)(dst + 720) = v;
        *(u16 *)dst = v;
        dst += 960;
    }
}
void tex_mrun(u8 *dst, int n, u32 uv, u32 duv, const u8 *mip, int row2, u32 lv)
{
    u32 mask = lv & 0xff, cs = lv >> 24, rs = lv >> 16 & 0xff;
    for (; n > 0; n--) {
        u32 v = mip[((uv >> rs) & mask) | uv >> cs];
        uv += duv;
        v |= v << 8;
        *(u16 *)(dst + row2) = v;
        *(u16 *)dst = v;
        dst += 2;
    }
}

extern s32 tex_camy;
extern const u16 *tex_tab;
extern const u8 pb_mip[][336];
extern const u16 pb_mipof[];
void tex_flat_pairs(u8 *d, int n, int color, int row2);
void tex_flat_cell(u8 *d, int n, int i, int row2);
#define PB_TILEPTR ((const u32 *)0x02002c60)          /* Payback's pointer to each tile (ROM or RAM) */
static u32 packuv(s32 X, s32 Z) { return ((u32)X << 14 & 0xffff0000u) | (u32)Z << 14 >> 16; }
static const u32 mlvs[4] = {0x1b0603e0, 0x1c0800f0, 0x1d0a0038, 0x1e0c000c};

/* texrun.s tex_walk: n pairs of pixels of a floor from d, split at the city cells' edges, each piece one run of its cell's tile */
void tex_walk(u8 *d, int n, s32 X, s32 Z, s32 dX, s32 dZ, u32 ix, u32 iz, int row2, int color)
{
    u32 duv = ((u32)dX << 14 & 0xffff0000u) + (u32)((s32)((u32)dZ << 3) >> 5);
    int quad = dX < 0x1000 && dX > -0x1000 && dZ < 0x1000 && dZ > -0x1000;
    s32 lim = tex_camy - 3000;
    if (lim < 0) lim = 0;
    if (lim > 6000) lim = 6000;
    lim = 0x3000 - lim;
    s32 big = dX < 0 ? -dX : dX, bz = dZ < 0 ? -dZ : dZ;
    if (bz > big) big = bz;
    int lv = 0;
    while (big >= lim && lv < 3) { lv++; big >>= 1; }
    u32 mlv = mlvs[lv];
    u32 moff = lv == 2 ? 256 : lv == 1 ? 0 : 320;
    const u16 *tab = tex_tab;
    while (n > 0) {
        s32 cx = X >> 18, cz = Z >> 18;
        if ((u32)(cx | cz) >= 128) {
            tex_flat_pairs(d, n, color, row2);
            return;
        }
        s32 m = n;
        if (dX != 0) {
            u32 r2 = dX > 0 ? (u32)(cx << 18) + 0x40000 - X : (u32)X - (u32)(cx << 18) + 1;
            u64 p = (u64)r2 * ix;
            s32 r3 = (s32)((u32)p >> 30 | (u32)(p >> 32) << 2) + 1;
            if (r3 < m) m = r3;
        }
        if (dZ != 0) {
            u32 r2 = dZ > 0 ? (u32)(cz << 18) + 0x40000 - Z : (u32)Z - (u32)(cz << 18) + 1;
            u64 p = (u64)r2 * iz;
            s32 r3 = (s32)((u32)p >> 30 | (u32)(p >> 32) << 2) + 1;
            if (r3 < m) m = r3;
        }
        int i = cx * 128 + cz;
        u32 id = tab[i];
        const u8 *tile = 0;
        if (id < 0x318) {
            u32 t = PB_TILEPTR[id], bank = t >> 24;
            /* (on the GBA: a tile in EWRAM, IWRAM, VRAM or ROM; on the PS1 a RAM tile's pointer is its host address) */
            if ((bank <= 8 && (0x14c >> bank & 1)) || (s32)t < 0)
                tile = (const u8 *)t;
        }
        if (!tile) {
            tex_flat_cell(d, m, i, row2);
        } else {
            u32 mo;
            if (lv != 0 && (mo = pb_mipof[id]) != 0) {
                const u8 *mip = pb_mip[mo - 1] + moff;
                if (lv == 1)
                    tex_mrun1(d, m, packuv(X, Z), duv, mip, row2);
                else
                    tex_mrun(d, m, packuv(X, Z), duv, mip, row2, mlv);
            } else if (quad && m >= 3) {
                u8 *e = d;
                int k = m;
                u32 uv = packuv(X, Z);
                if ((u32)d & 2) {
                    tex_hrun(d, 1, uv, duv, tile, row2);
                    e = d + 2;
                    k = m - 1;
                    uv += duv;
                }
                tex_hrun4((u32 *)e, k >> 1, uv, duv << 1, tile, row2);
                if (k & 1)
                    tex_hrun(e + (k >> 1) * 4, 1, uv + (k - 1) * duv, duv, tile, row2);
            } else {
                tex_hrun(d, m, packuv(X, Z), duv, tile, row2);
            }
        }
        d += m * 2;
        X += m * dX;
        Z += m * dZ;
        n -= m;
    }
}
