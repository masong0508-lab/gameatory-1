/* T0 for save.c on the PC: the image's crc, the password codec, the slots with a power cut at every point, and the
   identify step against models of the chips it may meet. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#include "../../src/save.h"

static int bad, total;
#define CHECK(c, ...) do { total++; if (!(c)) { bad++; printf("FAIL line %d: ", __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

static unsigned rs = 12345;
static unsigned rnd(void) { rs = rs * 1664525u + 1013904223u; return rs >> 8; }

/* ---- a block device with a power cut: after `cut` writes (counted from arm) nothing more lands; the write that
   hits the cut leaves `torn` bytes of garbage in the block ---- */
static u8 mem[1024][8];
static int cut = -1, torn, nwr;
static int d_rd(int b, u8 *o) { if (b < 0 || b >= 1024) return 1; memcpy(o, mem[b], 8); return 0; }
static int d_wr(int b, const u8 *i)
{
    if (b < 0 || b >= 1024) return 1;
    nwr++;
    if (cut == 0) return 1;                     /* power gone: nothing lands, the caller never sees it finish */
    if (cut > 0 && --cut == 0) {
        if (torn) for (int k = 0; k < 8; k++) mem[b][k] = k < torn ? i[k] : (u8)rnd();
        return 1;
    }
    memcpy(mem[b], i, 8);
    return 0;
}
static const SvDev dev = {d_rd, d_wr};

static void mkprog(Prog *p, unsigned seed)
{
    rs = seed;
    memset(p, 0, sizeof *p);
    for (int c = 0; c < CP_CHAPS; c++) {
        p->acts[c] = rnd() & 63, p->chal[c] = rnd() & 1023, p->medals[c] = rnd() & 63, p->contracts[c] = rnd() & 31;
    }
    for (int i = 0; i < 32; i++) p->sg[i] = rnd();
    for (int i = 0; i < CP_BEST; i++) p->best[i] = rnd() & 0x7fff;
    p->chap_cur = rnd() % 11, p->chap_unlocked = rnd() % 11, p->flags = 1, p->story[0] = rnd();
    prog_seal(p);
}

static void test_crc(void)
{
    Prog p;
    CHECK(sizeof(Prog) == 260, "Prog is %d bytes", (int)sizeof(Prog));
    CHECK(sv_crc16("123456789", 9) == 0x29b1, "crc16 ccitt-false of the check string: %04x", sv_crc16("123456789", 9));
    mkprog(&p, 1);
    CHECK(prog_ok(&p), "a sealed image is ok");
    Prog q = p;
    q.acts[3] ^= 1;
    CHECK(!prog_ok(&q), "a flipped bit is caught");
    q = p; q.magic ^= 1;
    CHECK(!prog_ok(&q), "a wrong magic is caught");
    q = p; q.ver++;
    CHECK(!prog_ok(&q), "a wrong version is caught");
    memset(&q, 0, sizeof q);
    CHECK(!prog_ok(&q), "zeros are not an image");
    q = p; q.chap_cur = 12; prog_seal(&q);
    CHECK(!prog_ok(&q), "a chapter out of range is caught");
}

/* what a password keeps of an image */
static void pw_view(const Prog *p, int *v)
{
    int done = 0, medals = 0;
    for (int c = 0; c < 11; c++) { done |= (p->acts[c] & 63) == 63 ? 1 << c : 0; medals += __builtin_popcount(p->medals[c] & 63); }
    medals += __builtin_popcount(p->sg[4] | p->sg[5] << 8);
    if (p->flags & 2) medals += p->spare[0];
    v[0] = p->chap_cur; v[1] = p->acts[p->chap_cur] & 63; v[2] = done; v[3] = (p->sg[8] & 3) | (p->sg[9] & 3) << 2 | (p->sg[10] & 3) << 4 | (p->sg[11] & 3) << 6;
    v[4] = (p->sg[6] | p->sg[7] << 8) >> 6 & 63;
    int cr = (int)(p->sg[0] | p->sg[1] << 8 | p->sg[2] << 16 | p->sg[3] << 24) / 100;
    v[5] = cr < 0 ? 0 : cr > 1023 ? 1023 : cr; v[6] = medals > 127 ? 127 : medals; v[7] = p->ace & 1; v[8] = p->story[0];
}

