/* host test of src/radio.c's song choice, skip, banner, handover at the end of an edit and the edits table (radio.c
   compiled with its hardware and Payback addresses replaced by host stand-ins) */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include "radio_h.c"

static int last_played;
static int rand_force = -1;
static unsigned rand_st = 12345;
int fake_rand(int n) { rand_st = rand_st * 1664525u + 1013904223u; return rand_force >= 0 ? rand_force % n : (rand_st >> 16) % n; }
void fake_play(int n) { last_played = n; PB_SONG_V = n; }
const char *fake_text(int id) { return "x"; }
void radio_seg(u8 *out, struct radio *r, int vol) { r->p += 1; memset(out, 0, 480); }
void pb_music(u8 *out) {}
char *d_cat(char *b, const char *s) { while ((*b = *s++)) b++; return b; }
void d_fill(int x, int y, int w, int h, int c) { last_w = w; }
void d_text(int x, int y, const char *s, int c) { strcpy(last_text, s); }
u8 opt_theme;

static u32 *tab, *ed;
#define ED_ADDR(i) (0x09200000 + 0x1000 * (i))
#define ED_SEG(i) (60 + 10 * (i))
#define ED_ID(i) ((i) * 3 % 11)                /* (not in order: the table gives the name) */
static void setup(int ne)
{
    tab[0] = 0x31444152; tab[1] = 3;
    for (int i = 0; i < 3; i++) { tab[2 + 3 * i] = 0x09a00040 + 0x1000 * i; tab[3 + 3 * i] = 100 + i; tab[4 + 3 * i] = i + 1; }
    memset(ed, 0, 256);
    if (ne) {
        ed[0] = 0x31444552; ed[1] = ne;
        for (int i = 0; i < ne; i++) { ed[2 + 3 * i] = ED_ADDR(i); ed[3 + 3 * i] = ED_SEG(i); ed[4 + 3 * i] = ED_ID(i); }
    }
}
static int check_fail;
#define CHECK(c) do { if (!(c)) { printf("FAIL line %d: %s\n", __LINE__, #c); check_fail++; } } while (0)
static const char *NAMES[11] = {"HARLEY MUSIC", "SPILT MILK", "GROOVY THING", "KNULLA KUK", "PELFORTH BLUES", "GUITAR SLINGER",
                                "REVERIE OF TRUTH", "GENERATION LOVE", "GROOVY ELEMENT", "OPERATION SEPTEMBER", "STREET JUNGLE"};

static int song(void) { return radio.now & 31; }

