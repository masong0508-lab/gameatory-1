/* See hudline.h. The page is redrawn every frame, so the text is inked once into bit strips when it changes and each
   frame only expanded onto the page: a word of four pixels from a nibble of the strip, no letter drawn. */
#include "stage2.h"
#include "hudline.h"
#include "mission.h"
#include "draw2d.h"
#include "render.h"
#include "palette.h"

#define INK COLOR(M_CREAM, 3, 0)
#define AMBER COLOR(M_GLOW, 3, 0)
#define PANEL COLOR(M_ROAD, 0, 0)  /* (the font's shadow is this colour too: on the panel a letter is its ink alone) */

#define NR 7                       /* ink rows of a letter (its eighth row is shadow only) */
#define LS 20                      /* a row of the line's strip: 20 bytes of 8 pixels = the 26 letters of 6 (18, a space, 7) it can hold */
#define CB 29                      /* a card line: 29 bytes = columns 4..235 (38 letters of 6) */
#define CS 32

typedef struct {                   /* ~630 bytes in keep */
    u8 line[NR][LS];               /* (first, and the rows a multiple of 4 on: the expander reads words) */
    u8 card[2][NR][CS];
    s32 key;                       /* what the status was formatted from (0: nothing) */
    u16 card_start, card_end;      /* PB_CLOCK's low 16 bits when the card comes and goes */
    u8 amber, card_on, card_n, ns, nl;
    char lt[HL_LEFT_MAX + 1];
    char st[HL_STAT_MAX + 1];
} HudLine __attribute__((aligned(4)));
static HudLine hl;

extern const u32 font_tiles[];     /* tables.c: ASCII 32..95, 8 pixels a row, 4 bits each, 1 = ink, 2 = shadow */

/* the ink of the first n letters of s into bits (NR rows of stride bytes, one bit a pixel, the left pixel the low bit),
   a letter's cell beginning at pixel px + 6 i; its pixels are at columns 1..5 of the font's cell */
static void ink(u8 *bits, int stride, int px, const char *s, int n)
{
    for (int i = 0; i < n; i++, px += 6) {
        int ch = s[i];
        if (ch >= 'a' && ch <= 'z')
            ch -= 32;
        if (ch <= 32 || ch > 95)
            continue;
        const u32 *g = &font_tiles[(ch - 32) * 8];
        for (int r = 0; r < NR; r++) {
            u32 w = g[r] >> 4;
            for (int k = 0; k < 5; k++, w >>= 4)
                if ((w & 15) == 1) {
                    int p = px + k;
                    bits[r * stride + (p >> 3)] |= 1 << (p & 7);
                }
        }
    }
}

/* pixels p0 .. p1 - 1 of every row off */
static void clr(u8 *bits, int stride, int p0, int p1)
{
    for (int r = 0; r < NR; r++, bits += stride)
        for (int b = p0 >> 3; b * 8 < p1; b++) {
            int lo = p0 - b * 8, hi = p1 - b * 8;
            lo = lo < 0 ? 0 : lo, hi = hi > 8 ? 8 : hi;
            bits[b] &= ~(((1 << hi) - 1) & ~((1 << lo) - 1));
        }
}

/* the line's letters: how many (at most n) of s, up to a newline */
static int cut(const char *s, int n)
{
    int k = 0;
    while (k < n && s[k] && s[k] != '\n')
        k++;
    return k;
}

/* the line is the objective, a space and the status in one run, so the page takes only the words it needs */
static int stat_x(void) { return (hl.nl + 1) * 6; }

void hl_text(const char *s)
{
    char t[HL_LEFT_MAX + 1];
    int n = s ? cut(s, HL_LEFT_MAX) : 0;
    for (int i = 0; i < n; i++)
        t[i] = s[i];
    t[n] = 0;
    int same = n == hl.nl;
    for (int i = 0; same && i < n; i++)
        same = t[i] == hl.lt[i];
    if (same)
        return;
    for (int i = 0; i <= n; i++)
        hl.lt[i] = t[i];
    hl.nl = n;
    clr(hl.line[0], LS, 0, LS * 8);
    ink(hl.line[0], LS, 0, hl.lt, n);
    if (hl.ns)
        ink(hl.line[0], LS, stat_x(), hl.st, hl.ns);   /* (it moves with the text's end) */
}

void hl_stat(int kind, int a, int b)
{
    static const char *const dir[8] = {"N", "NE", "E", "SE", "S", "SW", "W", "NW"};
    if (a < 0) a = 0;
    if (a > 0x3fff) a = 0x3fff;
    if (b < 0) b = 0;
    if (b > 0x3fff) b = 0x3fff;
    s32 key = (kind + 1) << 28 | a << 14 | b;
    if (key == hl.key)
        return;
    hl.key = key;
    hl.amber = kind == HLS_TIME && a <= 10;
    char buf[24], *p = buf;                         /* (a count of 16383 of 16383 is longer than the room: cut) */
    switch (kind) {
    case HLS_TIME:
        p = d_time(p, a);
        break;
    case HLS_COUNT:
        p = d_num(p, a);
        p = d_cat(p, "/");
        p = d_num(p, b);
        break;
    case HLS_HP:
        p = d_cat(p, "HP ");
        p = d_num(p, a);
        break;
    case HLS_BEAR:
        p = d_cat(p, dir[a & 7]);
        p = d_cat(p, " ");
        p = d_num(p, b);
        break;
    }
    *p = 0;
    int n = 0;
    for (; buf[n] && n < HL_STAT_MAX; n++)
        hl.st[n] = buf[n];
    hl.st[n] = 0;
    hl.ns = n;
    clr(hl.line[0], LS, stat_x(), LS * 8);
    ink(hl.line[0], LS, stat_x(), hl.st, n);
}