static void test_pw(void)
{
    int fine = 0, n = 3000, miss = 0, trials = 0;
    for (int s = 0; s < n; s++) {
        Prog p, q;
        mkprog(&p, 100 + s);
        p.ace = s & 1;
        for (int i = 8; i < 12; i++) p.sg[i] %= 3;
        p.sg[0] = rnd(); p.sg[1] = rnd(); p.sg[2] = rnd() & 1; p.sg[3] = 0;     /* credits up to ~130k */
        if (s % 3 == 0) p.acts[p.chap_cur] = 63;
        prog_seal(&p);
        char a[PW_LEN + 1], b[PW_LEN + 1];
        pw_encode(&p, a);
        CHECK(strlen(a) == 16, "password is 16 letters: %s", a);
        for (int i = 0; i < 16; i++) CHECK(strchr(PW_ALPHA, a[i]) && !strchr("01IO", a[i]), "letter %c is in the alphabet", a[i]);
        memset(&q, 0xcc, sizeof q);
        if (!pw_decode(a, &q)) { CHECK(0, "a fresh code is refused: %s", a); continue; }
        CHECK(prog_ok(&q), "the image from a code is sealed");
        int v1[9], v2[9];
        pw_view(&p, v1); pw_view(&q, v2);
        int same = !memcmp(v1, v2, sizeof v1);
        /* (an image whose current chapter has all its acts: its bits come back as the chapter's done bit alone) */
        if (!same) { for (int i = 0; i < 9; i++) printf("  %d: %d %d\n", i, v1[i], v2[i]); }
        CHECK(same, "everything the code keeps comes back: %s", a);
        pw_encode(&q, b);
        CHECK(!strcmp(a, b), "encode(decode(code)) is the code: %s %s", a, b);
        CHECK(q.chap_unlocked >= q.chap_cur, "the current chapter is open");
        fine += same;
        /* a wrong letter */
        for (int pos = 0; pos < 16; pos += 3) {
            char c[PW_LEN + 1];
            strcpy(c, a);
            c[pos] = PW_ALPHA[(strchr(PW_ALPHA, a[pos]) - PW_ALPHA + 1 + rnd() % 31) & 31];
            Prog z;
            trials++;
            if (pw_decode(c, &z)) miss++;
        }
        char lo[PW_LEN + 1];
        for (int i = 0; i < 16; i++) lo[i] = a[i] >= 'A' && a[i] <= 'Z' ? a[i] + 32 : a[i];
        lo[16] = 0;
        Prog z;
        CHECK(pw_decode(lo, &z), "lower case is taken");
    }
    CHECK(fine == n, "round trip %d of %d", fine, n);
    CHECK(miss * 100 <= trials / 2 + 5, "a changed letter passes %d of %d times", miss, trials);
    printf("password: %d codes, a changed letter got through %d of %d times\n", n, miss, trials);
    Prog z;
    CHECK(!pw_decode("ABCDEFGHJKLMNPQ", &z), "a short code is refused");
    CHECK(!pw_decode("ABCDEFGHJKLMNPQ0", &z), "a 0 is refused");
    CHECK(!pw_decode("ABCDEFGHJKLMNPQRS", &z), "a long code is refused");
    CHECK(!pw_decode("", &z), "an empty code is refused");
    CHECK(!pw_decode("AAAAAAAAAAAAAAAA", &z), "all A is refused");
}

/* ---- slots ---- */
static void wipe(void) { memset(mem, 0xff, sizeof mem); cut = -1; torn = 0; nwr = 0; }

static int save_all(const Prog *p, SvPick *pk, int *writes)
{
    SvW w;
    int r, w0 = nwr;
    sv_begin(&w, (const u8 *)p, sizeof *p, pk);
    do r = sv_step(&dev, &w, (const u8 *)p, sizeof *p); while (r > 0);
    if (writes) *writes = nwr - w0;
    if (r == 0) { pk->seq = w.seq, pk->slot = w.slot, pk->valid = 1; }
    return r;
}

