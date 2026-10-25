/* Saving the campaign (save.h): the image's crc and password, the two slots in EEPROM, and the identify step that
   decides whether Payback's chip may hold more than Payback's own 64 blocks. Plain C but for the last section. */
#include "save.h"
#ifndef SV_HOST
#include "pbapi.h"
#endif

/* ---- crc ---- */
static u16 crc_upd(u16 c, const u8 *p, int n)
{
    while (n--) {
        c ^= (u16)*p++ << 8;
        for (int i = 0; i < 8; i++)
            c = c & 0x8000 ? c << 1 ^ 0x1021 : c << 1;
    }
    return c;
}
u16 sv_crc16(const void *p, int n) { return crc_upd(0xffff, p, n); }

void prog_seal(Prog *p)
{
    p->magic = PROG_MAGIC;
    p->ver = PROG_VER;
    p->crc = sv_crc16((const u8 *)p + 8, sizeof *p - 8);
}

int prog_ok(const Prog *p)
{
    if (p->magic != PROG_MAGIC || p->ver != PROG_VER || p->crc != sv_crc16((const u8 *)p + 8, sizeof *p - 8))
        return 0;
    return p->chap_cur < CP_CHAPS && p->chap_unlocked < CP_CHAPS;
}

/* ---- the password: 16 letters of 5 bits, 80 bits ----
   chapter 4, acts of that chapter 6, chapters done 11, upgrades 4 x 2, paints 6, credits / 100 10, medals found 7,
   Ace 1, story flags 15 (8 used), crc 12. Best times, the chapters' challenges and each medal are not in it */
typedef struct { u8 b[10]; int n; } Bits;
static void put(Bits *s, u32 v, int w)
{
    for (int i = w - 1; i >= 0; i--, s->n++)
        if (v >> i & 1)
            s->b[s->n >> 3] |= 0x80 >> (s->n & 7);
}
static u32 get(Bits *s, int w)
{
    u32 v = 0;
    for (int i = 0; i < w; i++, s->n++)
        v = v << 1 | (s->b[s->n >> 3] >> (7 - (s->n & 7)) & 1);
    return v;
}
static int popc(u32 v) { int n = 0; for (; v; v &= v - 1) n++; return n; }
/* SgProgress as campaign.h's sg[32]: credits s32 +0, medals u16 +4, paints u16 +6, laser +8, engine +9, rack +10, shield +11 */
#define SG_CREDITS 0
#define SG_MEDALS 4
#define SG_PAINTS 6
#define SG_UP 8
static u32 rd16(const u8 *p) { return p[0] | p[1] << 8; }
static s32 rd32(const u8 *p) { return (s32)(p[0] | p[1] << 8 | p[2] << 16 | (u32)p[3] << 24); }
static void wr16(u8 *p, u32 v) { p[0] = v, p[1] = v >> 8; }
static void wr32(u8 *p, u32 v) { p[0] = v, p[1] = v >> 8, p[2] = v >> 16, p[3] = v >> 24; }

void pw_encode(const Prog *p, char out[PW_LEN + 1])
{
    Bits s = {{0}, 0};
    int cur = p->chap_cur, done = 0, medals = 0;
    for (int c = 0; c < CP_CHAPS - 1; c++) {
        done |= (p->acts[c] & 63) == 63 ? 1 << c : 0;
        medals += popc(p->medals[c] & 63);
    }
    medals += popc(rd16(p->sg + SG_MEDALS));
    if (p->flags & CPF_PW)
        medals += p->spare[0];                         /* (the count a code gave, before any found since) */
    s32 cr = rd32(p->sg + SG_CREDITS) / 100;
    put(&s, cur, 4);
    put(&s, p->acts[cur] & 63, 6);
    put(&s, done, 11);
    for (int i = 0; i < 4; i++)
        put(&s, p->sg[SG_UP + i] & 3, 2);
    put(&s, rd16(p->sg + SG_PAINTS) >> 6 & 63, 6);
    put(&s, cr < 0 ? 0 : cr > 1023 ? 1023 : cr, 10);
    put(&s, medals > 127 ? 127 : medals, 7);
    put(&s, p->ace & 1, 1);
    put(&s, p->story[0], 15);
    put(&s, sv_crc16(s.b, 9) & 0xfff, 12);
    s.n = 0;
    for (int i = 0; i < PW_LEN; i++)
        out[i] = PW_ALPHA[get(&s, 5)];
    out[PW_LEN] = 0;
}

