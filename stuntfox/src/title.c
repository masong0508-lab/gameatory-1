/* STAR-FLYBACK's title, in place of Payback's two films (merged build only).

   Payback plays two films with its own player (IWRAM 0x03001660, called with the film's address,
   returns 1 when A or B skipped it): the studio logo, then the intro that ends on the burning
   PAYBACK title. Both flash the whole screen white (headlights, a starburst, a logo on white),
   so build.py points both calls here instead:
     sf_studio_film: shows nothing and returns at once ("played to the end", so the intro follows)
     sf_intro_film:  our title card (tools/mklogo.py: STAR-FLYBACK burning in Payback's style),
                     faded in and out slowly with the hardware brightness fade, held for a few
                     seconds or until A, B or START. Nothing on it changes faster than a slow fade.
   Both leave the screen as Payback's player does: black, mode 4. The menu's "view intro" goes
   through the same call and so shows the title card too. */
#include "gba.h"

extern const u16 sf_title_card[240 * 160];

#define VRAM32 ((volatile u32 *)0x06000000)
#define KEYS_SKIP 0x000b                 /* A, B, START (KEYINPUT bits are 0 while held) */
#define FADE_STEP 3                      /* frames per brightness step: 16 steps = 0.8 s */
#define HOLD 270                         /* frames the card stays up (4.5 s) */

static void vsync(void)
{
    while (REG_VCOUNT >= 160)
        ;
    while (REG_VCOUNT < 160)
        ;
}

static int skip_pressed(void)
{
    return (~REG_KEYINPUT) & KEYS_SKIP;
}

static void clear_screen(void)
{
    for (int i = 0; i < 240 * 160 / 2; i++)
        VRAM32[i] = 0;
}

static void done(void)
{
    clear_screen();                      /* (still darkened to black: never forced blank, it shows white) */
    REG_BLDCNT = 0;
    REG_BLDY = 0;
    REG_DISPCNT = 0x0404;
}

int sf_studio_film(const void *film)
{
    (void)film;
    return 0;
}

int sf_intro_film(const void *film)
{
    (void)film;
    int level = 16, skipped = 0, held = skip_pressed();
    vsync();
    REG_BLDCNT = 0x00c4;                 /* BG2 darkened by BLDY (16 = black) */
    REG_BLDY = level;
    REG_DISPCNT = 0x0403;
    const u32 *src = (const u32 *)sf_title_card;
    for (int i = 0; i < 240 * 160 / 2; i++)
        VRAM32[i] = src[i];
    for (int f = 0; ; f++) {
        vsync();
        int k = skip_pressed();
        if (!k)
            held = 0;                    /* a button still held from the menu does not count */
        else if (!held && f > 8)
            skipped = 1;
        if (skipped || f >= 16 * FADE_STEP + HOLD) {
            if (level >= 16)
                break;
            if (skipped || f % FADE_STEP == 0)  /* skipping fades out at 1 step a frame (0.27 s) */
                REG_BLDY = ++level;
        } else if (level > 0 && f % FADE_STEP == 0) {
            REG_BLDY = --level;
        }
    }
    done();
    return 1;   /* "skipped": Payback then notes the time, else it waits out the film's full length */
}