static void test_slots(void)
{
    Prog a, b, got;
    SvPick pk = {0, 0, 0}, pk2;
    wipe();
    CHECK(!sv_load(&dev, (u8 *)&got, sizeof got, &pk2), "a blank chip has no save");
    mkprog(&a, 7);
    CHECK(save_all(&a, &pk, 0) == 0, "first save");
    CHECK(pk.slot == 0 && pk.seq == 1, "first save goes to slot A, seq 1");
    CHECK(sv_load(&dev, (u8 *)&got, sizeof got, &pk2) && !memcmp(&got, &a, sizeof a) && pk2.seq == 1 && pk2.slot == 0, "it loads back");
    /* 50 in a row: slots alternate, seq counts, each loads back */
    for (int i = 0; i < 50; i++) {
        mkprog(&b, 1000 + i);
        CHECK(save_all(&b, &pk, 0) == 0, "save %d", i);
        int ok = sv_load(&dev, (u8 *)&got, sizeof got, &pk2);
        CHECK(ok && !memcmp(&got, &b, sizeof b) && pk2.seq == 2 + i && pk2.slot == (i + 1) % 2, "save %d loads back, slot %d seq %d", i, pk2.slot, pk2.seq);
        pk = pk2;
    }
    /* only what changed is written: a flipped byte, one payload block and the header (plus what the other slot differs by) */
    b.acts[2] ^= 4; prog_seal(&b);
    int wr;
    save_all(&b, &pk, &wr);                              /* (into the slot that held the save before: it differs by the old change too) */
    save_all(&b, &pk, &wr);
    save_all(&b, &pk, &wr);
    CHECK(wr == 1, "the same image a third time writes only the header (%d writes)", wr);
    b.acts[2] ^= 4; prog_seal(&b);
    save_all(&b, &pk, &wr);
    CHECK(wr <= 2 * 2 + 1, "a one-byte change costs a few blocks (%d writes)", wr);
    printf("slots: a changed byte and its crc cost %d block writes\n", wr);
    /* a cut at every point of a save: the last good image is always the one that loads, and the new one once the header is in */
    mkprog(&a, 31); wipe(); memset(&pk, 0, sizeof pk);
    save_all(&a, &pk, 0);
    mkprog(&b, 32);
    int nb = (sizeof(Prog) + 7) / 8;
    for (int torn_k = 0; torn_k <= 8; torn_k += 4) {     /* 0: the cut write lands nothing; 4: half a block of new, half garbage; 8: a block of garbage tail */
        for (int c = 1; c <= nb + 1; c++) {
            u8 save[1024][8];
            memcpy(save, mem, sizeof mem);
            SvPick p2 = pk;
            cut = c; torn = torn_k; nwr = 0;
            int r = save_all(&b, &p2, 0);
            cut = -1;
            int ok = sv_load(&dev, (u8 *)&got, sizeof got, &pk2);
            int is_a = ok && !memcmp(&got, &a, sizeof a), is_b = ok && !memcmp(&got, &b, sizeof b);
            CHECK(ok && (is_a || is_b), "cut at write %d (torn %d): some good image loads", c, torn_k);
            CHECK(r < 0 ? (is_a || (torn_k == 8 && is_b)) : 1, "cut at write %d (torn %d): the old image is back (or the cut write had landed)", c, torn_k);
            /* the cut write is the header only when c == the count of writes a full save makes */
            if (r >= 0) CHECK(is_b, "no cut reached: the new image");
            /* and a save after the cut, from what loads, goes on */
            SvPick p3 = pk2;
            CHECK(save_all(&b, &p3, 0) == 0, "a save after the cut works");
            CHECK(sv_load(&dev, (u8 *)&got, sizeof got, &pk2) && !memcmp(&got, &b, sizeof b), "and loads");
            memcpy(mem, save, sizeof mem);
        }
    }
    /* a bad slot A: B loads */
    mkprog(&a, 41); wipe(); memset(&pk, 0, sizeof pk);
    save_all(&a, &pk, 0);
    mkprog(&b, 42);
    save_all(&b, &pk, 0);                                 /* B has b (seq 2), A has a (seq 1) */
    mem[SV_SLOT_B + 3][0] ^= 1;                           /* B's payload: its crc fails */
    CHECK(sv_load(&dev, (u8 *)&got, sizeof got, &pk2) && !memcmp(&got, &a, sizeof a) && pk2.slot == 0, "B damaged: A loads");
    mem[SV_SLOT_B + 3][0] ^= 1;
    mem[SV_SLOT_A][2] ^= 0xff;                            /* A's header: its own check fails */
    CHECK(sv_load(&dev, (u8 *)&got, sizeof got, &pk2) && !memcmp(&got, &b, sizeof b) && pk2.slot == 1, "A's header damaged: B loads");
    mem[SV_SLOT_B][4] ^= 1;
    CHECK(!sv_load(&dev, (u8 *)&got, sizeof got, &pk2), "both damaged: none");
    /* the count wraps */
    mkprog(&a, 51); wipe();
    pk.valid = 1; pk.slot = 1; pk.seq = 65534;
    save_all(&a, &pk, 0);                                 /* 65535 in A */
    mkprog(&b, 52);
    save_all(&b, &pk, 0);                                 /* 0 in B */
    CHECK(pk.seq == 0 && sv_load(&dev, (u8 *)&got, sizeof got, &pk2) && !memcmp(&got, &b, sizeof b) && pk2.slot == 1, "seq 0 after 65535 is newer");
    Prog c3; mkprog(&c3, 53);
    save_all(&c3, &pk, 0);
    CHECK(sv_load(&dev, (u8 *)&got, sizeof got, &pk2) && !memcmp(&got, &c3, sizeof c3) && pk2.seq == 1, "and 1 after it");
    /* a device that fails: the save says so */
    wipe(); cut = 0;
    memset(&pk, 0, sizeof pk);
    CHECK(save_all(&a, &pk, 0) < 0, "a dead chip fails the save");
    cut = -1;
}