/* a card: line a, line b; the long first line goes on into the second as it always has */
void hl_card(const char *s, int delay)
{
    hl.card_on = 0;
    if (!s || !s[0])
        return;
    for (u32 *p = (u32 *)hl.card; p < (u32 *)hl.card + sizeof hl.card / 4; p++)
        *p = 0;
    int la = cut(s, 38);
    ink(hl.card[0][0], CS, 0, s, la);
    s += la;
    if (*s == '\n')
        s++;
    int lb = cut(s, 38);
    ink(hl.card[1][0], CS, 0, s, lb);
    hl.card_n = lb ? 2 : 1;
    hl.card_start = (u16)(s2f.clock + (delay > 0 ? delay : 0));
    hl.card_end = hl.card_start + HL_CARD_TICKS;
    hl.card_on = 1;
}

void hl_clear(void)
{
    hl.nl = hl.ns = 0;
    hl.lt[0] = hl.st[0] = 0;
    hl.card_on = 0;
    hl.key = 0;
    hl.amber = 0;
}

void hl_off(void)
{
    u8 on = hl.card_on;
    hl_clear();
    hl.card_on = on;
}

static int card_live(void) { return hl.card_on && (s16)((u16)s2f.clock - hl.card_start) >= 0 && (s16)((u16)s2f.clock - hl.card_end) < 0; }

const char *hl_status(void) { return hl.st; }

int hl_up(void) { return hl.nl != 0 || card_live(); }

int s2_hud_owned(void) { return hl_up(); }

/* The expander. For each of n bytes of a strip row (eight pixels, the left one the low bit) two words of the page, each by
   a nibble's entry in a table of 16 words (four pixels as four bytes: the panel's colour, or the ink's where the bit is on),
   rows rows of it, the strip a stride on and the page 240 on, with a word of the panel's colour (entry 0) at either end of
   a row. Four strip bytes at a time and one store of eight page words, then a halfword and a byte for the rest; the first
   byte and the stride are word aligned. ARM, here in the ROM (there is no spare IWRAM): from the ROM an instruction takes
   its fetch, 4 cycles in ARM and 2 in Thumb whatever it does, so the loop is as few instructions as it can be (an `and`
   and a table load a word, the table on the stack, in IWRAM). Thumb from the ROM, byte by byte, measured 90 cycles a byte. */
