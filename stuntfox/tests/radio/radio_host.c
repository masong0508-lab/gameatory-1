/* host test of src/radio.c's song choice, skip, banner and Street Jungle loop (radio.c compiled with its hardware
   and Payback addresses replaced by host stand-ins) */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include "radio_h.c"

static int rng_calls, played[16], last_played;
static int rand_seq;
int fake_rand(int n) { rng_calls++; return (rand_seq++ * 7 + 3) % n; }
void fake_play(int n) { last_played = n; PB_SONG_V = n; }
const char *fake_text(int id) { return "x"; }
void radio_seg(u8 *out, struct radio *r, int vol) { r->p += 1; memset(out, 0, 480); }
void pb_music(u8 *out) {}
char *d_cat(char *b, const char *s) { while ((*b = *s++)) b++; return b; }
void d_fill(int x, int y, int w, int h, int c) { last_w = w; }
void d_text(int x, int y, const char *s, int c) { strcpy(last_text, s); }
u8 opt_theme;

#define STREAM_BASE 0x09a00000
static u32 *tab;
static void setup(int sj)
{
    tab[0] = 0x31444152; tab[1] = sj ? 4 : 3;
    for (int i = 0; i < 3; i++) { tab[2 + 3 * i] = 0x09a00040 + 0x1000 * i; tab[3 + 3 * i] = 100 + i; tab[4 + 3 * i] = i + 1; }
    memset(tab + 11, 0, 20);
    if (sj) { tab[11] = 0x09200060; tab[12] = 50; tab[13] = 0x09250000; tab[14] = 40; tab[15] = (u32)(u16)-1234 | (u32)(u16)5678 << 16; }
}
static int check_fail;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); check_fail++; } } while (0)