/* ---- the chips ---- */
enum { C64, C4WRAP, C4ZERO, C4DEAD, C4ERR };   /* C4ERR: holds no long read, and a long write lands on Payback's own block but is reported as an error */
typedef struct { int kind, mode, dir; u8 m[1024][8]; int writes, ident4; } Chip;
static Chip chip;
static int c_ident(int k) { chip.mode = k; return 0; }
static int c_rawrd(int blk, u8 *o)
{
    if (chip.mode == 4) {
        if (blk >= 64) return 1;
        if (chip.kind == C64) { memset(o, 0xff, 8); o[3] = (u8)blk; return 0; }     /* (a chip that wants 14 bits: whatever it answers, it is not the block) */
        memcpy(o, chip.m[blk], 8);
        return 0;
    }
    if (blk >= 1024) return 1;
    switch (chip.kind) {
    case C64: memcpy(o, chip.m[blk], 8); break;
    case C4WRAP: memcpy(o, chip.m[blk & 63], 8); break;
    case C4ZERO: memcpy(o, chip.m[0], 8); break;
    default: memset(o, 0xff, 8);
    }
    return 0;
}
static int c_rd(int blk, u8 *o) { return c_rawrd(blk, o); }
static int c_wr(int blk, const u8 *i)
{
    chip.writes++;
    if (chip.mode == 4) {
        if (blk >= 64) return 1;
        if (chip.kind != C64) memcpy(chip.m[blk], i, 8);
    } else if (blk < 1024) {
        switch (chip.kind) {
        case C64: memcpy(chip.m[blk], i, 8); break;
        case C4WRAP: memcpy(chip.m[blk & 63], i, 8); break;
        case C4ZERO: memcpy(chip.m[0], i, 8); break;
        case C4ERR: memcpy(chip.m[blk & 63], i, 8); return 1;
        }
    }
    u8 t[8];                                              /* (Payback's program routine verifies) */
    return c_rawrd(blk, t) || memcmp(t, i, 8);
}
static const SvEep eep = {c_ident, c_rd, c_wr};

static void fill_payback(int blank)
{
    memset(chip.m, 0xff, sizeof chip.m);
    if (!blank) {
        memcpy(chip.m[0], ".ckabyaP", 8);
        for (int b = 1; b < 64; b++) for (int k = 0; k < 8; k++) chip.m[b][k] = (b * 37 + k * 11) & 0xfe;
    }
}