int pw_decode(const char *str, Prog *p)
{
    Bits s = {{0}, 0};
    for (int i = 0; i < PW_LEN; i++) {
        char ch = str[i];
        int v = -1;
        if (ch >= 'a' && ch <= 'z')
            ch -= 32;
        for (int k = 0; k < 32; k++)
            if (PW_ALPHA[k] == ch)
                v = k;
        if (v < 0)
            return 0;
        put(&s, v, 5);
    }
    if (str[PW_LEN] && str[PW_LEN] != ' ' && str[PW_LEN] != '\n')
        return 0;
    s.n = 0;
    int cur = get(&s, 4), acts = get(&s, 6), done = get(&s, 11), up[4], paints, cr, medals, ace, story, crc;
    for (int i = 0; i < 4; i++)
        up[i] = get(&s, 2);
    paints = get(&s, 6), cr = get(&s, 10), medals = get(&s, 7), ace = get(&s, 1), story = get(&s, 15), crc = get(&s, 12);
    Bits t = {{0}, 0};
    for (int i = 0; i < 9; i++)
        t.b[i] = s.b[i];
    t.b[8] &= 0xf0;
    if (crc != (sv_crc16(t.b, 9) & 0xfff) || cur > CP_CHAPS - 2 || story >> 8)     /* (the crc is bits 68..79: it covers the 68 before) */
        return 0;
    for (u8 *q = (u8 *)p, *e = q + sizeof *p; q < e;)
        *q++ = 0;
    p->flags = CPF_ON | CPF_PW;
    p->chap_cur = cur;
    p->chap_unlocked = cur;
    for (int c = 0; c < CP_CHAPS - 1; c++)
        if (done >> c & 1) {
            p->acts[c] = 63;
            if (c + 1 > p->chap_unlocked)
                p->chap_unlocked = c + 1 > CP_CHAPS - 2 ? CP_CHAPS - 2 : c + 1;
        }
    if (!(done >> cur & 1))
        p->acts[cur] = acts;
    for (int i = 0; i < 4; i++)
        p->sg[SG_UP + i] = up[i] > 2 ? 2 : up[i];
    wr16(p->sg + SG_PAINTS, 0x3f | paints << 6);
    wr32(p->sg + SG_CREDITS, cr * 100);
    p->ace = ace;
    p->story[0] = story;
    p->spare[0] = medals;
    prog_seal(p);
    return 1;
}

/* ---- slots ---- */
static u8 hdr_chk(const u8 *h) { return h[0] ^ h[1] ^ h[2] ^ h[3] ^ h[4] ^ h[5] ^ h[6] ^ 0x5a; }

static int slot_read(const SvDev *d, int base, u8 *img, int n, u16 *seq)      /* img 0: only look if it is whole */
{
    u8 h[SV_BLK], b[SV_BLK];
    int nb = (n + SV_BLK - 1) / SV_BLK;
    if (d->rd(base, h) || h[0] != 0xa7 || h[7] != hdr_chk(h) || h[1] != nb)
        return 0;
    u16 c = 0xffff;
    for (int k = 0; k < nb; k++) {
        if (d->rd(base + 1 + k, b))
            return 0;
        c = crc_upd(c, b, SV_BLK);
        for (int i = 0; img && i < SV_BLK && k * SV_BLK + i < n; i++)
            img[k * SV_BLK + i] = b[i];
    }
    if (c != (h[4] | h[5] << 8))
        return 0;
    *seq = h[2] | h[3] << 8;
    return 1;
}

int sv_load(const SvDev *d, u8 *img, int n, SvPick *pk)
{
    u16 sq[2];
    int ok[2];
    if ((n + SV_BLK - 1) / SV_BLK > SV_PAY_MAX)
        return 0;
    ok[0] = slot_read(d, SV_SLOT_A, 0, n, &sq[0]);
    ok[1] = slot_read(d, SV_SLOT_B, 0, n, &sq[1]);
    if (!ok[0] && !ok[1])
        return 0;
    int w = ok[0] && ok[1] ? (s16)(sq[1] - sq[0]) > 0 : ok[1];     /* (the newer one by the count, which wraps) */
    if (!slot_read(d, w ? SV_SLOT_B : SV_SLOT_A, img, n, &sq[w]))
        return 0;
    pk->seq = sq[w], pk->slot = w, pk->valid = 1;
    return 1;
}

