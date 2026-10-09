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
    for (int j = y; j < y + h; j++)
        if ((unsigned)j < 160)
            for (int i = x; i < x + w; i++)
                if ((unsigned)i < 240)
                    put(r_target(), i, j, c);
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
    int c = pal_of(color);
    if (x0 < 0) x0 = 0;
    if (x1 > 239) x1 = 239;
    for (int x = x0; x <= x1; x++)
        put(r_target(), x, y, c);
}

void d_vline(int x, int y0, int y1, int color)
{
    if ((unsigned)x >= 240)
        return;
    int c = pal_of(color);
    if (y0 > y1) { int t = y0; y0 = y1; y1 = t; }
    if (y0 < 0) y0 = 0;
    if (y1 > 159) y1 = 159;
    for (int y = y0; y <= y1; y++)
        put(r_target(), x, y, c);
}

char *d_num(char *buf, int v)
{
    char t[12];
    int n = 0;
    if (v < 0) {
        *buf++ = '-';
        v = -v;
    }
    do {
        t[n++] = '0' + v % 10;
        v /= 10;
    } while (v);
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
