#include "hud.h"

extern const u32 font_tiles[];
static u16 shadow[128 * 4] EWRAM_BSS;
static int nspr;

static u16 rgb(int r, int g, int b) { return r | g << 5 | b << 10; }

void hud_init(void)
{
    for (int i = 0; i < 64 * 8; i++)
        OBJ_TILES[i] = font_tiles[i];
    static const u8 cols[5][3] = {{31, 31, 31}, {31, 28, 6}, {31, 9, 9}, {10, 28, 31}, {12, 31, 12}};
    for (int p = 0; p < 5; p++) {
        PAL_OBJ[p * 16 + 1] = rgb(cols[p][0], cols[p][1], cols[p][2]);
        PAL_OBJ[p * 16 + 2] = rgb(0, 0, 5);
    }
    for (int i = 0; i < 128; i++)
        shadow[i * 4] = 0x200;
    shadow[3] = 0x80;                   /* affine matrix 0: magnify 2x */
    shadow[7] = 0;
    shadow[11] = 0;
    shadow[15] = 0x80;
    hud_commit();
}

void hud_begin(void) { nspr = 0; }

static void put(int x, int y, int c, int pal, int big)
{
    if (c >= 'a' && c <= 'z')
        c -= 32;
    if (c <= 32 || c > 95 || nspr >= 128)
        return;
    u16 *o = &shadow[nspr++ * 4];
    o[0] = (y & 0xff) | (big ? 0x300 : 0);
    o[1] = (x & 0x1ff);
    o[2] = (512 + c - 32) | (pal << 12);
}

void hud_text(int x, int y, const char *s, int pal)
{
    for (; *s; s++, x += 8)
        put(x, y, *s, pal, 0);
}

void hud_big(int x, int y, const char *s, int pal)
{
    for (; *s; s++, x += 14)
        put(x, y, *s, pal, 1);
}

void hud_end(void)
{
    for (int i = nspr; i < 128; i++)
        shadow[i * 4] = 0x200;
}

void hud_commit(void)
{
    volatile u16 *o = OAM;
    for (int i = 0; i < 128 * 4; i++)
        o[i] = shadow[i];
}

char *hud_num(char *buf, int v)
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