int main(void)
{
    mmap((void *)0x02000000, 0x40000, PROT_READ | PROT_WRITE, MAP_FIXED | MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    tab = mmap((void *)STREAM_BASE, 4096, PROT_READ | PROT_WRITE, MAP_FIXED | MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    int hist[3][8];
    for (int sj = 0; sj < 2; sj++) {
        setup(sj);
        for (int mode = 0; mode < 3; mode++) {
            memset(hist[mode], 0, sizeof hist[mode]);
            radio.mode = mode;
            for (int p = 1; p <= 6 + sj; p++) {
                for (int rep = 0; rep < 40; rep++) {
                    radio.on = 0;
                    sf_play(p);
                    int t = radio.now & 7;
                    hist[mode][t]++;
                    CHECK(t >= 1 && t <= 6 + sj);
                    if (t == 7) { CHECK(sj); CHECK(radio.on == 1 && last_played == 1); CHECK(radio.p == (u8 *)0x09200060 && radio.left == 50); }
                    else if (t > 3) { CHECK(radio.on == (t - 1) % 3 + 1); CHECK(radio.p == (u8 *)(u32)(0x09a00040 + 0x1000 * (t - 4))); }
                    else CHECK(radio.on == 0 && last_played == (t - 1) % 3 + 1);
                    if (mode == RADIO_ORIGINALS) CHECK(t <= 3);
                    if (mode == RADIO_REMIXES) CHECK(t >= 4);
                }
            }
            printf("sj=%d mode=%d picks over all p:", sj, mode);
            for (int t = 1; t <= 7; t++) printf(" %d", hist[mode][t]);
            printf("\n");
        }
        /* skip never lands on the song it left, each mode's group is a cycle */
        for (int mode = 0; mode < 3; mode++)
            for (int start = 1; start <= 6 + sj; start++) {
                if ((mode == RADIO_ORIGINALS && start > 3) || (mode == RADIO_REMIXES && start < 4)) continue;
                int seen[9] = {0}, t = start;
                radio.mode = mode;
                for (int k = 0; k < 20; k++) {
                    radio.now = (radio.now & 0xf8) | t;
                    radio.mode = mode | 0x80;
                    for (int p = 1; p <= 6 + sj; p++) {
                        radio.on = 0; radio.mode = mode | 0x80;
                        sf_play(p);
                        CHECK((radio.now & 7) != t);
                        CHECK(!(radio.mode & 0x80));
                        radio.now = (radio.now & 0xf8) | t;
                    }
                }
            }
        /* the cycle of one skip chain in the ALL mode with sj and the remixes */
        radio.mode = 0; radio.now = 1; int t = 1; int path[16];
        for (int k = 0; k < 8; k++) { radio.mode |= 0x80; radio.on = 0; sf_play(1 + (t - 1) % (6 + sj)); /* pick equals the song it left */ t = radio.now & 7; path[k] = t; }
        printf("sj=%d skip chain ALL from 1 (pick = the song left):", sj); for (int k = 0; k < 8; k++) printf(" %d", path[k]); printf("\n");
        radio.mode = 2; radio.now = 4; t = 4;
        for (int k = 0; k < 8; k++) { radio.mode = 2 | 0x80; radio.on = 0; radio.now = (radio.now & 0xf8) | t; if (!sj) sf_play(1 + (t - 1) % 3); else { rand_seq = 0; /* force same pick */ sf_play(1); } t = radio.now & 7; path[k] = t; }
        printf("sj=%d skip chain REMIXES:", sj); for (int k = 0; k < 8; k++) printf(" %d", path[k]); printf("\n");
    }
    /* the interrupt: Street Jungle loops, others end */
    setup(1);
    radio.mode = 0; radio.on = 0; PB_SONG_V = 0; PB_VOL_V = 256;
    sf_play(7);
    CHECK((radio.now & 7) == 7 && radio.on == 1);
    u8 out[480]; int loops = 0, ended_flag = 0, jumps = 0;
    PB_ENDED_V = 0;
    for (int i = 0; i < 400; i++) {
        u8 *before = (u8 *)radio.p;
        radio_irq(out);
        if ((u8 *)radio.p != before + 1) { jumps++; CHECK(radio.p == (u8 *)(0x09250000 + 0)); CHECK(radio.left == 40);
            CHECK(radio.a == -1234 * 256 && radio.b == 5678 * 256); if (i > 0) { CHECK(i == 49 || (i - 49) % 40 == 0); } }
        if (PB_ENDED_V) ended_flag = 1;
    }
    printf("SJ interrupt: %d loop jumps in 400 interrupts (first at 49), ended flag %d, song still on=%d fade=%d\n", jumps, ended_flag, radio.on, radio.fade);
    CHECK(jumps == 1 + (400 - 50) / 40 && !ended_flag && radio.on == 1);
    /* a remix ends: flag at 3 left, then quiet */
    radio.mode = 2; radio.on = 0; radio.now = 0; PB_SONG_V = 0; PB_ENDED_V = 0;
    tab[1] = 3; sf_play(4); /* remix of song 1, 100 segments */
    ended_flag = 0; int at = -1;
    for (int i = 0; i < 120; i++) { radio_irq(out); if (PB_ENDED_V && !ended_flag) { ended_flag = 1; at = i; } }
    printf("remix 1 (100 segments): ended flag first at interrupt %d\n", at);
    CHECK(at == 96);
    /* banner */
    radio.now = 8 | 7; radio_hud(1, 1, 0); radio.now = 16 | 7; radio_hud(1, 1, 0);
    printf("banner: '%s' width %d (screen 240)\n", last_text, last_w);
    CHECK(!strcmp(last_text, "RADIO: STREET JUNGLE") && last_w + 4 < 240);
    radio.now = 24 | 5; radio_hud(1, 1, 0); printf("banner: '%s'\n", last_text); CHECK(!strcmp(last_text, "RADIO: SONG 2 REMIX"));
    radio.now = 32 | 3; radio_hud(1, 1, 0); printf("banner: '%s'\n", last_text); CHECK(!strcmp(last_text, "RADIO: SONG 4"));
    printf(check_fail ? "FAILED %d\n" : "ALL OK\n", check_fail);
    return check_fail != 0;
}
