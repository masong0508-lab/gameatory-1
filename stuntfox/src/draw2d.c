/* See draw2d.h. */
#include "draw2d.h"
#include "render.h"
#include "palette.h"
#include "tex.h"

extern const u32 font_tiles[];         /* tables.c: ASCII 32..95, 4 bits a pixel, 1 = ink, 2 = shadow */

static int pal_of(int c) { return c >= 0x100 ? c & 0xff : pb_pmap[c]; }

static inline void put(u8 *page, int x, int y, int c)
{
    u16 *p = (u16 *)(page + y * 240 + (x & ~1));
    *p = x & 1 ? (*p & 0xff) | (c << 8) : (*p & 0xff00) | c;
}

void d_pixel(int x, int y, int color)
{
    if ((unsigned)x < 240 && (unsigned)y < 160)
        put(r_target(), x, y, pal_of(color));
}

/* one whole letter, inside the screen (ARM, in borrowed IWRAM: text is drawn every frame) */
HOT3 static void glyph(u8 *at, const u32 *g, u32 ink, u32 shadow)
{
    for (int r = 0; r < 8; r++, at += 240) {
        u32 w = g[r];
        for (int k = 0; w; k++, w >>= 4) {
            u32 v = w & 15;
            if (!v)
                continue;
            u8 *a = at + k;
            u16 *p = (u16 *)((u32)a & ~1);
            u32 c = v == 1 ? ink : shadow;
            *p = (u32)a & 1 ? (*p & 0xff) | (c << 8) : (*p & 0xff00) | c;
        }
    }
}

void d_text(int x, int y, const char *s, int color)
{
    u8 *page = r_target();
    int ink = pal_of(color), shadow = pal_of(COLOR(M_ROAD, 0, 0));
    for (; *s; s++, x += TEXT_W) {
        int ch = *s;
        if (ch >= 'a' && ch <= 'z')
            ch -= 32;
        if (ch <= 32 || ch > 95)
            continue;
        const u32 *g = &font_tiles[(ch - 32) * 8];
        if (x >= 1 && x + 7 <= 240 && y >= 0 && y + 8 <= 160) {
            glyph(page + y * 240 + x - 1, g, ink, shadow);
            continue;
        }
        for (int r = 0; r < 8; r++) {
            int yy = y + r;
            if ((unsigned)yy >= 160)
                continue;
            u32 w = g[r];
            for (int k = 0; w; k++, w >>= 4) {
                int v = w & 15, xx = x + k - 1;
                if (v && (unsigned)xx < 240)
                    put(page, xx, yy, v == 1 ? ink : shadow);
            }
        }
    }
}

void d_rect(int x, int y, int w, int h, int color)
{
    int c = pal_of(color);
    if (x < 0) w += x, x = 0;
    if (x + w > 240) w = 240 - x;
    if (y < 0) h += y, y = 0;
    if (y + h > 160) h = 160 - y;
    if (w <= 0 || h <= 0)
        return;
    /* pixel pairs where it can (VRAM takes 16-bit writes), single pixels at odd ends */
    u8 *row = r_target() + y * 240;
    u16 cc = c | c << 8;
    for (; h > 0; h--, row += 240) {
        int i = x, e = x + w;
        if (i & 1)
            put(row, i++, 0, c);
        for (u16 *p = (u16 *)(row + i); i + 1 < e; i += 2)
            *p++ = cc;
        if (i < e)
            put(row, i, 0, c);
    }
}

#define REG_DMA3SAD (*(volatile u32 *)0x040000d4)
#define REG_DMA3DAD (*(volatile u32 *)0x040000d8)
#define REG_DMA3CNT (*(volatile u32 *)0x040000dc)

void d_fill(int x, int y, int w, int h, int color)
{
    u8 *page = r_target();
    u32 c = pal_of(color);
    c |= c << 8;
    c |= c << 16;
    x &= ~3;
    w = (w + 3) & ~3;
    if (x < 0) w += x, x = 0;
    if (x + w > 240) w = 240 - x;
    if (y < 0) h += y, y = 0;
    if (y + h > 160) h = 160 - y;
    if (w <= 0)
        return;
    /* a row at a time by DMA 3 from one word (source fixed). Payback's sound interrupt uses DMA 3
       too, so interrupts wait meanwhile (as in merge.c's copy32) */
    volatile u32 src = c;
    for (int j = 0; j < h; j++) {
        u16 ime = REG_IME;
        REG_IME = 0;
        REG_DMA3CNT = 0;
        REG_DMA3SAD = (u32)&src;
        REG_DMA3DAD = (u32)(page + (y + j) * 240 + x);
        REG_DMA3CNT = (w >> 2) | 0x85000000;
        REG_IME = ime;
    }
}

void d_panel(int x, int y, int w, int h)
{
    u8 *page = r_target();
    x &= ~1;
    w = (w + 1) & ~1;
    if (x < 0) w += x, x = 0;
    if (x + w > 240) w = 240 - x;
    for (int j = y; j < y + h; j++) {
        if ((unsigned)j >= 160)
            continue;
        u16 *p = (u16 *)(page + j * 240 + x);
        for (int i = 0; i < w; i += 2, p++) {
            u16 v = *p;
            int a = pb_shade[0][pb_shade[0][v & 0xff]], b = pb_shade[0][pb_shade[0][v >> 8]];
            *p = a | b << 8;
        }
    }
}

void d_hline(int x0, int x1, int y, int color)
{
    if ((unsigned)y >= 160)
        return;
    if (x0 < 0) x0 = 0;
    if (x1 > 239) x1 = 239;
    d_rect(x0, y, x1 - x0 + 1, 1, color);
}

void d_vline(int x, int y0, int y1, int color)
{
    if ((unsigned)x >= 240)
        return;
    int c = pal_of(color);
    if (y0 > y1) { int t = y0; y0 = y1; y1 = t; }
    if (y0 < 0) y0 = 0;
    if (y1 > 159) y1 = 159;
    u8 *page = r_target();
    for (int y = y0; y <= y1; y++)
        put(page, x, y, c);
}

/* n / 10 and its remainder by shifts and adds (a division would be a BIOS call) */
static u32 div10(u32 n, u32 *rem)
{
    u32 q = (n >> 1) + (n >> 2);
    q += q >> 4;
    q += q >> 8;
    q += q >> 16;
    q >>= 3;
    u32 r = n - q * 10;
    if (r > 9)
        q++, r -= 10;
    *rem = r;
    return q;
}

char *d_num(char *buf, int v)
{
    char t[12];
    int n = 0;
    if (v < 0) {
        *buf++ = '-';
        v = -v;
    }
    u32 u = v, r;
    do {
        u = div10(u, &r);
        t[n++] = '0' + r;
    } while (u);
    while (n)
        *buf++ = t[--n];
    *buf = 0;
    return buf;
}

char *d_time(char *buf, int s)
{
    if (s < 0) s = 0;
    buf = d_num(buf, s / 60);
    *buf++ = ':';
    *buf++ = '0' + (s % 60) / 10;
    *buf++ = '0' + s % 10;
    *buf = 0;
    return buf;
}

char *d_cat(char *buf, const char *s)
{
    while (*s)
        *buf++ = *s++;
    *buf = 0;
    return buf;
}