typedef struct {
    u32 *dst;                      /* the first row's first word (the margin) */
    const u8 *bits;
    const u32 *tab;
    u32 rows, n, stride;
} InkJob;
void hl_ink(const InkJob *j);
#ifdef __arm__
__asm__(".text\n.arm\n.balign 4\n.type hl_ink, %function\n"
        "  .macro BLK\n"
        "  ldr r4, [r1], #4\n"
        "  and r5, r4, #0x0000000f\n  ldr r5, [r3, r5, lsl #2]\n"
        "  and r6, r4, #0x000000f0\n  ldr r6, [r3, r6, lsr #2]\n"
        "  and r7, r4, #0x00000f00\n  ldr r7, [r3, r7, lsr #6]\n"
        "  and r8, r4, #0x0000f000\n  ldr r8, [r3, r8, lsr #10]\n"
        "  and r9, r4, #0x000f0000\n  ldr r9, [r3, r9, lsr #14]\n"
        "  and r10, r4, #0x00f00000\n  ldr r10, [r3, r10, lsr #18]\n"
        "  and r11, r4, #0x0f000000\n  ldr r11, [r3, r11, lsr #22]\n"
        "  and r12, r4, #0xf0000000\n  ldr r12, [r3, r12, lsr #26]\n"
        "  stmia r0!, {r5-r12}\n"
        "  .endm\n"
        "hl_ink:\n"
        "  stmfd sp!, {r4-r11, lr}\n"
        "  ldmia r0, {r1-r6}\n"                    /* r1 dst, r2 bits, r3 tab, r4 rows, r5 n, r6 stride */
        "  sub sp, sp, #16\n"
        "  rsb r7, r5, r6\n"                       /* the strip's step to the next row once n are read */
        "  rsb r8, r5, #0\n"
        "  mov r8, r8, lsl #3\n"
        "  add r8, r8, #232\n"                     /* the page's, once 8 n + 8 bytes are written */
        "  mov r9, r5, lsr #2\n"                   /* blocks of four bytes */
        "  and lr, r5, #3\n"                       /* and the bytes after them */
        "  stmia sp, {r4, r7, r8, r9}\n"           /* [sp] rows left, +4 strip step, +8 page step, +12 blocks */
        "  mov r0, r1\n"
        "  mov r1, r2\n"
        "1:\n"
        "  ldr r4, [r3]\n"
        "  str r4, [r0], #4\n"
        "  ldr r2, [sp, #12]\n"
        "  movs r2, r2, lsr #1\n"                 /* two blocks a turn (the flags live through them), one first if odd */
        "  bcc 2f\n"
        "  BLK\n"
        "2:\n"
        "  beq 3f\n"
        "6:\n"
        "  BLK\n"
        "  BLK\n"
        "  subs r2, r2, #1\n"
        "  bne 6b\n"
        "3:\n"
        "  tst lr, #2\n"
        "  beq 4f\n"
        "  ldrh r4, [r1], #2\n"
        "  and r5, r4, #0x000f\n  ldr r5, [r3, r5, lsl #2]\n"
        "  and r6, r4, #0x00f0\n  ldr r6, [r3, r6, lsr #2]\n"
        "  and r7, r4, #0x0f00\n  ldr r7, [r3, r7, lsr #6]\n"
        "  and r8, r4, #0xf000\n  ldr r8, [r3, r8, lsr #10]\n"
        "  stmia r0!, {r5-r8}\n"
        "4:\n"
        "  tst lr, #1\n"
        "  beq 5f\n"
        "  ldrb r4, [r1], #1\n"
        "  and r5, r4, #15\n  ldr r5, [r3, r5, lsl #2]\n"
        "  and r6, r4, #0xf0\n  ldr r6, [r3, r6, lsr #2]\n"
        "  stmia r0!, {r5, r6}\n"
        "5:\n"
        "  ldr r4, [r3]\n"
        "  str r4, [r0], #4\n"
        "  ldmia sp, {r2, r4, r5}\n"
        "  add r1, r1, r4\n"
        "  add r0, r0, r5\n"
        "  subs r2, r2, #1\n"
        "  str r2, [sp]\n"
        "  bne 1b\n"
        "  add sp, sp, #16\n"
        "  ldmfd sp!, {r4-r11, lr}\n"
        "  bx lr\n"
        ".size hl_ink, .-hl_ink\n");
#else
void hl_ink(const InkJob *j)                        /* (the PC's: the same in C, for tests/vm) */
{
    for (u32 r = 0; r < j->rows; r++) {
        u32 *d = j->dst + 60 * r;
        d[0] = d[1 + 2 * j->n] = j->tab[0];
        for (u32 i = 0; i < j->n; i++) {
            u32 b = j->bits[r * j->stride + i];
            d[1 + 2 * i] = j->tab[b & 15];
            d[2 + 2 * i] = j->tab[b >> 4];
        }
    }
}
#endif

/* the table for an ink: entry n has the ink's byte (xb: its palette index xor the panel's) at each pixel whose bit is on in n */
static void tab(u32 *t, u32 bg, u32 xb)
{
    u32 a = xb, b = xb << 8, c = xb << 16, d = xb << 24;
    t[0] = bg, t[1] = bg ^ a, t[2] = bg ^ b, t[3] = t[2] ^ a;
    t[4] = bg ^ c, t[5] = t[4] ^ a, t[6] = t[4] ^ b, t[7] = t[6] ^ a;
    t[8] = bg ^ d, t[9] = t[8] ^ a, t[10] = t[8] ^ b, t[11] = t[10] ^ a;
    t[12] = t[8] ^ c, t[13] = t[12] ^ a, t[14] = t[12] ^ b, t[15] = t[14] ^ a;
}

/* nrows rows of the strip, nb bytes each, onto the page at row y as a panel 8 nb + 8 wide in the ink c (the panel's colour is
   a word at each end). Words only: a page takes no byte writes. */
static void rows(int y, const u8 *bits, int stride, int nb, int nrows, int c)
{
    u32 pb = d_pal(PANEL), t[16];
    tab(t, pb * 0x01010101u, d_pal(c) ^ pb);
    InkJob j = {(u32 *)(r_target() + y * 240), bits, t, nrows, nb, stride};
    hl_ink(&j);
}

void hl_draw(void)
{
    if (s2f.paused || s2f.docked || PB_LEVEL_END || PB_RESPAWN > 0)
        return;
    if (hl.card_on && (s16)((u16)s2f.clock - hl.card_end) >= 0)
        hl.card_on = 0;
    if (card_live()) {
        d_fill(0, 98, 240, 2, PANEL);
        rows(100, hl.card[0][0], CS, CB, NR, INK);
        if (hl.card_n == 2) {
            d_fill(0, 107, 240, 1, PANEL);
            rows(108, hl.card[1][0], CS, CB, NR, INK);
            d_fill(0, 115, 240, 2, PANEL);
        } else {
            d_fill(0, 107, 240, 2, PANEL);
        }
    }
    if (hl.nl) {
        int nb = ((hl.nl + (hl.ns ? hl.ns + 1 : 0)) * 6 + 7) >> 3;
        rows(HL_Y, hl.line[0], LS, nb, NR, hl.amber ? AMBER : INK);
    }
}
