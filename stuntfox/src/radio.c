/* The car radio: Payback's songs 1, 2 and 4 and our remixes of them, six songs at random.

   Payback's radio (0x08077464 on getting in, 0x08077498 every tick) picks 1 + random(n) and
   plays it; the build makes that random(6) and the play sf_play. 1-3 are Payback's own songs,
   4-6 the remixes (as the RADIO option allows). A remix is started as Payback's song of the
   same number, so Payback's radio, pause, fades and scenes see a song playing as ever, but its
   sequencer is kept out (sf_seq) and its music pass gives way to radio_irq (sf_mus): the
   stream at the top of the cartridge (tools/mkradio.py), decoded into the music half of
   Payback's buffer, 480 samples an interrupt, at Payback's music volume. The effects half is
   left alone. Near the end the song-ended flag goes up and Payback's radio picks the next.

   The state is at the top of EWRAM, which only the boot clears: the interrupt needs it at any
   time, through level loads and the screens our memory is lent out for. 20 bytes is all there
   is there, hence the packing (radio.h). */
#include "gba.h"
#include "draw2d.h"
#include "render.h"
#include "palette.h"
#include "radio.h"

#define PB_SONG (*(volatile s16 *)0x020001c8)      /* Payback's song, -1: none */
#define PB_VOL (*(volatile s16 *)0x020001ca)       /* its music volume, 0-256 */
#define PB_ENDED (*(volatile u8 *)0x02001ce6)      /* its song-ended flag */
#define PB_PLAY ((void (*)(int))0x08076c99)
#define STREAMS ((const u32 *)0x09a00000)          /* magic, count, then {address, segments, song} */
#define STREAMS_MAGIC 0x31444152
#define ENDS_AT 3                  /* segments before the end when the song is said to have ended
                                      (Payback's radio takes a frame or two to pick the next) */
#define ORIG 0x80                  /* + Payback's song: a skip fades it */
#define TAIL 0x40                  /* a remix gave way to Payback's own song: one more interrupt */
#define SKIP 0x80                  /* in mode */
#define PB_BUF ((u8 *)0x02001514)  /* Payback's two sound buffers, 960 bytes each: effects, music */

struct radio radio __attribute__((section(".radio")));

void radio_seg(u8 *out, struct radio *r, int vol);   /* radiodec.s */
void pb_music(u8 *out);

static void quiet(u8 *out)
{
    for (int i = 0; i < 120; i++)
        ((u32 *)out)[i] = 0;
}

/* 20 ms in or out of silence, over one buffer: no click at a start, a stop or a skip */
static void ramp(u8 *out, int in)
{
    for (int i = 0; i < 480; i++)
        out[i] = (s8)out[i] * ((in ? i : 480 - i) * 17 >> 4) >> 9;
}

/* where the song before left off (the last sample of the other buffer's music half) eases to 0
   over this buffer, under the new song: no click when one song cuts in on another */
static void bridge(u8 *out)
{
    int last = (s8)(out == PB_BUF + 0x1e0 ? PB_BUF + 0x3c0 + 0x1e0 : PB_BUF + 0x1e0)[479];
    if (!last)
        return;
    for (int i = 0; i < 480; i++) {
        int v = (s8)out[i] + (last * (480 - i) * 17 >> 13);
        out[i] = v < -128 ? -128 : v > 127 ? 127 : v;
    }
}

/* the volume moved since the last buffer (Payback's ramps, its pause): ease from the old level
   to the new over this one rather than step to it */
static void glide(u8 *out, int from, int to)
{
    int f = (from << 16) / to, df;
    f = f > 8 << 16 ? 8 << 16 : f;
    df = ((1 << 16) - f) / 480;
    for (int i = 0; i < 480; i++, f += df) {
        int v = (s8)out[i] * f >> 16;
        out[i] = v < -128 ? -128 : v > 127 ? 127 : v;
    }
}

/* the interrupt (sf_mus, while on): the music half of the next buffer, 480 bytes */
void radio_irq(u8 *out)
{
    struct radio *r = &radio;
    int vol = PB_VOL < 0 ? 0 : PB_VOL > 256 ? 256 : PB_VOL, mine = PB_SONG == (r->on & 3);
    if (r->on == TAIL) {
        r->on = r->fade = 0;
        pb_music(out);
        bridge(out);
        return;
    }
    if (r->on & ORIG) {                        /* a skip: Payback's own song fades, then quiet */
        if (!mine) {
            r->on = r->fade = 0;
            pb_music(out);
        } else if (r->fade == 1) {
            pb_music(out);
            ramp(out, 0);
            r->fade = 2;
            PB_ENDED = 1;
        } else {
            quiet(out);
        }
        return;
    }
    if (!mine && r->fade != 2)                 /* Payback stopped it or started another song */
        r->fade = 1;
    int end = r->fade == 1;                    /* (the song-ended flag goes up once: Payback
                                                  clears it as it picks, and would pick again) */
    if (r->fade == 2 || !r->left) {
        quiet(out);
    } else {
        int was = r->vol + 1, v = vol ? vol : was;     /* (at volume 0 they keep their scale) */
        if (v != was) {                        /* (exact: they are multiples of the old one) */
            r->a = r->a / was * v;
            r->b = r->b / was * v;
            r->vol = v - 1;
        }
        radio_seg(out, r, v);
        end |= --r->left == ENDS_AT;
        if (!vol)
            quiet(out);
        else if (r->fade & 1)
            ramp(out, r->fade == 3);
        else if (v != was)
            glide(out, was, v);
        if (r->fade == 3 && vol)
            bridge(out);
    }
    if (!vol && !r->fade)
        r->fade = 3;                           /* (silenced: back in from silence) */
    else if (vol || r->fade != 3)
        r->fade = r->fade == 1 ? 2 : r->fade == 3 ? 0 : r->fade;
    if (mine && end)
        PB_ENDED = 1;
    if (!mine)
        r->on = r->fade = 0;
}

static void news(int now)
{
    radio.now = ((radio.now | 7) + 1) | now;
}

/* Payback's radio picks a song: 0 (a few vehicles and the menus), else 1 + random(6) */
void sf_play(int n)
{
    struct radio *r = &radio;
    r->on = r->on ? TAIL : 0;                  /* (the interrupt leaves any remix now) */
    r->fade = 0;
    if (n < 1 || n > 6) {
        PB_PLAY(n);
        return;
    }
    int remix = n > 3;
    n = remix ? n - 3 : n;
    int mode = r->mode & ~SKIP;
    if (mode != RADIO_ALL)
        remix = mode == RADIO_REMIXES;
    int t = n + 3 * remix;
    if ((r->mode & SKIP) && t == (r->now & 7))  /* a skip never lands on the song it left */
        t = mode == RADIO_ALL ? t % 6 + 1 : (t - 1) / 3 * 3 + t % 3 + 1;
    r->mode = mode;
    n = (t - 1) % 3 + 1;
    remix = t > 3;
    const u32 *s = STREAMS + 2 + 3 * (n - 1);
    if (!remix || STREAMS[0] != STREAMS_MAGIC || STREAMS[1] < 3) {
        PB_PLAY(n);
        news(n);
        return;
    }
    u16 ime = REG_IME;
    REG_IME = 0;
    PB_PLAY(n);                                /* Payback's state as for its song n */
    r->p = (const u8 *)s[0];
    r->left = s[1];
    r->a = r->b = 0;
    r->vol = 0;
    r->fade = 3;                               /* (in from silence: no click) */
    r->on = n;
    REG_IME = ime;
    news(n + 3);
}

void radio_skip(void)
{
    struct radio *r = &radio;
    if (PB_SONG < 1 || PB_SONG > 3 || r->fade || PB_ENDED)
        return;
    u16 ime = REG_IME;
    REG_IME = 0;
    if (r->on != PB_SONG)                      /* Payback's own: fade it in the interrupt */
        r->on = ORIG + PB_SONG;
    r->fade = 1;
    r->mode |= SKIP;
    REG_IME = ime;
}

/* every sound interrupt (sf_seq): Payback reads the keypad once a game frame, a tenth of a second
   apart in a car, too coarse to tell two buttons pressed together from one held and then the
   other */
void radio_keys(void)
{
    struct radio *r = &radio;
    u16 k = REG_KEYINPUT;                      /* (0: down) */
    int s = r->keys & 15, t = r->keys >> 4;
    s = k & KEY_SELECT ? 0 : s < 15 ? s + 1 : s;
    t = k & KEY_R ? 0 : t < 15 ? t + 1 : t;
    r->keys = t << 4 | s;
}

/* SELECT and R both down, the one pressed second within 6 interrupts (0.1-0.12 s) of the
   other: a chord. R held and then SELECT (boosting and calling the Arwing or swinging the
   camera), or SELECT held and then R, are not. Either still at 15 is too long ago to tell. */
int radio_chord(void)
{
    int k = radio.keys, s = k & 15, t = k >> 4;
    return s < 15 && t < 15 && (s > t ? s - t : t - s) <= 6;
}

int radio_mode(void)
{
    return radio.mode & ~SKIP;
}

void radio_set_mode(int m)
{
    radio.mode = m;
}

const char *radio_mode_name(int m)
{
    return m == RADIO_ORIGINALS ? "RADIO: ORIGINALS" : m == RADIO_REMIXES ? "RADIO: REMIXES" : "RADIO: ALL SONGS";
}

/* the song's name for 2 s when one starts in a car: left, under the hearts, clear of Payback's
   HUD (the car's name at the top as you get in, the minimap, the stunt letters lower down). It
   is drawn into our picture, which Payback keeps behind its pause menu and dialogs: START puts
   it away for good (start: Payback's START this frame). */
void radio_hud(int driving, int ticks, int start)
{
    static u8 seen, left, set;
    if (!set)
        set = 1, seen = radio.now;             /* (we started over: no new song) */
    if (radio.now != seen)
        seen = radio.now, left = 120;
    if (start)
        left = 0;
    if (!left)
        return;
    left = left > ticks ? left - ticks : 0;
    int now = radio.now & 7;
    if (!driving || !now || now > 6)
        return;
    char b[24], *p = d_cat(b, "RADIO: SONG ");
    static const char num[3] = {'1', '2', '4'};
    *p++ = num[(now - 1) % 3];
    *p = 0;
    if (now > 3)
        d_cat(p, " REMIX");
    int n = 0;
    while (b[n])
        n++;
    d_fill(4, 42, n * TEXT_W + 8, 12, COLOR(M_ROAD, 0, 0));
    d_text(8, 44, b, COLOR(M_GLOW, 3, 0));
}