int main(void)
{
    mmap((void *)0x02000000, 0x40000, PROT_READ | PROT_WRITE, MAP_FIXED | MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    tab = mmap((void *)0x09a00000, 4096, PROT_READ | PROT_WRITE, MAP_FIXED | MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    ed = (u32 *)0x094fff00; mmap((void *)0x094ff000, 4096, PROT_READ | PROT_WRITE, MAP_FIXED | MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
    int counts[] = {0, 1, 5, 11};
    for (int ci = 0; ci < 4; ci++) {
        int ne = counts[ci], top = 6 + ne;
        setup(ne);
        for (int mode = 0; mode < 3; mode++) {
            int hist[32] = {0};
            radio.mode = mode;
            for (int p = 1; p <= top; p++)
                for (int rep = 0; rep < 60; rep++) {
                    radio.on = 0; radio.now = 0;
                    sf_play(p);
                    int t = song();
                    hist[t]++;
                    CHECK(t >= 1 && t <= top);
                    if (t > 6) {
                        CHECK(ne && t == (radio.now & 31));
                        CHECK(radio.on == 1 && last_played == 1);
                        CHECK(radio.p == (u8 *)(u32)ED_ADDR(t - 7) && radio.left == ED_SEG(t - 7) && radio.fade == 3);
                    } else if (t > 3) {
                        CHECK(radio.on == (t - 1) % 3 + 1);
                        CHECK(radio.p == (u8 *)(u32)(0x09a00040 + 0x1000 * (t - 4)));
                    } else CHECK(radio.on == 0 && last_played == (t - 1) % 3 + 1);
                    if (mode == RADIO_ORIGINALS) CHECK(t <= 3);
                    if (mode == RADIO_REMIXES) CHECK(t >= 4);
                }
            int lo = mode == RADIO_REMIXES ? 4 : 1, hi = mode == RADIO_ORIGINALS ? 3 : top;
            for (int t = lo; t <= hi; t++) CHECK(hist[t] > 0);     /* every song of the group comes up */
            printf("edits=%d mode=%d picks:", ne, mode);
            for (int t = 1; t <= top; t++) printf(" %d", hist[t]);
            printf("\n");
        }
        /* a skip never lands on the song it left, by any draw the radio can make, and a chain of skips (the pick lands on the
           song it left every time, the worst case) goes round the whole group, each song once */
        for (int mode = 0; mode < 3; mode++) {
            int lo = mode == RADIO_REMIXES ? 4 : 1, hi = mode == RADIO_ORIGINALS ? 3 : top;
            for (int t = lo; t <= hi; t++)
                for (int p = 1; p <= top; p++)
                    for (int force = 0; force < 4; force++) {
                        radio.on = 0; radio.mode = mode | 0x80; rand_force = force;
                        radio.now = t;
                        sf_play(p);
                        CHECK(song() != t && song() >= lo && song() <= hi && !(radio.mode & 0x80));
                    }
            for (int start = lo; start <= hi; start++) {
                int seen[32] = {0}, t = start;
                for (int k = 0; k < hi - lo + 1; k++) {
                    seen[t]++;
                    radio.on = 0; radio.mode = mode | 0x80;
                    radio.now = t;
                    rand_force = t - 4 < 0 ? 0 : t - 4;                /* (REMIXES: the draw that lands on t) */
                    sf_play(mode == RADIO_ALL || t <= 6 ? t : 1);
                    t = song();
                }
                rand_force = -1;
                CHECK(t == start);
                for (int u = lo; u <= hi; u++) CHECK(seen[u] == 1);
            }
        }
    }
    /* the interrupt: an edit plays to its end, raises Payback's song-ended flag 3 segments before it, then is silent */
    setup(11);
    int pick = 7;                                   /* edit 1 of the table: ED_SEG(0) = 60 segments */
    for (int e = 0; e < 11; e += 5) {
        radio.mode = RADIO_ALL; radio.on = 0; radio.now = 0; PB_SONG_V = 0; PB_VOL_V = 256; PB_ENDED_V = 0;
        sf_play(7 + e);
        CHECK(song() == 7 + e && radio.left == ED_SEG(e));
        u8 out[480]; int first = -1, flags = 0;
        for (int i = 0; i < ED_SEG(e) + 20; i++) {
            u8 *before = (u8 *)radio.p;
            radio_irq(out);
            if (PB_ENDED_V && first < 0) first = i;
            if (i >= ED_SEG(e)) CHECK((u8 *)radio.p == before);          /* silent: nothing is decoded after the end */
            else CHECK((u8 *)radio.p == before + 1);                     /* ... and no jump back to anywhere before it */
        }
        printf("edit %d (%d segments): ended flag first at interrupt %d\n", e + 1, ED_SEG(e), first);
        CHECK(first == ED_SEG(e) - 4);
        CHECK(radio.left == 0 && radio.on == 1);
        /* ... Payback's radio picks the next song: the old one's tail is one buffer, then it is the new song's */
        PB_ENDED_V = 0;
        radio.mode = RADIO_REMIXES;
        sf_play(3);
        CHECK(song() >= 4);
    }
    /* a remix ends: flag at 3 left, then quiet (as it always did) */
    radio.mode = 2; radio.on = 0; radio.now = 0; PB_SONG_V = 0; PB_ENDED_V = 0;
    rand_force = 0; sf_play(4); rand_force = -1;
    CHECK(song() == 4);
    int ended = 0, at = -1; u8 out[480];
    for (int i = 0; i < 120; i++) { radio_irq(out); if (PB_ENDED_V && !ended) { ended = 1; at = i; } }
    printf("remix 1 (100 segments): ended flag first at interrupt %d\n", at);
    CHECK(at == 96);
    /* a skip fades the edit: radio_skip while it plays, and the interrupt ends it */
    radio.mode = 0; radio.on = 0; PB_SONG_V = 0; PB_ENDED_V = 0; sf_play(8);
    CHECK(song() == 8);
    PB_SONG_V = 1; radio.fade = 0; radio_skip();
    CHECK(radio.fade == 1 && (radio.mode & 0x80) && radio.on == 1);
    radio_irq(out);
    CHECK(PB_ENDED_V == 1 && radio.fade == 2);
    /* the banner: every name in the table, and none for a song of Payback's the wrong way round */
    for (int i = 0; i < 11; i++) {
        setup(11);
        radio.now = (32 * (i + 1)) | (7 + i) & 31; radio.on = 1;
        radio_hud(1, 1, 0); radio.now = (32 * (i + 2)) | (7 + i) & 31; radio_hud(1, 1, 0);
        char want[40]; sprintf(want, "RADIO: %s", NAMES[ED_ID(i)]);
        CHECK(!strcmp(last_text, want) && last_w + 4 < 240);
        if (i == 0 || i == 9) printf("banner: '%s' width %d (screen 240)\n", last_text, last_w);
    }
    radio.now = 64 | 5; radio_hud(1, 1, 0); printf("banner: '%s'\n", last_text); CHECK(!strcmp(last_text, "RADIO: SONG 2 REMIX"));
    radio.now = 96 | 3; radio_hud(1, 1, 0); printf("banner: '%s'\n", last_text); CHECK(!strcmp(last_text, "RADIO: SONG 4"));
    printf(check_fail ? "FAILED %d\n" : "ALL OK\n", check_fail);
    return check_fail != 0;
}