static void pad_block(const u8 *img, int n, int k, u8 *b)
{
    for (int i = 0; i < SV_BLK; i++)
        b[i] = k * SV_BLK + i < n ? img[k * SV_BLK + i] : 0;
}

int sv_img_crc(const u8 *img, int n)
{
    u16 c = 0xffff;
    u8 b[SV_BLK];
    for (int k = 0; k < (n + SV_BLK - 1) / SV_BLK; k++) {
        pad_block(img, n, k, b);
        c = crc_upd(c, b, SV_BLK);
    }
    return c;
}

void sv_begin(SvW *w, const u8 *img, int n, const SvPick *pk)
{
    w->slot = pk && pk->valid ? !pk->slot : 0;         /* (the one that is not the newest good one) */
    w->seq = pk && pk->valid ? pk->seq + 1 : 1;
    w->crc = sv_img_crc(img, n);
    w->nb = (n + SV_BLK - 1) / SV_BLK;
    w->k = 0;
    w->busy = 1;
}

/* one block: the slot's own is read, and written only if it differs; after the last the header goes in, last of all,
   so a cut before it leaves this slot with the old header over a new payload (its crc fails) and the other slot whole */
int sv_step(const SvDev *d, SvW *w, const u8 *img, int n)
{
    int base = w->slot ? SV_SLOT_B : SV_SLOT_A;
    u8 b[SV_BLK], o[SV_BLK];
    if (w->k < w->nb) {
        pad_block(img, n, w->k, b);
        int same = !d->rd(base + 1 + w->k, o);
        for (int i = 0; same && i < SV_BLK; i++)
            same = o[i] == b[i];
        if (!same && d->wr(base + 1 + w->k, b)) {
            w->busy = 0;
            return -1;
        }
        w->k++;
        return 1;
    }
    b[0] = 0xa7, b[1] = w->nb, b[2] = w->seq, b[3] = w->seq >> 8, b[4] = w->crc, b[5] = w->crc >> 8, b[6] = 1;
    b[7] = hdr_chk(b);
    w->busy = 0;
    return d->wr(base, b) ? -1 : 0;
}

/* ---- is the chip 64 Kbit? ----
   Payback addresses its chip as 4 Kbit (6 bits of block). A 64 Kbit chip wants 14, and anything else that answers to
   long requests may be a 4 Kbit chip that read the first six bits and took the rest as data, or one that wraps the
   block number. Blocks 64 and up are ours only if a write there leaves Payback's blocks alone, so:
     - block 64 holds our directory once it has been proved. Read at 64 Kbit addressing it cannot be Payback's own
       block 0 (a chip that wrapped would give that back): 64 Kbit, nothing written
     - else block 66 is read at 64 Kbit addressing: if it is the same as block 0 or 2 and those are not blank, the
       chip is wrapping (Payback's own is what 66 reads): 4 Kbit, nothing written
     - else Payback's blocks 0..2 are read twice at 4 Kbit addressing (the backup), a pattern goes to block 66 at
       64 Kbit addressing, and 0..2 are read again. A change there is a chip that took the long request for a short
       one: put them back and stay at 4 Kbit. No change: 66 must read back as the pattern, or the chip does not hold
       it (4 Kbit, nothing lost); then the old 66 and the directory go in. A blank chip loses nothing to this */
static const u8 DIR[8] = {'S', 'F', 'D', '1', 2, 0, 1, 0};
static u8 dir_chk(const u8 *b) { return b[0] ^ b[1] ^ b[2] ^ b[3] ^ b[4] ^ b[5] ^ b[6] ^ 0x5a; }
static int is_dir(const u8 *b)
{
    for (int i = 0; i < 7; i++)
        if (b[i] != DIR[i])
            return 0;
    return b[7] == dir_chk(b);
}
static int same8(const u8 *a, const u8 *b)
{
    for (int i = 0; i < 8; i++)
        if (a[i] != b[i])
            return 0;
    return 1;
}
static int blank8(const u8 *a)
{
    for (int i = 0; i < 8; i++)
        if (a[i] != 0xff)
            return 0;
    return 1;
}
static int wr3(const SvEep *e, int blk, const u8 *b)
{
    u8 t[8];
    for (int k = 0; k < 3; k++)
        if (!e->wr(blk, b) && !e->rd(blk, t) && same8(t, b))
            return 0;
    return 1;
}