static void test_ident(void)
{
    static const char *const nm[] = {"64K", "4K wrapping", "4K reading the first six bits", "4K that holds no long write", "4K whose long write lands and fails"};
    for (int kind = 0; kind < 5; kind++)
        for (int blank = 0; blank < 2; blank++) {
            memset(&chip, 0, sizeof chip);
            chip.kind = kind;
            fill_payback(blank);
            u8 keep[64][8];
            memcpy(keep, chip.m, sizeof keep);
            int want = kind == C64 ? SV_64K : SV_4K;
            int got = sv_identify(&eep);
            CHECK(got == want, "%s chip%s: %s (wanted %s)", nm[kind], blank ? ", blank" : "", got == SV_64K ? "64K" : "4K", want == SV_64K ? "64K" : "4K");
            CHECK(chip.mode == (want == SV_64K ? 64 : 4), "%s: the addressing is left at the answer (%d)", nm[kind], chip.mode);
            CHECK(!memcmp(keep, chip.m, sizeof keep), "%s%s: Payback's 64 blocks are as they were", nm[kind], blank ? " (blank)" : "");
            printf("ident %-30s %-5s -> %s, %d block writes\n", nm[kind], blank ? "blank" : "saved", got == SV_64K ? "64K" : "4K", chip.writes);
            if (want == SV_64K) {
                int w0 = chip.writes;
                CHECK(sv_identify(&eep) == SV_64K && chip.writes == w0, "%s: the next boot writes nothing", nm[kind]);
                CHECK(!memcmp(keep, chip.m, sizeof keep), "%s: and still leaves Payback's blocks", nm[kind]);
                u8 t[8];
                chip.mode = 64;
                c_rd(66, t);
                CHECK(t[0] == 0xff && t[7] == 0xff, "%s: block 66 is as it was", nm[kind]);
            } else if (!blank && kind != C4DEAD && kind != C4ERR) {
                CHECK(chip.writes == 0, "%s with a save: nothing was written to find out (%d writes)", nm[kind], chip.writes);
            }
        }
    /* the boot's look (sv_probe) only reads: no chip is written, the 64K one is known once the proof has been made */
    for (int kind = 0; kind < 5; kind++)
        for (int blank = 0; blank < 2; blank++) {
            memset(&chip, 0, sizeof chip);
            chip.kind = kind;
            fill_payback(blank);
            u8 keep[1024][8];
            memcpy(keep, chip.m, sizeof keep);
            CHECK(sv_probe(&eep) == SV_4K && chip.writes == 0 && chip.mode == 4 && !memcmp(keep, chip.m, sizeof keep),
                  "%s%s: the boot's look finds no proof, writes nothing, leaves the addressing at 4", nm[kind], blank ? " (blank)" : "");
            if (kind == C64) {
                CHECK(sv_identify(&eep) == SV_64K, "the proof is made when a save is first wanted");
                int w = chip.writes;
                CHECK(sv_probe(&eep) == SV_64K && chip.writes == w && chip.mode == 64, "and the next boot's look knows the chip with no writes");
            }
        }
    /* a 64K chip that already holds Payback's save written at 64 Kbit addressing, and ours */
    memset(&chip, 0, sizeof chip);
    chip.kind = C64;
    fill_payback(0);
    CHECK(sv_identify(&eep) == SV_64K, "64K chip with a save");
    memcpy(chip.m[SV_SLOT_A], "somedata", 8);
    CHECK(sv_identify(&eep) == SV_64K && !memcmp(chip.m[SV_SLOT_A], "somedata", 8), "a later boot leaves our slots alone");
    /* the 4K wrapping chip stays 4K after its (blank) test, boot after boot, with its blank blocks restored */
    memset(&chip, 0, sizeof chip);
    chip.kind = C4WRAP;
    fill_payback(1);
    for (int i = 0; i < 5; i++) CHECK(sv_identify(&eep) == SV_4K, "boot %d on the blank wrapping chip", i);
    int ff = 1;
    for (int b = 0; b < 64; b++) for (int k = 0; k < 8; k++) ff &= chip.m[b][k] == 0xff;
    CHECK(ff, "its blocks are blank again");
}

int main(void)
{
    test_crc();
    test_pw();
    test_slots();
    test_ident();
    printf("%s: %d checks, %d failed\n", bad ? "FAILED" : "ALL PASS", total, bad);
    return bad != 0;
}