/* the part that only reads: is block 64 our directory? Leaves the addressing at 64 Kbit if so, else at Payback's 4 */
int sv_probe(const SvEep *e)
{
    u8 d[8];
    e->ident(64);
    if (!e->rd(SV_DIR, d) && is_dir(d))
        return SV_64K;
    e->ident(4);
    return SV_4K;
}

int sv_identify(const SvEep *e)
{
    u8 b4[3][8], c4[3][8], d[8], p[8], old[8], t[8], a0[8], a2[8];
    int ok4 = 1;
    e->ident(4);
    for (int i = 0; i < 3; i++)
        ok4 &= !e->rd(i, b4[i]) && !e->rd(i, c4[i]) && same8(b4[i], c4[i]);   /* (a chip that does not understand the short request may not answer the same twice) */
    e->ident(64);
    if (!e->rd(SV_DIR, d) && is_dir(d))
        return SV_64K;
    if (e->rd(66, old) || e->rd(0, a0) || e->rd(2, a2))
        return e->ident(4), SV_4K;
    if ((!blank8(a0) && same8(old, a0)) || (!blank8(a2) && same8(old, a2)) ||
        (ok4 && ((!blank8(b4[0]) && same8(old, b4[0])) || (!blank8(b4[2]) && same8(old, b4[2])))))
        return e->ident(4), SV_4K;                     /* (it wraps: Payback's own is what block 66 reads) */
    for (int i = 0; i < 8; i++)
        p[i] = old[i] ^ (0xa5 + i);
    int werr = e->wr(66, p);           /* (a write that failed may still have landed somewhere: look either way) */
    e->ident(4);
    int moved = 0;
    for (int i = 0; i < 3; i++)
        moved |= ok4 && (e->rd(i, t) || !same8(t, b4[i]));
    if (moved) {                                       /* a 4 Kbit chip: the long write landed on Payback's own */
        for (int i = 0; i < 3; i++)
            if (e->rd(i, t) || !same8(t, b4[i]))
                wr3(e, i, b4[i]);
        return SV_4K;
    }
    if (werr)
        return SV_4K;
    e->ident(64);
    if (e->rd(66, t) || !same8(t, p)) {
        e->ident(4);
        return SV_4K;
    }
    wr3(e, 66, old);
    u8 dir[8];
    for (int i = 0; i < 8; i++)
        dir[i] = DIR[i];
    dir[7] = dir_chk(dir);
    if (wr3(e, SV_DIR, dir)) {
        e->ident(4);
        return SV_4K;
    }
    return SV_64K;
}

/* ---- the machine's ---- */
#ifndef SV_HOST
static int eep_rd(int blk, u8 *b)
{
    u16 t[4];
    int r = pb_eep_read(blk, t);
    for (int i = 0; i < 4; i++)
        b[2 * i] = t[i], b[2 * i + 1] = t[i] >> 8;
    return r;
}
static int eep_wr(int blk, const u8 *b)
{
    u16 t[4];
    for (int i = 0; i < 4; i++)
        t[i] = b[2 * i] | b[2 * i + 1] << 8;
    return pb_eep_prog(blk, t);
}
const SvDev sv_eeprom = {eep_rd, eep_wr};

int sv_mode(void) { return PB_EEP_CFG == PBA_EEP_CFG_64K ? SV_64K : SV_4K; }

static const SvEep sv_eep = {pb_eep_ident, eep_rd, eep_wr};

/* Payback's boot load calls this where it called its identify with 4. It stands before our memory is set up, so it
   keeps nothing: the answer is the config pointer's. It only reads (one block), so a game that never starts the campaign
   leaves the player's save as it found it; the proof that writes is sv_prove, when a save is first wanted */
__attribute__((section(".text.sf_hook_eep_ident")))
int sf_eep_identify(int kbit)
{
    if (kbit != 4)
        return pb_eep_ident(kbit);
    sv_probe(&sv_eep);
    return 0;
}

/* the proof that writes (sv_identify), run by the campaign when the player first wants a save: 1 if the chip is ours to use */
int sv_prove(void) { return sv_identify(&sv_eep) == SV_64K; }
#endif
